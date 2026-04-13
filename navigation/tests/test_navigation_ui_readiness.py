"""Readiness checks for Navigation API communication with app UI."""

import os
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from navigation.api_service import NavigationAPIService
from navigation.offline_cache import OfflineCache
from navigation.vision_bridge import NavigationVisionBridge
import navigation.server as nav_server


class TestNavigationUIReadiness(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._old_bridge = nav_server.bridge
        nav_server.bridge = NavigationVisionBridge(
            service=NavigationAPIService(
                offline_cache=OfflineCache(cache_dir=self._tmpdir),
                offline_after_failures=2,
                online_after_successes=2,
            ),
            nav_hint_sender=None,
            ui_state_sender=None,
        )
        self.client = TestClient(nav_server.app)
        self.route_data = {
            "origin": {"lat": 19.076, "lon": 72.877, "label": "Home"},
            "destination": {"lat": 19.100, "lon": 72.900, "label": "Airport"},
            "steps": [
                {
                    "lat": 19.078,
                    "lon": 72.879,
                    "instruction": "Turn right",
                    "distance": 300,
                }
            ],
        }

    def tearDown(self):
        nav_server.bridge = self._old_bridge

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    def test_ui_action_start_route_contract(self):
        response = self.client.post(
            "/api/navigation/ui/action",
            json={
                "session_id": "ride_ui_1",
                "ts_ms": 1000,
                "action_type": "START_NAVIGATION",
                "payload": {"origin": "A", "destination": "B"},
                "route_data": self.route_data,
            },
        )
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["action_type"], "START_NAVIGATION")
        self.assertEqual(body["reason"], "route_loaded")
        self.assertIn("nav_mode", body)
        self.assertIn("mode_reason", body)
        self.assertIn("mode_changed", body)
        self.assertIn("localization_control_commands", body)
        self.assertEqual(len(body["localization_control_commands"]), 2)
        self.assertIn("ui_state", body)
        self.assertEqual(body["ui_state"]["session_id"], "ride_ui_1")
        self.assertIn("next_instruction_text", body["ui_state"])
        self.assertIn("route_polyline", body["ui_state"])
        self.assertEqual(body["ui_state_delivery"]["status"], "no_sender")

    def test_ui_state_endpoint_returns_expected_fields(self):
        self.client.post(
            "/api/navigation/ui/action",
            json={
                "session_id": "ride_ui_2",
                "ts_ms": 1000,
                "action_type": "START_NAVIGATION",
                "payload": {"origin": "A", "destination": "B"},
                "route_data": self.route_data,
            },
        )

        response = self.client.post(
            "/api/navigation/ui/state",
            json={"session_id": "ride_ui_2", "ts_ms": 1500},
        )
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertIn("ui_state", body)
        ui_state = body["ui_state"]
        self.assertEqual(ui_state["session_id"], "ride_ui_2")
        self.assertIn(ui_state["nav_mode"], {"ONLINE", "OFFLINE", "DEGRADED"})
        self.assertIn(ui_state["position_mode"], {"GPS", "VISUAL", "UNKNOWN"})
        self.assertIn("distance_to_next_m", ui_state)
        self.assertIn("confidence", ui_state)

    def test_invalid_ui_action_returns_400(self):
        response = self.client.post(
            "/api/navigation/ui/action",
            json={
                "session_id": "ride_ui_3",
                "ts_ms": 1100,
                "action_type": "PAUSE_NAVIGATION",
                "payload": {},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid action_type", response.json().get("detail", ""))

    def test_connectivity_hysteresis_contract(self):
        first = self.client.post(
            "/api/navigation/connectivity/status",
            json={
                "session_id": "ride_ui_4",
                "ts_ms": 2000,
                "network_available": False,
                "internet_reachable": False,
            },
        )
        second = self.client.post(
            "/api/navigation/connectivity/status",
            json={
                "session_id": "ride_ui_4",
                "ts_ms": 2100,
                "network_available": False,
                "internet_reachable": False,
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        first_body = first.json()
        second_body = second.json()
        self.assertFalse(first_body["status_changed"])
        self.assertTrue(second_body["status_changed"])
        self.assertEqual(second_body["network_status"], "OFFLINE")
        self.assertEqual(len(second_body["commands"]), 2)

    def test_cors_preflight_for_web_ui(self):
        response = self.client.options(
            "/api/navigation/ui/action",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertIn(response.status_code, (200, 204))
        allow_origin = response.headers.get("access-control-allow-origin")
        self.assertIn(allow_origin, {"*", "http://localhost:3000"})


if __name__ == "__main__":
    unittest.main()
