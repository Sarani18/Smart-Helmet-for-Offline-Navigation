"""Integration-oriented tests for Navigation <-> Vision bridge behavior."""

import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from navigation.api_service import NavigationAPIService
from navigation.offline_cache import OfflineCache
from navigation.vision_bridge import NavigationVisionBridge


class TestNavigationVisionBridge(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.service = NavigationAPIService(
            offline_cache=OfflineCache(cache_dir=self.tmpdir),
            offline_after_failures=1,
            online_after_successes=1,
        )
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

    def test_start_navigation_dispatches_hint_to_vision(self):
        sent_hints = []

        async def sender(hint):
            sent_hints.append(hint)
            return {"ok": True, "status_code": 200, "body": {"status": "success"}}

        bridge = NavigationVisionBridge(service=self.service, nav_hint_sender=sender)
        payload = {
            "session_id": "ride_bridge_1",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }

        result = asyncio.run(bridge.ingest_ui_action(payload, route_data=self.route_data))

        self.assertTrue(result["accepted"])
        self.assertIsNotNone(result["nav_hint"])
        self.assertEqual(result["nav_hint"]["expected_next_turn"], "RIGHT")
        self.assertEqual(result["nav_hint_delivery"]["attempted"], True)
        self.assertEqual(result["nav_hint_delivery"]["sent"], True)
        self.assertEqual(result["nav_hint_delivery"]["status"], "delivered")
        self.assertEqual(len(sent_hints), 1)

    def test_visual_event_with_no_new_hint_skips_delivery(self):
        sent_hints = []

        async def sender(hint):
            sent_hints.append(hint)
            return {"ok": True}

        bridge = NavigationVisionBridge(service=self.service, nav_hint_sender=sender)

        start_payload = {
            "session_id": "ride_bridge_2",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }
        asyncio.run(bridge.ingest_ui_action(start_payload, route_data=self.route_data))

        event_payload = {
            "session_id": "ride_bridge_2",
            "event_id": "evt_1",
            "ts_ms": 1200,
            "event_type": "TURN",
            "confidence": 0.95,
            "payload": {"turn_class": "RIGHT"},
        }
        result = asyncio.run(bridge.ingest_visual_event(event_payload, now_ts_ms=1500))

        self.assertTrue(result["accepted"])
        self.assertIsNone(result["nav_hint"])
        self.assertEqual(result["nav_hint_delivery"]["attempted"], False)
        self.assertEqual(result["nav_hint_delivery"]["status"], "no_hint")
        self.assertEqual(len(sent_hints), 1)

    def test_sender_failure_does_not_break_navigation_response(self):
        async def failing_sender(_hint):
            raise RuntimeError("vision endpoint down")

        bridge = NavigationVisionBridge(service=self.service, nav_hint_sender=failing_sender)
        payload = {
            "session_id": "ride_bridge_3",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }

        result = asyncio.run(bridge.ingest_ui_action(payload, route_data=self.route_data))

        self.assertTrue(result["accepted"])
        self.assertEqual(result["nav_hint_delivery"]["attempted"], True)
        self.assertEqual(result["nav_hint_delivery"]["sent"], False)
        self.assertEqual(result["nav_hint_delivery"]["status"], "failed")
        self.assertIn("vision endpoint down", result["nav_hint_delivery"]["error"])

    def test_no_sender_reports_no_sender_status(self):
        bridge = NavigationVisionBridge(service=self.service, nav_hint_sender=None)
        payload = {
            "session_id": "ride_bridge_4",
            "ts_ms": 1000,
            "action_type": "START_NAVIGATION",
            "payload": {"origin": "A", "destination": "B"},
        }

        result = asyncio.run(bridge.ingest_ui_action(payload, route_data=self.route_data))

        self.assertTrue(result["accepted"])
        self.assertIsNotNone(result["nav_hint"])
        self.assertEqual(result["nav_hint_delivery"]["attempted"], False)
        self.assertEqual(result["nav_hint_delivery"]["sent"], False)
        self.assertEqual(result["nav_hint_delivery"]["status"], "no_sender")

    def test_connectivity_status_passthrough(self):
        bridge = NavigationVisionBridge(service=self.service, nav_hint_sender=None)
        result = asyncio.run(
            bridge.update_connectivity_status(
                {
                    "session_id": "ride_bridge_5",
                    "ts_ms": 2000,
                    "network_available": False,
                    "internet_reachable": False,
                }
            )
        )

        self.assertTrue(result["accepted"])
        self.assertIn(result["network_status"], {"ONLINE", "OFFLINE"})
        self.assertEqual(result["nav_hint_delivery"]["status"], "no_hint")


if __name__ == "__main__":
    unittest.main()
