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
