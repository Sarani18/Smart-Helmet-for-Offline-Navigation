"""
LED Controller
--------------
Controls the helmet's indicator LEDs to give the rider turn-direction
feedback without requiring them to look at a screen.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class LEDPattern(Enum):
    """Pre-defined LED blink/glow patterns for each navigation event."""

    OFF = "off"
    SOLID_GREEN = "solid_green"        # GPS fix confirmed / on-route
    BLINK_LEFT = "blink_left"          # Turn left
    BLINK_RIGHT = "blink_right"        # Turn right
    BLINK_BOTH = "blink_both"          # Destination reached / U-turn
    SOLID_RED = "solid_red"            # GPS lost / off-route
    RAPID_RED = "rapid_red"            # Crash / SOS triggered
    SOLID_BLUE = "solid_blue"          # Bluetooth connected
    BLINK_BLUE = "blink_blue"          # Bluetooth scanning / pairing


class LEDController:
    """
    Translates navigation instructions into LED output commands for the
    helmet-mounted microcontroller.

    In production the :meth:`apply_pattern` method would write to a GPIO
    pin (or send a packet to the embedded MCU over the serial/BLE link).
    The current implementation stores the active pattern for testing.

    Responsibilities
    ----------------
    - Map navigation instructions ("Turn left", "Arrive", etc.) to LED patterns.
    - Apply a requested LED pattern immediately.
    - Manage a timed auto-off so LEDs do not stay on indefinitely.
    - Provide a status read-back for the test harness.
    """

    # Mapping from instruction keywords to LED patterns
    INSTRUCTION_MAP = {
        "left": LEDPattern.BLINK_LEFT,
        "right": LEDPattern.BLINK_RIGHT,
        "u-turn": LEDPattern.BLINK_BOTH,
        "arrive": LEDPattern.BLINK_BOTH,
        "destination": LEDPattern.BLINK_BOTH,
        "straight": LEDPattern.SOLID_GREEN,
        "gps lost": LEDPattern.SOLID_RED,
        "crash": LEDPattern.RAPID_RED,
        "connected": LEDPattern.SOLID_BLUE,
        "scanning": LEDPattern.BLINK_BLUE,
    }

    def __init__(self) -> None:
        self._active_pattern = LEDPattern.OFF

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_pattern(self, pattern: LEDPattern) -> None:
        """
        Activate the given LED pattern.

        In a real build this method sends a command byte to the MCU.
        """
        self._active_pattern = pattern
        # TODO: write to GPIO / send over BluetoothComm

    def instruction_to_led(self, instruction: str) -> LEDPattern:
        """
        Convert a human-readable navigation instruction string to the
        appropriate :class:`LEDPattern` and apply it.

        Parameters
        ----------
        instruction:
            A string such as ``"Turn left"`` or ``"Turn sharply right"``.

        Returns
        -------
        LEDPattern
            The pattern that was applied.
        """
        lower = instruction.lower()
        for keyword, pattern in self.INSTRUCTION_MAP.items():
            if keyword in lower:
                self.apply_pattern(pattern)
                return pattern
        self.apply_pattern(LEDPattern.SOLID_GREEN)
        return LEDPattern.SOLID_GREEN

    def turn_off(self) -> None:
        """Turn all LEDs off."""
        self.apply_pattern(LEDPattern.OFF)

    @property
    def active_pattern(self) -> LEDPattern:
        """The currently active LED pattern."""
        return self._active_pattern
