/**
 * Heading tracker using a complementary filter.
 * Fuses gyroscope integration (high-freq) with accelerometer-derived tilt (drift-free).
 * Port of localization/heading_tracker.py + sensor_fusion.py.
 *
 * Filter: heading = α*(heading + gyroZ*dt) + (1-α)*accelHeading
 * α = 0.98, runs whenever new IMU data arrives (~10Hz).
 */

const ALPHA = 0.98;

let heading = 0; // degrees, 0=North, clockwise
let lastTs: number | null = null;
let initialized = false;

/**
 * Update heading with new IMU sample.
 * @param gyroZ  Z-axis gyroscope (rad/s) — rotation around vertical axis
 * @param accelX X-axis acceleration (m/s²)
 * @param accelY Y-axis acceleration (m/s²)
 * @param ts_ms  Sample timestamp in milliseconds
 */
export function updateHeading(
  gyroZ: number,
  accelX: number,
  accelY: number,
  ts_ms: number,
): void {
  if (lastTs === null) {
    lastTs = ts_ms;
    // Bootstrap heading from accelerometer (treats accel as gravity projection)
    heading = Math.atan2(accelY, accelX) * (180 / Math.PI);
    initialized = true;
    return;
  }

  const dt = (ts_ms - lastTs) / 1000; // seconds
  lastTs = ts_ms;

  if (dt <= 0 || dt > 1.0) {
    // Reject stale or out-of-order samples
    return;
  }

  // Gyroscope integration (convert rad/s to degrees, integrate over dt)
  const gyroContribution = heading + gyroZ * (180 / Math.PI) * dt;

  // Accelerometer-derived heading (yaw proxy from gravity vector projection)
  const accelHeading = Math.atan2(accelY, accelX) * (180 / Math.PI);

  // Complementary filter
  heading = ALPHA * gyroContribution + (1 - ALPHA) * accelHeading;

  // Normalize to [0, 360)
  heading = ((heading % 360) + 360) % 360;
}

export function getHeading(): number {
  return heading;
}

export function isHeadingInitialized(): boolean {
  return initialized;
}

export function resetHeading(): void {
  heading = 0;
  lastTs = null;
  initialized = false;
}
