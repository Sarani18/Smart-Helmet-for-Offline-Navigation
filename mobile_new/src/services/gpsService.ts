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
const listeners: Set<GPSListener> = new Set();

function notifyListeners(pos: GPSPosition | null): void {
  listeners.forEach(l => {
    try {
      l(pos);
    } catch (e) {
      console.warn('GPS listener error:', e);
    }
  });
}

export function startGPS(): void {
  if (watchId !== null) {
    return;
  }

  Geolocation.setRNConfiguration({
    skipPermissionRequests: true, // permissions already handled by permissions.ts
    authorizationLevel: 'whenInUse',
  });

  watchId = Geolocation.watchPosition(
    position => {
      gpsAvailable = true;
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
      gpsAvailable = false;
      notifyListeners(null);
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 5000,
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
}

export function isGPSAvailable(): boolean {
  return gpsAvailable;
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
