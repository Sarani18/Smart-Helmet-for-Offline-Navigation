from __future__ import annotations
from enum import Enum


class LEDPattern(Enum):
    OFF         = "off"
    SOLID_GREEN = "solid_green"
    BLINK_LEFT  = "blink_left"
    BLINK_RIGHT = "blink_right"
    BLINK_BOTH  = "blink_both"
    SOLID_RED   = "solid_red"
    RAPID_RED   = "rapid_red"
    SOLID_BLUE  = "solid_blue"
    BLINK_BLUE  = "blink_blue"


class LEDController:
    INSTRUCTION_MAP = {
        "left":        LEDPattern.BLINK_LEFT,
        "right":       LEDPattern.BLINK_RIGHT,
        "u-turn":      LEDPattern.BLINK_BOTH,
        "arrive":      LEDPattern.BLINK_BOTH,
        "destination": LEDPattern.BLINK_BOTH,
        "straight":    LEDPattern.SOLID_GREEN,
        "gps lost":    LEDPattern.SOLID_RED,
        "crash":       LEDPattern.RAPID_RED,
        "connected":   LEDPattern.SOLID_BLUE,
        "scanning":    LEDPattern.BLINK_BLUE,
    }

    def __init__(self) -> None:
        self._active_pattern = LEDPattern.OFF

    def apply_pattern(self, pattern: LEDPattern) -> None:
        self._active_pattern = pattern
        # TODO: write to GPIO / send over BLE

    def instruction_to_led(self, instruction: str) -> LEDPattern:
        lower = instruction.lower()
        for keyword, pattern in self.INSTRUCTION_MAP.items():
            if keyword in lower:
                self.apply_pattern(pattern)
                return pattern
        self.apply_pattern(LEDPattern.SOLID_GREEN)
        return LEDPattern.SOLID_GREEN

    def turn_off(self) -> None:
        self.apply_pattern(LEDPattern.OFF)

    @property
    def active_pattern(self) -> LEDPattern:
        return self._active_pattern