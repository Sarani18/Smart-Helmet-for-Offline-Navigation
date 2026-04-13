# Navigation Control System (NCS) Module

Owner: Sanskruti Rajesh Ninawe

## 1) Purpose

The `navigation` package is the control brain of the smart-helmet pipeline.
It receives UI requests, localization events, and connectivity updates,
processes them through a typed and validated flow, tracks route progress,
computes confidence, decides navigation mode, and emits outputs for UI and
localization modules.

This module supports:
- online navigation
- offline fallback using cached route data
- degraded-mode handling when confidence or event freshness drops

## 2) High-Level Internal Architecture

The package is organized as layered blocks:

1. Contracts Layer
- Defines enums and message dataclasses for all integration payloads.

2. Validation Layer
- Converts raw dict payloads into strongly typed messages.

3. Event Quality Layer
- Handles deduplication, staleness checks, and reorder buffering.

4. Route/Progress Layer
- Tracks current route step using semantic localization events.

5. Confidence & Mode Layer
- Updates confidence score and derives ONLINE/OFFLINE/DEGRADED state.

6. Orchestration API Layer
- Exposes async handlers that coordinate all layers end-to-end.

7. Supporting Utilities
- Route parsing, offline route cache, map manager, and turn extraction.

## 3) File-by-File Structure

| File | Role in the System |
|---|---|
| `api_service.py` | Main async orchestration facade (`NavigationAPIService`) combining validation, event processing, confidence, mode switching, cache fallback, nav hints, and UI state output |
| `contracts.py` | Shared enums/dataclasses for integration contracts (events, UI actions, connectivity status, nav hints, UI state, localization control) |
| `event_validator.py` | Input schema validator/parser (`NavigationContractValidator`) with strict type and field checks |
| `event_pipeline.py` | Stream quality control (`LocalizationEventPipeline`): dedupe, stale rejection, reorder-window buffering |
| `route_progress.py` | Semantic route-step advancement engine (`RouteProgressEngine`) and `ProgressUpdate` result model |
| `confidence_tracker.py` | Confidence scoring + temporal decay (`NavigationConfidenceTracker`) and state snapshot model |
| `route_processor.py` | Route loading and normalization into `Route`, `RouteStep`, and `Waypoint` |
| `offline_cache.py` | Persistent JSON route cache used when live route data is unavailable |
| `map_manager.py` | Local map segment loading and nearby segment lookup for offline/matching support |
| `turn_extractor.py` | Polyline decoding and turn instruction extraction from coordinate geometry |
| `__init__.py` | Public exports for package-level imports |

## 4) Core Data Contracts

### 4.1 Input Message Families
- Localization events (`EventMessage`):
  - `TURN`
  - `LANDMARK`
  - `SIGNBOARD`
- UI actions (`UIActionMessage`):
  - `START_NAVIGATION`
  - `STOP_NAVIGATION`
  - `REROUTE_REQUEST`
- Connectivity status (`ConnectivityStatusMessage`):
  - `network_available`
  - `internet_reachable`

### 4.2 Output Message Families
- Navigation hints (`NavHintMessage`): expected turn + distance to next turn.
- UI state (`UIStateMessage`): nav mode, position mode, instruction, confidence,
  destination flag, active step, route polyline.
- Localization control (`LocalizationControlMessage`):
  - target module: visual / dead-reckoning
  - action: start / stop
  - reason: mode/action trigger context

## 5) Request Handlers in `NavigationAPIService`

### `ingest_visual_event(payload, now_ts_ms)`
Flow:
1. Parse and validate localization payload.
2. Apply confidence time decay.
3. Ingest event into pipeline (duplicate/stale checks).
4. Pop ready events from reorder buffer.
5. For each ready event:
   - process against route progress
   - update confidence using event + progress outcome
6. Recompute nav mode and degraded reason.
7. Build nav hint (with change suppression).
8. Build UI state snapshot.
9. Return processing summary and outputs.

### `ingest_ui_action(payload, route_data=None)`
Flow by action type:
- `START_NAVIGATION` / `REROUTE_REQUEST`:
  - validate action
  - build localization control commands based on current network state
  - use provided route data; if missing, try offline cache
  - cache route for recovery
  - load route into `RouteProcessor` and `RouteProgressEngine`
  - initialize session state and return nav hint + UI state
- `STOP_NAVIGATION`:
  - reset progress and confidence state
  - clear route/session-dependent runtime fields
  - emit STOP commands for localization modules
  - return updated mode + UI state

### `update_connectivity_status(payload)`
Flow:
1. Validate connectivity payload.
2. Derive online signal = network_available AND internet_reachable.
3. Apply hysteresis counters to avoid rapid flapping:
   - offline transition after N failures
   - online transition after M successes
4. On transition, emit localization START/STOP commands.
5. Refresh nav mode and build current UI state.
6. Return status, commands, and detection context.

### `get_ui_state(payload)`
Flow:
1. Validate request shape (`session_id`, `ts_ms`).
2. Return current UI-ready state snapshot.

## 6) Mode & Confidence Logic

### 6.1 Confidence
- Confidence increases on event-to-step matches.
- Confidence decreases on mismatches.
- Confidence decays over time when no events arrive.

### 6.2 Mode Selection Priority
1. `DEGRADED` if degraded conditions are true.
2. Else `OFFLINE` if network is offline.
3. Else `ONLINE`.

Current degraded triggers:
- low confidence below threshold
- no recent localization events while offline and route is active

## 7) How Data and Logic Are Handled End-to-End

Typical run sequence:

1. UI sends `START_NAVIGATION`.
2. NCS loads route (live or cache), initializes progress state, and caches route.
3. Localization modules stream semantic events.
4. NCS validates and quality-filters events through pipeline.
5. Progress engine decides whether each event advances route steps.
6. Confidence tracker updates reliability score and decay.
7. Mode engine derives ONLINE/OFFLINE/DEGRADED.
8. NCS emits:
   - UI state snapshot
   - nav hints when maneuver/distance bucket changes
   - localization START/STOP commands based on mode and triggers
9. On connectivity changes, hysteresis prevents unstable toggling and only then
   triggers localization control transitions.

## 8) Extension Points

- Enable full dead-reckoning ingestion by implementing
  `ingest_dead_reckoning_event`.
- Integrate map matching through `MapManager` during degraded/offline periods.
- Add richer off-route detection and reroute policy hooks.
- Replace in-memory orchestration with transport adapters (HTTP/MQTT/BLE).

## 9) Dependencies

- Python standard library only.
- No third-party runtime dependency required for this package.

## 10) Vision Integration (Merged Branch Setup)

This repository now includes a transport adapter and bridge so Navigation and
Vision can run together as planned.

New files:
- `navigation/server.py`: FastAPI server exposing Navigation endpoints.
- `navigation/vision_bridge.py`: bridge that forwards nav hints from Navigation
  to Vision module.

Default endpoint mapping:
- Vision -> Navigation event push:
  - `POST /api/navigation/localization/visual-event`
- Navigation -> Vision nav hint push:
  - `POST http://127.0.0.1:8001/api/localization/nav-hint`

Environment options for Navigation server:
- `NCS_PUSH_NAV_HINTS=1` (default): enable nav-hint forwarding to Vision.
- `VISION_NAV_HINT_URL=http://127.0.0.1:8001/api/localization/nav-hint`
- `NCS_ENABLE_TILE_PREFETCH=1` (default): enable route-start tile prefetch.
- `NCS_TILE_CACHE_MAX_MB=200` (default): max tile cache size before oldest-first eviction.
- `NCS_TILE_ZOOMS=14,15` (default): comma-separated zoom levels for prefetch.
- `NCS_EVICT_SESSION_TILES_ON_STOP=0` (default): if `1`, evict active session tiles on STOP.

Run sequence:
1. Start Navigation API server (port 8000):
  - `uvicorn navigation.server:app --host 0.0.0.0 --port 8000`
2. Start Vision module server (port 8001):
  - `uvicorn localization.vision.main:app --host 0.0.0.0 --port 8001`
3. Start navigation from UI endpoint with route data:
  - `POST /api/navigation/ui/action` with action `START_NAVIGATION`
4. Send camera frames to Vision:
  - `POST /api/localization/frame`
5. Observe:
  - Vision emits visual events to Navigation.
  - Navigation computes progress/confidence/mode.
  - Navigation emits nav hints to Vision via bridge.

## 11) Suggested End-to-End Test Scenarios

1. Happy path turn match
- Start navigation with route containing "Turn right".
- Send Vision TURN RIGHT event.
- Expect: step advances, destination/progress updates, confidence improves.

2. Unexpected then expected detection
- Vision sends one unexpected turn followed by expected turn.
- Expect: mismatch lowers confidence slightly, then expected event recovers score.

3. Offline transition and localization control
- Send two offline connectivity updates (with hysteresis threshold = 2).
- Expect: mode switches to OFFLINE, START commands issued to localization modules.

4. Online recovery transition
- After OFFLINE, send two healthy connectivity updates.
- Expect: mode switches to ONLINE, STOP commands issued to localization modules.

5. No recent events while offline (degraded)
- Start route, go offline, then stop sending localization events beyond timeout.
- Expect: nav mode becomes DEGRADED with reason `no_recent_localization_events`.

6. Cache recovery route load
- Start once with live route_data, then start again without route_data.
- Expect: route is loaded from cache and processing continues.

7. Nav-hint forwarding robustness
- Simulate Vision nav-hint endpoint down.
- Expect: Navigation flow still succeeds; response includes
  `nav_hint_delivery.status = failed`.

Automated coverage:
- Existing orchestration tests: `navigation/tests/test_navigation.py`
- Added bridge integration tests: `navigation/tests/test_navigation_vision_bridge.py`

Runtime end-to-end check:
- With both servers running, execute:
  - `python navigation/tests/run_nav_vision_e2e.py`
