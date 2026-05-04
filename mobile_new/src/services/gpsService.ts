/**
 * GPS service using @react-native-community/geolocation.
 * Graceful degradation: if GPS unavailable, sets gpsAvailable=false
 * and notifies listeners — does NOT throw or crash the app.
 */
import Geolocation from '@react-native-community/geolocation';

export interface GPSPosition {
  lat: number;
  lon: number;
  accuracy: number; // metres
  speedMps: number; // metres/second, -1 if unavailable
  ts_ms: number;
}

type GPSListener = (pos: GPSPosition | null) => void;

let watchId: number | null = null;
let gpsAvailable = false;
let latestPosition: GPSPosition | null = null;
let lastLiveFixTsMs = 0;
let gpsError: string | null = null;
const listeners: Set<GPSListener> = new Set();
const GPS_STALE_MS = 7000;

function notifyListeners(pos: GPSPosition | null): void {
  listeners.forEach(l => {
    try {
      l(pos);
    } catch (e) {
      console.warn('GPS listener error:', e);
    }
  });
}

function markGPSUnavailable(error: string | null = null): void {
  const wasAvailable = gpsAvailable;
  gpsAvailable = false;
  gpsError = error;
  if (wasAvailable) {
    notifyListeners(null);
  }
}

function hasFreshLiveFix(): boolean {
  return lastLiveFixTsMs > 0 && Date.now() - lastLiveFixTsMs <= GPS_STALE_MS;
}

export function startGPS(): void {
  if (watchId !== null) {
    return;
  }

  Geolocation.setRNConfiguration({
    skipPermissionRequests: true, // permissions already handled by permissions.ts
    authorizationLevel: 'whenInUse',
  });

  // Immediately emit last-known cached position (up to 5 min old) so the map
  // shows a coarse dot within ~100ms while the accurate fix is being acquired.
  Geolocation.getCurrentPosition(
    position => {
      if (latestPosition === null) {
        latestPosition = {
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          accuracy: position.coords.accuracy,
          speedMps: -1,
          ts_ms: position.timestamp,
        };
        notifyListeners(latestPosition);
      }
    },
    () => {/* no cached position available — watchPosition will provide the first fix */},
    {enableHighAccuracy: false, timeout: 2000, maximumAge: 300000},
  );

  watchId = Geolocation.watchPosition(
    position => {
      gpsAvailable = true;
      gpsError = null;
      lastLiveFixTsMs = Date.now();
      latestPosition = {
        lat: position.coords.latitude,
        lon: position.coords.longitude,
        accuracy: position.coords.accuracy,
        speedMps:
          position.coords.speed !== null && position.coords.speed >= 0
            ? position.coords.speed
            : -1,
        ts_ms: position.timestamp,
      };
      notifyListeners(latestPosition);
    },
    error => {
      // GPS signal lost or permission denied — degrade gracefully
      console.warn('GPS error code', error.code, ':', error.message);
      markGPSUnavailable(error.message);
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 30000,
      distanceFilter: 0,
    },
  );
}

export function stopGPS(): void {
  if (watchId !== null) {
    Geolocation.clearWatch(watchId);
    watchId = null;
  }
  gpsAvailable = false;
  gpsError = null;
  lastLiveFixTsMs = 0;
}

export function isGPSAvailable(): boolean {
  if (gpsAvailable && !hasFreshLiveFix()) {
    markGPSUnavailable('GPS fix is stale');
  }
  return gpsAvailable;
}

export function getGPSError(): string | null {
  return gpsError;
}

export function getLatestGPS(): GPSPosition | null {
  return latestPosition;
}

export function addGPSListener(listener: GPSListener): () => void {
  listeners.add(listener);
  // Immediately call with current state
  listener(latestPosition);
  return () => listeners.delete(listener);
}
