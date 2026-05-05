from __future__ import annotations

import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]
CV_DIR = ROOT_DIR / "localization" / "CV"
if str(CV_DIR) not in sys.path:
    sys.path.insert(0, str(CV_DIR))

GOOGLE_KEY = (
    os.getenv("GOOGLE_STREET_VIEW_API_KEY")
    or os.getenv("GOOGLE_MAPS_API_KEY")
    or ""
).strip()
ALLOW_STATIC_FALLBACK = os.getenv("CV_SERVER_ALLOW_STATIC_FALLBACK", "0") == "1"
MAX_GOOGLE_FRAMES = int(os.getenv("CV_SERVER_MAX_GOOGLE_FRAMES", "0") or "0")
STATIC_FALLBACK_IMAGE = CV_DIR / "real_road_test.png"
STREET_VIEW_IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
STREET_VIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"

Status = Literal["OK", "DEGRADED", "UNAVAILABLE", "STOPPED"]


class LatLon(BaseModel):
    lat: float
    lon: float


class VisionStartRequest(BaseModel):
    session_id: str
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    origin: LatLon
    destination: LatLon
    current: LatLon
    route_polyline: List[LatLon] = Field(default_factory=list)
    route_progress_m: float = 0
    heading_deg: Optional[float] = None


class VisionUpdateRequest(BaseModel):
    session_id: str
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    current: LatLon
    route_progress_m: float = 0
    dr_distance_travelled_m: float = 0
    heading_deg: Optional[float] = None
    route_polyline: List[LatLon] = Field(default_factory=list)


class VisionStopRequest(BaseModel):
    session_id: str
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class PositionHint(BaseModel):
    lat: float
    lon: float
    route_progress_m: float
    source: str


class VisionResponse(BaseModel):
    status: Status
    message: str
    session_id: str
    ts_ms: int
    confidence: float = 0
    visual_event: Optional[Dict[str, Any]] = None
    position_hint: Optional[PositionHint] = None
    latest_detection: Optional[str] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ControlCommand(BaseModel):
    session_id: str
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    module: str = "VISUAL"
    action: str
    reason: str = ""


class NavHintMessage(BaseModel):
    session_id: str
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    expected_next_turn: str = "STRAIGHT"
    distance_to_next_turn_m: float = 0


@dataclass
class SessionState:
    session_id: str
    origin: LatLon
    destination: LatLon
    current: LatLon
    route_polyline: List[LatLon]
    route_progress_m: float
    active: bool = True
    latest: Optional[VisionResponse] = None


class RuntimeState:
    sessions: Dict[str, SessionState]
    model_loaded: bool
    model_error: Optional[str]
    google_frames_used: int
    device: Any
    segmentation_model: Any
    cnn_model: Any

    def __init__(self) -> None:
        self.sessions = {}
        self.model_loaded = False
        self.model_error = None
        self.google_frames_used = 0
        self.device = None
        self.segmentation_model = None
        self.cnn_model = None


state = RuntimeState()
app = FastAPI(title="Smart Helmet CV Bridge Server", version="0.1.0")


@app.get("/health")
async def health() -> Dict[str, Any]:
    model_path = CV_DIR / "models" / "best.pth"
    return {
        "ok": True,
        "service": "cv_bridge_server",
        "google_street_view_configured": bool(GOOGLE_KEY),
        "static_fallback_allowed": ALLOW_STATIC_FALLBACK,
        "cv_dir": str(CV_DIR),
        "main_model_present": model_path.exists(),
        "model_loaded": state.model_loaded,
        "model_error": state.model_error,
        "google_frames_used": state.google_frames_used,
        "max_google_frames": MAX_GOOGLE_FRAMES,
        "active_sessions": [
            sid for sid, session in state.sessions.items() if session.active
        ],
    }


@app.post("/api/vision/start", response_model=VisionResponse)
async def start_vision(req: VisionStartRequest) -> VisionResponse:
    session = SessionState(
        session_id=req.session_id,
        origin=req.origin,
        destination=req.destination,
        current=req.current,
        route_polyline=req.route_polyline,
        route_progress_m=req.route_progress_m,
    )
    state.sessions[req.session_id] = session
    response = await _analyze_for_session(
        session=session,
        current=req.current,
        route_progress_m=req.route_progress_m,
        heading_deg=req.heading_deg,
        dr_distance_travelled_m=0,
    )
    session.latest = response
    return response


@app.post("/api/vision/update", response_model=VisionResponse)
async def update_vision(req: VisionUpdateRequest) -> VisionResponse:
    session = state.sessions.get(req.session_id)
    if session is None:
        session = SessionState(
            session_id=req.session_id,
            origin=req.current,
            destination=req.current,
            current=req.current,
            route_polyline=req.route_polyline,
            route_progress_m=req.route_progress_m,
        )
        state.sessions[req.session_id] = session

    session.current = req.current
    session.route_progress_m = req.route_progress_m
    if req.route_polyline:
        session.route_polyline = req.route_polyline

    response = await _analyze_for_session(
        session=session,
        current=req.current,
        route_progress_m=req.route_progress_m,
        heading_deg=req.heading_deg,
        dr_distance_travelled_m=req.dr_distance_travelled_m,
    )
    session.latest = response
    return response


@app.post("/api/vision/stop", response_model=VisionResponse)
async def stop_vision(req: VisionStopRequest) -> VisionResponse:
    session = state.sessions.get(req.session_id)
    if session is not None:
        session.active = False
    response = VisionResponse(
        status="STOPPED",
        message="Vision session stopped",
        session_id=req.session_id,
        ts_ms=req.ts_ms,
    )
    if session is not None:
        session.latest = response
    return response


@app.get("/api/vision/latest", response_model=VisionResponse)
async def latest(session_id: str) -> VisionResponse:
    session = state.sessions.get(session_id)
    if session is None or session.latest is None:
        return VisionResponse(
            status="UNAVAILABLE",
            message="No latest vision result for session",
            session_id=session_id,
            ts_ms=int(time.time() * 1000),
        )
    return session.latest


@app.post("/api/localization/control")
async def compatibility_control(cmd: ControlCommand) -> Dict[str, Any]:
    if cmd.action.upper() == "STOP":
        await stop_vision(VisionStopRequest(session_id=cmd.session_id, ts_ms=cmd.ts_ms))
        return {"status": "stopped", "message": "Vision bridge stopped"}
    if cmd.action.upper() == "START":
        return {
            "status": "accepted",
            "message": "Use /api/vision/start with origin/destination/current coordinates",
        }
    return {"status": "ignored", "message": f"Unknown action {cmd.action}"}


@app.post("/api/localization/nav-hint")
async def compatibility_nav_hint(hint: NavHintMessage) -> Dict[str, Any]:
    session = state.sessions.get(hint.session_id)
    if session and session.latest:
        session.latest.diagnostics["nav_hint"] = hint.dict()
    return {"status": "accepted"}


@app.get("/api/localization/latest")
async def compatibility_latest() -> Dict[str, Any]:
    latest_response: Optional[VisionResponse] = None
    for session in state.sessions.values():
        if session.latest is None:
            continue
        if latest_response is None or session.latest.ts_ms > latest_response.ts_ms:
            latest_response = session.latest
    if latest_response is None:
        return {"latest": "Vision bridge awaiting session"}
    return {
        "latest": latest_response.latest_detection or latest_response.message,
        "status": latest_response.status,
    }


async def _analyze_for_session(
    session: SessionState,
    current: LatLon,
    route_progress_m: float,
    heading_deg: Optional[float],
    dr_distance_travelled_m: float,
) -> VisionResponse:
    ts_ms = int(time.time() * 1000)
    frame_result = await _get_street_view_frame(current, heading_deg)
    if frame_result["frame"] is None:
        return _response(
            status=frame_result["status"],
            message=frame_result["message"],
            session=session,
            ts_ms=ts_ms,
            diagnostics=frame_result["diagnostics"],
        )

    try:
        analysis = _run_cv_analysis(frame_result["frame"])
    except Exception as exc:
        return _response(
            status="UNAVAILABLE",
            message=f"CV analysis unavailable: {exc}",
            session=session,
            ts_ms=ts_ms,
            diagnostics={
                **frame_result["diagnostics"],
                "model_error": state.model_error,
            },
        )

    confidence = max(0.0, min(1.0, float(analysis.confidence) / 100.0))
    visual_event = _analysis_to_visual_event(session.session_id, analysis, confidence)
    position_point = _point_at_route_progress(session.route_polyline, route_progress_m)
    source = (
        "street_view_route_snap"
        if frame_result["status"] == "OK"
        else "static_fallback_route_snap"
    )
    position_hint = PositionHint(
        lat=position_point.lat,
        lon=position_point.lon,
        route_progress_m=route_progress_m,
        source=source,
    )

    status: Status = "OK" if frame_result["status"] == "OK" else "DEGRADED"
    latest_detection = (
        f"{analysis.nav_instruction} | {analysis.junction_type} | "
        f"conf:{analysis.confidence:.0f}%"
    )
    return VisionResponse(
        status=status,
        message=(
            "Vision fix generated from Google Street View"
            if status == "OK"
            else "Vision running on fallback imagery, not real Street View"
        ),
        session_id=session.session_id,
        ts_ms=ts_ms,
        confidence=confidence,
        visual_event=visual_event,
        position_hint=position_hint,
        latest_detection=latest_detection,
        diagnostics={
            **frame_result["diagnostics"],
            "dr_distance_travelled_m": dr_distance_travelled_m,
            "route_progress_m": route_progress_m,
            "turn_type": analysis.turn_type,
            "road_direction": analysis.road_direction,
            "junction_type": analysis.junction_type,
            "scene_type": analysis.scene_type,
        },
    )


async def _get_street_view_frame(
    current: LatLon,
    heading_deg: Optional[float],
) -> Dict[str, Any]:
    if GOOGLE_KEY:
        if MAX_GOOGLE_FRAMES > 0 and state.google_frames_used >= MAX_GOOGLE_FRAMES:
            if not ALLOW_STATIC_FALLBACK:
                return {
                    "frame": None,
                    "status": "UNAVAILABLE",
                    "message": f"Google frame limit reached ({MAX_GOOGLE_FRAMES})",
                    "diagnostics": {"google_frames_used": state.google_frames_used},
                }
        else:
            return await _fetch_google_street_view_frame(current, heading_deg)

    if ALLOW_STATIC_FALLBACK:
        return _get_static_fallback_frame()

    return {
        "frame": None,
        "status": "UNAVAILABLE",
        "message": "Google Street View API key missing",
        "diagnostics": {"google_key_env": "GOOGLE_STREET_VIEW_API_KEY"},
    }


async def _fetch_google_street_view_frame(
    current: LatLon,
    heading_deg: Optional[float],
) -> Dict[str, Any]:
    heading = 0 if heading_deg is None else heading_deg
    params = {
        "location": f"{current.lat},{current.lon}",
        "heading": str(heading),
        "pitch": "0",
        "fov": "90",
        "size": "640x640",
        "key": GOOGLE_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            metadata = await client.get(STREET_VIEW_METADATA_URL, params=params)
            metadata_json = metadata.json()
            if metadata_json.get("status") != "OK":
                return {
                    "frame": None,
                    "status": "UNAVAILABLE",
                    "message": f"Street View unavailable: {metadata_json.get('status')}",
                    "diagnostics": {"street_view_metadata": metadata_json},
                }

            image = await client.get(STREET_VIEW_IMAGE_URL, params=params)
            image.raise_for_status()
        state.google_frames_used += 1
        return {
            "frame": _decode_image_bytes(image.content),
            "status": "OK",
            "message": "Street View frame fetched",
            "diagnostics": {
                "street_view_metadata": metadata_json,
                "google_frames_used": state.google_frames_used,
                "max_google_frames": MAX_GOOGLE_FRAMES,
            },
        }
    except Exception as exc:
        if ALLOW_STATIC_FALLBACK:
            return _get_static_fallback_frame()
        return {
            "frame": None,
            "status": "UNAVAILABLE",
            "message": f"Street View fetch failed: {exc}",
            "diagnostics": {},
        }


def _get_static_fallback_frame() -> Dict[str, Any]:
    try:
        import cv2

        frame = cv2.imread(str(STATIC_FALLBACK_IMAGE))
        if frame is None:
            raise RuntimeError(f"Cannot read {STATIC_FALLBACK_IMAGE}")
        return {
            "frame": frame,
            "status": "DEGRADED",
            "message": "Using static fallback image",
            "diagnostics": {"static_fallback": str(STATIC_FALLBACK_IMAGE)},
        }
    except Exception as exc:
        return {
            "frame": None,
            "status": "UNAVAILABLE",
            "message": f"Static fallback unavailable: {exc}",
            "diagnostics": {},
        }


def _run_cv_analysis(frame: Any) -> Any:
    _ensure_models_loaded()
    from scene_analyzer import analyze_scene, preprocess, segment

    tensor = preprocess(frame)
    seg = segment(state.segmentation_model, tensor, state.device)
    return analyze_scene(seg, state.cnn_model, state.device)


def _ensure_models_loaded() -> None:
    if state.model_loaded:
        return
    if state.model_error is not None:
        raise RuntimeError(state.model_error)

    try:
        import torch
        from scene_analyzer import load_model

        try:
            from models import TinySceneCNN
        except Exception:
            TinySceneCNN = None

        if torch.cuda.is_available():
            state.device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            state.device = torch.device("mps")
        else:
            state.device = torch.device("cpu")

        model_path = CV_DIR / "models" / "best.pth"
        if not model_path.exists():
            raise FileNotFoundError(f"Missing CV model: {model_path}")
        state.segmentation_model = load_model(str(model_path), state.device)

        classifier_path = CV_DIR / "models" / "scene_classifier.pth"
        if classifier_path.exists() and TinySceneCNN is not None:
            state.cnn_model = TinySceneCNN().to(state.device)
            checkpoint = torch.load(
                str(classifier_path),
                map_location=state.device,
                weights_only=False,
            )
            state.cnn_model.load_state_dict(checkpoint["model_state_dict"])
            state.cnn_model.eval()

        state.model_loaded = True
    except Exception as exc:
        state.model_error = str(exc)
        raise


def _decode_image_bytes(content: bytes) -> Any:
    import cv2

    arr = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("Could not decode Street View image")
    return frame


def _analysis_to_visual_event(
    session_id: str,
    analysis: Any,
    confidence: float,
) -> Optional[Dict[str, Any]]:
    turn_class = _turn_class_from_analysis(analysis)
    if turn_class != "STRAIGHT":
        return {
            "session_id": session_id,
            "event_id": f"evt_cv_{uuid.uuid4().hex[:12]}",
            "ts_ms": int(time.time() * 1000),
            "event_type": "TURN",
            "confidence": confidence,
            "payload": {"turn_class": turn_class},
        }

    junction = getattr(analysis, "junction_type", "none")
    if junction in {"t_junction", "y_junction", "crossroad"}:
        return {
            "session_id": session_id,
            "event_id": f"evt_cv_{uuid.uuid4().hex[:12]}",
            "ts_ms": int(time.time() * 1000),
            "event_type": "LANDMARK",
            "confidence": confidence,
            "payload": {
                "landmark_class": "JUNCTION",
                "map_hint_name": junction,
            },
        }

    return None


def _turn_class_from_analysis(analysis: Any) -> str:
    turn_map = {
        "slight_left": "SLIGHT_LEFT",
        "left_turn": "LEFT",
        "sharp_left": "LEFT",
        "slight_right": "SLIGHT_RIGHT",
        "right_turn": "RIGHT",
        "sharp_right": "RIGHT",
        "u_turn": "U_TURN",
        "none": "STRAIGHT",
    }
    current_turn = turn_map.get(getattr(analysis, "turn_type", "none"), "STRAIGHT")
    if current_turn == "STRAIGHT":
        direction_map = {
            "slight_left": "SLIGHT_LEFT",
            "left_curve": "LEFT",
            "slight_right": "SLIGHT_RIGHT",
            "right_curve": "RIGHT",
        }
        current_turn = direction_map.get(
            getattr(analysis, "road_direction", "straight"),
            "STRAIGHT",
        )
    return current_turn


def _response(
    status: Status,
    message: str,
    session: SessionState,
    ts_ms: int,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> VisionResponse:
    return VisionResponse(
        status=status,
        message=message,
        session_id=session.session_id,
        ts_ms=ts_ms,
        diagnostics=diagnostics or {},
    )


def _point_at_route_progress(route: List[LatLon], progress_m: float) -> LatLon:
    if not route:
        return LatLon(lat=0, lon=0)
    if len(route) == 1 or progress_m <= 0:
        return route[0]
    remaining = progress_m
    for idx in range(len(route) - 1):
        a = route[idx]
        b = route[idx + 1]
        segment_m = _haversine_m(a, b)
        if remaining <= segment_m:
            t = 0 if segment_m <= 0 else remaining / segment_m
            return LatLon(
                lat=a.lat + (b.lat - a.lat) * t,
                lon=a.lon + (b.lon - a.lon) * t,
            )
        remaining -= segment_m
    return route[-1]


def _haversine_m(a: LatLon, b: LatLon) -> float:
    import math

    radius_m = 6_371_000
    d_lat = math.radians(b.lat - a.lat)
    d_lon = math.radians(b.lon - a.lon)
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return radius_m * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))
