/**
 * Route service: geocoding via Nominatim, routing via OSRM, local caching via RNFS.
<<<<<<< HEAD
 *
 * Key behaviours:
 * - Cache-first: same origin+destination → instant load from disk, no network hit
 * - 15s timeout on every fetch: never hangs, always throws a clear error
 * - Only needs network on first use for a given route
=======
 * Only needs network at route-fetch time. After that, works fully offline.
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
 */
import RNFS from 'react-native-fs';

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';
const OSRM_URL = 'https://router.project-osrm.org/route/v1/driving';
const CACHE_DIR = `${RNFS.DocumentDirectoryPath}/osrm_routes`;

<<<<<<< HEAD
const FETCH_TIMEOUT_MS = 120000; // 30s — OSRM demo server can be slow

function isAbortError(e: unknown): boolean {
  return (
    (e instanceof Error && e.name === 'AbortError') ||
    (e instanceof Error && e.message.toLowerCase().includes('abort'))
  );
}

=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
<<<<<<< HEAD
  polyline: LatLon[];
=======
  polyline: LatLon[]; // full path
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  steps: RouteStep[];
  rawJson: unknown;
}

<<<<<<< HEAD
// ---- Public API ----

/** Geocode a place name to coordinates using Nominatim. 15s timeout. */
export async function geocode(placeName: string): Promise<LatLon> {
  const params = new URLSearchParams({q: placeName, format: 'json', limit: '1'});
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${NOMINATIM_URL}?${params.toString()}`,
      {headers: {'User-Agent': 'SmartHelmetNav/1.0'}},
    );
  } catch (e: unknown) {
    if (isAbortError(e)) {
      throw new Error('Geocoding timed out (30s) — check your internet connection and retry.');
    }
    throw new Error(`Geocoding failed: ${e instanceof Error ? e.message : String(e)}`);
  }

  if (!res.ok) {
    throw new Error(`Nominatim returned ${res.status} — try again later.`);
  }
  const data = (await res.json()) as Array<{lat: string; lon: string}>;
  if (!data || data.length === 0) {
    throw new Error(`Location not found: "${placeName}". Try a more specific name.`);
=======
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
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  }
  return {lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon)};
}

<<<<<<< HEAD
/**
 * Fetch route from OSRM (cache-first).
 * If the same origin+destination was fetched before, returns cached result instantly.
 * Cache key is derived from the place name strings, not coordinates.
 */
=======
/** Fetch route from OSRM and cache to disk. */
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
export async function fetchRoute(
  origin: LatLon,
  dest: LatLon,
  sessionId: string,
<<<<<<< HEAD
  cacheKey?: string,
): Promise<ParsedRoute> {
  // Try cache first
  if (cacheKey) {
    const cached = await loadByKey(cacheKey);
    if (cached) {
      return {...cached, id: sessionId};
    }
  }

  const coords = `${origin.lon},${origin.lat};${dest.lon},${dest.lat}`;
  const url = `${OSRM_URL}/${coords}?overview=full&geometries=geojson&steps=true&annotations=false`;

  let res: Response;
  try {
    res = await fetchWithTimeout(url);
  } catch (e: unknown) {
    if (isAbortError(e)) {
      throw new Error(
        'Route fetch timed out (30s).\n\nThe OSRM server may be busy. Check your connection and try again.',
      );
    }
    throw new Error(`Route fetch failed: ${e instanceof Error ? e.message : String(e)}`);
  }

  if (!res.ok) {
    throw new Error(`OSRM returned ${res.status} — try again later.`);
  }

  const json = (await res.json()) as OSRMResponse;
  if (json.code !== 'Ok' || !json.routes || json.routes.length === 0) {
    throw new Error('No route found between these locations. Try different place names.');
  }

  const route = parseOSRMRoute(json, sessionId);
  // Cache under both sessionId and cacheKey
  await cacheRoute(sessionId, json);
  if (cacheKey && cacheKey !== sessionId) {
    await cacheRoute(cacheKey, json);
  }
  return route;
}

/**
 * Build a deterministic cache key from origin+destination strings.
 * Use this to check cache before geocoding.
 */
export function makeRouteCacheKey(origin: string, dest: string): string {
  return slugify(`${origin}_${dest}`);
}

/** Load a previously cached route by sessionId. Returns null if not found. */
export async function loadCachedRoute(
  sessionId: string,
): Promise<ParsedRoute | null> {
  return loadByKey(sessionId);
}

// ---- Internal helpers ----

async function loadByKey(key: string): Promise<ParsedRoute | null> {
  const path = `${CACHE_DIR}/route_${key}.json`;
=======
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
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  try {
    const exists = await RNFS.exists(path);
    if (!exists) {
      return null;
    }
    const raw = await RNFS.readFile(path, 'utf8');
    const json = JSON.parse(raw) as OSRMResponse;
<<<<<<< HEAD
    return parseOSRMRoute(json, key);
  } catch (e) {
    console.warn('loadByKey failed for', key, e);
=======
    return parseOSRMRoute(json, sessionId);
  } catch (e) {
    console.warn('loadCachedRoute failed:', e);
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    return null;
  }
}

<<<<<<< HEAD
/** fetch() with AbortController timeout. Throws on timeout or network error. */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = FETCH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {...options, signal: controller.signal});
  } finally {
    clearTimeout(timerId);
  }
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 80);
}
=======
// ---- Internal helpers ----
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

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
<<<<<<< HEAD
  const polyline: LatLon[] = r.geometry.coordinates.map(([lon, lat]) => ({lat, lon}));
=======

  const polyline: LatLon[] = r.geometry.coordinates.map(([lon, lat]) => ({
    lat,
    lon,
  }));
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

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

<<<<<<< HEAD
  return {id: sessionId, totalDistanceM: r.distance, polyline, steps, rawJson: json};
}

function buildInstruction(maneuver: {type: string; modifier?: string}): string {
  const mod = maneuver.modifier ?? '';
  switch (maneuver.type) {
    case 'turn':       return `Turn ${mod}`;
    case 'depart':     return 'Start route';
    case 'arrive':     return 'You have arrived';
    case 'roundabout': return `Enter roundabout, take exit ${mod}`;
    case 'merge':      return `Merge ${mod}`;
    case 'fork':       return `Keep ${mod}`;
    default:           return `Continue ${mod}`.trim();
  }
}

async function cacheRoute(key: string, json: OSRMResponse): Promise<void> {
=======
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
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  try {
    const exists = await RNFS.exists(CACHE_DIR);
    if (!exists) {
      await RNFS.mkdir(CACHE_DIR);
    }
<<<<<<< HEAD
    await RNFS.writeFile(`${CACHE_DIR}/route_${key}.json`, JSON.stringify(json), 'utf8');
=======
    const path = `${CACHE_DIR}/route_${sessionId}.json`;
    await RNFS.writeFile(path, JSON.stringify(json), 'utf8');
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  } catch (e) {
    console.warn('Failed to cache route:', e);
  }
}
