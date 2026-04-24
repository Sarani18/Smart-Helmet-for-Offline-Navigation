/**
 * Dead Reckoning service — port of localization/dead_reckoning.py.
 *
 * Estimates position by integrating speed × heading when GPS is lost.
 * Drift uncertainty grows at 2% of distance travelled (DRIFT_RATE=0.02).
 * Call anchor() whenever a GPS fix arrives to reset drift.
 */

const DRIFT_RATE = 0.02; // metres of uncertainty per metre travelled
const EARTH_RADIUS_M = 6_371_000;

export interface DRPosition {
  lat: number;
  lon: number;
  uncertaintyMeters: number;
}

interface State {
  position: DRPosition | null;
  lastTs: number | null;
}

const state: State = {
  position: null,
  lastTs: null,
};

/** Set current known GPS position and reset uncertainty to 0. */
export function anchor(lat: number, lon: number): void {
  state.position = {lat, lon, uncertaintyMeters: 0};
  state.lastTs = Date.now();
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
  if (state.position === null || state.lastTs === null) {
    // Cannot DR without an anchor fix
    return;
  }

  const dt = (ts_ms - state.lastTs) / 1000; // seconds
  state.lastTs = ts_ms;

  if (dt <= 0 || dt > 5.0 || speedMps < 0) {
    return;
  }

  const distanceM = speedMps * dt;
  const headingRad = headingDeg * (Math.PI / 180);

  // Haversine-based displacement
  const dLat = (distanceM * Math.cos(headingRad)) / EARTH_RADIUS_M;
  const dLon =
    (distanceM * Math.sin(headingRad)) /
    (EARTH_RADIUS_M * Math.cos(state.position.lat * (Math.PI / 180)));

  state.position = {
    lat: state.position.lat + dLat * (180 / Math.PI),
    lon: state.position.lon + dLon * (180 / Math.PI),
    uncertaintyMeters:
      state.position.uncertaintyMeters + distanceM * DRIFT_RATE,
  };
}

export function getPosition(): DRPosition | null {
  return state.position;
}

export function isAnchored(): boolean {
  return state.position !== null;
}

export function reset(): void {
  state.position = null;
  state.lastTs = null;
}
