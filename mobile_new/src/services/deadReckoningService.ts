/**
 * Dead Reckoning service - delegates to Python dead_reckoning.py via Chaquopy.
 * Keeps the same exported API as the previous TS port so positionCoordinator
 * needs no changes.
 */
import {pythonBridge} from './pythonBridge';

export interface DRPosition {
  lat: number;
  lon: number;
  uncertaintyMeters: number;
}

let distanceTravelledMeters = 0;
let lastUpdateTsMs: number | null = null;

/** Set current known GPS position and reset uncertainty to 0. */
export function anchor(lat: number, lon: number): void {
  pythonBridge.anchorDr(lat, lon);
  lastUpdateTsMs = null;
}

/**
 * Project position forward using speed and heading.
 * @param speedMps    Speed in metres per second
 * @param headingDeg  Heading in degrees (0=North, clockwise)
 * @param ts_ms       Current timestamp in milliseconds
 */
export function update(
  speedMps: number,
  headingDeg: number,
  ts_ms: number,
): void {
  pythonBridge.updateDr(speedMps, headingDeg, ts_ms);
  if (lastUpdateTsMs !== null && ts_ms > lastUpdateTsMs) {
    const dtSeconds = (ts_ms - lastUpdateTsMs) / 1000;
    distanceTravelledMeters += Math.max(0, speedMps) * dtSeconds;
  }
  lastUpdateTsMs = ts_ms;
}

export function getPosition(): DRPosition | null {
  const pos = pythonBridge.getDrPosition();
  if (!pos) {
    return null;
  }
  return {lat: pos.lat, lon: pos.lon, uncertaintyMeters: pos.uncertainty_m};
}

export function isAnchored(): boolean {
  return pythonBridge.isDrAnchored();
}

export function getDistanceTravelledMeters(): number {
  return distanceTravelledMeters;
}

export function resetDistanceTravelled(): void {
  distanceTravelledMeters = 0;
  lastUpdateTsMs = null;
}

export function reset(): void {
  pythonBridge.resetDr();
  distanceTravelledMeters = 0;
  lastUpdateTsMs = null;
}
