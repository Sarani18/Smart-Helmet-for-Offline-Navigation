# Integration Considerations (Simple Version)

Purpose: only keep the minimum communication fields needed between:

- Vijit (Localization) and Sanskruti (Navigation)
- Sanskruti (Navigation) and Priyal (UI)

API style to use:

- Transport: HTTP JSON APIs between modules on mobile app side.
- Localization -> Navigation calls must be async/non-blocking.
- UI -> Navigation can be request/response APIs.

Suggested endpoints:

- POST /api/navigation/localization/visual-event
- POST /api/navigation/localization/dead-reckoning-event (future)
- POST /api/navigation/ui/action
- POST /api/navigation/connectivity/status

## A) Navigation <-> Localization: endpoints and payloads

Direction 1: Localization -> Navigation (visual events, async)

- Endpoint: POST /api/navigation/localization/visual-event
- Sender: Localization module (Vijit)
- Receiver: Navigation module (Sanskruti)

Payload:

- session_id: string
- event_id: string
- ts_ms: integer
- event_type: TURN | LANDMARK | SIGNBOARD
- confidence: number [0, 1]
- payload: object (type-specific)
- heading_deg: optional number
- speed_mps: optional number

Direction 2: Localization -> Navigation (dead reckoning, future, async)

- Endpoint: POST /api/navigation/localization/dead-reckoning-event
- Sender: Localization module (dead reckoning stream, future)
- Receiver: Navigation module (Sanskruti)

Payload (planned):

- session_id: string
- event_id: string
- ts_ms: integer
- event_type / dr_type: string
- confidence: number [0, 1]
- payload: object

Direction 3: Navigation -> Localization (control trigger)

- Endpoint: POST /api/localization/control
- Sender: Navigation module (Sanskruti)
- Receiver: Localization module(s)

Payload:

- session_id: string
- ts_ms: integer
- module: VISUAL | DEAD_RECKONING
- action: START | STOP
- reason: network_offline | network_online

Direction 4: Navigation -> Localization (optional hint)

- Endpoint: POST /api/localization/nav-hint
- Sender: Navigation module (Sanskruti)
- Receiver: Localization module (Vijit)

Payload:

- session_id: string
- ts_ms: integer
- expected_next_turn: TurnClass
- distance_to_next_turn_m: number

## B) Network availability input to Navigation

Endpoint:

- POST /api/navigation/connectivity/status

Sender responsibility:

- Responsible sender: Mobile app system connectivity monitor (platform/network layer).
- Not sent by localization module.
- Not sent by navigation module.

Receiver:

- Navigation module (Sanskruti)

Payload:

- session_id: string
- ts_ms: integer
- network_available: boolean
- internet_reachable: boolean

Meaning:

- network_available indicates device has network interface connectivity.
- internet_reachable indicates actual internet can be reached.
- Navigation uses both values to decide ONLINE vs OFFLINE and then sends START/STOP triggers to localization modules.


## 1) Vijit -> Sanskruti (Localization to Navigation)

Purpose:
Send visual observations that help navigation track route progress when exact coordinates are not available.

Trigger:
Send whenever localization detects a meaningful event (turn, landmark, signboard).

API call:

- Caller: Localization module (Vijit)
- Callee: Navigation module (Sanskruti)
- Endpoint: POST /api/navigation/localization/visual-event
- Mode: Async fire-and-forget from localization side; navigation processes with reorder buffer.

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

API call:

- Caller: Navigation module (Sanskruti)
- Callee: Localization module (Vijit)
- Endpoint: POST /api/localization/nav-hint 
- Mode: Async best-effort.

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

API call:

- Caller: Navigation module (Sanskruti)
- Callee: UI module (Priyal)
- Endpoint: POST /api/ui/navigation-state.
- Mode: Low-latency periodic updates.

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

API call:

- Caller: UI module (Priyal)
- Callee: Navigation module (Sanskruti)
- Endpoint: POST /api/navigation/ui/action
- Mode: Request/response.

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

## 6) Online/Offline detection and localization control

Purpose:
Avoid continuous costly localization processing by enabling it only in OFFLINE mode.

Who detects network status:

- System connectivity monitor in mobile app layer (Android/iOS side).
- It sends periodic status to Navigation API.

Endpoint:

- POST /api/navigation/connectivity/status

Connectivity status payload:

- session_id: string
- ts_ms: integer (Unix epoch milliseconds, UTC)
- network_available: boolean
- internet_reachable: boolean

Detection logic in Navigation:

- Online signal = network_available AND internet_reachable
- Use hysteresis to avoid flapping:
  - Switch ONLINE -> OFFLINE only after 2 consecutive offline signals.
  - Switch OFFLINE -> ONLINE only after 2 consecutive online signals.

Trigger behavior:

- On OFFLINE transition: send START trigger to localization modules.
- On ONLINE transition: send STOP trigger to localization modules.

Localization control command fields:

- session_id: string
- ts_ms: integer
- module: VISUAL | DEAD_RECKONING
- action: START | STOP
- reason: network_offline | network_online

Sample connectivity update request:

~~~json
{
  "session_id": "ride_2026_03_15_01",
  "ts_ms": 1773571300000,
  "network_available": false,
  "internet_reachable": false
}
~~~

Sample connectivity response after OFFLINE transition:

~~~json
{
  "accepted": true,
  "network_status": "OFFLINE",
  "status_changed": true,
  "commands": [
    {
      "session_id": "ride_2026_03_15_01",
      "ts_ms": 1773571300000,
      "module": "VISUAL",
      "action": "START",
      "reason": "network_offline"
    },
    {
      "session_id": "ride_2026_03_15_01",
      "ts_ms": 1773571300000,
      "module": "DEAD_RECKONING",
      "action": "START",
      "reason": "network_offline"
    }
  ]
}
~~~
