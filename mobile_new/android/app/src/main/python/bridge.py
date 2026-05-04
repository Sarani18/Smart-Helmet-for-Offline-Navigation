"""
bridge.py — Single entry-point called by the Kotlin Native Module.

Exposes stateful sensor fusion + dead reckoning as flat functions so
Chaquopy can call them without needing to manage Python object references
on the Java side.

All state is held in module-level singletons — one set per app process.
"""
import json as _json

from dead_reckoning import DeadReckoning, MotionSample
from sensor_fusion import SensorFusion, IMUReading
from heading_tracker import HeadingTracker

_dr = DeadReckoning()
_sf = SensorFusion()
_ht = HeadingTracker()
_heading_initialized = False


# ── Dead Reckoning ────────────────────────────────────────────────────────────

def anchor_dr(lat: float, lon: float) -> None:
    _dr.anchor(lat, lon)


def update_dr(speed_mps: float, heading_deg: float, timestamp_s: float) -> str:
    """Returns JSON string: {"lat":…,"lon":…,"uncertainty_m":…} or "null"."""
    sample = MotionSample(
        speed_mps=speed_mps,
        heading_degrees=heading_deg,
        timestamp=timestamp_s,
    )
    pos = _dr.update(sample)
    if pos is None:
        return "null"
    return _json.dumps({
        "lat": pos.latitude,
        "lon": pos.longitude,
        "uncertainty_m": pos.uncertainty_meters,
    })


def get_dr_position() -> str:
    """Returns JSON string: {"lat":…,"lon":…,"uncertainty_m":…} or "null". Read-only."""
    pos = _dr.get_position()
    if pos is None:
        return "null"
    return _json.dumps({
        "lat": pos.latitude,
        "lon": pos.longitude,
        "uncertainty_m": pos.uncertainty_meters,
    })


def is_dr_anchored() -> bool:
    return _dr.get_position() is not None


def reset_dr() -> None:
    _dr.reset()


# ── Heading / Sensor Fusion ───────────────────────────────────────────────────

def update_heading(
    ax: float, ay: float, az: float,
    gx: float, gy: float, gz: float,
    timestamp_s: float,
) -> float:
    """Fuse IMU sample; return smoothed heading in degrees [0, 360)."""
    global _heading_initialized
    reading = IMUReading(
        accel_x=ax, accel_y=ay, accel_z=az,
        gyro_x=gx, gyro_y=gy, gyro_z=gz,
        timestamp=timestamp_s,
    )
    orientation = _sf.update(reading)
    heading = _ht.update(orientation.yaw)
    _heading_initialized = True
    return heading


def get_heading() -> float:
    return _ht.get_heading()


def is_heading_initialized() -> bool:
    return _heading_initialized


def is_crash_detected() -> bool:
    return _sf.is_crash_detected()


def reset_heading() -> None:
    global _heading_initialized
    _sf.reset()
    _ht.reset()
    _heading_initialized = False
