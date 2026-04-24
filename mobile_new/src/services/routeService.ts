/**
 * Route service: geocoding via Nominatim, routing via OSRM, local caching via RNFS.
 * Only needs network at route-fetch time. After that, works fully offline.
 */
import RNFS from 'react-native-fs';

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';
const OSRM_URL = 'https://router.project-osrm.org/route/v1/driving';
const CACHE_DIR = `${RNFS.DocumentDirectoryPath}/osrm_routes`;

export interface LatLon {
  lat: number;
  lon: number;
}

export interface RouteStep {
  instruction: string;
  distance: number; // metres
  bearing: number;  // degrees
  waypoints: LatLon[];
}

export interface ParsedRoute {
  id: string;
  totalDistanceM: number;
  polyline: LatLon[]; // full path
  steps: RouteStep[];
  rawJson: unknown;
}

/** Geocode a place name to coordinates using Nominatim. */
export async function geocode(placeName: string): Promise<LatLon> {
  const params = new URLSearchParams({
    q: placeName,
    format: 'json',
    limit: '1',
  });
  const res = await fetch(`${NOMINATIM_URL}?${params.toString()}`, {
    headers: {'User-Agent': 'SmartHelmetNav/1.0'},
  });
  if (!res.ok) {
    throw new Error(`Nominatim error: ${res.status}`);
  }
  const data = (await res.json()) as Array<{lat: string; lon: string}>;
  if (!data || data.length === 0) {
    throw new Error(`No results found for: ${placeName}`);
  }
  return {lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon)};
}

/** Fetch route from OSRM and cache to disk. */
export async function fetchRoute(
  origin: LatLon,
  dest: LatLon,
  sessionId: string,
): Promise<ParsedRoute> {
  const coords = `${origin.lon},${origin.lat};${dest.lon},${dest.lat}`;
  const url = `${OSRM_URL}/${coords}?overview=full&geometries=geojson&steps=true&annotations=false`;

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`OSRM error: ${res.status}`);
  }
  const json = (await res.json()) as OSRMResponse;

  if (json.code !== 'Ok' || !json.routes || json.routes.length === 0) {
    throw new Error('OSRM returned no routes');
  }

  const route = parseOSRMRoute(json, sessionId);
  await cacheRoute(sessionId, json);
  return route;
}

/** Load a previously cached route. Returns null if not found. */
export async function loadCachedRoute(
  sessionId: string,
): Promise<ParsedRoute | null> {
  const path = `${CACHE_DIR}/route_${sessionId}.json`;
  try {
    const exists = await RNFS.exists(path);
    if (!exists) {
      return null;
    }
    const raw = await RNFS.readFile(path, 'utf8');
    const json = JSON.parse(raw) as OSRMResponse;
    return parseOSRMRoute(json, sessionId);
  } catch (e) {
    console.warn('loadCachedRoute failed:', e);
    return null;
  }
}

// ---- Internal helpers ----

interface OSRMResponse {
  code: string;
  routes: OSRMRoute[];
}
interface OSRMRoute {
  distance: number;
  geometry: {coordinates: [number, number][]};
  legs: OSRMLeg[];
}
interface OSRMLeg {
  steps: OSRMStep[];
}
interface OSRMStep {
  maneuver: {bearing_after: number; type: string; modifier?: string};
  distance: number;
  geometry: {coordinates: [number, number][]};
}

function parseOSRMRoute(json: OSRMResponse, sessionId: string): ParsedRoute {
  const r = json.routes[0];

  const polyline: LatLon[] = r.geometry.coordinates.map(([lon, lat]) => ({
    lat,
    lon,
  }));

  const steps: RouteStep[] = [];
  for (const leg of r.legs) {
    for (const step of leg.steps) {
      steps.push({
        instruction: buildInstruction(step.maneuver),
        distance: step.distance,
        bearing: step.maneuver.bearing_after,
        waypoints: step.geometry.coordinates.map(([lon, lat]) => ({lat, lon})),
      });
    }
  }

  return {
    id: sessionId,
    totalDistanceM: r.distance,
    polyline,
    steps,
    rawJson: json,
  };
}

function buildInstruction(maneuver: {
  type: string;
  modifier?: string;
}): string {
  const mod = maneuver.modifier ?? '';
  switch (maneuver.type) {
    case 'turn':
      return `Turn ${mod}`;
    case 'depart':
      return 'Start route';
    case 'arrive':
      return 'You have arrived';
    case 'roundabout':
      return `Enter roundabout and take exit ${mod}`;
    case 'merge':
      return `Merge ${mod}`;
    case 'fork':
      return `Keep ${mod}`;
    default:
      return `Continue ${mod}`.trim();
  }
}

async function cacheRoute(sessionId: string, json: OSRMResponse): Promise<void> {
  try {
    const exists = await RNFS.exists(CACHE_DIR);
    if (!exists) {
      await RNFS.mkdir(CACHE_DIR);
    }
    const path = `${CACHE_DIR}/route_${sessionId}.json`;
    await RNFS.writeFile(path, JSON.stringify(json), 'utf8');
  } catch (e) {
    console.warn('Failed to cache route:', e);
  }
}
