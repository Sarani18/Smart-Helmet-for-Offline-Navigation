# Vision Module (Mock Pipeline)

This module provides the Computer Vision (CV) interface for the Smart Helmet navigation system. In this mock version, it simulates a vision pipeline that "detects" route features based on navigation hints.

## API Endpoints

### 1. Receive Navigation Hint
The Navigation module (Sanskruti) should hit this endpoint whenever there is a change in the expected maneuver or distance.

- **Endpoint:** `POST /api/localization/nav-hint`
- **Payload Format:** JSON
- **Fields:**
  - `session_id` (string): Unique ID for the current trip.
  - `ts_ms` (integer): Current Unix epoch time in milliseconds.
  - `expected_next_turn` (string): The maneuver vision should look for (e.g., "LEFT", "RIGHT", "U_TURN").
  - `distance_to_next_turn_m` (float): Meters until the turn.
  - `upcoming_features` (list of strings, optional): Other landmarks/features to prioritize.

**Example Request:**
```json
{
  "session_id": "ride_2026_03_22_01",
  "ts_ms": 1773571237000,
  "expected_next_turn": "LEFT",
  "distance_to_next_turn_m": 150.0
}
```

---

### 2. Receive Camera Frame
The hardware/camera bridge hits this endpoint to provide raw visual data.

- **Endpoint:** `POST /api/localization/frame`
- **Payload Format:** Multipart/Form-Data
- **Fields:**
  - `session_id` (form-data string): Unique trip ID.
  - `ts_ms` (form-data integer, optional): Frame capture timestamp.
  - `image` (file): Binary image data (JPEG/PNG).

*Note: In this dummy version, frames are logged and discarded.*

---

## Outbound Communication (Vision -> Navigation)

When the Vision module "detects" a feature (simulated by a 5-second timer in this mock), it will POST a `visual-event` back to the Navigation module.

- **Target Endpoint:** `POST /api/navigation/localization/visual-event`
- **Expected Payload:**
```json
{
  "session_id": "ride_2026_03_22_01",
  "event_id": "evt_123456789",
  "ts_ms": 1773571242000,
  "event_type": "TURN",
  "confidence": 0.95,
  "payload": {
    "turn_class": "LEFT"
  }
}
```

## Running the Module
1. Install dependencies: `pip install -r requirements.txt`
2. Start server: `uvicorn main:app --port 8001`
