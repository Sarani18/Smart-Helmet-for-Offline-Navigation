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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .api_service import NavigationAPIService
from .event_validator import ContractValidationError
from .map_manager import MapManager
from .osrm_client import fetch_route as osrm_fetch_route
from .vision_bridge import (
    HTTPUIStateSender,
    HTTPVisionNavHintSender,
    NavigationVisionBridge,
)


class UIActionRequest(BaseModel):
    session_id: str
    ts_ms: int
    action_type: str
    payload: Dict[str, Any]
    route_data: Optional[Dict[str, Any]] = None


def _build_bridge() -> NavigationVisionBridge:
    map_manager = MapManager()
    map_manager.configure_tile_download(
        tile_url_template=os.getenv(
            "NCS_TILE_URL_TEMPLATE",
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        ),
        zoom_levels=_parse_zoom_levels(os.getenv("NCS_TILE_ZOOMS", "14,15")),
        request_timeout_s=float(os.getenv("NCS_TILE_TIMEOUT_S", "5")),
        user_agent=os.getenv(
            "NCS_TILE_USER_AGENT",
            "SmartHelmetNavigation/1.0 (educational project)",
        ),
        max_cache_size_mb=float(os.getenv("NCS_TILE_CACHE_MAX_MB", "200")),
    )

    service = NavigationAPIService(
        map_manager=map_manager,
        enable_tile_prefetch=os.getenv("NCS_ENABLE_TILE_PREFETCH", "1") == "1",
        evict_session_tiles_on_stop=os.getenv("NCS_EVICT_SESSION_TILES_ON_STOP", "0") == "1",
    )

    nav_hint_sender = None
    push_nav_hints = os.getenv("NCS_PUSH_NAV_HINTS", "1") == "1"
    if push_nav_hints:
        nav_hint_url = os.getenv(
            "VISION_NAV_HINT_URL",
            "http://127.0.0.1:8001/api/localization/nav-hint",
        )
        nav_hint_sender = HTTPVisionNavHintSender(nav_hint_url=nav_hint_url)

    ui_state_sender = None
    push_ui_state = os.getenv("NCS_PUSH_UI_STATE", "0") == "1"
    if push_ui_state:
        ui_state_url = os.getenv("UI_STATE_SINK_URL", "http://127.0.0.1:8765/receive")
        ui_state_sender = HTTPUIStateSender(ui_state_url=ui_state_url)

    return NavigationVisionBridge(
        service=service,
        nav_hint_sender=nav_hint_sender,
        ui_state_sender=ui_state_sender,
    )


def _parse_allowed_origins(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        return ["*"]
    return values


def _parse_zoom_levels(raw: str) -> list[int]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = int(item)
        except ValueError:
            continue
        if 0 <= value <= 20:
            values.append(value)
    return values or [14, 15]


app = FastAPI(title="Navigation Control System API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(os.getenv("NCS_CORS_ORIGINS", "*")),
    allow_methods=["*"],
    allow_headers=["*"],
)
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

    route_data = request.route_data

    # When no pre-built route_data is supplied and the action is a navigation
    # start/reroute, attempt to build route_data by geocoding the origin and
    # destination via Nominatim and fetching a driving route from OSRM.
    if route_data is None and request.action_type in ("START_NAVIGATION", "REROUTE_REQUEST"):
        origin      = request.payload.get("origin", "")
        destination = request.payload.get("destination", "")
        if origin and destination:
            route_data = osrm_fetch_route(origin, destination)
            # osrm_fetch_route returns None on network failure — NCS will
            # fall back to offline cache automatically.

    try:
        return await bridge.ingest_ui_action(payload, route_data=route_data)
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
