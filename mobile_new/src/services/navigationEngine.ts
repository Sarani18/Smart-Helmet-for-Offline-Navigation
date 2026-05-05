/**
 * Navigation engine.
 * Tracks route progress, generates turn-by-turn instructions, detects
 * off-route conditions, and signals arrival.
 */
import type {ParsedRoute, RouteStep, LatLon} from './routeService';

const OFF_ROUTE_THRESHOLD_M = 50;
const TURN_ANNOUNCE_DISTANCE_M = 100;
const TURN_NOW_DISTANCE_M = 40;
const MANEUVER_PASSED_GRACE_M = 18;
const ARRIVAL_ANNOUNCE_DISTANCE_M = 80;

export interface NavState {
  nextInstructionText: string;
  distanceToNextM: number;
  activeStepIndex: number;
  offRoute: boolean;
  destinationReached: boolean;
  confidence: number;
}

interface StepProgress {
  startM: number;
  endM: number;
}

interface RouteProjection {
  point: LatLon;
  progressM: number;
  distanceFromRouteM: number;
}

interface UpcomingInstruction {
  text: string;
  distanceM: number;
  isArrival: boolean;
}

let loadedRoute: ParsedRoute | null = null;
let currentStepIndex = 0;
let stepProgress: StepProgress[] = [];
let totalRouteDistanceM = 0;

export function loadRoute(route: ParsedRoute): void {
  loadedRoute = route;
  currentStepIndex = 0;
  stepProgress = buildStepProgress(route.steps);
  totalRouteDistanceM =
    route.totalDistanceM ||
    stepProgress[stepProgress.length - 1]?.endM ||
    routeLength(route.polyline);
}

export function unloadRoute(): void {
  loadedRoute = null;
  currentStepIndex = 0;
  stepProgress = [];
  totalRouteDistanceM = 0;
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

  const projection = projectPointOntoRoute({lat, lon}, loadedRoute.polyline);
  currentStepIndex = stepIndexForProgress(projection.progressM);

  const distanceToDestinationM = Math.max(
    0,
    totalRouteDistanceM - projection.progressM,
  );
  if (distanceToDestinationM <= TURN_NOW_DISTANCE_M) {
    return {
      nextInstructionText: 'You have arrived',
      distanceToNextM: 0,
      activeStepIndex: currentStepIndex,
      offRoute: false,
      destinationReached: true,
      confidence: 1,
    };
  }

  const offRoute = projection.distanceFromRouteM > OFF_ROUTE_THRESHOLD_M;
  const confidence = offRoute
    ? 0.3
    : 1.0 - Math.min(projection.distanceFromRouteM / OFF_ROUTE_THRESHOLD_M, 0.7);

  const upcoming = findUpcomingInstruction(
    projection.progressM,
    distanceToDestinationM,
    loadedRoute.steps,
  );

  return {
    nextInstructionText: buildInstructionText(upcoming),
    distanceToNextM: shouldShowDistance(upcoming)
      ? Math.round(upcoming.distanceM)
      : 0,
    activeStepIndex: currentStepIndex,
    offRoute,
    destinationReached: false,
    confidence,
  };
}

export function getRoutePolyline(): LatLon[] {
  return loadedRoute?.polyline ?? [];
}

function buildStepProgress(steps: RouteStep[]): StepProgress[] {
  let cursorM = 0;
  return steps.map(step => {
    const distanceM = Math.max(0, step.distance || routeLength(step.waypoints));
    const progress = {startM: cursorM, endM: cursorM + distanceM};
    cursorM += distanceM;
    return progress;
  });
}

function stepIndexForProgress(progressM: number): number {
  if (stepProgress.length === 0) {
    return 0;
  }
  for (let i = 0; i < stepProgress.length; i++) {
    if (progressM < stepProgress[i].endM) {
      return i;
    }
  }
  return stepProgress.length - 1;
}

function findUpcomingInstruction(
  progressM: number,
  distanceToDestinationM: number,
  steps: RouteStep[],
): UpcomingInstruction {
  for (let i = currentStepIndex; i < steps.length; i++) {
    const instruction = steps[i].instruction;
    const maneuverProgressM = stepProgress[i]?.startM ?? 0;
    const distanceToManeuverM = maneuverProgressM - progressM;

    if (isArrivalInstruction(instruction)) {
      return {
        text: 'You have arrived',
        distanceM: distanceToDestinationM,
        isArrival: true,
      };
    }

    if (!isTurnInstruction(instruction)) {
      continue;
    }

    if (distanceToManeuverM < -MANEUVER_PASSED_GRACE_M) {
      continue;
    }

    return {
      text: normalizeTurnInstruction(instruction),
      distanceM: Math.max(0, distanceToManeuverM),
      isArrival: false,
    };
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
    if (upcoming.distanceM <= ARRIVAL_ANNOUNCE_DISTANCE_M) {
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
  return (
    Number.isFinite(upcoming.distanceM) &&
    upcoming.distanceM <= TURN_ANNOUNCE_DISTANCE_M &&
    upcoming.distanceM >= TURN_NOW_DISTANCE_M
  );
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
  if (lower.startsWith('enter roundabout')) {
    return sentenceCase(lower);
  }
  return sentenceCase(lower);
}

function sentenceCase(text: string): string {
  return text.length === 0 ? text : text[0].toUpperCase() + text.slice(1);
}

function projectPointOntoRoute(point: LatLon, route: LatLon[]): RouteProjection {
  if (route.length === 0) {
    return {point, progressM: 0, distanceFromRouteM: Infinity};
  }
  if (route.length === 1) {
    return {
      point: route[0],
      progressM: 0,
      distanceFromRouteM: haversineMetres(point, route[0]),
    };
  }

  let bestPoint = route[0];
  let bestProgressM = 0;
  let bestDistanceM = Infinity;
  let progressBeforeSegmentM = 0;

  for (let i = 0; i < route.length - 1; i++) {
    const a = route[i];
    const b = route[i + 1];
    const projected = projectPointOnSegment(point, a, b);
    const distanceM = Math.sqrt(projected.distanceSq);
    if (distanceM < bestDistanceM) {
      bestDistanceM = distanceM;
      bestPoint = projected.point;
      bestProgressM =
        progressBeforeSegmentM + haversineMetres(a, projected.point);
    }
    progressBeforeSegmentM += haversineMetres(a, b);
  }

  return {
    point: bestPoint,
    progressM: bestProgressM,
    distanceFromRouteM: bestDistanceM,
  };
}

function projectPointOnSegment(
  point: LatLon,
  a: LatLon,
  b: LatLon,
): {point: LatLon; distanceSq: number} {
  const originLatRad = (a.lat * Math.PI) / 180;
  const metresPerDegLat = 111_320;
  const metresPerDegLon = 111_320 * Math.cos(originLatRad);
  const bx = (b.lon - a.lon) * metresPerDegLon;
  const by = (b.lat - a.lat) * metresPerDegLat;
  const px = (point.lon - a.lon) * metresPerDegLon;
  const py = (point.lat - a.lat) * metresPerDegLat;
  const lengthSq = bx * bx + by * by;
  const t =
    lengthSq <= 0 ? 0 : Math.max(0, Math.min(1, (px * bx + py * by) / lengthSq));
  const projX = bx * t;
  const projY = by * t;
  return {
    point: {
      lat: a.lat + (b.lat - a.lat) * t,
      lon: a.lon + (b.lon - a.lon) * t,
    },
    distanceSq: (px - projX) ** 2 + (py - projY) ** 2,
  };
}

function routeLength(points: LatLon[]): number {
  let distanceM = 0;
  for (let i = 0; i < points.length - 1; i++) {
    distanceM += haversineMetres(points[i], points[i + 1]);
  }
  return distanceM;
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
  const rounded =
    metres >= TURN_NOW_DISTANCE_M
      ? Math.max(10, Math.round(metres / 10) * 10)
      : Math.round(metres);
  return `${rounded} m`;
}
