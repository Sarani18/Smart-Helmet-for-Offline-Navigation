# Integration Considerations (Simple Version)

Purpose: only keep the minimum communication fields needed between:

- Vijit (Localization) and Sanskruti (Navigation)
- Sanskruti (Navigation) and Priyal (UI)

Timestamp format for all messages:

- Field name: ts_ms
- Type: integer (64-bit)
- Meaning: Unix epoch time in milliseconds (UTC)
- Example: 1773571234567

## 1) Vijit -> Sanskruti (Localization to Navigation)

Purpose:
Send visual observations that help navigation track route progress when exact coordinates are not available.

Trigger:
Send whenever localization detects a meaningful event (turn, landmark, signboard).

### EventMessage class

- session_id: string
- event_id: string (unique per session)
- ts_ms: integer (Unix epoch milliseconds, UTC)
- event_type: LocalizationEventType
- confidence: number [0.0, 1.0]
- payload: TurnPayload | LandmarkPayload | SignboardPayload
- heading_deg: optional number
- speed_mps: optional number

### Enums and payload classes

LocalizationEventType:

- TURN
- LANDMARK
- SIGNBOARD

TurnClass:

- SLIGHT_LEFT
- LEFT
- SLIGHT_RIGHT
- RIGHT
- U_TURN
- STRAIGHT

LandmarkClass:

- TRAFFIC_LIGHT
- BRIDGE
- FUEL_STATION
- JUNCTION
- ROUNDABOUT

TurnPayload:

- turn_class: TurnClass

LandmarkPayload:

- landmark_class: LandmarkClass
- map_hint_name: optional string

SignboardPayload:

- text: string
- direction_hint: optional TurnClass

### Sample TURN event

~~~json
{
  "session_id": "ride_2026_03_15_01",
  "event_id": "evt_000234",
  "ts_ms": 1773571234567,
  "event_type": "TURN",
  "confidence": 0.92,
  "payload": {
    "turn_class": "RIGHT"
  },
  "heading_deg": 86.0
}
~~~

### Sample SIGNBOARD event

~~~json
{
  "session_id": "ride_2026_03_15_01",
  "event_id": "evt_000235",
  "ts_ms": 1773571236120,
  "event_type": "SIGNBOARD",
  "confidence": 0.81,
  "payload": {
    "text": "Airport Left",
    "direction_hint": "LEFT"
  }
}
~~~

## 2) Sanskruti -> Vijit (Navigation feedback to Localization)

Purpose:
Provide expected maneuver context so localization can prioritize relevant detections.

Trigger:
Send when next maneuver changes or distance bucket changes significantly (example: every 50 m).

### NavHintMessage class

- session_id: string
- ts_ms: integer (Unix epoch milliseconds, UTC)
- expected_next_turn: TurnClass
- distance_to_next_turn_m: number

### Sample NavHintMessage

~~~json
{
  "session_id": "ride_2026_03_15_01",
  "ts_ms": 1773571237000,
  "expected_next_turn": "RIGHT",
  "distance_to_next_turn_m": 120
}
~~~

## 3) Sanskruti -> Priyal (Navigation to UI)

Purpose:
Send the current navigation state for map rendering and rider instructions.

Trigger:
Send continuously at fixed update rate (recommended 2 to 5 Hz), and immediately on major state changes.

### UIStateMessage class

- session_id: string
- ts_ms: integer (Unix epoch milliseconds, UTC)
- nav_mode: NavMode
- position_mode: PositionMode
- next_instruction_text: string
- distance_to_next_m: number
- confidence: number [0.0, 1.0]
- off_route_flag: boolean
- destination_reached_flag: boolean
- active_step_index: number
- route_polyline: list of [lat, lon]

### Enums

NavMode:

- ONLINE
- OFFLINE
- DEGRADED

PositionMode:

- GPS
- VISUAL
- UNKNOWN

### Sample UIStateMessage

~~~json
{
  "session_id": "ride_2026_03_15_01",
  "ts_ms": 1773571240000,
  "nav_mode": "OFFLINE",
  "position_mode": "VISUAL",
  "next_instruction_text": "In 120 m, turn right",
  "distance_to_next_m": 120,
  "confidence": 0.78,
  "off_route_flag": false,
  "destination_reached_flag": false,
  "active_step_index": 5,
  "route_polyline": [
    [19.0760, 72.8777],
    [19.0768, 72.8790]
  ]
}
~~~

## 4) Priyal -> Sanskruti (UI actions to Navigation)

Purpose:
Send user actions from app UI into navigation processing.

Trigger:
Send on each user action: start, stop, reroute.

### UIActionMessage class

- session_id: string
- ts_ms: integer (Unix epoch milliseconds, UTC)
- action_type: UIActionType
- payload: StartNavigationPayload | RerouteRequestPayload | EmptyPayload

### Enums and payload classes

UIActionType:

- START_NAVIGATION
- STOP_NAVIGATION
- REROUTE_REQUEST

StartNavigationPayload:

- origin: string
- destination: string

RerouteRequestPayload:

- reason: string

### Sample START_NAVIGATION

~~~json
{
  "session_id": "ride_2026_03_15_01",
  "ts_ms": 1773571200000,
  "action_type": "START_NAVIGATION",
  "payload": {
    "origin": "VNIT Nagpur",
    "destination": "Nagpur Airport"
  }
}
~~~

## 5) Minimal merge-safe rules

- Keep enum names exactly as defined above.
- Keep confidence in [0, 1].
- Ignore duplicate event_id values.
- Reject message if required fields are missing.
