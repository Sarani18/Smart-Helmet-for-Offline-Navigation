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
<<<<<<< HEAD

export type PositionMode = 'GPS' | 'DR' | 'UNKNOWN';
=======
import * as backendService from './backendService';

export type PositionMode = 'GPS' | 'DR' | 'UNKNOWN' | 'FUSED';
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

export interface CoordinatorPosition {
  lat: number;
  lon: number;
  positionMode: PositionMode;
  confidence: number; // 0–1
<<<<<<< HEAD
  drDistanceTravelledM: number;
  ts_ms: number;
=======
  ts_ms: number;
  landmarkName?: string;
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
}

type PositionListener = (pos: CoordinatorPosition) => void;
const listeners: Set<PositionListener> = new Set();
let intervalId: ReturnType<typeof setInterval> | null = null;
<<<<<<< HEAD
let removeIMUListener: (() => void) | null = null;
let lastTs = 0;

export function startCoordinator(): void {
  if (intervalId !== null) {
    return;
  }

  try {
    deadReckoningService.reset();
  } catch (e) {
    console.warn('DR reset failed:', e);
  }

  // Wire IMU data into heading + DR
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
=======
let lastTs = 0;
let currentSessionId: string | null = null;
let latestLandmark: string | null = null;
let latestLandmarkTs = 0;

export function startCoordinator(sessionId?: string): void {
  if (intervalId !== null) {
    return;
  }
  currentSessionId = sessionId ?? null;

  // Wire IMU data into heading + DR
  sensorService.addIMUListener(imu => {
    headingService.updateHeading(
      imu.gyro.z,
      imu.accel.x,
      imu.accel.y,
      imu.ts_ms,
    );
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
<<<<<<< HEAD
  removeIMUListener?.();
  removeIMUListener = null;
=======
  currentSessionId = null;
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
<<<<<<< HEAD
    try {
      deadReckoningService.anchor(gps.lat, gps.lon);
    } catch (e) {
      console.warn('DR anchor failed:', e);
    }
    // Feed speed into DR for when GPS drops
    if (gps.speedMps >= 0 && headingService.isHeadingInitialized()) {
      try {
        deadReckoningService.update(gps.speedMps, headingService.getHeading(), now);
      } catch (e) {
        console.warn('DR update from GPS failed:', e);
      }
=======
    deadReckoningService.anchor(gps.lat, gps.lon);
    // Feed speed into DR for when GPS drops
    if (gps.speedMps >= 0 && headingService.isHeadingInitialized()) {
      deadReckoningService.update(gps.speedMps, headingService.getHeading(), now);
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    }
    emit({
      lat: gps.lat,
      lon: gps.lon,
      positionMode: 'GPS',
      confidence: Math.max(0, 1 - gps.accuracy / 50), // 50m accuracy = 0 confidence
<<<<<<< HEAD
      drDistanceTravelledM: deadReckoningService.getDistanceTravelledMeters(),
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
<<<<<<< HEAD
      try {
        deadReckoningService.update(speedMps, headingService.getHeading(), now);
      } catch (e) {
        console.warn('DR update failed:', e);
      }
=======
      deadReckoningService.update(speedMps, headingService.getHeading(), now);
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
<<<<<<< HEAD
        drDistanceTravelledM: deadReckoningService.getDistanceTravelledMeters(),
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
        ts_ms: now,
      });
      return;
    }
  }

<<<<<<< HEAD
=======
  // --- NEW: Backend Fusion (CV/Landmark Correction) ---
  if (currentSessionId) {
    checkBackendCorrections();
  }

>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  // No position source available — emit UNKNOWN
  // App stays open, UI shows warning banner
  const drPos = deadReckoningService.getPosition();
  emit({
    lat: drPos?.lat ?? 0,
    lon: drPos?.lon ?? 0,
    positionMode: 'UNKNOWN',
    confidence: 0,
<<<<<<< HEAD
    drDistanceTravelledM: deadReckoningService.getDistanceTravelledMeters(),
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    ts_ms: now,
  });
}

<<<<<<< HEAD
function emit(pos: CoordinatorPosition): void {
=======
async function checkBackendCorrections(): Promise<void> {
  if (!currentSessionId) return;

  const correction = await backendService.getVisionCorrection(currentSessionId);
  if (correction && correction.confidence > 0.8) {
    const name = correction.payload.landmark || correction.payload.map_hint_name || 'Junction';
    console.log(`[Coordinator] CV Correction received: ${name}`);
    
    latestLandmark = name;
    latestLandmarkTs = Date.now();
    
    // Snap position would happen here
  }
}

function emit(pos: CoordinatorPosition): void {
  // If we have a recent landmark (< 5s), include it and consider mode FUSED
  const now = Date.now();
  if (latestLandmark && now - latestLandmarkTs < 5000) {
    pos.landmarkName = latestLandmark;
    if (pos.positionMode === 'DR' || pos.positionMode === 'UNKNOWN') {
      pos.positionMode = 'FUSED';
      pos.confidence = Math.max(pos.confidence, 0.9); // Vision boosts confidence
    }
  } else {
    latestLandmark = null;
  }

>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
