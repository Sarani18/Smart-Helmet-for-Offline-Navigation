"""
UI Manager
----------
Manages the mobile application's real-time navigation feedback display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class NavDisplay:
    """
    The complete set of values shown on the navigation screen at any instant.

    Attributes
    ----------
    instruction : str
        The current turn instruction, e.g. ``"Turn right in 200 m"``.
    distance_meters : float
        Distance to the next manoeuvre in metres.
    speed_kph : float
        Current riding speed in km/h.
    gps_active : bool
        ``True`` when GPS is providing a live fix.
    heading_degrees : float
        Compass heading (0–360°).
    signal_strength : int
        BLE signal strength indicator (0–4 bars).
    """

    instruction: str = ""
    distance_meters: float = 0.0
    speed_kph: float = 0.0
    gps_active: bool = True
    heading_degrees: float = 0.0
    signal_strength: int = 0


class UIManager:
    """
    Renders the navigation state onto the mobile app's display layer.

    In a real Flutter/React-Native application, this class would update the
    relevant state variables and trigger a UI rebuild.  Here it maintains an
    in-memory :class:`NavDisplay` that tests can inspect.

    Responsibilities
    ----------------
    - Keep the :class:`NavDisplay` state up-to-date as the ride progresses.
    - Format raw values into user-friendly strings (e.g. "In 200 m, turn right").
    - Toggle between *GPS active* and *offline / dead-reckoning* mode banners.
    - Surface the BLE signal-strength indicator to the user.
    """

    def __init__(self) -> None:
        self._display = NavDisplay()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_instruction(self, instruction: str, distance_meters: float) -> None:
        """Update the turn instruction and distance shown to the rider."""
        self._display.instruction = self._format_instruction(instruction, distance_meters)
        self._display.distance_meters = distance_meters

    def update_speed(self, speed_kph: float) -> None:
        """Update the live speed readout."""
        self._display.speed_kph = round(speed_kph, 1)

    def update_gps_status(self, active: bool) -> None:
        """Switch between GPS-active and offline-mode banner."""
        self._display.gps_active = active

    def update_heading(self, heading_degrees: float) -> None:
        """Update the compass heading display."""
        self._display.heading_degrees = heading_degrees % 360

    def update_signal_strength(self, rssi_dbm: int) -> None:
        """
        Convert a raw RSSI value (dBm) to a 0–4 bar representation and store it.
        """
        if rssi_dbm >= -60:
            bars = 4
        elif rssi_dbm >= -70:
            bars = 3
        elif rssi_dbm >= -80:
            bars = 2
        elif rssi_dbm >= -90:
            bars = 1
        else:
            bars = 0
        self._display.signal_strength = bars

    def show_crash_alert(self) -> None:
        """Display a crash / emergency alert banner."""
        self._display.instruction = "⚠ CRASH DETECTED – SOS sent"

    def get_display(self) -> NavDisplay:
        """Return the current display state (read-only snapshot)."""
        return NavDisplay(**self._display.__dict__)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_instruction(instruction: str, distance_meters: float) -> str:
        if distance_meters > 0:
            if distance_meters >= 1000:
                dist_str = f"in {distance_meters / 1000:.1f} km"
            else:
                dist_str = f"in {int(distance_meters)} m"
            return f"{dist_str}, {instruction}"
        return instruction
