# Dead Reckoning (DR) Module

**Owner:** Jinesh Nanal  
**Port:** `8002` (Vision runs on `8001`, Navigation on `8000`)

---

## Purpose

This module **predicts the rider's position in real time** when GPS signal is lost (tunnels, flyovers, dense urban areas). It receives live sensor data from the Android phone's sensors via HTTP and applies dead-reckoning algorithms to maintain approximate positional awareness.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Android App (Phone)                        │
│                                                              │
│  SensorManager          LocationManager                      │
│  ├── Accelerometer      ├── GPS Fix → /gps-anchor            │
│  ├── Gyroscope          └── GPS Speed → sensor batch         │
│  ├── Magnetometer                                            │
│  ├── Step Counter                                            │
│  └── Rotation Vector                                         │
│         │                                                    │
│         └── Batch at 5-10 Hz → POST /sensor-data             │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│              Dead Reckoning Service (Port 8002)               │
│                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐   │
│  │ Sensor Fusion│──▶│  Heading     │──▶│   Position      │   │
│  │ Complementary│   │  Smoother   │   │   Integration   │   │
│  │ Filter       │   │ (circular   │   │ lat += v·dt·cos │   │
│  │ (α=0.98)    │   │  avg + spike│   │ lon += v·dt·sin │   │
│  │             │   │  rejection) │   │                 │   │
│  └─────────────┘   └─────────────┘   └──────┬──────────┘   │
│                                              │              │
│                                              ▼              │
│                                    DR Event Emitter         │
│                                    → Navigation API         │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
          POST /api/navigation/localization/dead-reckoning-event
```

---

## DR Algorithm — Step by Step

### 1. Sensor Fusion (Orientation)
- **Accelerometer** provides tilt (roll/pitch) from gravity direction
- **Gyroscope** provides angular velocity — integrated over time for orientation
- **Complementary filter** blends both: `new_angle = 0.98 × gyro_angle + 0.02 × accel_angle`
- This gives a **stable, drift-corrected orientation** (roll, pitch, yaw)

### 2. Heading Estimation
- Raw yaw from sensor fusion is smoothed using a **circular moving average** (window=10)
- **Spike rejection**: jumps > 90° between consecutive readings are discarded
- **Magnetometer correction**: if available, slowly blends compass heading into yaw (5% weight)
- **Rotation vector override**: if Android's fused rotation vector is available, it is trusted with 80% weight

### 3. Speed Source (Priority Order)
1. **GPS Speed** — most accurate, used whenever GPS was recently available
2. **Step Counter** — for walking scenarios when GPS speed = 0
3. **Linear Acceleration Integration** — fallback, heavily damped (noisy)

### 4. Position Prediction (Dead Reckoning Core)
```
distance = speed_mps × dt
Δlat = distance × cos(heading) / 111320
Δlon = distance × sin(heading) / (111320 × cos(lat))
uncertainty += distance × 0.02    (2% drift rate)
```

### 5. GPS Anchor Recovery
When GPS returns, `anchor()` resets position + uncertainty to zero.
The DR engine continues in the background but defers to GPS.

---

## API Endpoints

### 1. Receive Sensor Data Batch
**`POST /api/localization/dr/sensor-data`**

Called by the Android app at 5-10 Hz with batched sensor readings.

```json
{
  "session_id": "ride_2026_04_13_01",
  "ts_ms": 1773571234567,
  "readings": [
    {
      "sensor_type": "ACCELEROMETER",
      "values": [0.1, 0.2, 9.78],
      "timestamp_ns": 1234567890000,
      "accuracy": 3
    },
    {
      "sensor_type": "GYROSCOPE",
      "values": [0.01, -0.02, 0.5],
      "timestamp_ns": 1234567900000,
      "accuracy": 3
    }
  ]
}
```

**Supported sensor types:**
| Sensor Type | Android Constant | Values |
|-------------|-----------------|--------|
| `ACCELEROMETER` | `TYPE_ACCELEROMETER` | `[ax, ay, az]` m/s² |
| `GYROSCOPE` | `TYPE_GYROSCOPE` | `[gx, gy, gz]` rad/s |
| `MAGNETOMETER` | `TYPE_MAGNETIC_FIELD` | `[mx, my, mz]` μT |
| `LINEAR_ACCELERATION` | `TYPE_LINEAR_ACCELERATION` | `[ax, ay, az]` m/s² |
| `ROTATION_VECTOR` | `TYPE_ROTATION_VECTOR` | `[qx, qy, qz, qw]` |
| `STEP_COUNTER` | `TYPE_STEP_COUNTER` | `[cumulative_steps]` |
| `GPS_SPEED` | LocationManager | `[speed_mps]` |

---

### 2. GPS Anchor
**`POST /api/localization/dr/gps-anchor`**

Called whenever a GPS fix is obtained. Resets DR position and uncertainty.

```json
{
  "session_id": "ride_2026_04_13_01",
  "ts_ms": 1773571200000,
  "latitude": 19.0760,
  "longitude": 72.8777,
  "accuracy_m": 5.0,
  "speed_mps": 12.5,
  "bearing_deg": 85.0
}
```

---

### 3. Control (START / STOP)
**`POST /api/localization/dr/control`**

Triggered by Navigation module on network status transitions.

```json
{
  "session_id": "ride_2026_04_13_01",
  "ts_ms": 1773571300000,
  "action": "START",
  "reason": "network_offline"
}
```

---

### 4. Status
**`GET /api/localization/dr/status`**

Returns the current state of the DR engine.

```json
{
  "running": true,
  "latitude": 19.0762,
  "longitude": 72.8780,
  "heading_deg": 86.3,
  "speed_mps": 12.1,
  "uncertainty_m": 4.8,
  "step_count": 0,
  "last_update_ts_ms": 1773571234567
}
```

---

## Outbound: DR Events to Navigation

When the engine produces a position estimate, it POSTs to:

**`POST /api/navigation/localization/dead-reckoning-event`**

```json
{
  "session_id": "ride_2026_04_13_01",
  "event_id": "dr_1773571234567",
  "ts_ms": 1773571234567,
  "event_type": "DEAD_RECKONING",
  "confidence": 0.92,
  "payload": {
    "latitude": 19.0762,
    "longitude": 72.8780,
    "heading_deg": 86.3,
    "speed_mps": 12.1,
    "uncertainty_m": 4.8
  },
  "heading_deg": 86.3,
  "speed_mps": 12.1
}
```

Confidence decays linearly:  `confidence = 1.0 - (uncertainty_m / 500.0)`

---

## Running the Module

```bash
cd localization/DR
pip install -r requirements.txt
uvicorn main:app --port 8002
```

Or directly:
```bash
python main.py
```

---

## Running Tests

```bash
cd localization/DR
python -m unittest test_dead_reckoning -v
```

---

## Dependencies

- `fastapi` — HTTP framework
- `uvicorn` — ASGI server
- `httpx` — async HTTP client (for Navigation API calls)
- `pydantic` — request/response validation
- Python standard library: `math`, `collections`, `time`, `logging`

---

## Testing with Real Phone Sensors

You can test the DR module with your actual Android phone's accelerometer/gyroscope:

```bash
# 1. Start the DR server
cd localization/DR
python3 main.py

# 2. Open on phone (same WiFi): https://<your-mac-ip>:8002/phone
# 3. Accept the self-signed certificate warning
# 4. Tap "Enable Sensors" → "Start" → walk around
```

> **Note:** Generate SSL certs first (required for phone sensor access):
> ```bash
> openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
> ```

---

## Ride Simulator (No Phone Needed)

```bash
python3 ride_simulator.py
```

Simulates a full bike ride with realistic sensor data and shows DR accuracy vs actual GPS position.

---

## Integration with Other Modules

### For Navigation Module (Sanskruti)
The DR module **automatically POSTs position updates** to:
```
POST http://localhost:8000/api/navigation/localization/dead-reckoning-event
```
No extra setup needed — just start both servers on the same machine.

### For Navigation to control DR
Send START/STOP commands when GPS is lost/restored:
```
POST http://localhost:8002/api/localization/dr/control
{ "session_id": "...", "ts_ms": ..., "action": "START", "reason": "gps_lost" }
```

### Port Allocation
| Module | Port | Owner |
|--------|------|-------|
| Navigation | 8000 | Sanskruti |
| Vision/CV | 8001 | Vijit |
| Dead Reckoning | 8002 | Jinesh |

