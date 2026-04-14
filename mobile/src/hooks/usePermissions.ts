/**
 * usePermissions
 *
 * Requests all Android runtime permissions the app needs at startup:
 *   - ACCESS_FINE_LOCATION  (GPS)
 *   - BLUETOOTH_SCAN / BLUETOOTH_CONNECT  (Phase 5, Android 12+)
 *
 * Accelerometer and gyroscope do NOT require runtime permissions on Android.
 * Returns { granted, missingPermissions } so the UI can show a helpful message.
 */

import {useCallback, useState} from 'react';
import {PermissionsAndroid, Platform} from 'react-native';

export interface PermissionState {
  checking: boolean;
  locationGranted: boolean;
  bleGranted: boolean;
  allGranted: boolean;
  missing: string[];
}

const INITIAL: PermissionState = {
  checking: false,
  locationGranted: false,
  bleGranted: false,
  allGranted: false,
  missing: [],
};

export function usePermissions() {
  const [state, setState] = useState<PermissionState>(INITIAL);

  const requestAll = useCallback(async () => {
    // iOS / other platforms: sensors work without explicit permission
    if (Platform.OS !== 'android') {
      setState({checking: false, locationGranted: true, bleGranted: true, allGranted: true, missing: []});
      return;
    }

    setState(s => ({...s, checking: true}));

    // Build permission list based on Android API level
    const toRequest: string[] = [
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ];

    // BLUETOOTH_SCAN / BLUETOOTH_CONNECT are Android 12+ (API 31+)
    if (Platform.Version >= 31) {
      toRequest.push(
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      );
    }

    const results = await PermissionsAndroid.requestMultiple(
      toRequest as Array<(typeof PermissionsAndroid.PERMISSIONS)[keyof typeof PermissionsAndroid.PERMISSIONS]>,
    );

    const locationGranted =
      results[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION] === 'granted';

    const bleGranted =
      Platform.Version < 31 ||
      (results[PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN] === 'granted' &&
        results[PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT] === 'granted');

    const missing: string[] = [];
    if (!locationGranted) {missing.push('Location (GPS)');}
    if (!bleGranted)      {missing.push('Bluetooth');}

    setState({
      checking: false,
      locationGranted,
      bleGranted,
      allGranted: locationGranted, // BLE is optional for GPS/DR to work
      missing,
    });
  }, []);

  return {state, requestAll};
}
