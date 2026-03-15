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
from typing import Callable, Optional

from .nav_interface import (
    UIStateMessage, UIActionMessage,
    UIActionType, StartNavigationPayload, RerouteRequestPayload,
    PositionMode,
)
from .app_interface.ui_manager import UIManager
from .led_controller import LEDController

_LED_KEYWORDS = {
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

        self._latest_state: Optional[UIStateMessage]           = None
        self._on_state_update: Optional[Callable[[dict], None]] = None
        self._on_action: Optional[Callable[[UIActionMessage], None]] = None
        self._session_id = ""

    def register_state_callback(self, fn: Callable[[dict], None]) -> None:
        self._on_state_update = fn

    def register_action_callback(self, fn: Callable[[UIActionMessage], None]) -> None:
        self._on_action = fn

    def on_ui_state(self, state: UIStateMessage) -> None:
        self._latest_state = state
        self._session_id   = state.session_id

        self._ui.update_instruction(state.next_instruction_text, state.distance_to_next_m)
        self._ui.update_gps_status(state.position_mode in (PositionMode.GPS, PositionMode.VISUAL))

        if state.off_route_flag:
            self._ui.update_instruction("Off route — recalculating", 0)
            self._led.instruction_to_led("gps lost")
        elif state.destination_reached_flag:
            self._ui.update_instruction("You have arrived", 0)
            self._led.instruction_to_led("arrive")
        else:
            lower  = state.next_instruction_text.lower()
            led_kw = next((v for k, v in _LED_KEYWORDS.items() if k in lower), "straight")
            self._led.instruction_to_led(led_kw)

        if self._on_state_update:
            self._on_state_update(state.to_ws_dict())

    def start_navigation(self, origin: str, destination: str) -> UIActionMessage:
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
        action = UIActionMessage(
            session_id  = self._session_id,
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.STOP_NAVIGATION,
        )
        if self._on_action:
            self._on_action(action)
        return action

    def request_reroute(self, reason: str = "user_request") -> UIActionMessage:
        action = UIActionMessage(
            session_id  = self._session_id,
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.REROUTE_REQUEST,
            payload     = RerouteRequestPayload(reason=reason),
        )
        if self._on_action:
            self._on_action(action)
        return action

    @property
    def latest_state(self) -> Optional[UIStateMessage]:
        return self._latest_state

    def get_current_position(self) -> Optional[dict]:
        s = self._latest_state
        if s and s.current_lat() is not None:
            return {"lat": s.current_lat(), "lng": s.current_lng()}
        return None