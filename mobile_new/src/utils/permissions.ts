/**
 * Permission orchestrator for Android API 29–34.
 * Foreground location is requested first, then background location sequentially
 * (Android 11+ requires this order), then BLE permissions on API 31+.
 */
import {PermissionsAndroid, Platform} from 'react-native';
import type {Permission} from 'react-native';

export interface PermissionResult {
  fineLocation: boolean;
  backgroundLocation: boolean;
  bluetooth: boolean;
  allCriticalGranted: boolean;
}

export async function requestApplicationPermissions(): Promise<PermissionResult> {
  if (Platform.OS !== 'android') {
    return {
      fineLocation: true,
      backgroundLocation: true,
      bluetooth: true,
      allCriticalGranted: true,
    };
  }

  const apiLevel = Platform.Version as number;
  const result: PermissionResult = {
    fineLocation: false,
    backgroundLocation: false,
    bluetooth: false,
    allCriticalGranted: false,
  };

  try {
    // Step 1: Foreground location (required on all API levels)
    const foregroundPerms: Permission[] = [
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
      PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION,
    ];

    // Step 2: BLE permissions for API 31+ (requested together with location)
    if (apiLevel >= 31) {
      foregroundPerms.push(PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN);
      foregroundPerms.push(PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT);
    }

    const granted = await PermissionsAndroid.requestMultiple(foregroundPerms);

    result.fineLocation =
      granted[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION] ===
      PermissionsAndroid.RESULTS.GRANTED;

    const bleGranted =
      apiLevel < 31 ||
      (granted[PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN] ===
        PermissionsAndroid.RESULTS.GRANTED &&
        granted[PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT] ===
          PermissionsAndroid.RESULTS.GRANTED);
    result.bluetooth = bleGranted;

    // Step 3: Background location must be requested AFTER foreground is granted
    // Requesting simultaneously causes silent rejection on Android 11+
    if (result.fineLocation) {
      const bgGranted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.ACCESS_BACKGROUND_LOCATION,
        {
          title: 'Background Location Required',
          message:
            'To navigate when the screen is off, background location access is required.',
          buttonPositive: 'Allow',
        },
      );
      result.backgroundLocation =
        bgGranted === PermissionsAndroid.RESULTS.GRANTED;
      if (!result.backgroundLocation) {
        console.warn(
          'Background location denied — navigation will pause when screen is off.',
        );
      }
    }

    // Critical = fine location. BLE and background are degraded-mode only.
    result.allCriticalGranted = result.fineLocation;
    return result;
  } catch (err) {
    console.error('Permission request failed:', err);
    return result;
  }
}
