# Smart Helmet Mobile App - Technical System Document

## 1. Purpose

The mobile app is the rider-facing navigation and localization controller for
the Smart Helmet system. It provides offline-aware navigation, detects GPS loss,
activates fallback localization, and updates the map/UI using the best available
position source.

The complete intended system combines:

- GPS localization
- Dead Reckoning using phone IMU sensors
- Computer Vision using helmet camera frames
- Navigation Control System logic
- Offline map and route handling
- Helmet communication over Bluetooth

## 2. High-Level Architecture

```text
User
  |
  v
Mobile App UI
  |
  v
Navigation Control System (NCS)
  |
  |-- GPS Module
  |-- Dead Reckoning Module
  |-- Computer Vision Module
  |-- Navigation Engine
  |-- Map/UI Update Layer
  |
  v
Helmet / ESP32 / Camera / Display
```

The NCS is the decision-making layer. It decides which localization source is
trusted at any moment and sends the final position/instruction to the UI.

## 3. Mobile App Tech Stack

### App Framework

- **React Native**
  - Used for building the Android mobile app.
  - Provides cross-platform UI and native Android integration.

- **TypeScript**
  - Used for service logic, module interfaces, and safer data flow.

### Native Android Integration

- **Kotlin Native Modules**
  - Used for Android sensor access and Python bridge integration.

- Native modules:
  - `SmartHelmetSensorModule`
  - `SmartHelmetPythonModule`
  - `SmartHelmetPythonPackage`

### Python Integration

- **Chaquopy**
  - Bundles Python modules inside the Android app.
  - Allows React Native/Kotlin to call Python localization logic.

- Python modules used:
  - `dead_reckoning.py`
  - `sensor_fusion.py`
  - `heading_tracker.py`
  - `bridge.py`

### Map and Route

- **MapLibre inside React Native WebView**
  - Used for map rendering.
  - Supports zoom, pan, rider marker, route polyline, and destination markers.

- **OpenStreetMap tiles**
  - Used for map display.

- **OSRM**
  - Used for route generation.

- **Nominatim**
  - Used for geocoding place names to coordinates.

### Storage

- **react-native-fs**
  - Used for route and map tile caching.
  - Enables faster repeat route loading and offline map behavior.

### Bluetooth

- **react-native-ble-plx**
  - Used for communication with helmet hardware.
  - Intended to exchange navigation status, camera-related packets, and helmet
    module status.

## 4. Android Permissions and Their Purpose

### Location Permissions

Used by the GPS module.

- `ACCESS_FINE_LOCATION`
- `ACCESS_COARSE_LOCATION`
- `ACCESS_BACKGROUND_LOCATION`

Purpose:

- Read current GPS location.
- Track rider position during navigation.
- Detect GPS availability/loss.

### Bluetooth Permissions

Used by helmet communication.

Legacy Android:

- `BLUETOOTH`
- `BLUETOOTH_ADMIN`

Android 12+:

- `BLUETOOTH_SCAN`
- `BLUETOOTH_CONNECT`

Purpose:

- Connect to the helmet/ESP32 module.
- Send/receive navigation and module state packets.
- Receive camera/image packet stream in the intended CV flow.

### Sensor Permission

- `HIGH_SAMPLING_RATE_SENSORS`

Purpose:

- Allows higher frequency sensor sampling.
- Helps IMU-based DR by reducing sensor batching/throttling.

Note:

- Accelerometer and gyroscope do not require a runtime user popup like GPS.

### Network Permissions

- `INTERNET`
- `ACCESS_NETWORK_STATE`

Purpose:

- Fetch route/geocoding when online.
- Download map tiles.
- Check online/offline state.

## 5. Main App Modules

### Home Screen

Responsibilities:

- Takes origin and destination.
- Requests required permissions.
- Gets current GPS if user chooses current location.
- Fetches or loads cached route.
- Starts navigation.

### Navigation Screen

Responsibilities:

- Displays map and route.
- Displays next instruction.
- Shows GPS/DR/unknown mode.
- Shows DR sensor values only when fallback is active.
- Sends map updates to the MapLibre WebView.
- Provides stop/recenter controls.

### GPS Service

Responsibilities:

- Starts GPS watch.
- Reads last known/cached GPS quickly.
- Tracks latest GPS fix.
- Marks GPS unavailable when stale or permission/location fails.

### Sensor Service

Responsibilities:

- Starts/stops accelerometer and gyroscope.
- Uses native Android `SensorManager` where possible.
- Falls back to `react-native-sensors`.
- Smooths noisy sensor readings.
- Provides latest IMU sample to DR/NCS.

### Dead Reckoning Service

Responsibilities:

- Bridges to Python DR logic.
- Maintains anchor position.
- Updates DR distance travelled.
- Exposes DR distance to NCS.

### Heading Service

Responsibilities:

- Uses gyroscope and accelerometer input.
- Estimates/smooths heading.
- Supports DR calculations.

### Navigation Engine

Responsibilities:

- Tracks progress on the route.
- Generates next turn instruction.
- Detects off-route condition.
- Detects destination arrival.

### Position Coordinator / NCS

Responsibilities:

- Central source-selection logic.
- Chooses GPS when available.
- Activates DR and CV when GPS is lost.
- Fuses localization updates.
- Sends final coordinates to UI.

## 6. Dead Reckoning Module

### One-Line Explanation

Dead Reckoning estimates rider movement after GPS loss using IMU sensor data,
mainly distance travelled, so NCS can continue updating position on the route.

### Sensors Used

#### Accelerometer

Measures acceleration along X, Y, and Z axes.

Important detail:

- Even when the phone is still, it reads about `9.8 m/s²` on one axis because it
  also measures gravity.

Significance:

- Detects motion/vibration.
- Helps identify whether the rider is moving.
- Helps separate stillness from movement.
- Helps sensor fusion understand phone orientation relative to gravity.

#### Gyroscope

Measures angular velocity around X, Y, and Z axes.

Significance:

- Detects rotation and turning.
- Helps estimate heading changes.
- Helps understand rider/phone orientation changes when GPS is unavailable.

### DR Flow

```text
Accelerometer + Gyroscope
        |
        v
Sensor Service
        |
        v
Heading Service / Sensor Fusion
        |
        v
Dead Reckoning Service
        |
        v
Distance Travelled
        |
        v
NCS projects distance on route
        |
        v
Map position update
```

### Why Route Projection Is Used

Raw DR heading can drift due to sensor noise. If coordinates are projected only
from heading, the rider marker may move in random directions.

To avoid that:

- DR calculates distance travelled.
- NCS applies that distance to the known route polyline.
- The rider marker moves forward on the planned route.

This is more stable for short GPS-loss periods.

### DR Limitations

- Sensor errors accumulate over time.
- Phone vibration can create false motion.
- Heading can drift.
- DR cannot independently verify if rider left the route.
- It is best for short GPS outages.
- It needs GPS or Vision correction for long-term accuracy.

## 7. Computer Vision Module

### Purpose

The CV module provides visual localization support when GPS is unavailable.
It analyzes camera frames from the helmet camera and sends visual detections to
NCS.

### Intended Hardware Flow

```text
Helmet Camera
    |
    v
ESP32 / Helmet Controller
    |
    v
Bluetooth packet stream
    |
    v
Mobile App CV Module
    |
    v
Visual Events / Position Hints
    |
    v
NCS
```

### CV Tech Used

- Python-based CV pipeline
- Semantic segmentation
- Scene analysis
- Road direction detection
- Junction/turn detection

Existing CV logic is based on:

- `localization/CV/scene_analyzer.py`
- `localization/CV/predict.py`
- PyTorch / TorchVision models
- OpenCV image processing

### CV Input

In the intended product flow, CV receives:

- Camera frames from helmet camera
- Navigation hint from NCS
- Current approximate route position
- Expected upcoming turn

### CV Output

The CV module can output:

- Turn event
  - Example: `LEFT`, `RIGHT`, `SLIGHT_LEFT`, `STRAIGHT`
- Landmark event
  - Example: junction, roundabout, traffic-light-like point
- Confidence score
- Optional route-position hint

### CV Status Handling

CV does not have to be available for the app to work.

NCS treats CV as optional:

- If CV works: use it to improve/correct fallback localization.
- If CV is degraded: use it cautiously.
- If CV is unavailable: continue with DR.

This prevents navigation failure when camera frames, model inference, or visual
confidence are not available.

## 8. NCS Fallback Flow

### Normal GPS Mode

```text
GPS available
    |
    v
NCS trusts GPS
    |
    v
Map updates using GPS coordinates
    |
    v
DR/CV hidden or idle
```

### GPS Lost Mode

```text
GPS lost
    |
    v
NCS starts fallback
    |
    |-- Start DR
    |-- Start sensors
    |-- Start CV module
    |
    v
DR sends distance travelled
CV sends visual events if available
    |
    v
NCS fuses fallback data
    |
    v
NCS sends updated coordinates to UI
```

### GPS Restored Mode

```text
GPS restored
    |
    v
NCS stops fallback
    |
    |-- Stop DR display
    |-- Stop sensor display
    |-- Stop CV processing
    |
    v
Map returns to GPS updates
```

## 9. Complete App Flow

1. User enters source and destination.
2. App requests permissions.
3. Route is loaded from cache or fetched from OSRM.
4. Navigation screen starts.
5. GPS provides live location.
6. Navigation engine generates instructions.
7. Map shows route and rider marker.
8. If GPS is lost:
   - NCS detects stale/lost GPS.
   - NCS starts DR.
   - NCS starts CV.
   - DR sends distance travelled.
   - CV sends visual events if available.
   - NCS updates rider position on route.
9. If GPS returns:
   - NCS returns to GPS mode.
   - DR/CV fallback UI is hidden.

## 10. Turn Instruction Flow

The navigation engine does not always say the next turn immediately.

Behavior:

- If next turn is more than 100 m away:
  - `Continue straight`
- If next turn is between 100 m and 40 m:
  - `Take left in 100 m`
  - `Take right in 50 m`
- If next turn is less than 40 m away:
  - `Take left`
  - `Take right`
- After the maneuver point is passed:
  - Old turn instruction is cleared.
  - App returns to `Continue straight` until the next turn is close.

## 11. Reliability Strategy

The system is designed to degrade gracefully.

Priority order:

1. GPS
2. GPS + cached route
3. DR + CV
4. DR only
5. Unknown/no signal state

Failure handling:

- GPS unavailable: fallback starts.
- DR noisy: smoothing/deadband reduces false movement.
- CV unavailable: NCS continues with DR.
- Network unavailable: cached route/tiles are used when available.
- BLE unavailable: mobile navigation still continues.

## 12. Presentation Summary

- The mobile app is the central controller for rider navigation.
- GPS is primary; DR and CV are fallback modules.
- DR uses accelerometer and gyroscope data to estimate movement.
- NCS uses DR distance on the known route to avoid random marker drift.
- CV uses helmet camera frames to detect road/turn/landmark context.
- CV output is optional and confidence-based.
- NCS fuses available sources and sends only final coordinates to the UI.
- The app is robust: failure of one module does not stop navigation.
