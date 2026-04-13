"""
Ride Simulator
--------------
Generates realistic sensor data for a complete bike ride, simulating what
Android's SensorManager and LocationManager would produce in real-time.

This is the key testing tool: it proves the DR algorithm works with
realistic data BEFORE you deploy on an actual phone.

Usage:
    python3 ride_simulator.py

    It will simulate a ride from a start location through several turns,
    show GPS vs DR predicted positions, and measure accuracy.
"""

from __future__ import annotations

import math
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sensor_collector import (
    SensorCollector,
    SensorEvent,
    LocationFix,
    AndroidSensorType,
    SensorDelay,
)
from main import DeadReckoningEngine, SensorReading, SensorType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ride_simulator")


# ===================================================================
#  Route Waypoints — define the ride path
# ===================================================================

@dataclass
class RouteWaypoint:
    """A point along the simulated ride."""
    lat: float
    lon: float
    speed_mps: float       # speed at this point (m/s)
    hold_seconds: float    # how long to stay on this heading before next waypoint
    label: str = ""


# A realistic ride in Nagpur (near VNIT campus)
DEMO_ROUTE: List[RouteWaypoint] = [
    RouteWaypoint(21.1458, 79.0882, 0.0,  2.0, "Start: VNIT Gate"),
    RouteWaypoint(21.1458, 79.0882, 8.0,  5.0, "Accelerate North on Ambazari Rd"),
    RouteWaypoint(21.1490, 79.0882, 12.0, 8.0, "Cruising North"),
    RouteWaypoint(21.1530, 79.0882, 10.0, 3.0, "Slow down for turn"),
    RouteWaypoint(21.1530, 79.0920, 12.0, 8.0, "Turn East — heading 90°"),
    RouteWaypoint(21.1530, 79.0970, 8.0,  3.0, "Slow down approaching dest"),
    RouteWaypoint(21.1530, 79.0985, 0.0,  2.0, "Arrive: Destination"),
]


# ===================================================================
#  Sensor Data Generator
# ===================================================================

class SensorDataGenerator:
    """
    Generates realistic IMU readings for a given speed and heading.
    
    Simulates what Android's SensorManager would produce:
    - Accelerometer: gravity + vibration noise + lean in turns
    - Gyroscope: angular velocity during turns
    - Magnetometer: compass heading
    - Step counter: increments (0 for riding, non-zero for walking)
    """

    GRAVITY = 9.81
    EARTH_RADIUS_M = 6_371_000

    def __init__(self, noise_level: float = 0.1) -> None:
        self._noise = noise_level
        self._step_count = 1000  # cumulative (Android step counter starts from boot)
        self._rng_state = 42     # deterministic pseudo-random for reproducibility

    def _pseudo_random(self) -> float:
        """Simple deterministic pseudo-random for reproducibility."""
        self._rng_state = (self._rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        return (self._rng_state / 0x7FFFFFFF) * 2 - 1  # [-1, 1]
    
    def _noise_val(self) -> float:
        return self._pseudo_random() * self._noise

    def generate_accelerometer(
        self, heading_deg: float, turn_rate_dps: float, timestamp_ns: int
    ) -> SensorEvent:
        """
        Simulate accelerometer reading.
        When riding straight: mostly gravity on Z axis.
        During turns: lateral acceleration on X axis (lean).
        """
        # Centripetal acceleration during turn = v * omega
        lean_accel = turn_rate_dps * 0.1  # simplified lean model

        ax = lean_accel + self._noise_val() * 0.3  # lateral (turn lean + vibration)
        ay = self._noise_val() * 0.2                # forward (engine vibration)
        az = self.GRAVITY + self._noise_val() * 0.1  # gravity + road bumps

        return SensorEvent(
            sensor_type=AndroidSensorType.TYPE_ACCELEROMETER,
            values=[ax, ay, az],
            timestamp_ns=timestamp_ns,
            accuracy=3,
        )

    def generate_gyroscope(
        self, turn_rate_dps: float, timestamp_ns: int
    ) -> SensorEvent:
        """
        Simulate gyroscope reading.
        Android gyroscope reports in rad/s.
        """
        # Mainly rotation around Z axis (yaw) during turns
        gx = self._noise_val() * 0.02  # small roll vibration
        gy = self._noise_val() * 0.02  # small pitch vibration
        gz = math.radians(turn_rate_dps) + self._noise_val() * 0.01  # yaw in rad/s

        return SensorEvent(
            sensor_type=AndroidSensorType.TYPE_GYROSCOPE,
            values=[gx, gy, gz],
            timestamp_ns=timestamp_ns,
            accuracy=3,
        )

    def generate_magnetometer(
        self, heading_deg: float, timestamp_ns: int
    ) -> SensorEvent:
        """
        Simulate magnetometer reading.
        Produces mx, my that encode compass heading.
        """
        heading_rad = math.radians(heading_deg)
        # Simplified: mx = cos(heading), my = -sin(heading), mz ≈ vertical component
        mag_strength = 45.0  # μT typical
        mx = mag_strength * math.cos(heading_rad) + self._noise_val() * 2
        my = -mag_strength * math.sin(heading_rad) + self._noise_val() * 2
        mz = -30.0 + self._noise_val() * 1  # vertical component (Nagpur ~ -30μT)

        return SensorEvent(
            sensor_type=AndroidSensorType.TYPE_MAGNETIC_FIELD,
            values=[mx, my, mz],
            timestamp_ns=timestamp_ns,
            accuracy=2,
        )

    def generate_gps_fix(
        self, lat: float, lon: float, speed_mps: float,
        bearing_deg: float, timestamp_ms: int
    ) -> LocationFix:
        """Simulate a GPS fix from LocationManager."""
        return LocationFix(
            latitude=lat + self._noise_val() * 0.00002,  # ~2m noise
            longitude=lon + self._noise_val() * 0.00002,
            speed_mps=max(0, speed_mps + self._noise_val() * 0.5),
            bearing_deg=(bearing_deg + self._noise_val() * 2) % 360,
            accuracy_m=5.0 + abs(self._noise_val()) * 3,
            timestamp_ms=timestamp_ms,
        )


# ===================================================================
#  The Ride Simulator
# ===================================================================

def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute bearing from point 1 to point 2 in degrees."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlon = lon2_r - lon1_r
    y = math.sin(dlon) * math.cos(lat2_r)
    x = (math.cos(lat1_r) * math.sin(lat2_r) -
         math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon))
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two lat/lon points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def simulate_ride(
    route: List[RouteWaypoint],
    gps_loss_after_s: float = 15.0,
    gps_restore_after_s: float = 999.0,
    sensor_rate_hz: float = 50.0,
    gps_rate_hz: float = 1.0,
) -> None:
    """
    Simulate a complete ride and show DR accuracy.

    Parameters
    ----------
    route : list of waypoints to follow
    gps_loss_after_s : seconds into the ride when GPS is lost
    gps_restore_after_s : seconds when GPS comes back (set high to keep it lost)
    sensor_rate_hz : IMU sampling rate (Android SENSOR_DELAY_GAME ≈ 50Hz)
    gps_rate_hz : GPS update rate (typically 1Hz)
    """

    print("=" * 70)
    print("  SMART HELMET — DEAD RECKONING RIDE SIMULATION")
    print("=" * 70)
    print(f"  Route: {route[0].label} → {route[-1].label}")
    print(f"  GPS loss at: {gps_loss_after_s}s | Restore at: {gps_restore_after_s}s")
    print(f"  Sensor rate: {sensor_rate_hz} Hz | GPS rate: {gps_rate_hz} Hz")
    print("=" * 70)

    # Initialise components
    engine = DeadReckoningEngine()
    engine.running = True
    gen = SensorDataGenerator(noise_level=0.15)
    collector = SensorCollector()

    # Wire the collector to the engine (this is what the Android service does)
    def on_sensor(event: SensorEvent):
        # Convert SensorEvent → SensorReading (our DR format)
        type_map = {
            AndroidSensorType.TYPE_ACCELEROMETER: SensorType.ACCELEROMETER,
            AndroidSensorType.TYPE_GYROSCOPE: SensorType.GYROSCOPE,
            AndroidSensorType.TYPE_MAGNETIC_FIELD: SensorType.MAGNETOMETER,
        }
        dr_type = type_map.get(event.sensor_type)
        if dr_type:
            engine.process_reading(SensorReading(
                sensor_type=dr_type,
                values=event.values,
                timestamp_ns=event.timestamp_ns,
                accuracy=event.accuracy,
            ))

    def on_gps(fix: LocationFix):
        engine.anchor(
            lat=fix.latitude,
            lon=fix.longitude,
            speed_mps=fix.speed_mps if fix.has_speed else None,
            bearing_deg=fix.bearing_deg if fix.has_bearing else None,
        )

    # Register listeners (mirrors Android SensorManager.registerListener)
    collector.register_listener(
        AndroidSensorType.TYPE_ACCELEROMETER, on_sensor, SensorDelay.SENSOR_DELAY_GAME
    )
    collector.register_listener(
        AndroidSensorType.TYPE_GYROSCOPE, on_sensor, SensorDelay.SENSOR_DELAY_GAME
    )
    collector.register_listener(
        AndroidSensorType.TYPE_MAGNETIC_FIELD, on_sensor, SensorDelay.SENSOR_DELAY_UI
    )
    collector.register_gps_listener(on_gps)

    # Simulate the ride
    sensor_dt = 1.0 / sensor_rate_hz
    gps_dt = 1.0 / gps_rate_hz
    sim_time = 0.0
    last_gps_time = 0.0
    gps_lost = False

    # Track actual position for accuracy comparison
    actual_lat = route[0].lat
    actual_lon = route[0].lon
    current_heading = 0.0
    current_speed = 0.0

    results: List[dict] = []
    segment_idx = 0
    segment_time = 0.0

    print(f"\n{'Time':>6s}  {'Status':>8s}  {'Actual Lat':>12s}  {'Actual Lon':>12s}  "
          f"{'DR Lat':>12s}  {'DR Lon':>12s}  {'Error(m)':>9s}  {'Uncert(m)':>9s}  {'Heading':>8s}")
    print("-" * 110)

    total_sim_time = sum(wp.hold_seconds for wp in route)

    while segment_idx < len(route) - 1 and sim_time < total_sim_time + 5:
        wp_current = route[segment_idx]
        wp_next = route[min(segment_idx + 1, len(route) - 1)]

        # Compute target heading and distance for this segment
        target_heading = compute_bearing(
            wp_current.lat, wp_current.lon, wp_next.lat, wp_next.lon
        )
        segment_distance = haversine(
            wp_current.lat, wp_current.lon, wp_next.lat, wp_next.lon
        )

        # Interpolate speed
        t_frac = min(1.0, segment_time / max(0.1, wp_current.hold_seconds))
        current_speed = wp_current.speed_mps + (wp_next.speed_mps - wp_current.speed_mps) * t_frac

        # Smoothly turn towards target heading
        heading_diff = ((target_heading - current_heading) + 180) % 360 - 180
        turn_rate = heading_diff * 2.0  # deg/s — smooth turn
        turn_rate = max(-45, min(45, turn_rate))  # limit turn rate
        current_heading = (current_heading + turn_rate * sensor_dt) % 360

        # Update actual position
        if current_speed > 0:
            dist = current_speed * sensor_dt
            heading_rad = math.radians(current_heading)
            actual_lat += (dist * math.cos(heading_rad)) / 111_320
            actual_lon += (dist * math.sin(heading_rad)) / (
                111_320 * math.cos(math.radians(actual_lat))
            )

        # Timestamp in nanoseconds (simulated boot time)
        ts_ns = int(sim_time * 1e9)
        ts_ms = int(sim_time * 1e3)

        # Generate and dispatch sensor events
        accel_event = gen.generate_accelerometer(current_heading, turn_rate, ts_ns)
        gyro_event = gen.generate_gyroscope(turn_rate, ts_ns)
        mag_event = gen.generate_magnetometer(current_heading, ts_ns)

        collector.dispatch_sensor_event(accel_event)
        collector.dispatch_sensor_event(gyro_event)
        collector.dispatch_sensor_event(mag_event)

        # GPS updates (at lower rate, and respect loss window)
        if sim_time >= gps_loss_after_s and sim_time < gps_restore_after_s:
            if not gps_lost:
                gps_lost = True
                collector.set_gps_available(False)
                print(f"\n  ⚠️  GPS SIGNAL LOST at {sim_time:.1f}s — DR takes over\n")
        elif gps_lost and sim_time >= gps_restore_after_s:
            gps_lost = False
            collector.set_gps_available(True)
            print(f"\n  ✅  GPS SIGNAL RESTORED at {sim_time:.1f}s\n")

        if not gps_lost and (sim_time - last_gps_time) >= gps_dt:
            gps_fix = gen.generate_gps_fix(
                actual_lat, actual_lon, current_speed, current_heading, ts_ms
            )
            collector.dispatch_gps_fix(gps_fix)
            last_gps_time = sim_time

            # Also send GPS speed
            engine.process_reading(SensorReading(
                sensor_type=SensorType.GPS_SPEED,
                values=[gps_fix.speed_mps],
                timestamp_ns=ts_ns,
                accuracy=3,
            ))

        # Print status every 2 seconds
        if int(sim_time * 10) % 20 == 0 and sim_time > 0:
            dr_lat = engine.latitude
            dr_lon = engine.longitude

            if dr_lat is not None and dr_lon is not None:
                error_m = haversine(actual_lat, actual_lon, dr_lat, dr_lon)
                status = "GPS" if not gps_lost else "DR"
                results.append({
                    "time": sim_time,
                    "status": status,
                    "error_m": error_m,
                    "uncertainty_m": engine.uncertainty_m,
                })

                print(
                    f"{sim_time:6.1f}s  {status:>8s}  {actual_lat:12.6f}  {actual_lon:12.6f}  "
                    f"{dr_lat:12.6f}  {dr_lon:12.6f}  {error_m:8.1f}m  "
                    f"{engine.uncertainty_m:8.1f}m  {engine.heading_deg:7.1f}°"
                )

        # Advance time
        sim_time += sensor_dt
        segment_time += sensor_dt

        # Check if segment is done
        if segment_time >= wp_current.hold_seconds:
            segment_idx += 1
            segment_time = 0.0

    # ============================
    # Summary
    # ============================
    print("\n" + "=" * 70)
    print("  SIMULATION RESULTS")
    print("=" * 70)

    gps_results = [r for r in results if r["status"] == "GPS"]
    dr_results = [r for r in results if r["status"] == "DR"]

    if gps_results:
        avg_gps_error = sum(r["error_m"] for r in gps_results) / len(gps_results)
        max_gps_error = max(r["error_m"] for r in gps_results)
        print(f"\n  GPS Mode ({len(gps_results)} samples):")
        print(f"    Average error:  {avg_gps_error:.1f} m")
        print(f"    Maximum error:  {max_gps_error:.1f} m")

    if dr_results:
        avg_dr_error = sum(r["error_m"] for r in dr_results) / len(dr_results)
        max_dr_error = max(r["error_m"] for r in dr_results)
        avg_uncertainty = sum(r["uncertainty_m"] for r in dr_results) / len(dr_results)
        print(f"\n  Dead Reckoning Mode ({len(dr_results)} samples):")
        print(f"    Average error:      {avg_dr_error:.1f} m")
        print(f"    Maximum error:      {max_dr_error:.1f} m")
        print(f"    Average uncertainty: {avg_uncertainty:.1f} m")
        print(f"    DR duration:        {dr_results[-1]['time'] - dr_results[0]['time']:.1f}s")

    print(f"\n  Total ride time:     {sim_time:.1f}s")
    print(f"  Final position:      ({engine.latitude:.6f}, {engine.longitude:.6f})")
    print(f"  Final heading:       {engine.heading_deg:.1f}°")
    print(f"  Position history:    {len(engine.position_history)} entries")
    print("=" * 70)

    return results


# ===================================================================
#  Main
# ===================================================================
if __name__ == "__main__":
    print("\n🏍️  Simulating a ride from VNIT Nagpur to a nearby destination...\n")
    print("   The GPS will be lost at 15 seconds (e.g., entering a tunnel)")
    print("   Dead Reckoning will take over and predict positions.\n")

    simulate_ride(
        route=DEMO_ROUTE,
        gps_loss_after_s=15.0,      # GPS lost after 15 seconds
        gps_restore_after_s=999.0,  # stays lost for the whole ride (worst case)
        sensor_rate_hz=50.0,        # 50 Hz (Android SENSOR_DELAY_GAME)
        gps_rate_hz=1.0,            # 1 Hz GPS updates
    )
