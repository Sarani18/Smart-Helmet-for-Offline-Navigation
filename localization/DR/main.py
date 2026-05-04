"""
Dead Reckoning Service
----------------------
FastAPI microservice that receives live Android sensor data (accelerometer,
gyroscope, magnetometer, step counter, GPS) and continuously predicts the
rider's position using dead-reckoning when GPS is unavailable.

Endpoints
---------
POST /api/localization/dr/sensor-data   – ingest a batch of sensor readings
POST /api/localization/dr/gps-anchor    – set known GPS position (anchor)
POST /api/localization/dr/control       – START / STOP the DR engine
GET  /api/localization/dr/status        – current DR position & state

Outbound
--------
When the engine is running and producing position estimates, it POSTs
dead-reckoning events to the Navigation module at:
  POST /api/navigation/localization/dead-reckoning-event
"""

from __future__ import annotations

import math
import time
import logging
from enum import Enum
from typing import List, Optional
from collections import deque

import os
from pathlib import Path

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import httpx

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("dead_reckoning_service")

# ---------------------------------------------------------------------------
# Navigation API target (same machine, different port to nav service)
# ---------------------------------------------------------------------------
NAV_API_URL = "http://127.0.0.1:8000/api/navigation/localization/dead-reckoning-event"

# ===================================================================
#  Pydantic models — Android sensor data as received from the app
# ===================================================================

class SensorType(str, Enum):
    """Maps to Android SensorManager TYPE_* constants."""
    ACCELEROMETER = "ACCELEROMETER"            # TYPE_ACCELEROMETER
    GYROSCOPE = "GYROSCOPE"                    # TYPE_GYROSCOPE
    MAGNETOMETER = "MAGNETOMETER"              # TYPE_MAGNETIC_FIELD
    LINEAR_ACCELERATION = "LINEAR_ACCELERATION"  # TYPE_LINEAR_ACCELERATION
    ROTATION_VECTOR = "ROTATION_VECTOR"        # TYPE_ROTATION_VECTOR
    GAME_ROTATION_VECTOR = "GAME_ROTATION_VECTOR"
    STEP_COUNTER = "STEP_COUNTER"              # TYPE_STEP_COUNTER
    GPS_SPEED = "GPS_SPEED"                    # from LocationManager


class SensorReading(BaseModel):
    """
    A single sensor event from the Android SensorManager.

    Fields mirror what Android provides in SensorEvent:
    - sensor_type : which sensor produced this event
    - values      : SensorEvent.values[] array (axis data or scalar)
    - timestamp_ns: SensorEvent.timestamp in nanoseconds (boot-time clock)
    - accuracy    : SensorEvent.accuracy (0-3)
    """
    sensor_type: SensorType
    values: List[float] = Field(..., min_length=1, max_length=6)
    timestamp_ns: int = Field(..., description="Android SensorEvent.timestamp (nanoseconds)")
    accuracy: int = Field(default=3, ge=0, le=3)


class SensorBatch(BaseModel):
    """
    A batch of sensor readings sent by the Android app in one HTTP call.
    Batching reduces network overhead (Android's SensorManager can produce
    readings at 50-200 Hz; we batch and send at ~5-10 Hz).
    """
    session_id: str
    ts_ms: int = Field(..., description="Unix epoch ms when the batch was sent")
    readings: List[SensorReading]


class GPSAnchor(BaseModel):
    """A confirmed GPS fix used to anchor (reset) the DR estimate."""
    session_id: str
    ts_ms: int
    latitude: float
    longitude: float
    accuracy_m: float = Field(default=5.0, description="GPS horizontal accuracy in metres")
    speed_mps: Optional[float] = Field(default=None, description="GPS-derived speed in m/s")
    bearing_deg: Optional[float] = Field(default=None, description="GPS-derived bearing in degrees")


class ControlCommand(BaseModel):
    """START or STOP the DR engine."""
    session_id: str
    ts_ms: int
    action: str = Field(..., pattern="^(START|STOP)$")
    reason: str = ""


class ActionResponse(BaseModel):
    status: str
    message: str


class DRStatus(BaseModel):
    running: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    heading_deg: Optional[float] = None
    speed_mps: Optional[float] = None
    uncertainty_m: Optional[float] = None
    step_count: int = 0
    last_update_ts_ms: Optional[int] = None


# ===================================================================
#  Dead Reckoning Engine  (pure Python, no external numerical libs)
# ===================================================================

class DeadReckoningEngine:
    """
    Core dead-reckoning algorithm.

    Pipeline
    --------
    1. Accelerometer + Gyroscope → **Orientation** (complementary filter)
    2. Smoothed yaw → **Heading** (circular moving-average)
    3. Speed estimate (from last GPS speed, step detection, or linear accel integration)
    4. heading + speed × dt → **Position displacement** (lat/lon update)
    5. Growing uncertainty radius → **Confidence** decay

    All maths use the standard library only — no numpy/scipy required.
    """

    # Complementary filter blend (0.98 trusts gyro, 0.02 trusts accel)
    ALPHA = 0.98

    # Drift uncertainty: grows by 2% of distance travelled
    DRIFT_RATE = 0.02

    # Step length in metres (average walking/riding step — tunable)
    STEP_LENGTH_M = 0.75

    # Heading smoothing window
    HEADING_WINDOW = 10

    # Spike rejection threshold (degrees)
    SPIKE_THRESHOLD = 90.0

    # Earth radius for lat/lon conversion
    METERS_PER_DEG_LAT = 111_320.0

    def __init__(self) -> None:
        # Position state
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.uncertainty_m: float = 0.0

        # Orientation state (degrees)
        self.roll: float = 0.0
        self.pitch: float = 0.0
        self.yaw: float = 0.0

        # Heading smoother
        self._heading_window: deque = deque(maxlen=self.HEADING_WINDOW)
        self._last_raw_heading: Optional[float] = None
        self.heading_deg: float = 0.0

        # Speed
        self.speed_mps: float = 0.0
        self._last_gps_speed_mps: float = 0.0

        # Step counter
        self.step_count: int = 0
        self._prev_step_count: Optional[int] = None

        # Timestamps (seconds, converted from Android nanoseconds)
        self._last_accel_ts: Optional[float] = None
        self._last_gyro_ts: Optional[float] = None
        self._last_position_ts: Optional[float] = None

        # Running flag
        self.running: bool = False

        # History
        self.position_history: list = []

    # ------------------------------------------------------------------
    # GPS Anchor
    # ------------------------------------------------------------------
    def anchor(self, lat: float, lon: float, speed_mps: Optional[float] = None,
               bearing_deg: Optional[float] = None) -> None:
        """Set a confirmed GPS position and reset uncertainty."""
        self.latitude = lat
        self.longitude = lon
        self.uncertainty_m = 0.0
        if speed_mps is not None:
            self.speed_mps = speed_mps
            self._last_gps_speed_mps = speed_mps
        if bearing_deg is not None:
            self.yaw = bearing_deg
            self.heading_deg = bearing_deg
            self._heading_window.clear()
            self._heading_window.append(bearing_deg)
            self._last_raw_heading = bearing_deg
        logger.info(
            f"[DR] Anchored at ({lat:.6f}, {lon:.6f}), "
            f"speed={self.speed_mps:.1f} m/s, heading={self.heading_deg:.1f}°"
        )

    # ------------------------------------------------------------------
    # Sensor Ingestion
    # ------------------------------------------------------------------
    def process_reading(self, reading: SensorReading) -> None:
        """Route a single Android sensor reading to the correct handler."""
        ts_sec = reading.timestamp_ns / 1e9  # nanoseconds → seconds

        if reading.sensor_type == SensorType.ACCELEROMETER:
            self._process_accelerometer(reading.values, ts_sec)

        elif reading.sensor_type == SensorType.GYROSCOPE:
            self._process_gyroscope(reading.values, ts_sec)

        elif reading.sensor_type == SensorType.MAGNETOMETER:
            self._process_magnetometer(reading.values, ts_sec)

        elif reading.sensor_type == SensorType.LINEAR_ACCELERATION:
            self._process_linear_acceleration(reading.values, ts_sec)

        elif reading.sensor_type in (SensorType.ROTATION_VECTOR,
                                      SensorType.GAME_ROTATION_VECTOR):
            self._process_rotation_vector(reading.values, ts_sec)

        elif reading.sensor_type == SensorType.STEP_COUNTER:
            self._process_step_counter(reading.values, ts_sec)

        elif reading.sensor_type == SensorType.GPS_SPEED:
            self._process_gps_speed(reading.values)

    # ------------------------------------------------------------------
    # Accelerometer  →  tilt-based roll/pitch
    # ------------------------------------------------------------------
    def _process_accelerometer(self, values: List[float], ts: float) -> None:
        ax, ay, az = values[0], values[1], values[2]

        # Tilt from accelerometer (gravity reference)
        accel_roll = math.degrees(math.atan2(ay, az))
        accel_pitch = math.degrees(math.atan2(-ax, math.sqrt(ay**2 + az**2)))

        if self._last_accel_ts is None:
            # First reading — initialise directly from accelerometer
            self.roll = accel_roll
            self.pitch = accel_pitch
            self._last_accel_ts = ts
            return

        # Complementary filter blends gyro-integrated angles (already updated
        # in _process_gyroscope if gyro data arrived first) with accel tilt.
        self.roll = self.ALPHA * self.roll + (1 - self.ALPHA) * accel_roll
        self.pitch = self.ALPHA * self.pitch + (1 - self.ALPHA) * accel_pitch

        self._last_accel_ts = ts

    # ------------------------------------------------------------------
    # Gyroscope  →  angular velocity integration (roll/pitch/yaw)
    # ------------------------------------------------------------------
    def _process_gyroscope(self, values: List[float], ts: float) -> None:
        # Android gyro values are in rad/s — convert to deg/s
        gx_dps = math.degrees(values[0])
        gy_dps = math.degrees(values[1])
        gz_dps = math.degrees(values[2])

        if self._last_gyro_ts is None:
            self._last_gyro_ts = ts
            return

        dt = ts - self._last_gyro_ts
        if dt <= 0:
            return
        self._last_gyro_ts = ts

        # Integrate angular velocity → angle change
        self.roll += gx_dps * dt
        self.pitch += gy_dps * dt
        self.yaw = (self.yaw + gz_dps * dt) % 360

        # Update smoothed heading
        self._update_heading(self.yaw)

        # Advance position
        self._advance_position(ts)

    # ------------------------------------------------------------------
    # Magnetometer  →  absolute heading correction (compass)
    # ------------------------------------------------------------------
    def _process_magnetometer(self, values: List[float], ts: float) -> None:
        """
        Use magnetometer to correct yaw drift.
        Computes magnetic heading from mx, my, then blends with gyro-yaw.
        """
        mx, my = values[0], values[1]
        mag_heading = (math.degrees(math.atan2(-my, mx)) + 360) % 360

        # Soft-blend magnetometer heading with current yaw (low trust ~5%)
        MAG_WEIGHT = 0.05
        diff = self._angular_diff(mag_heading, self.yaw)
        self.yaw = (self.yaw + MAG_WEIGHT * diff) % 360

    # ------------------------------------------------------------------
    # Linear Acceleration  →  speed integration (fallback)
    # ------------------------------------------------------------------
    def _process_linear_acceleration(self, values: List[float], ts: float) -> None:
        """
        Android TYPE_LINEAR_ACCELERATION gives acceleration minus gravity.
        We use the forward component to adjust speed when no GPS speed is
        available.  This is noisy, so we apply heavy damping.
        """
        # Approximate forward acceleration (assume phone is roughly upright)
        # In a proper implementation this would be rotated to world frame.
        forward_accel = values[1]  # y-axis (forward when phone is in portrait)

        if self._last_position_ts is not None:
            dt = ts - self._last_position_ts
            if dt > 0:
                # Integrate acceleration to speed with damping
                new_speed = self.speed_mps + forward_accel * dt
                # Clamp to non-negative (we don't track reverse)
                self.speed_mps = max(0.0, new_speed * 0.95)  # 5% damping

    # ------------------------------------------------------------------
    # Rotation Vector  →  direct orientation (if available)
    # ------------------------------------------------------------------
    def _process_rotation_vector(self, values: List[float], ts: float) -> None:
        """
        Android TYPE_ROTATION_VECTOR gives a quaternion [x, y, z, w].
        Convert to Euler angles for heading.  This is the most accurate
        orientation source on modern Android phones.
        """
        if len(values) < 4:
            return

        qx, qy, qz = values[0], values[1], values[2]
        qw = values[3] if len(values) >= 4 else math.sqrt(max(0, 1 - qx**2 - qy**2 - qz**2))

        # Quaternion → Euler (ZYX convention)
        sinr_cosp = 2.0 * (qw * qx + qy * qz)
        cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
        roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))

        sinp = 2.0 * (qw * qy - qz * qx)
        sinp = max(-1.0, min(1.0, sinp))
        pitch = math.degrees(math.asin(sinp))

        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        yaw = (math.degrees(math.atan2(siny_cosp, cosy_cosp)) + 360) % 360

        # Rotation vector is reliable — apply with high trust
        ROT_WEIGHT = 0.8
        self.roll = ROT_WEIGHT * roll + (1 - ROT_WEIGHT) * self.roll
        self.pitch = ROT_WEIGHT * pitch + (1 - ROT_WEIGHT) * self.pitch

        diff = self._angular_diff(yaw, self.yaw)
        self.yaw = (self.yaw + ROT_WEIGHT * diff) % 360

        self._update_heading(self.yaw)
        self._advance_position(ts)

    # ------------------------------------------------------------------
    # Step Counter  →  displacement via step length
    # ------------------------------------------------------------------
    def _process_step_counter(self, values: List[float], ts: float) -> None:
        """
        Android TYPE_STEP_COUNTER gives cumulative step count since boot.
        We detect new steps and apply STEP_LENGTH_M per step.
        """
        current_count = int(values[0])

        if self._prev_step_count is None:
            self._prev_step_count = current_count
            return

        new_steps = current_count - self._prev_step_count
        if new_steps > 0:
            self._prev_step_count = current_count
            self.step_count += new_steps

            # Estimate speed from steps (useful for walking scenarios)
            # For riding, GPS_SPEED is the primary source
            step_distance = new_steps * self.STEP_LENGTH_M
            if self._last_position_ts is not None:
                dt = ts - self._last_position_ts
                if dt > 0:
                    step_speed = step_distance / dt
                    # Only use step speed if no GPS speed available
                    if self._last_gps_speed_mps <= 0.5:
                        self.speed_mps = step_speed

    # ------------------------------------------------------------------
    # GPS Speed  →  speed calibration
    # ------------------------------------------------------------------
    def _process_gps_speed(self, values: List[float]) -> None:
        """Last known GPS speed — used as the speed source until GPS is lost."""
        self.speed_mps = max(0.0, values[0])
        self._last_gps_speed_mps = self.speed_mps

    # ------------------------------------------------------------------
    # Heading Smoothing (circular moving average with spike rejection)
    # ------------------------------------------------------------------
    def _update_heading(self, raw_yaw: float) -> None:
        raw_yaw = raw_yaw % 360

        if self._last_raw_heading is not None:
            delta = abs(self._angular_diff(raw_yaw, self._last_raw_heading))
            if delta > self.SPIKE_THRESHOLD:
                return  # reject spike

        self._last_raw_heading = raw_yaw
        self._heading_window.append(raw_yaw)
        self.heading_deg = self._circular_mean(list(self._heading_window))

    # ------------------------------------------------------------------
    # Position Advancement (the actual dead-reckoning step)
    # ------------------------------------------------------------------
    def _advance_position(self, ts: float) -> None:
        """
        Core DR equation:
            new_lat = lat + (speed × dt × cos(heading)) / 111320
            new_lon = lon + (speed × dt × sin(heading)) / (111320 × cos(lat))
        """
        if self.latitude is None or self.longitude is None:
            self._last_position_ts = ts
            return

        if self._last_position_ts is None:
            self._last_position_ts = ts
            return

        dt = ts - self._last_position_ts
        if dt <= 0 or dt > 5.0:  # reject stale data (> 5s gap)
            self._last_position_ts = ts
            return

        self._last_position_ts = ts

        distance = self.speed_mps * dt  # metres
        if distance < 0.001:
            return  # negligible movement

        heading_rad = math.radians(self.heading_deg)
        delta_lat = (distance * math.cos(heading_rad)) / self.METERS_PER_DEG_LAT
        delta_lon = (
            distance * math.sin(heading_rad)
            / (self.METERS_PER_DEG_LAT * math.cos(math.radians(self.latitude)))
        )

        self.latitude += delta_lat
        self.longitude += delta_lon
        self.uncertainty_m += distance * self.DRIFT_RATE

        self.position_history.append({
            "lat": self.latitude,
            "lon": self.longitude,
            "heading": self.heading_deg,
            "speed": self.speed_mps,
            "uncertainty": self.uncertainty_m,
            "ts": ts,
        })

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _angular_diff(a: float, b: float) -> float:
        """Signed angular difference (degrees)."""
        return ((a - b) + 180) % 360 - 180

    @staticmethod
    def _circular_mean(angles: List[float]) -> float:
        """Compute circular (angular) mean of degree values."""
        sin_sum = sum(math.sin(math.radians(a)) for a in angles)
        cos_sum = sum(math.cos(math.radians(a)) for a in angles)
        return (math.degrees(math.atan2(sin_sum, cos_sum)) + 360) % 360

    def reset(self) -> None:
        """Reset all internal state."""
        self.latitude = None
        self.longitude = None
        self.uncertainty_m = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self._heading_window.clear()
        self._last_raw_heading = None
        self.heading_deg = 0.0
        self.speed_mps = 0.0
        self._last_gps_speed_mps = 0.0
        self.step_count = 0
        self._prev_step_count = None
        self._last_accel_ts = None
        self._last_gyro_ts = None
        self._last_position_ts = None
        self.position_history.clear()
        logger.info("[DR] Engine reset")

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "heading_deg": self.heading_deg,
            "speed_mps": self.speed_mps,
            "uncertainty_m": self.uncertainty_m,
            "step_count": self.step_count,
            "position_history_length": len(self.position_history),
        }


# ===================================================================
#  FastAPI Application
# ===================================================================

app = FastAPI(
    title="Dead Reckoning Service",
    version="1.0.0",
    description="Receives Android sensor data and predicts rider position via dead reckoning",
)

# Allow phone browser to call the API (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/localization/dr", tags=["Dead Reckoning"])

# Global DR engine instance
engine = DeadReckoningEngine()


# ------------------------------------------------------------------
# Endpoint: Receive sensor data batch from Android app
# ------------------------------------------------------------------
@router.post("/sensor-data", response_model=ActionResponse)
async def receive_sensor_data(batch: SensorBatch):
    """
    Called by the Android app at 5-10 Hz with a batch of sensor readings.

    The batch typically contains 10-50 readings from accelerometer,
    gyroscope, magnetometer, step counter, etc. collected since the
    last batch was sent.
    """
    if not engine.running:
        return ActionResponse(status="ignored", message="DR engine is not running")

    # Sort readings by timestamp to process in chronological order
    sorted_readings = sorted(batch.readings, key=lambda r: r.timestamp_ns)

    for reading in sorted_readings:
        engine.process_reading(reading)

    # If we have a position estimate, emit a DR event to Navigation
    if engine.latitude is not None and engine.longitude is not None:
        await _emit_dr_event(batch.session_id)

    logger.debug(
        f"[DR] Processed {len(sorted_readings)} readings. "
        f"Position: ({engine.latitude}, {engine.longitude}), "
        f"Heading: {engine.heading_deg:.1f}°, Speed: {engine.speed_mps:.1f} m/s, "
        f"Uncertainty: {engine.uncertainty_m:.1f}m"
    )

    return ActionResponse(
        status="processed",
        message=f"Processed {len(sorted_readings)} sensor readings",
    )


# ------------------------------------------------------------------
# Endpoint: GPS Anchor (set known position)
# ------------------------------------------------------------------
@router.post("/gps-anchor", response_model=ActionResponse)
async def receive_gps_anchor(anchor: GPSAnchor):
    """
    Called by the Android app whenever a GPS fix is obtained.
    Resets the DR position and uncertainty.
    """
    engine.anchor(
        lat=anchor.latitude,
        lon=anchor.longitude,
        speed_mps=anchor.speed_mps,
        bearing_deg=anchor.bearing_deg,
    )
    return ActionResponse(
        status="anchored",
        message=f"Position anchored at ({anchor.latitude:.6f}, {anchor.longitude:.6f})",
    )


# ------------------------------------------------------------------
# Endpoint: Control (START / STOP)
# ------------------------------------------------------------------
@router.post("/control", response_model=ActionResponse)
async def control_dr(cmd: ControlCommand):
    """
    Called by the Navigation module to start or stop dead reckoning.
    Typically triggered when the system transitions to/from OFFLINE mode.
    """
    if cmd.action == "START":
        engine.running = True
        logger.info(f"[DR] Engine STARTED (reason: {cmd.reason})")
        return ActionResponse(status="started", message="Dead reckoning engine started")
    elif cmd.action == "STOP":
        engine.running = False
        logger.info(f"[DR] Engine STOPPED (reason: {cmd.reason})")
        return ActionResponse(status="stopped", message="Dead reckoning engine stopped")
    else:
        return ActionResponse(status="error", message=f"Unknown action: {cmd.action}")


# ------------------------------------------------------------------
# Endpoint: Status (current DR state)
# ------------------------------------------------------------------
@router.get("/status", response_model=DRStatus)
async def get_status():
    """Return the current state of the dead reckoning engine."""
    return DRStatus(
        running=engine.running,
        latitude=engine.latitude,
        longitude=engine.longitude,
        heading_deg=engine.heading_deg,
        speed_mps=engine.speed_mps,
        uncertainty_m=engine.uncertainty_m,
        step_count=engine.step_count,
        last_update_ts_ms=(
            int(engine._last_position_ts * 1000)
            if engine._last_position_ts
            else None
        ),
    )


# ------------------------------------------------------------------
# Outbound: Emit DR event to Navigation module
# ------------------------------------------------------------------
async def _emit_dr_event(session_id: str) -> None:
    """
    Send the current DR position estimate to the Navigation module.
    Follows the dead-reckoning-event contract from INTEGRATION_CONSIDERATIONS.md.
    """
    event_payload = {
        "session_id": session_id,
        "event_id": f"dr_{int(time.time() * 1000)}",
        "ts_ms": int(time.time() * 1000),
        "event_type": "DEAD_RECKONING",
        "confidence": max(0.0, 1.0 - (engine.uncertainty_m / 500.0)),  # decays with drift
        "payload": {
            "latitude": engine.latitude,
            "longitude": engine.longitude,
            "heading_deg": engine.heading_deg,
            "speed_mps": engine.speed_mps,
            "uncertainty_m": engine.uncertainty_m,
        },
        "heading_deg": engine.heading_deg,
        "speed_mps": engine.speed_mps,
    }

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.post(NAV_API_URL, json=event_payload)
            logger.debug(f"[DR] Emitted DR event → Navigation (status {resp.status_code})")
        except Exception as e:
            logger.warning(f"[DR] Failed to emit DR event to Navigation: {e}")


# Register router
app.include_router(router)


# ------------------------------------------------------------------
# Serve phone sensor page at /phone (Optimized with Memory Cache)
# ------------------------------------------------------------------
HTML_DIR = Path(__file__).parent
_CACHED_PHONE_HTML: Optional[str] = None

@app.get("/phone", response_class=HTMLResponse)
async def phone_page():
    """Serve the phone sensor streaming page from memory for high speed."""
    global _CACHED_PHONE_HTML
    if _CACHED_PHONE_HTML is None:
        html_path = HTML_DIR / "phone_stream.html"
        if html_path.exists():
            _CACHED_PHONE_HTML = html_path.read_text()
        else:
            return HTMLResponse(content="<h1>phone_stream.html not found</h1>", status_code=404)
    
    return HTMLResponse(content=_CACHED_PHONE_HTML, status_code=200)


# ===================================================================
#  Entry point
# ===================================================================
if __name__ == "__main__":
    import uvicorn

    # Check for SSL certificates (needed for phone sensor access over HTTPS)
    cert_file = Path(__file__).parent / "cert.pem"
    key_file = Path(__file__).parent / "key.pem"

    if cert_file.exists() and key_file.exists():
        logger.info("Starting Dead Reckoning service on port 8002 (HTTPS)")
        logger.info("Phone URL: https://<your-ip>:8002/phone")
        uvicorn.run(
            app, host="0.0.0.0", port=8002,
            ssl_certfile=str(cert_file),
            ssl_keyfile=str(key_file),
        )
    else:
        logger.info("Starting Dead Reckoning service on port 8002 (HTTP)")
        logger.info("For phone sensor access, generate SSL certs:")
        logger.info('  openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"')
        uvicorn.run(app, host="0.0.0.0", port=8002)
