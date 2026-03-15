# Smart Helmet for Offline Navigation

> **An Intelligent, Physical-AI–Enabled Wearable System for Navigation, Situational Awareness, and Rider Safety**

Two-wheeler riders increasingly depend on digital navigation yet most existing solutions assume uninterrupted GPS and network connectivity. This project builds a **smart helmet** that works even when connectivity is lost — inside tunnels, hilly terrain, dense urban corridors, or remote highways — by fusing onboard motion sensors with offline maps.

---

## Project Objectives

1. Provide navigation assistance independent of continuous GPS and network connectivity.
2. Implement offline localization using sensor fusion, dead-reckoning, and map-based correction.
3. Enhance rider safety through real-time situational awareness and HUD-based visualization.
4. Detect accidents and abnormal motion patterns and trigger timely emergency responses.
5. Deliver a modular, low-cost, and scalable Physical AI system ready for real-world deployment.

---

## Repository Structure

```
Smart-Helmet-for-Offline-Navigation/
│
├── navigation/                  # Route processing & offline map management
│   ├── route_processor.py
│   ├── map_manager.py
│   ├── turn_extractor.py
│   ├── offline_cache.py
│   ├── tests/
│   └── README.md
│
├── localization/                # Sensor fusion, dead reckoning & map matching
│   ├── sensor_fusion.py
│   ├── dead_reckoning.py
│   ├── heading_tracker.py
│   ├── map_matching.py
│   ├── tests/
│   └── README.md
│
├── embedded/                    # Helmet firmware & mobile app interface
│   ├── bluetooth_comm.py
│   ├── led_controller.py
│   ├── instruction_parser.py
│   ├── app_interface/
│   │   ├── ui_manager.py
│   │   └── device_manager.py
│   └── README.md
│
├── communication/               # Inter-device protocol & synchronisation
│   ├── protocol.py
│   ├── packet_handler.py
│   ├── sync_manager.py
│   ├── tests/
│   └── README.md
│
├── hardware/                    # Hardware integration (placeholder)
│   ├── hardware_interface.py
│   └── README.md
│
└── app/                         # Application entry-point
    ├── main.py
    └── README.md
```

---

## Module Overview

### 1. `navigation/` — Navigation & Route Intelligence
**Owner: Sanskruti Rajesh Ninawe**

This module is the brain of the navigation system. It converts raw route data from online map services (or local storage) into clean, step-by-step riding instructions. Even without internet, it keeps the rider on the right path by using cached routes.

| File | What it does |
|------|-------------|
| `route_processor.py` | Loads, validates, and steps through the active route |
| `map_manager.py` | Loads offline road-network data; finds nearby roads |
| `turn_extractor.py` | Decodes encoded polylines; classifies turns (left/right/U-turn) |
| `offline_cache.py` | Saves and loads full route data to/from local disk |

**Key capabilities:**
- Parses Google/OSRM route API responses into structured `Route` and `RouteStep` objects.
- Decodes Google Polyline Algorithm Format (encoded polyline strings) into GPS coordinates.
- Classifies bearing changes into human-readable manoeuvres: *"Turn slightly right"*, *"Turn sharply left"*, *"Make a U-turn"*.
- Persists decoded routes as JSON files so the rider can navigate offline without any re-planning.
- Revalidates the route corridor as the rider moves; flags when a re-route is needed.

---

### 2. `localization/` — Sensor Fusion & Localization
**Owner: Vijit Ayush Pandey**

This module answers "where is the rider right now?" even when GPS has dropped out. It reads the phone's built-in motion sensors and continuously estimates position and heading using mathematical filtering.

| File | What it does |
|------|-------------|
| `sensor_fusion.py` | Fuses accelerometer + gyroscope into stable orientation (roll/pitch/yaw) |
| `dead_reckoning.py` | Projects position forward using speed + heading when GPS is unavailable |
| `heading_tracker.py` | Smooths the raw yaw reading; rejects sensor noise spikes |
| `map_matching.py` | Snaps dead-reckoned position onto the nearest road segment |

**Key capabilities:**
- **Complementary filter** — combines high-frequency gyroscope integration with drift-free accelerometer tilt estimates to produce a smooth, accurate orientation.
- **Dead reckoning** — when GPS signal is lost, the module integrates speed × time in the current heading direction to estimate displacement, with a growing uncertainty radius to communicate confidence.
- **Map matching** — projects the estimated position onto the closest road in the offline map, significantly reducing accumulated drift.
- **Crash detection** — checks if roll > 75° or pitch > 60°, which indicates a potential fall, and raises an alert.

---

### 3. `embedded/` — Embedded Systems & Application Interface
**Owner: Priyal Jain**

This module has two closely related jobs:
1. Controls the *physical hardware* on the helmet (LEDs, Bluetooth radio, instruction decoder).
2. Provides the *mobile app's UI layer* (navigation display, device pairing management).

| File | What it does |
|------|-------------|
| `bluetooth_comm.py` | BLE connection lifecycle: scan, connect, send, receive, reconnect |
| `led_controller.py` | Maps navigation events to LED patterns (blink left, solid red, etc.) |
| `instruction_parser.py` | Decodes 5-byte binary packets into typed instruction objects |
| `app_interface/ui_manager.py` | Maintains the navigation display state (instruction, speed, GPS status) |
| `app_interface/device_manager.py` | Helmet discovery, pairing, and automatic reconnection |

**Key capabilities:**
- Compact **5-byte packet format** (code + 2-byte distance + 2 pad bytes) keeps BLE bandwidth usage minimal.
- LED patterns give the rider at-a-glance feedback without looking at a screen: left arrow blinks left LEDs, right arrow blinks right LEDs, crash triggers rapid red flash.
- `UIManager.update_instruction()` formats distances into *"In 200 m, turn right"* style strings.
- `DeviceManager` remembers the last-paired helmet address for instant reconnect on app restart.

---

### 4. `communication/` — Communication Protocol, Integration & Performance
**Owner: Jinesh Nanal**

This module is the "nervous system" connecting the phone app and the helmet. It defines the exact binary format for every message, ensures reliable delivery over a lossy Bluetooth link, and keeps both devices in sync.

| File | What it does |
|------|-------------|
| `protocol.py` | 8-byte packet format: encode, decode, XOR checksum validation |
| `packet_handler.py` | Send/receive queues, ACK tracking, duplicate detection, retry logic |
| `sync_manager.py` | Heartbeat keep-alive, GPS mode-change notifications, link-health monitoring |

**Key capabilities:**
- **8-byte binary protocol** with magic byte (0xAB), type code, 2-byte sequence number, 3-byte payload, and XOR checksum.
- Rolling sequence numbers + ACK mechanism guarantee that critical packets (turn instructions, crash alerts) are not silently lost.
- Duplicate detection prevents the same packet from being processed twice after a retry.
- Heartbeat: if no reply within 6 seconds, the link is declared unhealthy and automatic reconnection is triggered.
- GPS status changes are immediately propagated to the helmet so the LED colour updates in real time.

**Packet types:**

| Code | Name | Direction | Meaning |
|------|------|-----------|---------|
| 0x01 | NAV_INSTRUCTION | App → Helmet | Turn instruction + distance |
| 0x02 | GPS_STATUS | App → Helmet | GPS active / lost |
| 0x03 | SPEED_UPDATE | App → Helmet | Current speed |
| 0x10 | IMU_DATA | Helmet → App | Raw sensor snapshot |
| 0x11 | BATTERY_LEVEL | Helmet → App | Battery % |
| 0x12 | ACK | Both | Acknowledgement |
| 0x20 | CRASH_EVENT | Both | Crash detected |
| 0x21 | SOS_CONFIRM | Both | SOS acknowledged |
| 0xFE | HEARTBEAT | Both | Link keep-alive |
| 0xFF | RESET | Both | Full system reset |

---

### 5. `hardware/` — Hardware Integration (Placeholder)
**Software-first phase — hardware implementation planned for next phase**

This module defines the *interface* that physical hardware drivers must satisfy, so all other software modules can be written and tested without real hardware. When hardware is integrated, only this module needs to be updated.

| Component | Role |
|-----------|------|
| IMU (e.g. MPU-6050) | Accelerometer + gyroscope → localization module |
| Camera (e.g. OV2640) | Environment monitoring, obstacle detection |
| HUD display (e.g. OLED) | Shows turn instructions and status |
| RGB LEDs | At-a-glance direction and alert feedback |
| MCU (e.g. ESP32 / RPi Zero 2W) | Runs firmware; bridges hardware to phone |
| Power management IC | Battery monitoring; safe shutdown |
| Local flash storage | Offline map tiles and event logs |

---

### 6. `app/` — Application Entry Point

`app/main.py` wires all modules together into a single `SmartHelmetApp` class. The lifecycle is:

1. `initialize()` — start hardware, register callbacks.
2. `start_navigation(route_data)` — load route, send first instruction to helmet.
3. `run()` / `tick()` — main loop: read sensors, update orientation, advance dead reckoning, sync state.
4. `shutdown()` — disconnect BLE, power down hardware.

---

## System Architecture (ISA-95–Inspired Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4 – Planning & Analytics                             │
│  Route planning, performance logging, field test reports    │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 – Operational Decision Making                      │
│  navigation/ + communication/ modules                       │
│  Route revalidation, GPS-mode switching, SOS triggering     │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 – Real-Time Perception                             │
│  localization/ + embedded/ modules                          │
│  Sensor fusion, dead reckoning, LED control, UI display     │
├─────────────────────────────────────────────────────────────┤
│  Layer 1 – Physical Sensing                                 │
│  hardware/ module (stub → real drivers in next phase)       │
│  IMU, Camera, HUD, LEDs, MCU, Battery, Storage             │
└─────────────────────────────────────────────────────────────┘
```

---

## Running the Tests

All modules include unit tests written with Python's built-in `unittest` library.
No external dependencies are required.

```bash
# Navigation module tests
python -m unittest discover -s navigation/tests -v

# Localization module tests
python -m unittest discover -s localization/tests -v

# Communication module tests
python -m unittest discover -s communication/tests -v
```

---

## Hardware & Software Requirements

### Software (Current Focus)
- Python 3.9+
- Standard library only (no external packages required for core modules)
- In production: `bleak` for cross-platform BLE communication

### Hardware (Next Phase)
- Helmet-mounted IMU (accelerometer + gyroscope)
- Forward-facing camera module
- Compact processing unit (ESP32 / Raspberry Pi Zero 2W)
- HUD / visor display
- RGB status LEDs
- Battery and power management system
- Local flash storage for offline maps

---

## Team

| Module | Owner |
|--------|-------|
| Navigation & Route Intelligence | Sanskruti Rajesh Ninawe |
| Sensor Fusion & Localization | Vijit Ayush Pandey |
| Embedded Systems & App Interface | Priyal Jain |
| Communication Protocol & Integration | Jinesh Nanal |
