# 🚀 Smart Helmet - Execution Guide

Follow these steps in 4 separate terminal windows to run the full simulation.

### 1️⃣ Terminal 1: Navigation Server (Port 8000)
**Role:** Main API and HUD state manager.
```bash
python3 -m uvicorn navigation.server:app --port 8000
```

### 2️⃣ Terminal 2: Computer Vision Service (Port 8001)
**Role:** Processes road segmentation and turn detection.
```bash
cd localization/CV
python3 main.py
```

### 3️⃣ Terminal 3: Simulation Driver (GPS/DR)
**Role:** Sends simulated location data to the server.
1. Open Browser: [http://localhost:8000/simulator](http://localhost:8000/simulator)
2. Click the green **"START PUNE TRIP"** button.
3. Run the driver:
```bash
python3 simulation_driver.py
```

### 4️⃣ Terminal 4: CV Detailed Demo (Optional)
**Role:** See a detailed text-only stream of AI detections (no server required).
```bash
cd localization/CV
python3 test_cv_video.py
```

---

## 🛠️ Option 2: Standalone CV Terminal Demo
Use this mode if you **only** want to see the AI's "brain" and technical logs (Turns, Landmarks, Scenes) in your terminal without starting the Navigation Server or Browser.

1. **Open a Terminal**
2. **Run the demo:**
```bash
cd localization/CV
python3 test_cv_video.py
```

---
**💡 Tip:** If you see "Port already in use", you can kill the old processes:
* **Nav Server (8000):** `lsof -ti:8000 | xargs kill -9`
* **CV Service (8001):** `lsof -ti:8001 | xargs kill -9`

