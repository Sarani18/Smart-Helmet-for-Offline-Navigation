/**
 * Position coordinator.
 *
 * This is the app-side NCS handoff layer:
 *   1. GPS available -> use GPS and keep DR anchored.
 *   2. GPS lost -> activate DR and request Vision.
 *   3. Vision is unavailable for now, so DR provides fallback map updates.
 *   4. If neither source can update position, emit UNKNOWN without crashing.
 */
import * as gpsService from './gpsService';
import * as sensorService from './sensorService';
import * as deadReckoningService from './deadReckoningService';
import * as headingService from './headingService';

export type PositionMode = 'GPS' | 'DR' | 'UNKNOWN';
export type VisionStatus = 'IDLE' | 'UNAVAILABLE';

export interface CoordinatorPosition {
  lat: number;
  lon: number;
  positionMode: PositionMode;
  confidence: number;
  drActive: boolean;
  visionStatus: VisionStatus;
  ncsStatus: string;
  drDistanceTravelledM: number;
  ts_ms: number;
}

type PositionListener = (pos: CoordinatorPosition) => void;

const listeners: Set<PositionListener> = new Set();
let intervalId: ReturnType<typeof setInterval> | null = null;
let removeIMUListener: (() => void) | null = null;
let lastTs = 0;
let fallbackActive = false;
let lastKnownSpeedMps = 0;

const FALLBACK_SPEED_MPS = 1.5;
const MIN_MOVING_GPS_SPEED_MPS = 0.5;
const GRAVITY_MPS2 = 9.80665;
const ACCEL_MOTION_THRESHOLD_MPS2 = 0.45;
const GYRO_MOTION_THRESHOLD_RADPS = 0.08;

export function startCoordinator(): void {
  if (intervalId !== null) {
    return;
  }

  fallbackActive = false;
  lastKnownSpeedMps = 0;
  try {
    deadReckoningService.reset();
    headingService.resetHeading();
  } catch (e) {
    console.warn('NCS reset failed:', e);
  }

  removeIMUListener = sensorService.addIMUListener(imu => {
    try {
      headingService.updateHeading(
        imu.gyro.z,
        imu.accel.x,
        imu.accel.y,
        imu.ts_ms,
      );
    } catch (e) {
      console.warn('Heading update failed:', e);
    }
  });

  intervalId = setInterval(resolvePosition, 500);
}

export function stopCoordinator(): void {
  if (intervalId !== null) {
    clearInterval(intervalId);
    intervalId = null;
  }
  removeIMUListener?.();
  removeIMUListener = null;
  fallbackActive = false;
  sensorService.stopSensors();
  listeners.clear();
}

export function addPositionListener(listener: PositionListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function enterFallback(): void {
  if (fallbackActive) {
    return;
  }
  fallbackActive = true;
  const lastGPS = gpsService.getLatestGPS();
  try {
    if (lastGPS) {
      deadReckoningService.anchor(lastGPS.lat, lastGPS.lon);
    }
    deadReckoningService.resetDistanceTravelled();
    headingService.resetHeading();
  } catch (e) {
    console.warn('NCS fallback init failed:', e);
  }
  sensorService.startSensors();
}

function leaveFallback(): void {
  if (!fallbackActive) {
    return;
  }
  fallbackActive = false;
  sensorService.stopSensors();
  try {
    deadReckoningService.resetDistanceTravelled();
    headingService.resetHeading();
  } catch (e) {
    console.warn('NCS fallback stop failed:', e);
  }
}

function hasMotionEvidence(imu: sensorService.IMUReading | null): boolean {
  if (!imu) {
    return false;
  }
  const accelMagnitude = Math.sqrt(
    imu.accel.x * imu.accel.x +
      imu.accel.y * imu.accel.y +
      imu.accel.z * imu.accel.z,
  );
  const gyroMagnitude = Math.sqrt(
    imu.gyro.x * imu.gyro.x +
      imu.gyro.y * imu.gyro.y +
      imu.gyro.z * imu.gyro.z,
  );
  return (
    Math.abs(accelMagnitude - GRAVITY_MPS2) > ACCEL_MOTION_THRESHOLD_MPS2 ||
    gyroMagnitude > GYRO_MOTION_THRESHOLD_RADPS
  );
}

function resolveFallbackSpeed(imu: sensorService.IMUReading | null): number {
  if (lastKnownSpeedMps >= MIN_MOVING_GPS_SPEED_MPS) {
    return lastKnownSpeedMps;
  }
  return hasMotionEvidence(imu) ? FALLBACK_SPEED_MPS : 0;
}

function resolvePosition(): void {
  const now = Date.now();
  const gps = gpsService.getLatestGPS();
  const gpsOk = gpsService.isGPSAvailable() && gps !== null;

  if (gpsOk && gps !== null) {
    leaveFallback();
    try {
      deadReckoningService.anchor(gps.lat, gps.lon);
    } catch (e) {
      console.warn('DR anchor failed:', e);
    }
    if (gps.speedMps >= 0) {
      lastKnownSpeedMps = gps.speedMps;
    }
    emit({
      lat: gps.lat,
      lon: gps.lon,
      positionMode: 'GPS',
      confidence: Math.max(0, 1 - gps.accuracy / 50),
      drActive: false,
      visionStatus: 'IDLE',
      ncsStatus: 'GPS active',
      drDistanceTravelledM: 0,
      ts_ms: now,
    });
    return;
  }

  enterFallback();

  const imu = sensorService.getLatestIMU();
  const imuAvailable = sensorService.isSensorsAvailable();
  if (imuAvailable && deadReckoningService.isAnchored()) {
    if (imu && headingService.isHeadingInitialized()) {
      try {
        deadReckoningService.update(
          resolveFallbackSpeed(imu),
          headingService.getHeading(),
          now,
        );
      } catch (e) {
        console.warn('DR update failed:', e);
      }
    }

    const drPos = deadReckoningService.getPosition();
    if (drPos) {
      emit({
        lat: drPos.lat,
        lon: drPos.lon,
        positionMode: 'DR',
        confidence: Math.max(0, 1 - drPos.uncertaintyMeters / 100),
        drActive: true,
        visionStatus: 'UNAVAILABLE',
        ncsStatus: 'GPS lost - NCS activated DR; Vision unavailable',
        drDistanceTravelledM: deadReckoningService.getDistanceTravelledMeters(),
        ts_ms: now,
      });
      return;
    }
  }

  const drPos = deadReckoningService.getPosition();
  emit({
    lat: drPos?.lat ?? 0,
    lon: drPos?.lon ?? 0,
    positionMode: 'UNKNOWN',
    confidence: 0,
    drActive: fallbackActive,
    visionStatus: 'UNAVAILABLE',
    ncsStatus: sensorService.getSensorError()
      ? `DR unavailable: ${sensorService.getSensorError()}`
      : 'GPS lost - waiting for DR sensor data; Vision unavailable',
    drDistanceTravelledM: deadReckoningService.getDistanceTravelledMeters(),
    ts_ms: now,
  });
}

function emit(pos: CoordinatorPosition): void {
  if (pos.ts_ms <= lastTs) {
    return;
  }
  lastTs = pos.ts_ms;
  listeners.forEach(listener => {
    try {
      listener(pos);
    } catch (e) {
      console.warn('Position listener error:', e);
    }
  });
}
