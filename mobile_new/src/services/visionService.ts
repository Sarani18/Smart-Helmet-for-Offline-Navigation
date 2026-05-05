/**
 * Optional Vision bridge client.
 *
 * The app calls this only during GPS fallback. If the server is unreachable or
 * reports degraded/unavailable state, NCS keeps DR running and surfaces the
 * Vision status in the UI.
 */
import type {LatLon} from './routeService';

export type VisionServerStatus = 'OK' | 'DEGRADED' | 'UNAVAILABLE' | 'STOPPED';

export interface VisionPositionHint {
  lat: number;
  lon: number;
  route_progress_m: number;
  source: string;
}

export interface VisionEvent {
  event_type: 'TURN' | 'LANDMARK' | 'SIGNBOARD';
  confidence: number;
  payload: {
    turn_class?: string;
    landmark_class?: string;
    map_hint_name?: string;
    text?: string;
    direction_hint?: string;
  };
}

export interface VisionResponse {
  status: VisionServerStatus;
  message: string;
  session_id: string;
  ts_ms: number;
  confidence: number;
  visual_event?: VisionEvent | null;
  position_hint?: VisionPositionHint | null;
  latest_detection?: string | null;
  diagnostics?: Record<string, unknown>;
}

export interface VisionStartPayload {
  session_id: string;
  origin: LatLon;
  destination: LatLon;
  current: LatLon;
  route_polyline: LatLon[];
  route_progress_m: number;
  heading_deg?: number;
}

export interface VisionUpdatePayload {
  session_id: string;
  current: LatLon;
  route_polyline: LatLon[];
  route_progress_m: number;
  dr_distance_travelled_m: number;
  heading_deg?: number;
}

// Put your laptop/server IP first for physical-phone testing.
const VISION_SERVER_URLS = [
  'http://192.168.1.2:8010',
  'http://10.0.2.2:8010',
  'http://127.0.0.1:8010',
];

const REQUEST_TIMEOUT_MS = 1800;
const RETRY_BACKOFF_MS = 5000;

let activeBaseUrl: string | null = null;
let retryAfterTsMs = 0;

export async function startVisionSession(
  payload: VisionStartPayload,
): Promise<VisionResponse> {
  return postVision('/api/vision/start', {
    ...payload,
    ts_ms: Date.now(),
  });
}

export async function updateVisionSession(
  payload: VisionUpdatePayload,
): Promise<VisionResponse> {
  return postVision('/api/vision/update', {
    ...payload,
    ts_ms: Date.now(),
  });
}

export async function stopVisionSession(sessionId: string): Promise<void> {
  if (!activeBaseUrl) {
    return;
  }
  try {
    await fetchWithTimeout(`${activeBaseUrl}/api/vision/stop`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, ts_ms: Date.now()}),
    });
  } catch (_) {
    // Stop is best-effort; never let Vision shutdown affect navigation.
  }
}

async function postVision(path: string, body: unknown): Promise<VisionResponse> {
  if (Date.now() < retryAfterTsMs && activeBaseUrl === null) {
    return unavailable('Vision server retry backoff active');
  }

  const candidates = activeBaseUrl
    ? [activeBaseUrl]
    : VISION_SERVER_URLS;

  for (const baseUrl of candidates) {
    try {
      const res = await fetchWithTimeout(`${baseUrl}${path}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        continue;
      }
      const data = (await res.json()) as VisionResponse;
      activeBaseUrl = baseUrl;
      retryAfterTsMs = 0;
      return data;
    } catch (_) {
      // Try the next configured server URL.
    }
  }

  activeBaseUrl = null;
  retryAfterTsMs = Date.now() + RETRY_BACKOFF_MS;
  return unavailable('Vision server unreachable');
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, {...init, signal: controller.signal});
  } finally {
    clearTimeout(timeout);
  }
}

function unavailable(message: string): VisionResponse {
  return {
    status: 'UNAVAILABLE',
    message,
    session_id: '',
    ts_ms: Date.now(),
    confidence: 0,
  };
}
