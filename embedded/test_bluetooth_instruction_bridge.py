import time

from embedded.bluetooth_instruction_bridge import (
    BluetoothInstructionBridge,
    command_from_ui_state,
)
from embedded.nav_interface import NavMode, PositionMode, UIStateMessage


class FakeWriter:
    def __init__(self):
        self.lines = []

    def send_line(self, line: str) -> bool:
        self.lines.append(line)
        return True

    def close(self) -> None:
        pass


def make_state(instruction, **overrides):
    values = {
        "session_id": "ride_test",
        "ts_ms": 1000,
        "nav_mode": NavMode.OFFLINE,
        "position_mode": PositionMode.VISUAL,
        "next_instruction_text": instruction,
        "distance_to_next_m": 50.0,
        "confidence": 0.9,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 1,
        "route_polyline": [[19.0, 73.0]],
    }
    values.update(overrides)
    return UIStateMessage(**values)


def test_command_mapping_uses_map_instruction_text():
    assert command_from_ui_state(make_state("In 40 m, turn left")) == "LEFT"
    assert command_from_ui_state(make_state("Keep slight right at junction")) == "RIGHT"
    assert command_from_ui_state(make_state("Continue straight")) == "STRAIGHT"


def test_safety_and_terminal_states_have_priority():
    assert command_from_ui_state(make_state("Turn left", off_route_flag=True)) == "HAZARD"
    assert command_from_ui_state(make_state("CRASH DETECTED - SOS sent")) == "SOS_ON"
    assert command_from_ui_state(make_state("Turn right", destination_reached_flag=True)) == "ARRIVED"


def test_bridge_sends_only_changed_commands_without_blocking_ui_path():
    writer = FakeWriter()
    bridge = BluetoothInstructionBridge(writer=writer, enabled=True)

    bridge.publish_ui_state(make_state("Turn right"))
    bridge.publish_ui_state(make_state("Turn right"))
    bridge.publish_ui_state(make_state("Turn left"))

    deadline = time.time() + 2.0
    while len(writer.lines) < 2 and time.time() < deadline:
        time.sleep(0.01)

    bridge.close()
    assert writer.lines == ["RIGHT", "LEFT"]
