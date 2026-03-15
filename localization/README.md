# Localization & Sensor Fusion Module

**Owner:** Vijit Ayush Pandey

---

## Purpose

This module keeps track of *where the rider is* at all times – even when the
GPS signal is lost inside tunnels, under flyovers, or in dead zones.  It does
this by reading the phone's built-in motion sensors and combining their data
mathematically to estimate movement and direction.

---

## Files

| File | Responsibility |
|------|---------------|
| `sensor_fusion.py` | Combines accelerometer + gyroscope data into a stable orientation (roll/pitch/yaw) using a complementary filter |
| `dead_reckoning.py` | Estimates the rider's current lat/lon by integrating speed and heading over time |
| `heading_tracker.py` | Smooths the raw yaw (compass bearing) reading to remove noise and spikes |
| `map_matching.py` | Snaps the dead-reckoned position onto the nearest road segment to reduce drift |

---

## How It Works (Step by Step)

1. **Raw sensor data arrives** – The smartphone IMU produces accelerometer and
   gyroscope readings many times per second.

2. **Orientation estimation** – `SensorFusion.update()` runs a *complementary
   filter*: it trusts the gyroscope for rapid movements (it is very accurate
   short-term) and the accelerometer for slow drift correction (it knows which
   way is "down").  The result is a stable roll/pitch/yaw angle.

3. **Heading smoothing** – `HeadingTracker.update()` feeds the yaw angle
   through a moving-average window so that small vibrations from the engine
   or road bumps do not cause the navigation arrows to flicker.

4. **Dead reckoning** – When GPS is lost, `DeadReckoning.update()` uses the
   current speed (from the last known GPS update or odometer) and the smoothed
   heading to project the rider's position forward in small time steps.  Each
   step adds a small uncertainty radius to signal how confident the estimate is.

5. **Map matching** – `MapMatcher.match()` takes the dead-reckoned position and
   finds the closest point on any nearby road segment (loaded from the offline
   map).  If the match is within 50 metres, the position is *snapped* to the
   road, significantly reducing accumulated drift.

6. **GPS restoration** – When GPS is restored, `DeadReckoning.anchor()` is
   called with the confirmed coordinates, resetting uncertainty to zero.

---

## Crash Detection

`SensorFusion.is_crash_detected()` checks whether the orientation angles
exceed safe thresholds (e.g. a roll > 75° or pitch > 60°).  If triggered,
the Emergency module is notified.

---

## Key Classes

### `SensorFusion`
- `update(reading: IMUReading)` → `Orientation`
- `get_orientation()` → `Orientation`
- `is_crash_detected()` → `bool`
- `reset()`

### `DeadReckoning`
- `anchor(lat, lon)` – fix position from GPS
- `update(sample: MotionSample)` → `Position | None`
- `get_position()` → `Position | None`
- `get_history()` → `list[Position]`

### `HeadingTracker`
- `update(yaw_degrees)` → `float`
- `get_heading()` → `float`
- `reset()`

### `MapMatcher`
- `update_segments(road_segments)`
- `match(position: Position)` → `(Position | None, float)`

---

## Dependencies

- Python standard library only (`math`, `collections`).
