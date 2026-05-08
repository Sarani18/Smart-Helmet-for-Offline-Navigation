from __future__ import annotations

from typing import Any, Dict, Optional


VALID_LED_COMMANDS = {
    "CLEAR",
    "STRAIGHT",
    "LEFT",
    "LEFT_PREPARE",
    "LEFT_NOW",
    "LEFT_MISSED",
    "RIGHT",
    "RIGHT_PREPARE",
    "RIGHT_NOW",
    "RIGHT_MISSED",
    "HAZARD",
    "SOS_ON",
    "SOS_OFF",
    "ARRIVED",
    "PING",
}


def normalize_led_command(command: str) -> str:
    value = command.strip().upper()
    if value not in VALID_LED_COMMANDS:
        raise ValueError(f"Unsupported LED command: {command}")
    return value


def command_from_ui_state(ui_state: Dict[str, Any]) -> str:
    if ui_state.get("is_emergency"):
        return "SOS_ON"
    if ui_state.get("destination_reached_flag"):
        return "ARRIVED"
    if ui_state.get("off_route_flag"):
        return "HAZARD"

    instruction = str(ui_state.get("next_instruction_text") or "").upper()
    if "ARRIVE" in instruction or "DESTINATION" in instruction:
        return "ARRIVED"
    if "U-TURN" in instruction or "U TURN" in instruction:
        return "RIGHT_NOW"
    if "RIGHT" in instruction:
        return "RIGHT_NOW"
    if "LEFT" in instruction:
        return "LEFT_NOW"
    return "STRAIGHT"


def command_from_instruction(
    instruction: str,
    *,
    is_gps_failed: bool = False,
    is_emergency: bool = False,
    off_route: bool = False,
    destination_reached: bool = False,
) -> str:
    return command_from_ui_state(
        {
            "next_instruction_text": instruction,
            "is_emergency": is_emergency,
            "off_route_flag": off_route or is_gps_failed,
            "destination_reached_flag": destination_reached,
        }
    )


def describe_ui_state(ui_state: Dict[str, Any]) -> str:
    instruction = str(ui_state.get("next_instruction_text") or "")
    if len(instruction) > 80:
        instruction = instruction[:77] + "..."
    return (
        f"instruction={instruction!r} "
        f"step={ui_state.get('active_step_index')} "
        f"distance={ui_state.get('distance_to_next_m')} "
        f"emergency={bool(ui_state.get('is_emergency'))}"
    )
