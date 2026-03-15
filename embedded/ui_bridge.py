"""
ui_bridge.py
------------
Replaces position_bridge.py.

Receives UIStateMessage brain/navigation module and:
  1. Updates UIManager (HUD text, speed, heading, GPS status)
  2. Fires LEDController (turn signals on helmet)
  3. Broadcasts the full state over WebSocket to browser / Android map UI

Sends UIActionMessage back to brain when the rider interacts with the UI.
"""

from __future__ import annotations

import time
from typing import Optional, Callable

from .nav_interface import (
    UIStateMessage, UIActionMessage,
    UIActionType, StartNavigationPayload, RerouteRequestPayload,
    NavMode, PositionMode, TurnClass
)
from .app_interface.ui_manager import UIManager
from .led_controller import LEDController


# Maps instruction text keywords → LED pattern keywords understood by LEDController
_INSTRUCTION_TO_LED_KEYWORD = {
    "left":        "left",
    "right":       "right",
    "u-turn":      "u-turn",
    "u_turn":      "u-turn",
    "arrive":      "arrive",
    "destination": "arrive",
    "lost":        "gps lost",
    "crash":       "crash",
}


class UIBridge:
    def __init__(
        self,
        ui_manager:     Optional[UIManager]     = None,
        led_controller: Optional[LEDController] = None,
    ) -> None:
        self._ui  = ui_manager     or UIManager()
        self._led = led_controller or LEDController()

        self._latest_state: Optional[UIStateMessage] = None

        # Called with the serialised state dict every time a UIStateMessage arrives.
        # The WebSocket server registers here to broadcast to clients.
        self._on_state_update: Optional[Callable[[dict], None]] = None

        # Called with UIActionMessage when the user triggers an action.
        # nav module registers here to receive user actions.
        self._on_action: Optional[Callable[[UIActionMessage], None]] = None

        self._session_id: str = ""

    # ── Registration ─────────────────────────────────────────────────────────

    def register_state_callback(self, fn: Callable[[dict], None]) -> None:
        """WebSocket server registers here. fn receives a JSON-serialisable dict."""
        self._on_state_update = fn

    def register_action_callback(self, fn: Callable[[UIActionMessage], None]) -> None:
        """nav module registers here to receive user-triggered actions."""
        self._on_action = fn

    # ── Inbound: Navigation → UIBridge ───────────────────────────────────────

    def on_ui_state(self, state: UIStateMessage) -> None:
        """
        Called by navigation module at 2-5 Hz.
        This is the ONLY inbound method for the map UI.

        What it does:
          - Extracts current position from the tail of route_polyline
          - Updates HUD instruction text and distance
          - Updates GPS / position mode status
          - Fires LED for the next turn
          - Broadcasts full state dict to WebSocket clients
        """
        self._latest_state = state
        self._session_id   = state.session_id

        # 1. Update HUD text
        self._ui.update_instruction(
            state.next_instruction_text,
            state.distance_to_next_m,
        )

        # 2. Update GPS status banner
        gps_ok = state.position_mode in (PositionMode.GPS, PositionMode.VISUAL)
        self._ui.update_gps_status(gps_ok)

        # 3. Crash / off-route states
        if state.off_route_flag:
            self._ui.update_instruction("Off route — recalculating", 0)
            self._led.instruction_to_led("gps lost")  # solid red = off route
        elif state.destination_reached_flag:
            self._ui.update_instruction("You have arrived", 0)
            self._led.instruction_to_led("arrive")
        else:
            # 4. LED from instruction text
            lower = state.next_instruction_text.lower()
            led_kw = "straight"
            for kw, led in _INSTRUCTION_TO_LED_KEYWORD.items():
                if kw in lower:
                    led_kw = led
                    break
            self._led.instruction_to_led(led_kw)

        # 5. Broadcast to WebSocket → browser / Android
        if self._on_state_update:
            self._on_state_update(state.to_ws_dict())

    # ── Outbound: UIBridge → Navigation ──────────────────────────────────────

    def start_navigation(self, origin: str, destination: str) -> UIActionMessage:
        """Call when the rider taps START. Returns the action; also fires callback."""
        action = UIActionMessage(
            session_id  = self._session_id or f"ride_{int(time.time())}",
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.START_NAVIGATION,
            payload     = StartNavigationPayload(origin=origin, destination=destination),
        )
        if self._on_action:
            self._on_action(action)
        return action

    def stop_navigation(self) -> UIActionMessage:
        """Call when the rider taps STOP."""
        action = UIActionMessage(
            session_id  = self._session_id,
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.STOP_NAVIGATION,
            payload     = None,
        )
        if self._on_action:
            self._on_action(action)
        return action

    def request_reroute(self, reason: str = "user_request") -> UIActionMessage:
        """Call when the rider taps REROUTE."""
        action = UIActionMessage(
            session_id  = self._session_id,
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.REROUTE_REQUEST,
            payload     = RerouteRequestPayload(reason=reason),
        )
        if self._on_action:
            self._on_action(action)
        return action

    # ── Read-back ─────────────────────────────────────────────────────────────

    @property
    def latest_state(self) -> Optional[UIStateMessage]:
        return self._latest_state

    def get_current_position(self) -> Optional[dict]:
        """Returns {lat, lng} of the current rider position, or None."""
        s = self._latest_state
        if s and s.current_lat() is not None:
            return {"lat": s.current_lat(), "lng": s.current_lng()}
        return None