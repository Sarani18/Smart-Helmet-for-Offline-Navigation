"""
Unit tests for the Navigation & Route Intelligence Module.
"""

import json
import asyncio
import os
import sys
import tempfile
import unittest

# Ensure repository root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from navigation.route_processor import RouteProcessor, Route
from navigation.map_manager import MapManager
from navigation.turn_extractor import TurnExtractor
from navigation.offline_cache import OfflineCache
from navigation.contracts import (
    LocalizationEventType,
    TurnClass,
    LandmarkClass,
    NavMode,
    PositionMode,
    UIActionType,
    TurnPayload,
    LandmarkPayload,
    SignboardPayload,
    EventMessage,
    NavHintMessage,
    UIStateMessage,
    StartNavigationPayload,
    RerouteRequestPayload,
    UIActionMessage,
)
from navigation.event_validator import NavigationContractValidator, ContractValidationError
from navigation.event_pipeline import LocalizationEventPipeline
from navigation.route_progress import RouteProgressEngine, ProgressUpdate
from navigation.api_service import NavigationAPIService
from navigation.confidence_tracker import NavigationConfidenceTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_route_data():
    return {
        "origin": {"lat": 19.076, "lon": 72.877, "label": "Home"},
        "destination": {"lat": 19.100, "lon": 72.900, "label": "Office"},
        "steps": [
            {"lat": 19.078, "lon": 72.879, "instruction": "Turn right", "distance": 300},
            {"lat": 19.085, "lon": 72.885, "instruction": "Go straight", "distance": 700},
            {"lat": 19.100, "lon": 72.900, "instruction": "Arrive", "distance": 500},
        ],
    }


def _sample_map_data():
    return {
        "segments": [
            {
                "id": "seg1",
                "name": "MG Road",
                "start": {"lat": 19.076, "lon": 72.877},
                "end": {"lat": 19.085, "lon": 72.885},
            }
        ]
    }


# ---------------------------------------------------------------------------
# RouteProcessor tests
# ---------------------------------------------------------------------------

class TestRouteProcessor(unittest.TestCase):

    def setUp(self):
        self.processor = RouteProcessor()

    def test_load_valid_route(self):
        route = self.processor.load_route(_sample_route_data())
        self.assertIsInstance(route, Route)
        self.assertEqual(len(route.steps), 3)
        self.assertAlmostEqual(route.total_distance_meters, 1500.0)

    def test_load_sets_current_route(self):
        self.processor.load_route(_sample_route_data())
        self.assertIsNotNone(self.processor.get_current_route())

    def test_load_strips_html_from_instruction(self):
        data = _sample_route_data()
        data["steps"][0]["instruction"] = "<b>Turn right</b>"
        route = self.processor.load_route(data)
        self.assertEqual(route.steps[0].instruction, "Turn right")

    def test_load_empty_steps_raises(self):
        data = _sample_route_data()
        data["steps"] = []
        with self.assertRaises(ValueError):
            self.processor.load_route(data)

    def test_advance_step_returns_first_step(self):
        self.processor.load_route(_sample_route_data())
        step = self.processor.advance_step()
        self.assertIsNotNone(step)
        self.assertEqual(step.instruction, "Turn right")
        self.assertEqual(len(self.processor.get_current_route().steps), 2)

    def test_revalidate_route_close_position(self):
        self.processor.load_route(_sample_route_data())
        # Very close to the first step waypoint
        result = self.processor.revalidate_route(19.078, 72.879)
        self.assertTrue(result)

    def test_revalidate_route_far_position(self):
        self.processor.load_route(_sample_route_data())
        # Far away (different city)
        result = self.processor.revalidate_route(28.6139, 77.2090)  # Delhi
        self.assertFalse(result)

    def test_no_current_route_returns_none(self):
        self.assertIsNone(self.processor.get_current_route())


# ---------------------------------------------------------------------------
# MapManager tests
# ---------------------------------------------------------------------------

class TestMapManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = MapManager(map_data_dir=self.tmpdir)

    def _write_map_file(self, data=None):
        path = os.path.join(self.tmpdir, "test_map.json")
        with open(path, "w") as f:
            json.dump(data or _sample_map_data(), f)
        return path

    def test_load_valid_map(self):
        path = self._write_map_file()
        self.assertTrue(self.manager.load_map(path))

    def test_load_missing_file(self):
        self.assertFalse(self.manager.load_map("/nonexistent/map.json"))

    def test_get_nearby_segments_within_radius(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        # Midpoint of seg1 is approx (19.0805, 72.881)
        segs = self.manager.get_nearby_segments(19.0805, 72.881, radius_meters=500)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["name"], "MG Road")

    def test_get_nearby_segments_outside_radius(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        segs = self.manager.get_nearby_segments(28.6139, 77.2090, radius_meters=100)
        self.assertEqual(len(segs), 0)

    def test_has_offline_coverage_true(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        self.assertTrue(self.manager.has_offline_coverage((19.0, 72.8, 19.2, 73.0)))

    def test_has_offline_coverage_false(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        # Bounding box nowhere near Mumbai
        self.assertFalse(self.manager.has_offline_coverage((28.0, 76.0, 29.0, 78.0)))


# ---------------------------------------------------------------------------
# TurnExtractor tests
# ---------------------------------------------------------------------------

class TestTurnExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = TurnExtractor()

    def test_decode_polyline_simple(self):
        # Known encoded polyline for two points
        # Encoding of [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        coords = self.extractor.decode_polyline(encoded)
        self.assertEqual(len(coords), 3)
        self.assertAlmostEqual(coords[0][0], 38.5, places=4)
        self.assertAlmostEqual(coords[0][1], -120.2, places=4)

    def test_extract_turns_too_few_points(self):
        coords = [(19.0, 72.0), (19.1, 72.1)]
        self.assertEqual(self.extractor.extract_turns(coords), [])

    def test_extract_turns_straight(self):
        # Three collinear points going north – no turn expected
        coords = [(19.0, 72.0), (19.1, 72.0), (19.2, 72.0)]
        turns = self.extractor.extract_turns(coords)
        self.assertEqual(turns, [])

    def test_classify_turn_right(self):
        instruction = self.extractor._classify_turn(45)
        self.assertIn("right", instruction.lower())

    def test_classify_turn_left(self):
        instruction = self.extractor._classify_turn(-45)
        self.assertIn("left", instruction.lower())

    def test_classify_u_turn(self):
        instruction = self.extractor._classify_turn(175)
        self.assertIn("U-turn", instruction)

    def test_classify_slight_left(self):
        instruction = self.extractor._classify_turn(-10)
        self.assertEqual(instruction, "")  # below threshold → straight


# ---------------------------------------------------------------------------
# OfflineCache tests
# ---------------------------------------------------------------------------

class TestOfflineCache(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = OfflineCache(cache_dir=self.tmpdir)

    def test_save_and_load(self):
        data = _sample_route_data()
        self.assertTrue(self.cache.save_route("test_route", data))
        loaded = self.cache.load_route("test_route")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["origin"]["label"], "Home")

    def test_load_missing_returns_none(self):
        self.assertIsNone(self.cache.load_route("does_not_exist"))

    def test_is_cached(self):
        self.cache.save_route("my_route", {"key": "value"})
        self.assertTrue(self.cache.is_cached("my_route"))
        self.assertFalse(self.cache.is_cached("other_route"))

    def test_list_cached_routes(self):
        self.cache.save_route("route_a", {})
        self.cache.save_route("route_b", {})
        keys = self.cache.list_cached_routes()
        self.assertIn("route_a", keys)
        self.assertIn("route_b", keys)

    def test_delete_route(self):
        self.cache.save_route("temp_route", {})
        self.assertTrue(self.cache.delete_route("temp_route"))
        self.assertFalse(self.cache.is_cached("temp_route"))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.cache.delete_route("ghost_route"))


# ---------------------------------------------------------------------------
# Contracts tests
# ---------------------------------------------------------------------------

class TestContracts(unittest.TestCase):

    def test_event_message_with_turn_payload(self):
        message = EventMessage(
            session_id="ride_1",
            event_id="evt_1",
            ts_ms=1_773_571_234_567,
            event_type=LocalizationEventType.TURN,
            confidence=0.9,
            payload=TurnPayload(turn_class=TurnClass.RIGHT),
            heading_deg=86.0,
        )
        self.assertEqual(message.event_type, LocalizationEventType.TURN)
        self.assertEqual(message.payload.turn_class, TurnClass.RIGHT)

    def test_event_message_with_landmark_payload(self):
        message = EventMessage(
            session_id="ride_1",
            event_id="evt_2",
            ts_ms=1_773_571_236_120,
            event_type=LocalizationEventType.LANDMARK,
            confidence=0.75,
            payload=LandmarkPayload(
                landmark_class=LandmarkClass.BRIDGE,
                map_hint_name="Flyover",
            ),
        )
        self.assertEqual(message.payload.landmark_class, LandmarkClass.BRIDGE)

    def test_event_message_with_signboard_payload(self):
        message = EventMessage(
            session_id="ride_1",
            event_id="evt_3",
            ts_ms=1_773_571_237_000,
            event_type=LocalizationEventType.SIGNBOARD,
            confidence=0.81,
            payload=SignboardPayload(text="Airport Left", direction_hint=TurnClass.LEFT),
        )
        self.assertEqual(message.payload.text, "Airport Left")
        self.assertEqual(message.payload.direction_hint, TurnClass.LEFT)

    def test_nav_hint_message(self):
        hint = NavHintMessage(
            session_id="ride_1",
            ts_ms=1_773_571_237_100,
            expected_next_turn=TurnClass.RIGHT,
            distance_to_next_turn_m=120.0,
        )
        self.assertEqual(hint.expected_next_turn, TurnClass.RIGHT)

    def test_ui_state_message(self):
        state = UIStateMessage(
            session_id="ride_1",
            ts_ms=1_773_571_240_000,
            nav_mode=NavMode.OFFLINE,
            position_mode=PositionMode.VISUAL,
            next_instruction_text="In 120 m, turn right",
            distance_to_next_m=120.0,
            confidence=0.78,
            off_route_flag=False,
            destination_reached_flag=False,
            active_step_index=5,
            route_polyline=[(19.0760, 72.8777), (19.0768, 72.8790)],
        )
        self.assertEqual(state.nav_mode, NavMode.OFFLINE)
        self.assertEqual(state.position_mode, PositionMode.VISUAL)

    def test_ui_action_messages(self):
        start_action = UIActionMessage(
            session_id="ride_1",
            ts_ms=1_773_571_200_000,
            action_type=UIActionType.START_NAVIGATION,
            payload=StartNavigationPayload(origin="VNIT Nagpur", destination="Nagpur Airport"),
        )
        reroute_action = UIActionMessage(
            session_id="ride_1",
            ts_ms=1_773_571_260_000,
            action_type=UIActionType.REROUTE_REQUEST,
            payload=RerouteRequestPayload(reason="off_route"),
        )
        self.assertEqual(start_action.action_type, UIActionType.START_NAVIGATION)
        self.assertEqual(reroute_action.action_type, UIActionType.REROUTE_REQUEST)


class TestNavigationContractValidator(unittest.TestCase):

    def setUp(self):
        self.validator = NavigationContractValidator()

    def test_parse_localization_turn_event(self):
        payload = {
            "session_id": "ride_1",
            "event_id": "evt_1",
            "ts_ms": 1_773_571_234_567,
            "event_type": "TURN",
            "confidence": 0.91,
            "payload": {"turn_class": "RIGHT"},
        }
        parsed = self.validator.parse_localization_event(payload)
        self.assertEqual(parsed.event_type, LocalizationEventType.TURN)
        self.assertEqual(parsed.payload.turn_class, TurnClass.RIGHT)

    def test_parse_localization_invalid_confidence(self):
        payload = {
            "session_id": "ride_1",
            "event_id": "evt_1",
            "ts_ms": 1_773_571_234_567,
            "event_type": "TURN",
            "confidence": 1.2,
            "payload": {"turn_class": "RIGHT"},
        }
        with self.assertRaises(ContractValidationError):
            self.validator.parse_localization_event(payload)

    def test_parse_localization_missing_required_field(self):
        payload = {
            "session_id": "ride_1",
            "event_id": "evt_1",
            "event_type": "SIGNBOARD",
            "confidence": 0.81,
            "payload": {"text": "Airport Left"},
        }
        with self.assertRaises(ContractValidationError):
            self.validator.parse_localization_event(payload)

    def test_parse_ui_action_start_navigation(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1_773_571_200_000,
            "action_type": "START_NAVIGATION",
            "payload": {
                "origin": "VNIT Nagpur",
                "destination": "Nagpur Airport",
            },
        }
        parsed = self.validator.parse_ui_action(payload)
        self.assertEqual(parsed.action_type, UIActionType.START_NAVIGATION)
        self.assertEqual(parsed.payload.origin, "VNIT Nagpur")

    def test_parse_ui_action_stop_navigation(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1_773_571_210_000,
            "action_type": "STOP_NAVIGATION",
            "payload": {},
        }
        parsed = self.validator.parse_ui_action(payload)
        self.assertEqual(parsed.action_type, UIActionType.STOP_NAVIGATION)

    def test_parse_ui_action_invalid_enum_value(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1_773_571_220_000,
            "action_type": "PAUSE_NAVIGATION",
            "payload": {},
        }
        with self.assertRaises(ContractValidationError):
            self.validator.parse_ui_action(payload)

    def test_parse_connectivity_status_valid(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1_773_571_220_000,
            "network_available": True,
            "internet_reachable": False,
        }
        parsed = self.validator.parse_connectivity_status(payload)
        self.assertTrue(parsed.network_available)
        self.assertFalse(parsed.internet_reachable)

    def test_parse_connectivity_status_invalid_type(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1_773_571_220_000,
            "network_available": "yes",
            "internet_reachable": False,
        }
        with self.assertRaises(ContractValidationError):
            self.validator.parse_connectivity_status(payload)


class TestLocalizationEventPipeline(unittest.TestCase):

    def setUp(self):
        self.pipeline = LocalizationEventPipeline(
            max_staleness_ms=1500,
            reorder_window_ms=300,
            seen_cache_size=10,
        )

    @staticmethod
    def _turn_event(event_id: str, ts_ms: int):
        return EventMessage(
            session_id="ride_1",
            event_id=event_id,
            ts_ms=ts_ms,
            event_type=LocalizationEventType.TURN,
            confidence=0.9,
            payload=TurnPayload(turn_class=TurnClass.RIGHT),
        )

    def test_reject_duplicate_event_id(self):
        now = 10_000
        event = self._turn_event("evt_dup", 9_800)
        first = self.pipeline.ingest(event, now)
        second = self.pipeline.ingest(event, now)
        self.assertTrue(first.accepted)
        self.assertFalse(second.accepted)
        self.assertEqual(second.reason, "duplicate_event_id")

    def test_reject_stale_event(self):
        now = 10_000
        stale = self._turn_event("evt_old", 8_000)
        result = self.pipeline.ingest(stale, now)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "stale_event")

    def test_pop_ready_orders_by_timestamp(self):
        now = 10_000
        late_arrival = self._turn_event("evt_2", 9_500)
        early_arrival = self._turn_event("evt_1", 9_200)

        self.pipeline.ingest(late_arrival, now)
        self.pipeline.ingest(early_arrival, now)

        ready = self.pipeline.pop_ready(now)
        self.assertEqual([event.event_id for event in ready], ["evt_1", "evt_2"])

    def test_reorder_window_holds_recent_events(self):
        now = 10_000
        # cutoff is 9700 when reorder window is 300
        not_ready = self._turn_event("evt_new", 9_850)
        self.pipeline.ingest(not_ready, now)
        ready = self.pipeline.pop_ready(now)
        self.assertEqual(ready, [])
        self.assertEqual(self.pipeline.pending_count, 1)

    def test_flush_all_returns_pending_events(self):
        self.pipeline.ingest(self._turn_event("evt_1", 1_000), 1_100)
        self.pipeline.ingest(self._turn_event("evt_2", 1_050), 1_100)
        flushed = self.pipeline.flush_all()
        self.assertEqual([event.event_id for event in flushed], ["evt_1", "evt_2"])
        self.assertEqual(self.pipeline.pending_count, 0)


class TestRouteProgressEngine(unittest.TestCase):

    def setUp(self):
        self.engine = RouteProgressEngine()
        processor = RouteProcessor()
        route_data = {
            "origin": {"lat": 19.076, "lon": 72.877, "label": "Home"},
            "destination": {"lat": 19.100, "lon": 72.900, "label": "Airport"},
            "steps": [
                {"lat": 19.078, "lon": 72.879, "instruction": "Turn right", "distance": 300},
                {"lat": 19.085, "lon": 72.885, "instruction": "At traffic light turn left", "distance": 700},
            ],
        }
        self.route = processor.load_route(route_data)
        self.engine.load_route(self.route)

    def test_advance_on_matching_turn_event(self):
        event = EventMessage(
            session_id="ride_1",
            event_id="evt_turn_1",
            ts_ms=1000,
            event_type=LocalizationEventType.TURN,
            confidence=0.9,
            payload=TurnPayload(turn_class=TurnClass.RIGHT),
        )
        result = self.engine.process_event(event)
        self.assertTrue(result.advanced)
        self.assertEqual(result.active_step_index, 1)

    def test_no_advance_on_non_matching_turn_event(self):
        event = EventMessage(
            session_id="ride_1",
            event_id="evt_turn_2",
            ts_ms=1001,
            event_type=LocalizationEventType.TURN,
            confidence=0.9,
            payload=TurnPayload(turn_class=TurnClass.LEFT),
        )
        result = self.engine.process_event(event)
        self.assertFalse(result.advanced)
        self.assertEqual(result.active_step_index, 0)

    def test_advance_on_matching_signboard_direction(self):
        sign_event = EventMessage(
            session_id="ride_1",
            event_id="evt_sign_1",
            ts_ms=1002,
            event_type=LocalizationEventType.SIGNBOARD,
            confidence=0.8,
            payload=SignboardPayload(text="Airport Right"),
        )
        result = self.engine.process_event(sign_event)
        self.assertTrue(result.advanced)

    def test_advance_on_landmark_hint(self):
        # First progress to second step.
        self.engine.process_event(
            EventMessage(
                session_id="ride_1",
                event_id="evt_turn_3",
                ts_ms=1003,
                event_type=LocalizationEventType.TURN,
                confidence=0.9,
                payload=TurnPayload(turn_class=TurnClass.RIGHT),
            )
        )
        # Step text contains "traffic light" so this should match.
        landmark_event = EventMessage(
            session_id="ride_1",
            event_id="evt_lm_1",
            ts_ms=1004,
            event_type=LocalizationEventType.LANDMARK,
            confidence=0.85,
            payload=LandmarkPayload(landmark_class=LandmarkClass.TRAFFIC_LIGHT),
        )
        result = self.engine.process_event(landmark_event)
        self.assertTrue(result.advanced)
        self.assertTrue(result.destination_reached)

    def test_process_without_route_loaded(self):
        engine = RouteProgressEngine()
        event = EventMessage(
            session_id="ride_1",
            event_id="evt_turn_4",
            ts_ms=1005,
            event_type=LocalizationEventType.TURN,
            confidence=0.9,
            payload=TurnPayload(turn_class=TurnClass.RIGHT),
        )
        result = engine.process_event(event)
        self.assertFalse(result.advanced)
        self.assertEqual(result.reason, "route_not_loaded")

    def test_expected_next_turn_and_distance_helpers(self):
        expected_turn = self.engine.get_expected_next_turn()
        expected_distance = self.engine.get_distance_to_next_turn_m()
        self.assertEqual(expected_turn, TurnClass.RIGHT)
        self.assertEqual(expected_distance, 300.0)


class TestNavigationAPIService(unittest.TestCase):

    def setUp(self):
        self.service = NavigationAPIService(
            offline_after_failures=2,
            online_after_successes=2,
        )
        self.route_data = {
            "origin": {"lat": 19.076, "lon": 72.877, "label": "Home"},
            "destination": {"lat": 19.100, "lon": 72.900, "label": "Airport"},
            "steps": [
                {"lat": 19.078, "lon": 72.879, "instruction": "Turn right", "distance": 300},
            ],
        }

    def test_ui_start_navigation_requires_route_data(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        result = asyncio.run(self.service.ingest_ui_action(payload))
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "route_data_required")
        self.assertIn("nav_mode", result)
        self.assertIn("degraded", result)

    def test_ui_start_navigation_loads_route(self):
        payload = {
            "session_id": "ride_1",
            "ts_ms": 1001,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        result = asyncio.run(self.service.ingest_ui_action(payload, self.route_data))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["reason"], "route_loaded")
        self.assertEqual(result["nav_mode"], "ONLINE")
        self.assertFalse(result["degraded"])
        self.assertIsNotNone(result["nav_hint"])
        self.assertEqual(result["nav_hint"]["expected_next_turn"], "RIGHT")

    def test_async_visual_event_ingestion(self):
        start_payload = {
            "session_id": "ride_1",
            "ts_ms": 1001,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        asyncio.run(self.service.ingest_ui_action(start_payload, self.route_data))

        event_payload = {
            "session_id": "ride_1",
            "event_id": "evt_1",
            "ts_ms": 1200,
            "event_type": "TURN",
            "confidence": 0.95,
            "payload": {"turn_class": "RIGHT"},
        }
        result = asyncio.run(self.service.ingest_visual_event(event_payload, now_ts_ms=2000))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["active_step_index"], 1)
        self.assertTrue(result["destination_reached"])
        self.assertGreaterEqual(result["confidence_score"], 0.0)
        self.assertLessEqual(result["confidence_score"], 1.0)
        self.assertIn(result["nav_mode"], {"ONLINE", "OFFLINE", "DEGRADED"})
        # Route has only one step in this test setup; after match, no next hint.
        self.assertIsNone(result["nav_hint"])

    def test_nav_hint_not_repeated_without_change(self):
        route_data = {
            "origin": {"lat": 19.076, "lon": 72.877, "label": "Home"},
            "destination": {"lat": 19.100, "lon": 72.900, "label": "Airport"},
            "steps": [
                {"lat": 19.078, "lon": 72.879, "instruction": "Turn right", "distance": 300},
                {"lat": 19.085, "lon": 72.885, "instruction": "Turn left", "distance": 700},
            ],
        }

        start_payload = {
            "session_id": "ride_1",
            "ts_ms": 1001,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        start_result = asyncio.run(self.service.ingest_ui_action(start_payload, route_data))
        self.assertIsNotNone(start_result["nav_hint"])

        # Mismatch event does not advance step; hint signature remains same.
        event_payload = {
            "session_id": "ride_1",
            "event_id": "evt_mismatch",
            "ts_ms": 1200,
            "event_type": "TURN",
            "confidence": 0.8,
            "payload": {"turn_class": "LEFT"},
        }
        result = asyncio.run(self.service.ingest_visual_event(event_payload, now_ts_ms=1500))
        self.assertIsNone(result["nav_hint"])

    def test_dead_reckoning_endpoint_is_placeholder(self):
        result = asyncio.run(self.service.ingest_dead_reckoning_event({"dummy": 1}))
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "dead_reckoning_not_enabled")

    def test_connectivity_offline_transition_emits_start_commands(self):
        payload_1 = {
            "session_id": "ride_1",
            "ts_ms": 2000,
            "network_available": True,
            "internet_reachable": False,
        }
        payload_2 = {
            "session_id": "ride_1",
            "ts_ms": 2100,
            "network_available": False,
            "internet_reachable": False,
        }

        first = asyncio.run(self.service.update_connectivity_status(payload_1))
        second = asyncio.run(self.service.update_connectivity_status(payload_2))

        self.assertFalse(first["status_changed"])
        self.assertTrue(second["status_changed"])
        self.assertEqual(second["network_status"], "OFFLINE")
        self.assertEqual(len(second["commands"]), 2)
        self.assertEqual(second["commands"][0]["action"], "START")
        self.assertIn(second["nav_mode"], {"OFFLINE", "DEGRADED"})

    def test_connectivity_online_transition_emits_stop_commands(self):
        # First move to OFFLINE.
        asyncio.run(
            self.service.update_connectivity_status(
                {
                    "session_id": "ride_1",
                    "ts_ms": 3000,
                    "network_available": False,
                    "internet_reachable": False,
                }
            )
        )
        asyncio.run(
            self.service.update_connectivity_status(
                {
                    "session_id": "ride_1",
                    "ts_ms": 3100,
                    "network_available": False,
                    "internet_reachable": False,
                }
            )
        )

        # Then recover to ONLINE with hysteresis.
        first = asyncio.run(
            self.service.update_connectivity_status(
                {
                    "session_id": "ride_1",
                    "ts_ms": 3200,
                    "network_available": True,
                    "internet_reachable": True,
                }
            )
        )
        second = asyncio.run(
            self.service.update_connectivity_status(
                {
                    "session_id": "ride_1",
                    "ts_ms": 3300,
                    "network_available": True,
                    "internet_reachable": True,
                }
            )
        )

        self.assertFalse(first["status_changed"])
        self.assertTrue(second["status_changed"])
        self.assertEqual(second["network_status"], "ONLINE")
        self.assertEqual(len(second["commands"]), 2)
        self.assertEqual(second["commands"][0]["action"], "STOP")
        self.assertIn(second["nav_mode"], {"ONLINE", "DEGRADED"})

    def test_connectivity_payload_validation(self):
        with self.assertRaises(ContractValidationError):
            asyncio.run(self.service.update_connectivity_status({"session_id": "ride_1"}))

    def test_degraded_mode_on_low_confidence(self):
        start_payload = {
            "session_id": "ride_1",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        asyncio.run(self.service.ingest_ui_action(start_payload, self.route_data))

        # Send mismatching turn events to drive confidence below threshold.
        event_1 = {
            "session_id": "ride_1",
            "event_id": "evt_m1",
            "ts_ms": 2000,
            "event_type": "TURN",
            "confidence": 0.9,
            "payload": {"turn_class": "LEFT"},
        }
        event_2 = {
            "session_id": "ride_1",
            "event_id": "evt_m2",
            "ts_ms": 2300,
            "event_type": "TURN",
            "confidence": 0.9,
            "payload": {"turn_class": "LEFT"},
        }
        asyncio.run(self.service.ingest_visual_event(event_1, now_ts_ms=2600))
        result = asyncio.run(self.service.ingest_visual_event(event_2, now_ts_ms=3000))

        self.assertEqual(result["nav_mode"], "DEGRADED")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["degraded_reason"], "low_confidence")

    def test_degraded_mode_on_no_recent_events_while_offline(self):
        service = NavigationAPIService(
            offline_after_failures=1,
            online_after_successes=1,
            degraded_no_event_ms=1000,
        )
        start_payload = {
            "session_id": "ride_1",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        asyncio.run(service.ingest_ui_action(start_payload, self.route_data))

        # Move to offline immediately.
        asyncio.run(
            service.update_connectivity_status(
                {
                    "session_id": "ride_1",
                    "ts_ms": 1200,
                    "network_available": False,
                    "internet_reachable": False,
                }
            )
        )

        # No localization event arrives for more than degraded_no_event_ms.
        result = asyncio.run(
            service.update_connectivity_status(
                {
                    "session_id": "ride_1",
                    "ts_ms": 2601,
                    "network_available": False,
                    "internet_reachable": False,
                }
            )
        )

        self.assertEqual(result["nav_mode"], "DEGRADED")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["degraded_reason"], "no_recent_localization_events")


class TestNavigationConfidenceTracker(unittest.TestCase):

    def setUp(self):
        self.tracker = NavigationConfidenceTracker(initial_score=0.6)

    @staticmethod
    def _event(confidence: float, ts_ms: int, turn: TurnClass):
        return EventMessage(
            session_id="ride_1",
            event_id=f"evt_{ts_ms}",
            ts_ms=ts_ms,
            event_type=LocalizationEventType.TURN,
            confidence=confidence,
            payload=TurnPayload(turn_class=turn),
        )

    def test_confidence_increases_on_match(self):
        event = self._event(confidence=0.9, ts_ms=1000, turn=TurnClass.RIGHT)
        before = self.tracker.get_score()
        self.tracker.update_from_event(
            event,
            progress=ProgressUpdate(
                advanced=True,
                active_step_index=1,
                destination_reached=False,
                reason="step_advanced",
            ),
        )
        after = self.tracker.get_score()
        self.assertGreater(after, before)

    def test_confidence_decreases_on_mismatch(self):
        event = self._event(confidence=0.8, ts_ms=1000, turn=TurnClass.LEFT)
        before = self.tracker.get_score()
        self.tracker.update_from_event(
            event,
            progress=ProgressUpdate(
                advanced=False,
                active_step_index=0,
                destination_reached=False,
                reason="no_match",
            ),
        )
        after = self.tracker.get_score()
        self.assertLess(after, before)

    def test_confidence_time_decay(self):
        event = self._event(confidence=0.9, ts_ms=1000, turn=TurnClass.RIGHT)
        self.tracker.update_from_event(
            event,
            progress=ProgressUpdate(
                advanced=True,
                active_step_index=1,
                destination_reached=False,
                reason="step_advanced",
            ),
        )
        before_decay = self.tracker.get_score()
        self.tracker.apply_time_decay(now_ts_ms=12_000)
        after_decay = self.tracker.get_score()
        self.assertLess(after_decay, before_decay)


if __name__ == "__main__":
    unittest.main()
