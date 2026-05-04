# Smart Helmet for Offline Navigation — Setup Instructions

This guide covers everything a new team member needs to get the mobile app running from scratch.

---

## Table of Contents

1. [What This App Does](#what-this-app-does)
2. [Repository Structure](#repository-structure)
3. [Prerequisites](#prerequisites)
4. [Android Device Setup](#android-device-setup)
5. [Installing Dependencies](#installing-dependencies)
6. [Building and Running the App](#building-and-running-the-app)
7. [First-Time App Usage](#first-time-app-usage)
8. [Module Ownership](#module-ownership)
9. [Troubleshooting](#troubleshooting)

---

## What This App Does

This is a **fully standalone Android app** — no laptop server, no cloud backend required after the first route download.

- Enter an origin and destination on the home screen
- The app geocodes them (via Nominatim/OSM), fetches the route (via OSRM), and downloads all map tiles needed for the journey
- During navigation, it uses the phone's **GPS**, **accelerometer**, and **gyroscope**
- If GPS signal is lost (tunnel, dense area), it automatically switches to **Dead Reckoning** using the IMU sensors
- Navigation instructions are sent to the helmet over **BLE** if a helmet is connected
- Everything works **offline** once the route and tiles are downloaded on the first run

---

## Repository Structure

```
Smart-Helmet-for-Offline-Navigation/
│
├── mobile_new/          ← React Native Android app (THIS IS WHAT YOU BUILD)
│   ├── android/         ← Android native project
│   ├── src/
│   │   ├── screens/
│   │   │   ├── HomeScreen.tsx       ← Route input, geocoding, tile download
│   │   │   └── NavigationScreen.tsx ← Live map, instructions, sensor loop
│   │   ├── services/
│   │   │   ├── gpsService.ts           ← GPS watchPosition
│   │   │   ├── sensorService.ts        ← Accelerometer + gyroscope (10 Hz)
│   │   │   ├── headingService.ts       ← Complementary filter → heading degrees
│   │   │   ├── deadReckoningService.ts ← DR position estimation
│   │   │   ├── positionCoordinator.ts  ← GPS → DR fallback logic
│   │   │   ├── navigationEngine.ts     ← Step tracking, turn instructions
│   │   │   ├── routeService.ts         ← Nominatim geocoding, OSRM routing, cache
│   │   │   ├── tileService.ts          ← OSM tile download and cache
│   │   │   └── bleService.ts           ← BLE connection to helmet
│   │   └── utils/
│   │       └── permissions.ts          ← Android runtime permission requests
│   └── App.tsx          ← App root, screen state machine, foreground service
│
├── navigation/          ← Python route processing module (Sanskruti)
├── localization/        ← Python sensor fusion module (Vijit)
├── communication/       ← Python BLE protocol module (Jinesh)
├── embedded/            ← Python helmet interface module (Priyal)
├── hardware/            ← Hardware interface stubs
└── app/                 ← Python entry point
```

> **Note:** All work for the mobile app happens inside `mobile_new/`. The Python modules are the reference implementation — the TypeScript services in `mobile_new/src/services/` are ports of those algorithms.

---

## Prerequisites

Install all of these before proceeding. Versions matter — do not use newer or older versions without checking compatibility.

### 1. Node.js — v20.11.0 (LTS)

Download from https://nodejs.org/en/download (pick "LTS").

Verify:
```bash
node --version   # must print v20.x.x
npm --version
```

### 2. JDK 17

The build requires **JDK 17 exactly**. JDK 11 or JDK 21 will cause Gradle errors.

- **Windows:** Download from https://adoptium.net — pick "Temurin 17"
- After install, set `JAVA_HOME` to the JDK 17 folder and add `%JAVA_HOME%\bin` to PATH

Verify:
```bash
java -version   # must print "17.x.x"
```

### 3. Android Studio + Android SDK

Download Android Studio from https://developer.android.com/studio

During setup (or via SDK Manager inside Android Studio), install:
- **Android SDK Platform 34** (Android 14)
- **Android SDK Build-Tools 34.0.0**
- **Android Emulator** (optional — physical device recommended)

Set these environment variables:
```
ANDROID_HOME = C:\Users\<you>\AppData\Local\Android\Sdk   (Windows)
ANDROID_HOME = ~/Library/Android/sdk                       (Mac)
```

Add to PATH:
```
%ANDROID_HOME%\platform-tools
%ANDROID_HOME%\emulator
```

Verify:
```bash
adb version   # should print ADB version info
```

### 4. React Native CLI

```bash
npm install -g react-native@0.73.9
```

### 5. Python 3.9+ (for the Python backend modules)

Only needed if you're working on the Python navigation/localization modules (not required to build the Android app).

```bash
python --version   # 3.9 or higher
```

---

## Android Device Setup

Using a **physical Android device** is strongly recommended (sensors behave correctly; emulators often lack real IMU data).

1. On your Android phone, go to **Settings → About Phone**
2. Tap **Build Number** 7 times to enable Developer Options
3. Go to **Settings → Developer Options** and turn on **USB Debugging**
4. Connect phone to your laptop via USB
5. Accept the "Allow USB Debugging" prompt on the phone

Verify the device is detected:
```bash
adb devices   # should list your device, not just "List of devices attached"
```

---

## Installing Dependencies

### Step 1 — Clone the repo

```bash
git clone https://github.com/Sarani18/Smart-Helmet-for-Offline-Navigation.git
cd Smart-Helmet-for-Offline-Navigation
```

### Step 2 — Install Node packages

```bash
cd mobile_new
npm install
```

This installs all required packages listed in `package.json`:

| Package | Version | Purpose |
|---|---|---|
| `react-native` | 0.73.9 | Core framework (old arch, stable for BLE + sensors) |
| `react-native-sensors` | 7.3.0 | Accelerometer and gyroscope |
| `@react-native-community/geolocation` | 3.4.0 | GPS location |
| `react-native-ble-plx` | 3.2.0 | Bluetooth LE connection to helmet |
| `react-native-maps` | 1.10.0 | OSM map tile rendering |
| `react-native-fs` | 2.20.0 | Read/write map tiles and route cache to disk |
| `react-native-background-actions` | 4.0.0 | Foreground service to keep BLE alive when screen is off |
| `react-native-safe-area-context` | 4.8.x | Safe area insets for notch/status bar |

> **Important:** Do not upgrade `react-native` past `0.73.9` or enable `newArchEnabled=true`. The BLE and sensor libraries require the old bridge architecture. This is set in `android/gradle.properties`.

### Step 3 — No additional configuration needed

There are no API keys, no `.env` files, no server URLs to configure. The app uses:
- **Nominatim** (OSM) for geocoding — free, no key required
- **OSRM demo server** for routing — free, no key required
- **OSM tile server** for map tiles — free, no key required

---

## Building and Running the App

All commands below are run from inside the `mobile_new/` directory.

```bash
cd mobile_new
```

### Option A — Run directly on device (development)

Start Metro bundler in one terminal:
```bash
npm start
```

In a second terminal, build and deploy to connected device:
```bash
npm run android
```

The app will install and launch on your phone automatically.

### Option B — Build a release APK

```bash
cd android
./gradlew assembleRelease
```

On Windows use:
```bash
cd android
gradlew.bat assembleRelease
```

The APK will be at:
```
mobile_new/android/app/build/outputs/apk/release/app-release.apk
```

Install on a connected device:
```bash
adb install android/app/build/outputs/apk/release/app-release.apk
```

### TypeScript check (before building)

```bash
npx tsc --noEmit
```

This should produce no errors.

---

## First-Time App Usage

1. **Open the app** on your Android phone
2. **Grant all permissions** when prompted:
   - Location (Fine) — required for GPS
   - Location (Background) — required to continue navigating when screen is off
   - Nearby Devices / Bluetooth — required for helmet BLE connection
3. **Enter your origin and destination** (e.g. "VNIT Nagpur" and "Nagpur Airport")
4. Tap **Start Navigation**
5. The app will:
   - Geocode both locations (needs internet)
   - Fetch the route from OSRM (needs internet)
   - Download map tiles for the route area (needs internet, may take 30–60 seconds)
6. Once tiles are downloaded, the navigation screen opens
7. **After first use, the app works fully offline** — tiles and route are cached on-device

### Sensor behaviour during navigation

| Situation | What the app does |
|---|---|
| GPS working | Uses GPS directly, blue dot on map |
| GPS lost | Switches to Dead Reckoning (gyro + accel), yellow DR badge |
| GPS + IMU both unavailable | Shows "NO SIGNAL" red badge, map stays open, no crash |
| Helmet BLE connected | Sends 8-byte nav instructions to helmet in real-time |
| Helmet not found | Navigation continues normally, no error |

---

## Module Ownership

| Area | Owner | Files |
|---|---|---|
| Mobile App (RN) | Priyal Jain | `mobile_new/` |
| Navigation & Routing (Python) | Sanskruti Rajesh Ninawe | `navigation/` |
| Localization & Dead Reckoning (Python) | Vijit Ayush Pandey | `localization/` |
| Communication Protocol (Python) | Jinesh Nanal | `communication/` |

### Running the Python modules (for backend team)

```bash
# Navigation tests
python -m unittest discover -s navigation/tests -v

# Localization tests
python -m unittest discover -s localization/tests -v

# Communication tests
python -m unittest discover -s communication/tests -v
```

---

## Troubleshooting

### `JAVA_HOME is not set` or wrong JDK version
Set `JAVA_HOME` to JDK 17. On Windows, search "Environment Variables" in Start Menu.

### `adb devices` shows nothing
- Enable USB Debugging on the phone
- Try a different USB cable (data cable, not charge-only)
- Run `adb kill-server && adb start-server`

### Build error: `newArchEnabled` / `ViewManagerWithGeneratedInterface`
Make sure `android/gradle.properties` contains `newArchEnabled=false`. Do not upgrade packages without checking old-arch compatibility.

### Gradle build fails with `SDK location not found`
Create a file at `mobile_new/android/local.properties` with:
```
sdk.dir=C:\\Users\\<your-username>\\AppData\\Local\\Android\\Sdk
```
(Use your actual SDK path. On Mac: `/Users/<you>/Library/Android/sdk`)

### App crashes on sensor start
The `HIGH_SAMPLING_RATE_SENSORS` permission is declared in the manifest and is auto-granted. If sensors still crash, check that the phone has a physical gyroscope (most mid-range and above phones do).

### Map shows blank / grey tiles
The tiles are cached at `DocumentDirectoryPath/offline_tiles/`. On first use, internet is required to download them. After that, they load from disk. If you've changed the route, the new tiles will be downloaded automatically.

### Route fetch fails
The app uses the public OSRM demo server. If it is temporarily down, wait a few minutes and retry. The route is cached after the first successful fetch so subsequent offline launches work fine.

### BLE helmet not connecting
- Ensure the helmet device name is `SmartHelmet_BLE` or `NaviHelmet` (defined in `bleService.ts`)
- Grant Nearby Devices permission when prompted
- BLE failure is non-fatal — navigation works without the helmet
