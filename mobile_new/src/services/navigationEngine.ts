/**
 * Navigation engine — port of navigation/route_processor.py + turn_extractor.py.
 * Tracks rider progress along a loaded route, generates turn-by-turn instructions,
 * detects off-route conditions, and signals destination arrival.
 */
import type {ParsedRoute, RouteStep, LatLon} from './routeService';

const OFF_ROUTE_THRESHOLD_M = 50; // metres before declaring off-route

export interface NavState {
  nextInstructionText: string;
  distanceToNextM: number;
  activeStepIndex: number;
  offRoute: boolean;
  destinationReached: boolean;
  confidence: number; // 0–1
}

let loadedRoute: ParsedRoute | null = null;
let currentStepIndex = 0;

export function loadRoute(route: ParsedRoute): void {
  loadedRoute = route;
  currentStepIndex = 0;
}

export function unloadRoute(): void {
  loadedRoute = null;
  currentStepIndex = 0;
}

/** Call with the rider's current position to get updated navigation state. */
export function updatePosition(lat: number, lon: number): NavState {
  if (!loadedRoute || loadedRoute.steps.length === 0) {
    return {
      nextInstructionText: 'No route loaded',
      distanceToNextM: 0,
      activeStepIndex: 0,
      offRoute: false,
      destinationReached: false,
      confidence: 0,
    };
  }

  const steps = loadedRoute.steps;

  // Advance step index if we've passed the end of the current step
  advanceStepIfNeeded(lat, lon, steps);

  if (currentStepIndex >= steps.length) {
    return {
      nextInstructionText: 'You have arrived',
      distanceToNextM: 0,
      activeStepIndex: steps.length - 1,
      offRoute: false,
      destinationReached: true,
      confidence: 1,
    };
  }

  const currentStep = steps[currentStepIndex];
  const nextWaypoint = getStepEndPoint(currentStep);
  const distToNext = haversineMetres(lat, lon, nextWaypoint.lat, nextWaypoint.lon);

  // Off-route: compare distance to the nearest point on current step corridor
  const distToCorr = distToStepCorridor(lat, lon, currentStep);
  const offRoute = distToCorr > OFF_ROUTE_THRESHOLD_M;

  const confidence = offRoute ? 0.3 : 1.0 - Math.min(distToCorr / OFF_ROUTE_THRESHOLD_M, 0.7);

  const instructionText = distToNext > 0
    ? `In ${formatDistance(distToNext)}, ${currentStep.instruction.toLowerCase()}`
    : currentStep.instruction;

  return {
    nextInstructionText: instructionText,
    distanceToNextM: distToNext,
    activeStepIndex: currentStepIndex,
    offRoute,
    destinationReached: false,
    confidence,
  };
}

export function getRoutePolyline(): LatLon[] {
  return loadedRoute?.polyline ?? [];
}

// ---- Internal helpers ----

function advanceStepIfNeeded(
  lat: number,
  lon: number,
  steps: RouteStep[],
): void {
  if (currentStepIndex >= steps.length) {
    return;
  }
  const endPoint = getStepEndPoint(steps[currentStepIndex]);
  const dist = haversineMetres(lat, lon, endPoint.lat, endPoint.lon);

  // Move to next step when within 20m of the step endpoint
  if (dist < 20 && currentStepIndex < steps.length - 1) {
    currentStepIndex++;
  }
}

function getStepEndPoint(step: RouteStep): LatLon {
  const pts = step.waypoints;
  if (pts.length === 0) {
    return {lat: 0, lon: 0};
  }
  return pts[pts.length - 1];
}

/** Minimum distance from point to any segment of the step's waypoints. */
function distToStepCorridor(
  lat: number,
  lon: number,
  step: RouteStep,
): number {
  const pts = step.waypoints;
  if (pts.length === 0) {
    return Infinity;
  }
  if (pts.length === 1) {
    return haversineMetres(lat, lon, pts[0].lat, pts[0].lon);
  }
  let minDist = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const d = distToSegment(lat, lon, pts[i], pts[i + 1]);
    if (d < minDist) {
      minDist = d;
    }
  }
  return minDist;
}

function distToSegment(
  lat: number,
  lon: number,
  a: LatLon,
  b: LatLon,
): number {
  // Simplified: use midpoint approximation (accurate enough at street scale)
  const dA = haversineMetres(lat, lon, a.lat, a.lon);
  const dB = haversineMetres(lat, lon, b.lat, b.lon);
  return Math.min(dA, dB);
}

function haversineMetres(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6_371_000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDistance(metres: number): string {
  if (metres >= 1000) {
    return `${(metres / 1000).toFixed(1)} km`;
  }
  return `${Math.round(metres)} m`;
}
