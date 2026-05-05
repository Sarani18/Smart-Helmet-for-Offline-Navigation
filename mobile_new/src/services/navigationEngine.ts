/**
 * Navigation engine.
 * Tracks rider progress along a loaded route, generates turn-by-turn
 * instructions, detects off-route conditions, and signals arrival.
 */
import type {ParsedRoute, RouteStep, LatLon} from './routeService';

const OFF_ROUTE_THRESHOLD_M = 50;
const TURN_ANNOUNCE_DISTANCE_M = 100;
const TURN_NOW_DISTANCE_M = 40;

export interface NavState {
  nextInstructionText: string;
  distanceToNextM: number;
  activeStepIndex: number;
  offRoute: boolean;
  destinationReached: boolean;
  confidence: number;
}

interface UpcomingInstruction {
  text: string;
  distanceM: number;
  isArrival: boolean;
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
  const distToCorr = distToStepCorridor(lat, lon, currentStep);
  const offRoute = distToCorr > OFF_ROUTE_THRESHOLD_M;
  const confidence = offRoute
    ? 0.3
    : 1.0 - Math.min(distToCorr / OFF_ROUTE_THRESHOLD_M, 0.7);

  const upcoming = findUpcomingInstruction(lat, lon, steps);
  const instructionText = buildInstructionText(upcoming);

  return {
    nextInstructionText: instructionText,
    distanceToNextM: shouldShowDistance(upcoming) ? Math.round(upcoming.distanceM) : 0,
    activeStepIndex: currentStepIndex,
    offRoute,
    destinationReached: false,
    confidence,
  };
}

export function getRoutePolyline(): LatLon[] {
  return loadedRoute?.polyline ?? [];
}

function findUpcomingInstruction(
  lat: number,
  lon: number,
  steps: RouteStep[],
): UpcomingInstruction {
  const currentStep = steps[currentStepIndex];
  let distanceToStepStart = distanceToEndOfStep(lat, lon, currentStep);

  for (let i = currentStepIndex + 1; i < steps.length; i++) {
    const instruction = steps[i].instruction;
    if (isArrivalInstruction(instruction)) {
      return {
        text: 'You have arrived',
        distanceM: distanceToStepStart,
        isArrival: true,
      };
    }
    if (isTurnInstruction(instruction)) {
      return {
        text: normalizeTurnInstruction(instruction),
        distanceM: distanceToStepStart,
        isArrival: false,
      };
    }
    distanceToStepStart += Math.max(0, steps[i].distance);
  }

  return {
    text: 'Continue straight',
    distanceM: Infinity,
    isArrival: false,
  };
}

function buildInstructionText(upcoming: UpcomingInstruction): string {
  if (upcoming.isArrival) {
    if (upcoming.distanceM <= TURN_NOW_DISTANCE_M) {
      return 'You have arrived';
    }
    if (upcoming.distanceM <= TURN_ANNOUNCE_DISTANCE_M) {
      return `Arrive in ${formatDistance(upcoming.distanceM)}`;
    }
    return 'Continue straight';
  }

  if (upcoming.distanceM > TURN_ANNOUNCE_DISTANCE_M) {
    return 'Continue straight';
  }
  if (upcoming.distanceM < TURN_NOW_DISTANCE_M) {
    return upcoming.text;
  }
  return `${upcoming.text} in ${formatDistance(upcoming.distanceM)}`;
}

function shouldShowDistance(upcoming: UpcomingInstruction): boolean {
  return Number.isFinite(upcoming.distanceM) &&
    upcoming.distanceM <= TURN_ANNOUNCE_DISTANCE_M;
}

function isTurnInstruction(instruction: string): boolean {
  const lower = instruction.toLowerCase();
  if (lower.includes('arrived') || lower.includes('start route')) {
    return false;
  }
  if (lower.includes('roundabout') || lower.includes('merge')) {
    return true;
  }
  if (lower.startsWith('turn ') || lower.startsWith('keep ')) {
    return !lower.includes('straight');
  }
  return (
    lower.includes(' left') ||
    lower.includes(' right') ||
    lower.includes('u-turn')
  ) && !lower.includes('continue straight');
}

function isArrivalInstruction(instruction: string): boolean {
  return instruction.toLowerCase().includes('arrived');
}

function normalizeTurnInstruction(instruction: string): string {
  const lower = instruction.toLowerCase();
  if (lower.startsWith('turn ')) {
    return `Take ${lower.replace(/^turn\s+/, '')}`;
  }
  if (lower.startsWith('keep ')) {
    return `Keep ${lower.replace(/^keep\s+/, '')}`;
  }
  if (lower.startsWith('merge ')) {
    return `Merge ${lower.replace(/^merge\s+/, '')}`;
  }
  return sentenceCase(lower);
}

function sentenceCase(text: string): string {
  return text.length === 0 ? text : text[0].toUpperCase() + text.slice(1);
}

function advanceStepIfNeeded(
  lat: number,
  lon: number,
  steps: RouteStep[],
): void {
  if (currentStepIndex >= steps.length) {
    return;
  }
  const endPoint = getStepEndPoint(steps[currentStepIndex]);
  const dist = haversineMetres(
    {lat, lon},
    {lat: endPoint.lat, lon: endPoint.lon},
  );

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

function distanceToEndOfStep(
  lat: number,
  lon: number,
  step: RouteStep,
): number {
  const pts = step.waypoints;
  if (pts.length === 0) {
    return 0;
  }
  if (pts.length === 1) {
    return haversineMetres({lat, lon}, pts[0]);
  }

  const nearestIndex = nearestWaypointIndex({lat, lon}, pts);
  let distanceM = haversineMetres({lat, lon}, pts[nearestIndex]);
  for (let i = nearestIndex; i < pts.length - 1; i++) {
    distanceM += haversineMetres(pts[i], pts[i + 1]);
  }
  return distanceM;
}

function nearestWaypointIndex(point: LatLon, pts: LatLon[]): number {
  let nearestIndex = 0;
  let nearestDistance = Infinity;
  for (let i = 0; i < pts.length; i++) {
    const d = haversineMetres(point, pts[i]);
    if (d < nearestDistance) {
      nearestDistance = d;
      nearestIndex = i;
    }
  }
  return nearestIndex;
}

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
    return haversineMetres({lat, lon}, pts[0]);
  }
  let minDist = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const d = distToSegment({lat, lon}, pts[i], pts[i + 1]);
    if (d < minDist) {
      minDist = d;
    }
  }
  return minDist;
}

function distToSegment(point: LatLon, a: LatLon, b: LatLon): number {
  const dA = haversineMetres(point, a);
  const dB = haversineMetres(point, b);
  return Math.min(dA, dB);
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

function formatDistance(metres: number): string {
  const rounded = metres >= TURN_NOW_DISTANCE_M
    ? Math.max(10, Math.round(metres / 10) * 10)
    : Math.round(metres);
  return `${rounded} m`;
}
