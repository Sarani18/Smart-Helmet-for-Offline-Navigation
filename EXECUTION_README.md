# Smart Helmet: End-to-End Execution Guide

This document details how to run the **Parallel Integration** of the Navigation, Computer Vision (CV), and Dead Reckoning (DR) modules. 

The integration simulates what happens when a rider enters an area with no internet connectivity. The central Navigation node detects the outage and broadcasts a `START` command, triggering the localized sub-systems (CV on port 8001 and DR on port 8002) to awaken, process data locally in parallel, and aggressively feed routing context back to the Navigation coordinator on port 8000.

---

## 🏗 Subsystem Architecture & Port Allocations

To operate the full parallel simulation natively on your machine, three separate FastAPI microservices must be running on different ports:

| Subsystem | Port  | Directory | Description |
|-----------|-------|-----------|-------------|
| **Navigation** | `8000` | `navigation/` | Orchestrator. Coordinates states, holds the offline map, and aggregates localization events to recalculate directions. |
| **Vision (CV)** | `8001` | `localization/CV/` | Awaits `START` commands. Once active, reads frames, executes PyTorch MobileNet+CNN ensemble segmentation natively in python, and posts `TURN` / `LANDMARK` events back to `8000`. |
| **Dead Reckoning (DR)** | `8002` | `localization/DR/` | Awaits `START` commands. Once active, processes IMU sensor streams from the Android companion app and routes stable coordinates to `8000`. |

---

## 🚀 Scenario 1: Automated End-to-End Simulation

A Python script is included at the root of the project to automatically spin up all three subsystems, mock an offline emergency to kickstart them, and monitor their parallel outputs.

### Running the Test
Simply run the following command from the root of the repository:

```bash
python3 test_e2e_integration.py
```

### What Happens:
1. **Bootstrapping**: Subprocesses spawn `uvicorn` instances for ports 8000, 8001, and 8002.
2. **Model Loading**: The CV script loads its `models/best.pth` and `models/scene_classifier.pth` weights tightly into memory immediately. The simulation pauses for 10 seconds to allow everything to boot cleanly.
3. **Trigger Offline Pivot**: The script POSTs `{ "network_available": false }` to the Navigation API. Navigation natively broadcasts `action: START` to ports 8001 and 8002.
4. **Observation**: 
   - **CV** opens the `localization/CV/sample_drive.mp4` video (from `intel-iot-devkit`), analyzes geometry and classifications via the CNN ensemble, and fires formatted `visual-event` API routes to Port 8000 natively.
   - **DR** engages and silently monitors its `POST` ingestion queue awaiting Android sensor stream ticks.
5. **Clean Exit**: The script observes outputs for 15 seconds, terminates all three child processes securely, and exits.

---

## 🛠 Scenario 2: Manual End-to-End Execution

If you wish to keep the servers running indefinitely to test with the Android companion app, you can start the components manually in separate terminal windows.

### Terminal 1: Navigation Coordinator
```bash
python3 -m uvicorn navigation.server:app --port 8000
```

### Terminal 2: Computer Vision (CV)
```bash
cd localization/CV
python3 -m uvicorn main:app --port 8001
```
*(You will see model loading outputs here. It will then idle at 0% CPU).*

### Terminal 3: Dead Reckoning (DR)
```bash
cd localization/DR
python3 -m uvicorn main:app --port 8002
```

### Step 4: Fire the Trigger
Simulate the App losing service by sending this payload to `8000`. You can do this using cURL:

```bash
curl -X POST http://localhost:8000/api/navigation/connectivity/status \
     -H "Content-Type: application/json" \
     -d '{
           "session_id": "manual_test_run",
           "ts_ms": 1773571300000,
           "network_available": false,
           "internet_reachable": false
         }'
```

Watch the Vision window; it will instantly register `"CV Engine STARTED (Reason: network_offline)"` and will begin spooling frame analyses!

### Step 5: Stop the Trigger
To gracefully stop computation and switch back to online GPS tracking, send the exact same webhook, but with `true` payloads.

```bash
curl -X POST http://localhost:8000/api/navigation/connectivity/status \
     -H "Content-Type: application/json" \
     -d '{
           "session_id": "manual_test_run",
           "ts_ms": 1773571300000,
           "network_available": true,
           "internet_reachable": true
         }'
```
