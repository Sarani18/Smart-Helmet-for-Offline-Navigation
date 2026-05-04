/**
 * Heading service - delegates to Python sensor_fusion.py + heading_tracker.py
 * via Chaquopy.  Keeps the same exported API as the previous TS port so
 * positionCoordinator needs no changes.
 */
import {pythonBridge} from './pythonBridge';

/**
 * Update heading with new IMU sample.
 * @param gyroZ  Z-axis gyroscope (rad/s)
 * @param accelX X-axis acceleration (m/s^2)
 * @param accelY Y-axis acceleration (m/s^2)
 * @param ts_ms  Sample timestamp in milliseconds
 *
 * Note: Python SensorFusion expects full 6-DOF input.
 * gyroX/gyroY default to 0 since positionCoordinator only passes gyroZ.
 */
const RAD_TO_DEG = 180 / Math.PI;

export function updateHeading(
  gyroZ: number,  // rad/s from react-native-sensors
  accelX: number, // m/s^2
  accelY: number, // m/s^2
  ts_ms: number,
): void {
  // Python SensorFusion expects gyro in deg/s, accel in m/s^2
  pythonBridge.updateHeading(accelX, accelY, 9.81, 0, 0, gyroZ * RAD_TO_DEG, ts_ms);
}

export function getHeading(): number {
  return pythonBridge.getHeading();
}

export function isHeadingInitialized(): boolean {
  return pythonBridge.isHeadingInitialized();
}

export function resetHeading(): void {
  pythonBridge.resetHeading();
}
