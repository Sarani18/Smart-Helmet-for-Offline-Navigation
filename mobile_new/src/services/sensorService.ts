/**
 * IMU sensor service using react-native-sensors@7.3.0 (bridge-based, old arch).
 * Samples accelerometer + gyroscope at 10Hz (100ms interval).
 * Graceful degradation: logs warning if sensors unavailable, does not crash.
 */
import {
  accelerometer,
  gyroscope,
  setUpdateIntervalForType,
  SensorTypes,
} from 'react-native-sensors';
import type {Subscription} from 'rxjs';


export interface IMUReading {
  accel: {x: number; y: number; z: number};
  gyro: {x: number; y: number; z: number};
  ts_ms: number;
}

let accelSub: Subscription | null = null;
let gyroSub: Subscription | null = null;
let sensorsAvailable = false;

let latestAccel = {x: 0, y: 0, z: 0};
let latestGyro = {x: 0, y: 0, z: 0};
let latestTs = 0;

type IMUListener = (reading: IMUReading) => void;
const listeners: Set<IMUListener> = new Set();

function notifyListeners(): void {
  if (latestTs === 0) {
    return;
  }
  const reading: IMUReading = {
    accel: {...latestAccel},
    gyro: {...latestGyro},
    ts_ms: latestTs,
  };
  listeners.forEach(l => {
    try {
      l(reading);
    } catch (e) {
      console.warn('IMU listener error:', e);
    }
  });
}

export function startSensors(): void {
  try {
    setUpdateIntervalForType(SensorTypes.accelerometer, 100); // 10Hz
    setUpdateIntervalForType(SensorTypes.gyroscope, 100);

    accelSub = accelerometer.subscribe({
      next: (data: {x: number; y: number; z: number}) => {
        sensorsAvailable = true;
        latestAccel = {x: data.x, y: data.y, z: data.z};
        latestTs = Date.now();
        notifyListeners();
      },
      error: (e: unknown) => {
        console.warn('Accelerometer unavailable — DR heading will be skipped:', e);
        sensorsAvailable = false;
      },
    });

    gyroSub = gyroscope.subscribe({
      next: (data: {x: number; y: number; z: number}) => {
        sensorsAvailable = true;
        latestGyro = {x: data.x, y: data.y, z: data.z};
      },
      error: (e: unknown) => {
        console.warn('Gyroscope unavailable:', e);
      },
    });
  } catch (e) {
    console.warn('Sensors unavailable — DR heading will be skipped:', e);
    sensorsAvailable = false;
  }
}

export function stopSensors(): void {
  try {
    accelSub?.unsubscribe();
    gyroSub?.unsubscribe();
  } catch (_) {}
  accelSub = null;
  gyroSub = null;
  sensorsAvailable = false;
}

export function isSensorsAvailable(): boolean {
  return sensorsAvailable;
}

export function getLatestIMU(): IMUReading | null {
  if (!sensorsAvailable || latestTs === 0) {
    return null;
  }
  return {accel: {...latestAccel}, gyro: {...latestGyro}, ts_ms: latestTs};
}

export function addIMUListener(listener: IMUListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
