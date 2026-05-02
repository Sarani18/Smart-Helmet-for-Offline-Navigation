# Smart Helmet Navigation - Demo Simulation Guide

This guide provides the exact commands needed to run the fully integrated, high-frequency offline navigation simulation on your local machine.

The demo consists of 4 components that must be run simultaneously in separate terminal windows.

---

### Terminal 1: Navigation API Server
This is the core server that hosts the Google Maps UI, handles state management, and receives events from the CV and DR modules.

```bash
# From the project root directory
python3 -m uvicorn navigation.server:app --port 8000
```
*Wait for `Uvicorn running on http://127.0.0.1:8000` before opening the browser.*

---

### Terminal 2: Computer Vision (CV) Inference Service
This service loops a static image (`real_road_test.png`) through the LRASPP and CNN models, simulating a live dashcam feed and firing `TURN` and `LANDMARK` events.

```bash
# Navigate to the CV module
cd localization/CV

# Start the CV server
python3 main.py
```
*It will load the PyTorch models and bind to port `8001`.*

---

### Terminal 3: Dead Reckoning (DR) Service
This service handles sensor ingestion. During the simulation, it sits idle on port `8002` (while `simulation_driver.py` directly handles the marker math), but it MUST be running for the system architecture to be complete.

```bash
# Navigate to the DR module
cd localization/DR

# Start the DR server (uses HTTPS for real mobile sensor streaming)
python3 main.py
```

---

### Terminal 4: The Simulation Driver
This script drives the demo! It computes the route using OSRM, interpolates coordinates at a high frequency (12.5 updates/sec), and pushes the `lat/lon` data to the Navigation server so the arrow glides smoothly on the map.

```bash
# From the project root directory
python3 simulation_driver.py
```

---

## 🚀 Viewing the Demo
Once all 4 terminals are running, open your web browser (Chrome recommended) and go to:
**[http://localhost:8000/demo/index.html](http://localhost:8000/demo/index.html)**

- Click **"Start Navigation"** to see the route drawn.
- Watch the driver script push the arrow seamlessly along the route.
- Note the **Fusion Console** showing CV detection events (Turns/Junctions) being fired live!
