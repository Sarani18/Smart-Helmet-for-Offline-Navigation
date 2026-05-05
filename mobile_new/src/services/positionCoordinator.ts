/**
 * Position coordinator.
 *
 * This is the app-side NCS handoff layer:
 *   1. GPS available -> use GPS and keep route progress anchored.
 *   2. GPS lost -> activate DR and request Vision.
 *   3. Vision is unavailable for now.
 *   4. DR contributes distance only; NCS projects that distance onto the route.
 */
import * as gpsService from './gpsService';
import * as sensorService from './sensorService';
import * as deadReckoningService from './deadReckoningService';
import * as headingService from './headingService';
import * as navigationEngine from './navigationEngine';
import type {LatLon} from './routeService';

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
  routeProgressM: number;
  ts_ms: number;
}

type PositionListener = (pos: CoordinatorPosition) => void;

const listeners: Set<PositionListener> = new Set();
let intervalId: ReturnType<typeof setInterval> | null = null;
let removeIMUListener: (() => void) | null = null;
let lastTs = 0;
let fallbackActive = false;
let lastKnownSpeedMps = 0;
let lastRouteProgressM = 0;
let fallbackStartRouteProgressM = 0;
let lastFallbackEmitProgressM = -Infinity;
let lastFallbackEmitTsMs = 0;

const FALLBACK_SPEED_MPS = 1.5;
const MIN_MOVING_GPS_SPEED_MPS = 0.5;
const GRAVITY_MPS2 = 9.80665;
const ACCEL_MOTION_THRESHOLD_MPS2 = 0.45;
const GYRO_MOTION_THRESHOLD_RADPS = 0.08;
const DR_ROUTE_CHECKPOINT_M = 25;
const DR_ROUTE_CHECKPOINT_MS = 2500;

export function startCoordinator(): void {
  if (intervalId !== null) {
    return;
  }

  fallbackActive = false;
  lastKnownSpeedMps = 0;
  lastRouteProgressM = 0;
  fallbackStartRouteProgressM = 0;
  lastFallbackEmitProgressM = -Infinity;
  lastFallbackEmitTsMs = 0;
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
  fallbackStartRouteProgressM = lastRouteProgressM;
  lastFallbackEmitProgressM = -Infinity;
  lastFallbackEmitTsMs = 0;
  const routePoint = getPointAtRouteProgress(fallbackStartRouteProgressM);
  try {
    deadReckoningService.anchor(routePoint.lat, routePoint.lon);
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

function shouldEmitFallbackCheckpoint(progressM: number, now: number): boolean {
  if (lastFallbackEmitProgressM === -Infinity) {
    return true;
  }
  const movedEnough =
    Math.abs(progressM - lastFallbackEmitProgressM) >= DR_ROUTE_CHECKPOINT_M;
  const waitedEnough = now - lastFallbackEmitTsMs >= DR_ROUTE_CHECKPOINT_MS;
  return movedEnough && waitedEnough;
}

function resolvePosition(): void {
  const now = Date.now();
  const gps = gpsService.getLatestGPS();
  const gpsOk = gpsService.isGPSAvailable() && gps !== null;

  if (gpsOk && gps !== null) {
    leaveFallback();
    const projected = projectPointOntoRoute({lat: gps.lat, lon: gps.lon});
    lastRouteProgressM = projected.progressM;
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
      routeProgressM: lastRouteProgressM,
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

    const drDistanceM = deadReckoningService.getDistanceTravelledMeters();
    const routeProgressM = fallbackStartRouteProgressM + drDistanceM;
    const routePoint = getPointAtRouteProgress(routeProgressM);
    lastRouteProgressM = routeProgressM;

    if (!shouldEmitFallbackCheckpoint(routeProgressM, now)) {
      return;
    }

    lastFallbackEmitProgressM = routeProgressM;
    lastFallbackEmitTsMs = now;
    emit({
      lat: routePoint.lat,
      lon: routePoint.lon,
      positionMode: 'DR',
      confidence: 0.72,
      drActive: true,
      visionStatus: 'UNAVAILABLE',
      ncsStatus: 'GPS lost - NCS using DR distance on route; Vision unavailable',
      drDistanceTravelledM: drDistanceM,
      routeProgressM,
      ts_ms: now,
    });
    return;
  }

  const routePoint = getPointAtRouteProgress(lastRouteProgressM);
  emit({
    lat: routePoint.lat,
    lon: routePoint.lon,
    positionMode: 'UNKNOWN',
    confidence: 0,
    drActive: fallbackActive,
    visionStatus: 'UNAVAILABLE',
    ncsStatus: sensorService.getSensorError()
      ? `DR unavailable: ${sensorService.getSensorError()}`
      : 'GPS lost - waiting for DR sensor data; Vision unavailable',
    drDistanceTravelledM: deadReckoningService.getDistanceTravelledMeters(),
    routeProgressM: lastRouteProgressM,
    ts_ms: now,
  });
}

function getPointAtRouteProgress(progressM: number): LatLon {
  const route = navigationEngine.getRoutePolyline();
  if (route.length === 0) {
    const gps = gpsService.getLatestGPS();
    return gps ? {lat: gps.lat, lon: gps.lon} : {lat: 0, lon: 0};
  }
  if (route.length === 1 || progressM <= 0) {
    return route[0];
  }

  let remaining = progressM;
  for (let i = 0; i < route.length - 1; i++) {
    const a = route[i];
    const b = route[i + 1];
    const segmentM = haversineMetres(a, b);
    if (remaining <= segmentM) {
      const t = segmentM <= 0 ? 0 : remaining / segmentM;
      return {
        lat: a.lat + (b.lat - a.lat) * t,
        lon: a.lon + (b.lon - a.lon) * t,
      };
    }
    remaining -= segmentM;
  }
  return route[route.length - 1];
}

function projectPointOntoRoute(point: LatLon): {point: LatLon; progressM: number} {
  const route = navigationEngine.getRoutePolyline();
  if (route.length === 0) {
    return {point, progressM: 0};
  }
  if (route.length === 1) {
    return {point: route[0], progressM: 0};
  }

  let bestPoint = route[0];
  let bestProgress = 0;
  let bestDistanceSq = Infinity;
  let progressBeforeSegment = 0;

  for (let i = 0; i < route.length - 1; i++) {
    const a = route[i];
    const b = route[i + 1];
    const projected = projectPointOnSegment(point, a, b);
    if (projected.distanceSq < bestDistanceSq) {
      bestDistanceSq = projected.distanceSq;
      bestPoint = projected.point;
      bestProgress =
        progressBeforeSegment + haversineMetres(a, projected.point);
    }
    progressBeforeSegment += haversineMetres(a, b);
  }

  return {point: bestPoint, progressM: bestProgress};
}

function projectPointOnSegment(
  point: LatLon,
  a: LatLon,
  b: LatLon,
): {point: LatLon; distanceSq: number} {
  const originLatRad = (a.lat * Math.PI) / 180;
  const metresPerDegLat = 111_320;
  const metresPerDegLon = 111_320 * Math.cos(originLatRad);
  const ax = 0;
  const ay = 0;
  const bx = (b.lon - a.lon) * metresPerDegLon;
  const by = (b.lat - a.lat) * metresPerDegLat;
  const px = (point.lon - a.lon) * metresPerDegLon;
  const py = (point.lat - a.lat) * metresPerDegLat;
  const vx = bx - ax;
  const vy = by - ay;
  const lengthSq = vx * vx + vy * vy;
  const t =
    lengthSq <= 0 ? 0 : Math.max(0, Math.min(1, (px * vx + py * vy) / lengthSq));
  const projX = ax + vx * t;
  const projY = ay + vy * t;
  return {
    point: {
      lat: a.lat + (b.lat - a.lat) * t,
      lon: a.lon + (b.lon - a.lon) * t,
    },
    distanceSq: (px - projX) ** 2 + (py - projY) ** 2,
  };
}

function haversineMetres(a: LatLon, b: LatLon): number {
  const R = 6_371_000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
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
