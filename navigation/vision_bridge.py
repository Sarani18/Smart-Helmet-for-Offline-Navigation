"""
Bridge utilities for Navigation <-> Vision integration.

This module keeps NavigationAPIService transport-agnostic while adding
optional side effects such as forwarding nav hints to the Vision module.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from .api_service import NavigationAPIService

logger = logging.getLogger(__name__)

NavHintSender = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class HTTPVisionNavHintSender:
    """Send nav hints to the Vision module over HTTP."""

    def __init__(self, nav_hint_url: str, timeout_s: float = 2.0) -> None:
        self._nav_hint_url = nav_hint_url
        self._timeout_s = timeout_s

    async def __call__(self, nav_hint_payload: Dict[str, Any]) -> Dict[str, Any]:
        # Imported lazily so core navigation tests do not require httpx.
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(self._nav_hint_url, json=nav_hint_payload)

        body: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body = response.json()
        else:
            body = response.text

        return {
            "ok": response.is_success,
            "status_code": response.status_code,
            "body": body,
        }


class NavigationVisionBridge:
    """
    Adds integration behavior around NavigationAPIService.

    Primary responsibility:
    - forward emitted nav hints to a Vision endpoint (if configured)
    """

    def __init__(
        self,
        service: NavigationAPIService,
        nav_hint_sender: Optional[NavHintSender] = None,
    ) -> None:
        self._service = service
        self._nav_hint_sender = nav_hint_sender

    async def ingest_visual_event(
        self,
        payload: Dict[str, Any],
        now_ts_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        result = await self._service.ingest_visual_event(payload, now_ts_ms=now_ts_ms)
        return await self._attach_nav_hint_delivery(result)

    async def ingest_dead_reckoning_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._service.ingest_dead_reckoning_event(payload)
        return await self._attach_nav_hint_delivery(result)

    async def ingest_ui_action(
        self,
        payload: Dict[str, Any],
        route_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = await self._service.ingest_ui_action(payload, route_data=route_data)
        return await self._attach_nav_hint_delivery(result)

    async def update_connectivity_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._service.update_connectivity_status(payload)
        return await self._attach_nav_hint_delivery(result)

    async def get_ui_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._service.get_ui_state(payload)

    async def _attach_nav_hint_delivery(self, result: Dict[str, Any]) -> Dict[str, Any]:
        nav_hint = result.get("nav_hint")
        if nav_hint is None:
            result["nav_hint_delivery"] = {
                "attempted": False,
                "sent": False,
                "status": "no_hint",
            }
            return result

        if self._nav_hint_sender is None:
            result["nav_hint_delivery"] = {
                "attempted": False,
                "sent": False,
                "status": "no_sender",
            }
            return result

        try:
            send_response = await self._nav_hint_sender(nav_hint)
            result["nav_hint_delivery"] = {
                "attempted": True,
                "sent": bool(send_response.get("ok", True)),
                "status": "delivered" if send_response.get("ok", True) else "rejected",
                "response": send_response,
            }
            return result
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("Failed to deliver nav hint to vision: %s", exc)
            result["nav_hint_delivery"] = {
                "attempted": True,
                "sent": False,
                "status": "failed",
                "error": str(exc),
            }
            return result
