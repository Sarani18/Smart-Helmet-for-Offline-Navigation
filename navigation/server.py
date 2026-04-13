"""
Navigation HTTP server
----------------------
FastAPI transport adapter over NavigationAPIService.

This server exposes integration endpoints expected by other modules.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .api_service import NavigationAPIService
from .event_validator import ContractValidationError
from .vision_bridge import HTTPVisionNavHintSender, NavigationVisionBridge


class UIActionRequest(BaseModel):
    session_id: str
    ts_ms: int
    action_type: str
    payload: Dict[str, Any]
    route_data: Optional[Dict[str, Any]] = None


def _build_bridge() -> NavigationVisionBridge:
    service = NavigationAPIService()

    push_nav_hints = os.getenv("NCS_PUSH_NAV_HINTS", "1") == "1"
    if not push_nav_hints:
        return NavigationVisionBridge(service=service, nav_hint_sender=None)

    nav_hint_url = os.getenv(
        "VISION_NAV_HINT_URL",
        "http://127.0.0.1:8001/api/localization/nav-hint",
    )
    sender = HTTPVisionNavHintSender(nav_hint_url=nav_hint_url)
    return NavigationVisionBridge(service=service, nav_hint_sender=sender)


app = FastAPI(title="Navigation Control System API", version="1.0.0")
bridge = _build_bridge()


def _raise_as_http(exc: Exception) -> None:
    if isinstance(exc, (ContractValidationError, ValueError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/navigation/localization/visual-event")
async def ingest_visual_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return await bridge.ingest_visual_event(payload)
    except Exception as exc:  # pragma: no cover - transport guard
        _raise_as_http(exc)
        raise


@app.post("/api/navigation/localization/dead-reckoning-event")
async def ingest_dead_reckoning_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return await bridge.ingest_dead_reckoning_event(payload)
    except Exception as exc:  # pragma: no cover - transport guard
        _raise_as_http(exc)
        raise


@app.post("/api/navigation/ui/action")
async def ingest_ui_action(request: UIActionRequest) -> Dict[str, Any]:
    payload = {
        "session_id": request.session_id,
        "ts_ms": request.ts_ms,
        "action_type": request.action_type,
        "payload": request.payload,
    }
    try:
        return await bridge.ingest_ui_action(payload, route_data=request.route_data)
    except Exception as exc:  # pragma: no cover - transport guard
        _raise_as_http(exc)
        raise


@app.post("/api/navigation/connectivity/status")
async def update_connectivity_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return await bridge.update_connectivity_status(payload)
    except Exception as exc:  # pragma: no cover - transport guard
        _raise_as_http(exc)
        raise


@app.post("/api/navigation/ui/state")
async def get_ui_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return await bridge.get_ui_state(payload)
    except Exception as exc:  # pragma: no cover - transport guard
        _raise_as_http(exc)
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
