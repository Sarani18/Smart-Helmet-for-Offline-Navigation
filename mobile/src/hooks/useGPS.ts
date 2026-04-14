/**
 * useGPS  —  always-on GPS daemon
 *
 * Runs from the moment the user grants location permission and NEVER stops,
 * exactly like Google Maps — if the device GPS is off it will keep trying.
 *
 *  ONLINE path:
 *    - Streams position updates to callers (lat, lon, speed, heading)
 *    - Sends connectivity_status {network_available: true} to NCS on each fix
 *      (only when an active sessionId is present)
 *
 *  OFFLINE path (GPS_DEAD_THRESHOLD consecutive timeouts / errors):
 *    - Declares GPS lost; sends connectivity_status false to NCS
 *    - NCS 2-tap hysteresis → OFFLINE after 2 signals → DEAD_RECKONING START
 *
 *  Recovery:
 *    - First valid fix after loss resets the dead counter and tells NCS online
 *
 *  Session lifecycle:
 *    - sessionId is optional — GPS watches regardless
 *    - NCS is only contacted when sessionId is non-empty
 */

import {useCallback, useEffect, useRef, useState} from 'react';
import Geolocation from '@react-native-community/geolocation';
import {sendConnectivityStatus} from '../services/NCSService';
import {LocalizationControlAction, LocalizationModuleType} from '../types';

// ── Constants ────────────────────────────────────────────────────────────────

/** Consecutive GPS failures before declaring the link lost */
const GPS_DEAD_THRESHOLD = 3;

/** watchPosition options — high accuracy, no cache, minimum 5 m movement */
const GPS_OPTIONS = {
  enableHighAccuracy: true,
  timeout:            5000,
  maximumAge:         0,
  distanceFilter:     5,
};

// ── Types ─────────────────────────────────────────────────────────────────────

export interface GPSPosition {
  latitude:  number;
  longitude: number;
  accuracy:  number;    // metres
  speed:     number;    // m/s
  heading:   number;    // degrees, clockwise from North
  timestamp: number;    // Unix ms
}

export interface GPSState {
  position:  GPSPosition | null;
  gpsLost:   boolean;   // true after GPS_DEAD_THRESHOLD consecutive failures
  deadCount: number;    // consecutive failure count
  drActive:  boolean;   // NCS has commanded DEAD_RECKONING START
  error:     string | null;
}

export interface GPSCallbacks {
  /** Called when NCS issues a localization control command */
  onNCSCommand?: (module: LocalizationModuleType, action: LocalizationControlAction) => void;
  /** Called on each fresh GPS fix — use to anchor the DR engine */
  onGPSFix?: (position: GPSPosition) => void;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useGPS(sessionId: string, callbacks: GPSCallbacks = {}): GPSState {
  const [state, setState] = useState<GPSState>({
    position:  null,
    gpsLost:   false,
    deadCount: 0,
    drActive:  false,
    error:     null,
  });

  const deadCountRef  = useRef(0);
  const gpsLostRef    = useRef(false);
  const drActiveRef   = useRef(false);
  const sessionRef    = useRef(sessionId);
  const callbacksRef  = useRef(callbacks);

  useEffect(() => { sessionRef.current   = sessionId; },  [sessionId]);
  useEffect(() => { callbacksRef.current = callbacks; }, [callbacks]);

  // ── NCS status reporter — guarded by active session ──────────────────────
  const sendStatus = useCallback(async (online: boolean) => {
    if (!sessionRef.current) {return;} // no session → skip NCS entirely
    try {
      const res = await sendConnectivityStatus(sessionRef.current, online, online);

      const commands: Array<{module: string; action: string}> =
        (res as unknown as {commands?: Array<{module: string; action: string}>}).commands ?? [];

      for (const cmd of commands) {
        const module = cmd.module as LocalizationModuleType;
        const action = cmd.action as LocalizationControlAction;

        if (module === LocalizationModuleType.DEAD_RECKONING) {
          const active = action === LocalizationControlAction.START;
          drActiveRef.current = active;
          setState(s => ({...s, drActive: active}));
        }

        callbacksRef.current.onNCSCommand?.(module, action);
      }
    } catch {
      // best-effort
    }
  }, []);

  // ── GPS success ───────────────────────────────────────────────────────────
  const onPosition = useCallback((raw: {
    coords: {latitude: number; longitude: number; accuracy: number; speed: number | null; heading: number | null};
    timestamp: number;
  }) => {
    const position: GPSPosition = {
      latitude:  raw.coords.latitude,
      longitude: raw.coords.longitude,
      accuracy:  raw.coords.accuracy,
      speed:     raw.coords.speed   ?? 0,
      heading:   raw.coords.heading ?? 0,
      timestamp: raw.timestamp,
    };

    deadCountRef.current = 0;
    gpsLostRef.current   = false;
    setState(s => ({...s, position, gpsLost: false, deadCount: 0, error: null}));

    callbacksRef.current.onGPSFix?.(position);
    sendStatus(true);
  }, [sendStatus]);

  // ── GPS error / timeout ───────────────────────────────────────────────────
  const onError = useCallback((err: {code: number; message: string}) => {
    deadCountRef.current += 1;
    const deadCount = deadCountRef.current;
    const gpsLost   = deadCount >= GPS_DEAD_THRESHOLD;

    setState(s => ({...s, deadCount, gpsLost, error: err.message}));

    if (gpsLost && !gpsLostRef.current) {
      gpsLostRef.current = true;
    }

    sendStatus(false);
  }, [sendStatus]);

  // ── Always-on GPS watch (never stopped while hook is mounted) ─────────────
  // sessionId intentionally not in the deps — GPS watches from permission grant,
  // regardless of whether navigation is active.
  useEffect(() => {
    const watchId = Geolocation.watchPosition(onPosition, onError, GPS_OPTIONS);
    return () => { Geolocation.clearWatch(watchId); };
  }, [onPosition, onError]);

  return state;
}
