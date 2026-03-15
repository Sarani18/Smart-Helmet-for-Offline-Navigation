"""
Navigation API service
----------------------
Async orchestration layer for API-style interactions between:
- localization -> navigation
- UI -> navigation

This layer is transport-agnostic and can be connected to FastAPI, Flask,
or any async web framework.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .contracts import (
    LocalizationControlAction,
    LocalizationControlMessage,
    LocalizationModuleType,
    NetworkStatus,
    UIActionType,
)
from .event_pipeline import LocalizationEventPipeline
from .event_validator import NavigationContractValidator
from .route_processor import RouteProcessor
from .route_progress import ProgressUpdate, RouteProgressEngine


class NavigationAPIService:
    """Async service facade for navigation API calls."""

    def __init__(
        self,
        validator: Optional[NavigationContractValidator] = None,
        pipeline: Optional[LocalizationEventPipeline] = None,
        progress_engine: Optional[RouteProgressEngine] = None,
        route_processor: Optional[RouteProcessor] = None,
        offline_after_failures: int = 2,
        online_after_successes: int = 2,
    ) -> None:
        self._validator = validator or NavigationContractValidator()
        self._pipeline = pipeline or LocalizationEventPipeline()
        self._progress = progress_engine or RouteProgressEngine()
        self._route_processor = route_processor or RouteProcessor()

        self._network_status = NetworkStatus.ONLINE
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._offline_after_failures = max(1, offline_after_failures)
        self._online_after_successes = max(1, online_after_successes)

    async def ingest_visual_event(
        self,
        payload: Dict[str, Any],
        now_ts_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Async handler for visual localization event API calls.

        Expected call pattern:
        - localization service sends one event per request
        - navigation validates, buffers, and processes ready events
        """
        event = self._validator.parse_localization_event(payload)
        now_ts_ms = now_ts_ms if now_ts_ms is not None else self._now_ms()

        ingest = self._pipeline.ingest(event, now_ts_ms)
        updates: List[ProgressUpdate] = []
        if ingest.accepted:
            for ready in self._pipeline.pop_ready(now_ts_ms):
                updates.append(self._progress.process_event(ready))

        return {
            "accepted": ingest.accepted,
            "reason": ingest.reason,
            "processed_count": len(updates),
            "active_step_index": self._progress.get_active_step_index(),
            "destination_reached": self._progress.is_destination_reached(),
            "progress_reasons": [update.reason for update in updates],
        }

    async def ingest_dead_reckoning_event(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Async placeholder for future dead-reckoning integration API.
        """
        _ = payload
        return {
            "accepted": False,
            "reason": "dead_reckoning_not_enabled",
        }

    async def ingest_ui_action(
        self,
        payload: Dict[str, Any],
        route_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Async handler for UI action API calls.

        For START_NAVIGATION and REROUTE_REQUEST, route_data must be provided
        by the caller (e.g. from maps backend response).
        """
        action = self._validator.parse_ui_action(payload)

        if action.action_type == UIActionType.STOP_NAVIGATION:
            self._progress.reset()
            return {
                "accepted": True,
                "action_type": action.action_type.value,
                "reason": "navigation_stopped",
            }

        if action.action_type in (UIActionType.START_NAVIGATION, UIActionType.REROUTE_REQUEST):
            if route_data is None:
                return {
                    "accepted": False,
                    "action_type": action.action_type.value,
                    "reason": "route_data_required",
                }

            route = self._route_processor.load_route(route_data)
            self._progress.load_route(route)

            return {
                "accepted": True,
                "action_type": action.action_type.value,
                "reason": "route_loaded",
                "step_count": len(route.steps),
                "active_step_index": self._progress.get_active_step_index(),
            }

        return {
            "accepted": False,
            "action_type": action.action_type.value,
            "reason": "unsupported_action",
        }

    async def update_connectivity_status(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Endpoint for online/offline context updates and localization control.

        Payload fields:
        - session_id: string
        - ts_ms: int
        - network_available: bool
        - internet_reachable: bool

        Logic:
        - Online signal = network_available AND internet_reachable
        - Uses hysteresis counters to avoid rapid online/offline flapping
        - Emits localization start/stop commands on status transitions
        """
        status = self._validator.parse_connectivity_status(payload)
        is_online_signal = status.network_available and status.internet_reachable

        commands: List[LocalizationControlMessage] = []
        status_changed = False

        if is_online_signal:
            self._consecutive_successes += 1
            self._consecutive_failures = 0
            if (
                self._network_status == NetworkStatus.OFFLINE
                and self._consecutive_successes >= self._online_after_successes
            ):
                self._network_status = NetworkStatus.ONLINE
                status_changed = True
                commands = self._build_localization_commands(
                    session_id=status.session_id,
                    ts_ms=status.ts_ms,
                    action=LocalizationControlAction.STOP,
                    reason="network_online",
                )
        else:
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            if (
                self._network_status == NetworkStatus.ONLINE
                and self._consecutive_failures >= self._offline_after_failures
            ):
                self._network_status = NetworkStatus.OFFLINE
                status_changed = True
                commands = self._build_localization_commands(
                    session_id=status.session_id,
                    ts_ms=status.ts_ms,
                    action=LocalizationControlAction.START,
                    reason="network_offline",
                )

        return {
            "accepted": True,
            "network_status": self._network_status.value,
            "status_changed": status_changed,
            "commands": [
                {
                    "session_id": cmd.session_id,
                    "ts_ms": cmd.ts_ms,
                    "module": cmd.module.value,
                    "action": cmd.action.value,
                    "reason": cmd.reason,
                }
                for cmd in commands
            ],
            "detection_context": {
                "online_signal": is_online_signal,
                "consecutive_successes": self._consecutive_successes,
                "consecutive_failures": self._consecutive_failures,
                "offline_after_failures": self._offline_after_failures,
                "online_after_successes": self._online_after_successes,
            },
        }

    @property
    def network_status(self) -> NetworkStatus:
        return self._network_status

    @staticmethod
    def _build_localization_commands(
        session_id: str,
        ts_ms: int,
        action: LocalizationControlAction,
        reason: str,
    ) -> List[LocalizationControlMessage]:
        return [
            LocalizationControlMessage(
                session_id=session_id,
                ts_ms=ts_ms,
                module=LocalizationModuleType.VISUAL,
                action=action,
                reason=reason,
            ),
            LocalizationControlMessage(
                session_id=session_id,
                ts_ms=ts_ms,
                module=LocalizationModuleType.DEAD_RECKONING,
                action=action,
                reason=reason,
            ),
        ]

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
