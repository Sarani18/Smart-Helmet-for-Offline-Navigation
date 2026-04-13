# Vision Module (Mock Pipeline)

This module provides the Computer Vision (CV) interface for the Smart Helmet navigation system. It analyzes camera frames through multiple concurrent pipelines (e.g., scene detection for turns/intersections, object detection for traffic signals) and reports all recognized features to the Navigation module.

## Architectural Behavior

1. **Autonomous Processing**: Vision continuously processes camera frames. It does not wait for navigation hints to start detecting. 
2. **Continuous Reporting**: The Vision module sends *everything* it detects (turns, signals, intersections, etc.), even if the detections are unexpected or not part of the current route list. It is up to the Navigation/Control module to accept or reject this data.
3. **Weight Adjustment via Nav Hints**: When the Navigation module sends a `/nav-hint`, it merely informs the Vision module of the `expected_next_turn`. Vision uses this hint *only* to adjust internal weights/confidences (e.g., if approaching a known intersection, the threshold for classifying "LEFT" might be lowered slightly). It does **not** act as a filter.
4. **Multiple Pipelines per Frame**: A single frame might contain multiple features (e.g., both an intersection and a traffic signal). Vision runs multiple models simultaneously and will report objects as they are identified, sequentially.

---

## API Endpoints

### 1. Receive Navigation Hint
The Navigation module (Sanskruti) should hit this endpoint whenever there is a change in the expected maneuver.

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
The hardware/camera bridge hits this endpoint to provide raw visual data. **This is what triggers the detection pipelines.**

- **Endpoint:** `POST /api/localization/frame`
- **Payload Format:** Multipart/Form-Data
- **Fields:**
  - `session_id` (form-data string): Unique trip ID.
  - `ts_ms` (form-data integer, optional): Frame capture timestamp.
  - `image` (file): Binary image data (JPEG/PNG).

---

## Outbound Communication (Vision -> Navigation)

When the Vision module detects a feature (e.g., processing a frame), it will POST a `visual-event` back to the Navigation module.

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
