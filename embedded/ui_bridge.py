"""
ui_bridge.py
------------
Master logic hub between Sanskruti's navigation brain and all outputs.

Inbound  (Sanskruti → here via websocket_server.receive_ui_state):
    UIStateMessage at 2-5 Hz

Outbound (here → Sanskruti via registered callback):
    UIActionMessage — sent when rider taps Start / Stop / Reroute

Outbound (here → browser/app via WebSocket broadcast):
    UIStateMessage serialised as JSON

Outbound (here → helmet hardware):
    LEDController pattern updates

Mode combinations per integration spec:
    ONLINE  + GPS     — normal navigation, OSM tiles live
    ONLINE  + VISUAL  — nav online but GPS lost, Vijit CV active
    OFFLINE + GPS     — GPS fix, no internet, cached tiles
    OFFLINE + VISUAL  — no internet, no GPS, Vijit CV active
    DEGRADED + VISUAL — partial signal, Vijit CV only
    DEGRADED + UNKNOWN — no signal at all, last known position
"""
from __future__ import annotations
import time
from typing import Callable, Optional

from .nav_interface import (
    UIStateMessage, UIActionMessage,
    UIActionType, StartNavigationPayload, RerouteRequestPayload,
    NavMode, PositionMode,
)
from .app_interface.ui_manager import UIManager
from .led_controller import LEDController

_LED_KEYWORDS: dict[str, str] = {
    "left":        "left",
    "right":       "right",
    "u-turn":      "u-turn",
    "u_turn":      "u-turn",
    "arrive":      "arrive",
    "destination": "arrive",
    "lost":        "gps lost",
    "crash":       "crash",
    "sos":         "crash",
}


class UIBridge:
    def __init__(
        self,
        ui_manager:     Optional[UIManager]     = None,
        led_controller: Optional[LEDController] = None,
    ) -> None:
        self._ui  = ui_manager     or UIManager()
        self._led = led_controller or LEDController()

        self._latest_state:    Optional[UIStateMessage]                   = None
        self._on_state_update: Optional[Callable[[dict], None]]           = None
        self._on_action:       Optional[Callable[[UIActionMessage], None]] = None
        self._session_id = ""

    # ── registration ─────────────────────────────────────────────────────────

    def register_state_callback(self, fn: Callable[[dict], None]) -> None:
        self._on_state_update = fn

    def register_action_callback(self, fn: Callable[[UIActionMessage], None]) -> None:
        self._on_action = fn

    # ── inbound — called by websocket_server.receive_ui_state ────────────────

    def on_ui_state(self, state: UIStateMessage) -> None:
        """
        Entry point for every UIStateMessage from Sanskruti.
        1. Updates UIManager display state
        2. Fires correct LED pattern based on mode combination
        3. Broadcasts full state JSON to WebSocket clients (browser/app)
        """
        self._latest_state = state
        self._session_id   = state.session_id
        lower = state.next_instruction_text.lower()

        # GPS active = GPS or VISUAL (Vijit CV localization)
        gps_active = state.position_mode in (PositionMode.GPS, PositionMode.VISUAL)
        self._ui.update_gps_status(gps_active)
        self._ui.update_instruction(state.next_instruction_text, state.distance_to_next_m)

        # LED logic — priority order: crash > off-route > destination > turn instruction
        if "crash" in lower or "sos" in lower:
            self._led.instruction_to_led("crash")
            self._ui.show_crash_alert()
        elif state.off_route_flag:
            self._ui.update_instruction("Off route — recalculating", 0)
            self._led.instruction_to_led("gps lost")
        elif state.destination_reached_flag:
            self._ui.update_instruction("You have arrived", 0)
            self._led.instruction_to_led("arrive")
        elif state.position_mode == PositionMode.UNKNOWN:
            # DEGRADED + UNKNOWN — no position at all
            self._led.instruction_to_led("gps lost")
        else:
            led_kw = next((v for k, v in _LED_KEYWORDS.items() if k in lower), "straight")
            self._led.instruction_to_led(led_kw)

        # Broadcast to all WebSocket clients
        if self._on_state_update:
            self._on_state_update(state.to_ws_dict())

    # ── outbound — UI actions sent back to Sanskruti as UIActionMessage ───────
    # These are proper API calls per section 4 of the integration spec.

    def start_navigation(self, origin: str, destination: str) -> UIActionMessage:
        """
        Sends START_NAVIGATION to Sanskruti.
        Triggered when rider taps Start in the UI.
        """
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
        """Sends STOP_NAVIGATION to Sanskruti."""
        action = UIActionMessage(
            session_id  = self._session_id,
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.STOP_NAVIGATION,
        )
        if self._on_action:
            self._on_action(action)
        return action

    def request_reroute(self, reason: str = "user_request") -> UIActionMessage:
        """Sends REROUTE_REQUEST to Sanskruti."""
        action = UIActionMessage(
            session_id  = self._session_id,
            ts_ms       = int(time.time() * 1000),
            action_type = UIActionType.REROUTE_REQUEST,
            payload     = RerouteRequestPayload(reason=reason),
        )
        if self._on_action:
            self._on_action(action)
        return action

    # ── read-back ─────────────────────────────────────────────────────────────

    @property
    def latest_state(self) -> Optional[UIStateMessage]:
        return self._latest_state

    def get_current_position(self) -> Optional[dict]:
        s = self._latest_state
        if s and s.current_lat() is not None:
            return {"lat": s.current_lat(), "lng": s.current_lng()}
        return None