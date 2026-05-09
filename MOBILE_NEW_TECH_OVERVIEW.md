# Smart Helmet Mobile App - Tech Overview

This document summarizes the Android/mobile stack, module permissions, and the
runtime flow used in `mobile_new`.

## 1. Main Tech Stack

- **React Native 0.73.9**
  - Main Android app framework.
  - Screens: `HomeScreen.tsx`, `NavigationScreen.tsx`.

- **TypeScript**
  - Used for app logic, service layers, and typed APIs between modules.

- **Android Kotlin Native Modules**
  - Used where JavaScript libraries were not enough.
  - Native modules:
    - `SmartHelmetPythonModule.kt`
    - `SmartHelmetSensorModule.kt`
    - `SmartHelmetPythonPackage.kt`

- **Chaquopy**
  - Bundles Python code into the Android app.
  - Used to call Python DR and sensor-fusion logic from React Native.
  - Python files bundled inside Android:
    - `dead_reckoning.py`
    - `sensor_fusion.py`
    - `heading_tracker.py`
    - `bridge.py`

- **MapLibre inside React Native WebView**
  - `react-native-webview` hosts the map UI.
  - `MapLibreView.tsx` sends map commands into the WebView.
  - Used for route polyline, rider marker, origin/destination markers, panning,
    zooming, and recenter behavior.

- **OSM / OSRM / Nominatim**
  - Nominatim: geocoding place names to coordinates.
  - OSRM: route fetch and route steps.
  - OpenStreetMap tiles: map display and tile caching.

- **FastAPI CV Bridge Server**
  - New optional server at `cv_bridge_server/`.
  - Receives packets from mobile NCS when GPS is lost.
  - Uses Google Street View imagery when configured.
  - Reuses teammate's `localization/CV/scene_analyzer.py`.
  - Returns `OK`, `DEGRADED`, or `UNAVAILABLE` so the app never crashes if CV fails.

## 2. Android Packages / SDK Modules Used

### Location / GPS

- Package:
  - `@react-native-community/geolocation`

- Files:
  - `src/services/gpsService.ts`
  - `src/screens/HomeScreen.tsx`

- Android permissions:
  - `android.permission.ACCESS_FINE_LOCATION`
  - `android.permission.ACCESS_COARSE_LOCATION`
  - `android.permission.ACCESS_BACKGROUND_LOCATION`

- Runtime permission API:
  - `PermissionsAndroid` from `react-native`
  - Implemented in `src/utils/permissions.ts`

- Purpose:
  - Fetch current location.
  - Watch GPS updates during navigation.
  - Detect stale/lost GPS and trigger fallback.

### IMU Sensors

- Primary implementation:
  - Custom native module `SmartHelmetSensorModule.kt`
  - Uses Android `SensorManager`.

- Fallback library:
  - `react-native-sensors`

- Files:
  - `android/app/src/main/java/com/smarthelmetnav/SmartHelmetSensorModule.kt`
  - `src/services/sensorService.ts`

- Android permission:
  - `android.permission.HIGH_SAMPLING_RATE_SENSORS`

- Notes:
  - Accelerometer and gyroscope are normal Android sensors.
  - They do not require a runtime prompt like location.
  - The high sampling permission helps prevent OS batching/throttling.

- Purpose:
  - Provide accelerometer and gyroscope values for DR fallback.
  - Show sensor values only when NCS activates fallback.

### Dead Reckoning / Python Bridge

- Android/Python bridge:
  - Chaquopy
  - Kotlin native module: `SmartHelmetPythonModule.kt`
  - TS wrapper: `pythonBridge.ts`

- Files:
  - `src/services/deadReckoningService.ts`
  - `src/services/headingService.ts`
  - `src/services/pythonBridge.ts`
  - `android/app/src/main/python/dead_reckoning.py`
  - `android/app/src/main/python/sensor_fusion.py`
  - `android/app/src/main/python/heading_tracker.py`

- Permissions:
  - No direct Android runtime permission.
  - Depends on sensor access from the IMU module.

- Purpose:
  - Maintain DR distance travelled.
  - Estimate heading from gyro/accelerometer.
  - In the final NCS flow, DR distance is used on the route instead of free-moving
    randomly by heading.

### Bluetooth / Helmet Communication

- Package:
  - `react-native-ble-plx`

- File:
  - `src/services/bleService.ts`

- Android permissions:
  - Legacy Android:
    - `android.permission.BLUETOOTH`
    - `android.permission.BLUETOOTH_ADMIN`
  - Android 12+:
    - `android.permission.BLUETOOTH_SCAN`
    - `android.permission.BLUETOOTH_CONNECT`

- Runtime permission API:
  - `PermissionsAndroid` in `src/utils/permissions.ts`

- Purpose:
  - Send navigation instruction/status to helmet hardware when BLE is connected.

### Networking / CV Server / Route Fetch

- APIs:
  - JS `fetch`
  - FastAPI server for CV bridge

- Files:
  - `src/services/routeService.ts`
  - `src/services/visionService.ts`
  - `cv_bridge_server/main.py`

- Android permissions:
  - `android.permission.INTERNET`
  - `android.permission.ACCESS_NETWORK_STATE`

- Android app setting:
  - `android:usesCleartextTraffic="true"`
  - Needed because the local CV server is `http://192.168.1.2:8010`.

- Purpose:
  - Fetch route from OSRM.
  - Fetch geocoding from Nominatim.
  - Contact optional CV bridge server when GPS is lost.

### Offline Maps / File Cache

- Package:
  - `react-native-fs`

- File:
  - `src/services/tileService.ts`

- Permissions:
  - No external storage permission is needed because app-private storage is used.

- Purpose:
  - Cache route JSON.
  - Cache downloaded OSM tiles for offline map display.

## 3. Permission Request Flow

- File: `src/utils/permissions.ts`

- On Android, app requests:
  - Fine location
  - Coarse location
  - Bluetooth scan/connect on Android 12+
  - Background location when foreground location is already granted

- Sensors do not show a user permission popup.
- Internet does not show a user permission popup.
- BLE and GPS are the main permissions the user sees.

## 4. Main Runtime Flow

### Start Navigation

1. User enters origin and destination in `HomeScreen`.
2. App requests permissions.
3. GPS is warmed up using `startGPS()`.
4. App checks cached route.
5. If route is not cached:
   - Geocode origin/destination with Nominatim.
   - Fetch route from OSRM.
6. Navigation screen loads route and starts services.

### GPS Mode

1. `gpsService` watches live GPS.
2. `positionCoordinator` receives GPS as the highest-priority source.
3. NCS anchors route progress using current GPS.
4. DR and sensor UI are hidden.
5. Vision server is not called.
6. Map updates smoothly using GPS coordinates.

### GPS Lost / Fallback Mode

1. `gpsService.isGPSAvailable()` becomes false when GPS is stale/lost.
2. `positionCoordinator` acts as NCS and enters fallback.
3. NCS starts:
   - DR path
   - IMU sensors
   - optional Vision server session
4. DR calculates distance travelled.
5. NCS projects that distance forward on the route polyline.
6. Map marker moves checkpoint-by-checkpoint on the planned route.
7. Sensor values and DR distance are shown at the top.
8. If Vision server works, NCS can fuse a Vision route-position hint.
9. If Vision fails, NCS keeps DR active and shows Vision unavailable/degraded.

### GPS Restored

1. NCS exits fallback.
2. Sensors are stopped.
3. Vision session is stopped.
4. DR distance display is hidden.
5. App returns to GPS-based position updates.

## 5. Dead Reckoning Flow

1. Android `SensorManager` collects accelerometer and gyroscope events.
2. `sensorService.ts` smooths sensor values and applies deadbands for noise.
3. `headingService.ts` sends IMU values to Python sensor-fusion code.
4. `deadReckoningService.ts` updates DR distance.
5. NCS does not blindly trust heading for map coordinates.
6. Instead, NCS uses DR distance to move forward on the existing route.
7. This prevents the map dot from moving randomly if sensor heading fluctuates.

## 6. NCS Logic

- File:
  - `src/services/positionCoordinator.ts`

- Priority:
  1. GPS
  2. DR + Vision, if GPS is lost
  3. DR only, if Vision unavailable
  4. UNKNOWN, if both GPS and DR are unavailable

- Important behavior:
  - GPS on: no DR/sensor panel.
  - GPS off: DR/sensor panel appears.
  - Vision works: status becomes active/degraded and can influence route progress.
  - Vision unavailable: app continues with DR.

## 7. Turn Instruction Logic

- File:
  - `src/services/navigationEngine.ts`

- Behavior:
  - If next turn is more than 100 m away: `Continue straight`
  - From 100 m to 40 m: `Take left in 100 m`, `Take right in 50 m`, etc.
  - Under 40 m: `Take left` / `Take right`
  - After passing the maneuver point, the instruction stops repeating the old turn.

## 8. CV Bridge Flow

- Folder:
  - `cv_bridge_server/`

- Run:
  ```powershell
  cd F:\p\sh
  $env:GOOGLE_STREET_VIEW_API_KEY="your_key"
  $env:CV_SERVER_MAX_GOOGLE_FRAMES="2"
  python -m uvicorn cv_bridge_server.main:app --host 0.0.0.0 --port 8010
  ```

- Phone talks to:
  - `http://192.168.1.2:8010`

- CV server receives:
  - session id
  - origin
  - destination
  - current coordinates
  - route polyline
  - DR distance
  - route progress

- CV server returns:
  - `OK`: Google Street View + CV worked
  - `DEGRADED`: fallback image or partial CV
  - `UNAVAILABLE`: Street View/model/server issue

- NCS behavior:
  - Uses Vision only if the response is healthy and confident.
  - Never stops navigation if Vision fails.

## 9. Presentation Summary

- GPS is the primary localization source.
- When GPS fails, NCS activates fallback localization.
- DR estimates distance travelled from phone sensors.
- NCS uses DR distance to move along the route, not random heading projection.
- Vision is optional and server-based.
- Vision can improve confidence/location, but app remains robust without it.
- The UI shows DR and sensor values only when fallback is active.
- The system degrades gracefully from GPS to DR + Vision to DR only.
