/**
 * NCSService — typed HTTP client for the Navigation Control System.
 *
 * Covers every endpoint defined in navigation/server.py.
 * All methods throw on non-2xx responses.
 */

import {NCS_BASE_URL} from './config';
import {UIStateMessage, UIActionType} from '../types';

// ── Generic fetch helper ────────────────────────────────────────────────────

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${NCS_BASE_URL}${path}`, {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`NCS ${path} → ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${NCS_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`NCS ${path} → ${response.status}`);
  }
  return response.json() as Promise<T>;
}

// ── Health ──────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{status: string}> {
  return get('/health');
}

// ── UI actions ──────────────────────────────────────────────────────────────

export interface StartNavActionResponse {
  accepted: boolean;
  reason: string;
  route_source?: string;
  step_count?: number;
  nav_mode: string;
  confidence_score: number;
  tile_prefetch?: {
    attempted: boolean;
    status: string;
    cached_tile_count?: number;
  };
  ui_state: UIStateMessage | null;
}

/** Send START_NAVIGATION to NCS.
 *  NCS will geocode origin/destination via Nominatim and fetch route from OSRM. */
export async function startNavigation(
  sessionId: string,
  origin: string,
  destination: string,
): Promise<StartNavActionResponse> {
  return post('/api/navigation/ui/action', {
    session_id:  sessionId,
    ts_ms:       Date.now(),
    action_type: UIActionType.START_NAVIGATION,
    payload:     {origin, destination},
    // route_data intentionally omitted — NCS fetches it from OSRM
  });
}

export async function stopNavigation(sessionId: string): Promise<{accepted: boolean}> {
  return post('/api/navigation/ui/action', {
    session_id:  sessionId,
    ts_ms:       Date.now(),
    action_type: UIActionType.STOP_NAVIGATION,
    payload:     {},
  });
}

export async function requestReroute(
  sessionId: string,
  reason = 'user_request',
): Promise<{accepted: boolean}> {
  return post('/api/navigation/ui/action', {
    session_id:  sessionId,
    ts_ms:       Date.now(),
    action_type: UIActionType.REROUTE_REQUEST,
    payload:     {reason},
  });
}

// ── UI state poll ───────────────────────────────────────────────────────────

export interface UIStateResponse {
  accepted: boolean;
  ui_state: UIStateMessage | null;
}

/** Poll NCS for the current navigation state (call at 2–5 Hz). */
export async function getUIState(sessionId: string): Promise<UIStateResponse> {
  return post('/api/navigation/ui/state', {
    session_id: sessionId,
    ts_ms:      Date.now(),
  });
}

// ── Module status (BLE / Vision health reports) ─────────────────────────────

/**
 * Best-effort report to NCS that a hardware module is compromised or recovered.
 * NCS logs it; no routing changes are triggered.
 * Always resolves (never throws) — fire-and-forget.
 */
export async function sendModuleStatus(
  sessionId: string,
  module: string,
  status: 'compromised' | 'recovered',
  reason?: string,
): Promise<void> {
  try {
    await post('/api/navigation/module/status', {
      session_id: sessionId,
      ts_ms:      Date.now(),
      module,
      status,
      reason:     reason ?? '',
    });
  } catch {
    // Intentionally swallowed — informational only
  }
}

// ── Dead-reckoning events ───────────────────────────────────────────────────

export interface DREventResponse {
  accepted: boolean;
  reason?: string;
}

/** Post a dead-reckoning position estimate to NCS.
 *  NCS processes this for route progress when GPS is unavailable.
 *  Per INTEGRATION_CONSIDERATIONS.md §1 (DR direction, future endpoint). */
export async function postDeadReckoningEvent(
  sessionId: string,
  eventId: string,
  latitude: number,
  longitude: number,
  uncertaintyMeters: number,
  headingDegrees: number,
  speedMps: number,
  confidence: number,
): Promise<DREventResponse> {
  return post('/api/navigation/localization/dead-reckoning-event', {
    session_id:  sessionId,
    event_id:    eventId,
    ts_ms:       Date.now(),
    event_type:  'DEAD_RECKONING',
    confidence,
    payload: {
      latitude,
      longitude,
      uncertainty_meters: uncertaintyMeters,
      heading_degrees:    headingDegrees,
      speed_mps:          speedMps,
    },
  });
}

// ── Connectivity status ─────────────────────────────────────────────────────

export async function sendConnectivityStatus(
  sessionId: string,
  networkAvailable: boolean,
  internetReachable: boolean,
): Promise<{accepted: boolean; network_status: string; status_changed: boolean}> {
  return post('/api/navigation/connectivity/status', {
    session_id:         sessionId,
    ts_ms:              Date.now(),
    network_available:  networkAvailable,
    internet_reachable: internetReachable,
  });
}
