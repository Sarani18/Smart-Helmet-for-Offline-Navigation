/**
 * Position coordinator — decides which position source to use every 500ms.
 *
 * Priority:
 *   1. GPS available → use GPS, anchor DR
 *   2. GPS lost + IMU available → use DR (estimated position)
 *   3. Neither → emit UNKNOWN with confidence 0 (app stays open, shows warning)
 *
 * Does NOT crash the app under any sensor failure combination.
 */
import * as gpsService from './gpsService';
import * as sensorService from './sensorService';
import * as deadReckoningService from './deadReckoningService';
import * as headingService from './headingService';

export type PositionMode = 'GPS' | 'DR' | 'UNKNOWN';

export interface CoordinatorPosition {
  lat: number;
  lon: number;
  positionMode: PositionMode;
  confidence: number; // 0–1
  ts_ms: number;
}

type PositionListener = (pos: CoordinatorPosition) => void;
const listeners: Set<PositionListener> = new Set();
let intervalId: ReturnType<typeof setInterval> | null = null;
let lastTs = 0;

export function startCoordinator(): void {
  if (intervalId !== null) {
    return;
  }

  // Wire IMU data into heading + DR
  sensorService.addIMUListener(imu => {
    headingService.updateHeading(
      imu.gyro.z,
      imu.accel.x,
      imu.accel.y,
      imu.ts_ms,
    );
  });

  // Run position resolution at 2Hz
  intervalId = setInterval(() => {
    resolvePosition();
  }, 500);
}

export function stopCoordinator(): void {
  if (intervalId !== null) {
    clearInterval(intervalId);
    intervalId = null;
  }
  listeners.clear();
}

export function addPositionListener(listener: PositionListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// ---- Internal resolution logic ----

function resolvePosition(): void {
  const now = Date.now();
  const gps = gpsService.getLatestGPS();
  const gpsOk = gpsService.isGPSAvailable() && gps !== null;

  if (gpsOk && gps !== null) {
    // GPS available: use it directly, anchor DR for fallback
    deadReckoningService.anchor(gps.lat, gps.lon);
    // Feed speed into DR for when GPS drops
    if (gps.speedMps >= 0 && headingService.isHeadingInitialized()) {
      deadReckoningService.update(gps.speedMps, headingService.getHeading(), now);
    }
    emit({
      lat: gps.lat,
      lon: gps.lon,
      positionMode: 'GPS',
      confidence: Math.max(0, 1 - gps.accuracy / 50), // 50m accuracy = 0 confidence
      ts_ms: now,
    });
    return;
  }

  // GPS lost — try dead reckoning
  const imuAvailable = sensorService.isSensorsAvailable();
  if (imuAvailable && deadReckoningService.isAnchored()) {
    const imu = sensorService.getLatestIMU();
    if (imu && headingService.isHeadingInitialized()) {
      // Estimate speed from last known GPS speed or assume slow creep
      const lastGPS = gpsService.getLatestGPS();
      const speedMps = lastGPS && lastGPS.speedMps >= 0 ? lastGPS.speedMps : 2.0;
      deadReckoningService.update(speedMps, headingService.getHeading(), now);
    }

    const drPos = deadReckoningService.getPosition();
    if (drPos) {
      // Confidence degrades with uncertainty radius
      const confidence = Math.max(0, 1 - drPos.uncertaintyMeters / 100);
      emit({
        lat: drPos.lat,
        lon: drPos.lon,
        positionMode: 'DR',
        confidence,
        ts_ms: now,
      });
      return;
    }
  }

  // No position source available — emit UNKNOWN
  // App stays open, UI shows warning banner
  const drPos = deadReckoningService.getPosition();
  emit({
    lat: drPos?.lat ?? 0,
    lon: drPos?.lon ?? 0,
    positionMode: 'UNKNOWN',
    confidence: 0,
    ts_ms: now,
  });
}

function emit(pos: CoordinatorPosition): void {
  // Deduplicate if ts hasn't advanced
  if (pos.ts_ms <= lastTs) {
    return;
  }
  lastTs = pos.ts_ms;
  listeners.forEach(l => {
    try {
      l(pos);
    } catch (e) {
      console.warn('Position listener error:', e);
    }
  });
}
