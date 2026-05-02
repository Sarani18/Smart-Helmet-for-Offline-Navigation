/**
 * Backend Service: communicates with the Python Navigation Control System (NCS).
 * Retrieves visual landmark confirmations (CV) and fused state updates.
 */

const BACKEND_URL = 'http://192.168.1.5:8000'; // Updated to Mac Local IP for Android testing

export interface VisualEvent {
  event_type: 'TURN' | 'LANDMARK';
  confidence: number;
  payload: {
    turn_class?: string;
    landmark_class?: string;
    map_hint_name?: string;
    landmark?: string;
  };
}

export interface BackendState {
  ui_state?: {
    instruction: string;
    distance_m: number;
    current_lat: number;
    current_lon: number;
  };
  latest_visual_event?: VisualEvent;
}

export async function fetchLatestUpdate(sessionId: string): Promise<BackendState | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/navigation/ui/state`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        session_id: sessionId,
        ts_ms: Date.now(), // REQUIRED BY BACKEND
      }),
    });

    if (!res.ok) {
      return null;
    }

    const data = await res.json();
    return {
      ui_state: data.ui_state,
      latest_visual_event: data.latest_visual_event,
    };
  } catch (e) {
    console.warn('Failed to fetch from backend:', e);
    return null;
  }
}

/** 
 * Poll the backend for significant "Vision Corrections" or "Landmark Snaps".
 * These are used by the PositionCoordinator to zero out DR drift.
 */
export async function getVisionCorrection(sessionId: string): Promise<VisualEvent | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/navigation/ui/state`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        session_id: sessionId,
        ts_ms: Date.now(), // REQUIRED BY BACKEND
      }),
    });

    if (!res.ok) return null;
    const data = await res.json();
    
    // Check if there's a recent high-confidence visual event in ui_state
    if (data.ui_state && data.ui_state.last_visual_event) {
       return data.ui_state.last_visual_event;
    }
    return null;
  } catch (e) {
    return null;
  }
}
