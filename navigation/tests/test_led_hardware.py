import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from navigation.api_service import NavigationAPIService
from navigation.hardware_service import HardwareService
from navigation.led_command_mapper import command_from_ui_state


class FakeBluetoothTransport:
    def __init__(self):
        self.commands = []

    def send(self, command):
        self.commands.append(command)
        return True


class FakeHardware:
    def __init__(self):
        self.states = []

    async def update_from_ui_state(self, ui_state):
        self.states.append(dict(ui_state))


class TestLEDCommandMapper(unittest.TestCase):
    def test_maps_turn_instructions(self):
        self.assertEqual(
            command_from_ui_state({"next_instruction_text": "In 40 m, turn right"}),
            "RIGHT_NOW",
        )
        self.assertEqual(
            command_from_ui_state({"next_instruction_text": "Turn left on MG Road"}),
            "LEFT_NOW",
        )

    def test_maps_safety_and_terminal_states_first(self):
        self.assertEqual(
            command_from_ui_state(
                {"is_emergency": True, "next_instruction_text": "Turn right"}
            ),
            "SOS_ON",
        )
        self.assertEqual(
            command_from_ui_state(
                {"off_route_flag": True, "next_instruction_text": "Turn left"}
            ),
            "HAZARD",
        )
        self.assertEqual(
            command_from_ui_state(
                {"destination_reached_flag": True, "next_instruction_text": "Turn left"}
            ),
            "ARRIVED",
        )

    def test_defaults_to_straight(self):
        self.assertEqual(
            command_from_ui_state({"next_instruction_text": "Continue straight"}),
            "STRAIGHT",
        )


class TestHardwareServiceBluetooth(unittest.TestCase):
    def test_bluetooth_send_uses_queue_and_suppresses_duplicates(self):
        service = HardwareService(transport="bluetooth", bluetooth_port=None)
        fake = FakeBluetoothTransport()
        service._bt_transport = fake

        asyncio.run(service.send_command("RIGHT_NOW"))
        asyncio.run(service.send_command("RIGHT_NOW"))
        asyncio.run(service.send_command("LEFT_NOW"))

        self.assertEqual(fake.commands, ["RIGHT_NOW", "LEFT_NOW"])


class TestNavigationLEDIntegration(unittest.TestCase):
    def test_dead_reckoning_update_publishes_same_ui_state_to_hardware(self):
        service = NavigationAPIService(enable_tile_prefetch=False)
        fake = FakeHardware()
        service.hardware = fake

        route_data = {
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

        asyncio.run(
            service.ingest_ui_action(
                {
                    "session_id": "ride_led",
                    "ts_ms": 1000,
                    "action_type": "START_NAVIGATION",
                    "payload": {"origin": "A", "destination": "B"},
                },
                route_data=route_data,
            )
        )
        result = asyncio.run(
            service.ingest_dead_reckoning_event(
                {
                    "session_id": "ride_led",
                    "ts_ms": 1100,
                    "lat": 19.0779,
                    "lon": 72.8789,
                    "heading": 86.0,
                }
            )
        )

        self.assertTrue(result["accepted"])
        self.assertGreaterEqual(len(fake.states), 2)
        self.assertEqual(fake.states[-1]["next_instruction_text"], result["ui_state"]["next_instruction_text"])
        self.assertEqual(command_from_ui_state(fake.states[-1]), "RIGHT_NOW")


if __name__ == "__main__":
    unittest.main()
