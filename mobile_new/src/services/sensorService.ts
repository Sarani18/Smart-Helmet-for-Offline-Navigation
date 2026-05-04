/**
 * IMU sensor service using react-native-sensors@7.3.0 (bridge-based, old arch).
 * Samples accelerometer + gyroscope at 10Hz (100ms interval).
 * Graceful degradation: logs warning if sensors unavailable, does not crash.
 */
import {
  NativeEventEmitter,
  NativeModules,
} from 'react-native';
import type {Subscription} from 'rxjs';

[
  'RNSensorsAccelerometer',
  'RNSensorsGyroscope',
  'RNSensorsMagnetometer',
  'RNSensorsBarometer',
  'RNSensorsOrientation',
  'RNSensorsGravity',
].forEach(moduleName => {
  const nativeModule = NativeModules[moduleName];
  if (nativeModule) {
    nativeModule.addListener = nativeModule.addListener ?? (() => {});
    nativeModule.removeListeners = nativeModule.removeListeners ?? (() => {});
  }
});

const {
  accelerometer,
  gyroscope,
  setUpdateIntervalForType,
  SensorTypes,
} = require('react-native-sensors');

interface SmartHelmetSensorNative {
  start(updateIntervalMs: number): void;
  stop(): void;
  getStatus(): void;
  addListener(eventName: string): void;
  removeListeners(count: number): void;
}

interface NativeSensorData {
  kind: 'accelerometer' | 'gyroscope';
  x: number;
  y: number;
  z: number;
  timestamp: number;
}

interface NativeSensorStatus {
  active: boolean;
  accelerometer: boolean;
  gyroscope: boolean;
}

const smartHelmetSensors = NativeModules.SmartHelmetSensors as
  | SmartHelmetSensorNative
  | undefined;
const smartHelmetEmitter = smartHelmetSensors
  ? new NativeEventEmitter(smartHelmetSensors)
  : null;

export interface IMUReading {
  accel: {x: number; y: number; z: number};
  gyro: {x: number; y: number; z: number};
  ts_ms: number;
}

let accelSub: Subscription | null = null;
let gyroSub: Subscription | null = null;
let nativeDataSub: {remove: () => void} | null = null;
let nativeStatusSub: {remove: () => void} | null = null;
let sensorsAvailable = false;
let sensorError: string | null = null;
let accelActive = false;
let gyroActive = false;
let usingNativeSensors = false;
let nativeStarted = false;
let sensorStatusMessage: string | null = null;

let latestAccel = {x: 0, y: 0, z: 0};
let latestGyro = {x: 0, y: 0, z: 0};
let latestTs = 0;

const FILTER_ALPHA = 0.18;
const ACCEL_DEADBAND = 0.03;
const GYRO_DEADBAND = 0.005;

function smoothValue(
  previous: number,
  next: number,
  alpha: number,
  deadband: number,
): number {
  const smoothed = previous + alpha * (next - previous);
  return Math.abs(smoothed) < deadband ? 0 : smoothed;
}

function smoothVector(
  previous: {x: number; y: number; z: number},
  next: {x: number; y: number; z: number},
  deadband: number,
): {x: number; y: number; z: number} {
  return {
    x: smoothValue(previous.x, next.x, FILTER_ALPHA, deadband),
    y: smoothValue(previous.y, next.y, FILTER_ALPHA, deadband),
    z: smoothValue(previous.z, next.z, FILTER_ALPHA, deadband),
  };
}

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
  if (nativeStarted || accelSub || gyroSub) {
    return;
  }

  sensorError = null;
  sensorStatusMessage = null;

  if (smartHelmetSensors && smartHelmetEmitter) {
    usingNativeSensors = true;
    nativeStarted = true;
    nativeDataSub = smartHelmetEmitter.addListener(
      'SmartHelmetSensorData',
      (data: NativeSensorData) => {
        sensorsAvailable = true;
        sensorError = null;
        latestTs = Math.round(data.timestamp || Date.now());
        if (data.kind === 'accelerometer') {
          accelActive = true;
          latestAccel = smoothVector(
            latestAccel,
            {x: data.x, y: data.y, z: data.z},
            ACCEL_DEADBAND,
          );
        } else if (data.kind === 'gyroscope') {
          gyroActive = true;
          latestGyro = smoothVector(
            latestGyro,
            {x: data.x, y: data.y, z: data.z},
            GYRO_DEADBAND,
          );
        }
        notifyListeners();
      },
    );
    nativeStatusSub = smartHelmetEmitter.addListener(
      'SmartHelmetSensorStatus',
      (status: NativeSensorStatus) => {
        accelActive = status.accelerometer && accelActive;
        gyroActive = status.gyroscope && gyroActive;
        if (!status.accelerometer && !status.gyroscope) {
          sensorsAvailable = false;
          sensorError = 'No accelerometer or gyroscope found on this device';
        } else if (!status.accelerometer) {
          sensorStatusMessage = 'No accelerometer found';
        } else if (!status.gyroscope) {
          sensorStatusMessage = 'No gyroscope found';
        } else if (status.active) {
          sensorStatusMessage = 'Native accelerometer/gyroscope started';
        }
      },
    );
    smartHelmetSensors.start(100);
    smartHelmetSensors.getStatus();
    return;
  }

  try {
    setUpdateIntervalForType(SensorTypes.accelerometer, 100); // 10Hz
    setUpdateIntervalForType(SensorTypes.gyroscope, 100);

    accelSub = accelerometer.subscribe({
      next: (data: {x: number; y: number; z: number}) => {
        sensorsAvailable = true;
        accelActive = true;
        latestAccel = smoothVector(latestAccel, data, ACCEL_DEADBAND);
        latestTs = Date.now();
        notifyListeners();
      },
      error: (e: unknown) => {
        const msg = String(e);
        console.warn('Accelerometer unavailable â€” DR heading will be skipped:', msg);
        accelActive = false;
        sensorsAvailable = gyroActive;
        sensorError = `Accelerometer: ${msg}`;
      },
    });

    gyroSub = gyroscope.subscribe({
      next: (data: {x: number; y: number; z: number}) => {
        sensorsAvailable = true;
        gyroActive = true;
        latestGyro = smoothVector(latestGyro, data, GYRO_DEADBAND);
        // Notify with updated gyro only if accel has already fired at least once
        if (latestTs !== 0) {
          notifyListeners();
        }
      },
      error: (e: unknown) => {
        const msg = String(e);
        console.warn('Gyroscope unavailable:', msg);
        gyroActive = false;
        sensorsAvailable = accelActive;
        sensorError = `Gyroscope: ${msg}`;
      },
    });
  } catch (e) {
    const msg = String(e);
    console.warn('Sensors unavailable â€” DR heading will be skipped:', msg);
    sensorsAvailable = false;
    accelActive = false;
    gyroActive = false;
    sensorError = msg;
  }
}

export function stopSensors(): void {
  try {
    smartHelmetSensors?.stop();
    nativeDataSub?.remove();
    nativeStatusSub?.remove();
    accelSub?.unsubscribe();
    gyroSub?.unsubscribe();
  } catch (_) {}
  nativeDataSub = null;
  nativeStatusSub = null;
  nativeStarted = false;
  usingNativeSensors = false;
  accelSub = null;
  gyroSub = null;
  sensorsAvailable = false;
  accelActive = false;
  gyroActive = false;
  sensorError = null;
  sensorStatusMessage = null;
}

export function getSensorError(): string | null {
  return sensorError;
}

export function isSensorsAvailable(): boolean {
  return sensorsAvailable;
}

export function getSensorStatus(): string {
  if (sensorError) {
    return sensorError;
  }
  if (accelActive && gyroActive) {
    return usingNativeSensors
      ? 'Native accelerometer + gyroscope live'
      : 'Accelerometer + gyroscope live';
  }
  if (accelActive) {
    return 'Accelerometer live, waiting for gyroscope';
  }
  if (gyroActive) {
    return 'Gyroscope live, waiting for accelerometer';
  }
  if (sensorStatusMessage) {
    return sensorStatusMessage;
  }
  if (nativeStarted || accelSub || gyroSub) {
    return usingNativeSensors
      ? 'Native sensors started, waiting for events'
      : 'Waiting for accelerometer/gyroscope';
  }
  return 'Sensors not started';
}

export function getLatestIMU(): IMUReading | null {
  if (!sensorsAvailable || latestTs === 0) {
    return null;
  }
  return {accel: {...latestAccel}, gyro: {...latestGyro}, ts_ms: latestTs};
}

export function addIMUListener(listener: IMUListener): () => void {
  listeners.add(listener);
  const latest = getLatestIMU();
  if (latest) {
    listener(latest);
  }
  return () => listeners.delete(listener);
}
