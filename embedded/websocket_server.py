"""
WebSocket server — bridges the Python navigation brain to browser / Android clients.

Sanskruti calls:  receive_ui_state(dict)   at 2-5 Hz
Browser/Android:  connects to ws://localhost:8765/ws

Install:  pip install fastapi uvicorn websockets python-multipart aiofiles
Run:      python -m embedded.websocket_server
Open:     http://localhost:8765/
"""

from __future__ import annotations
import asyncio
import json
import pathlib
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from .nav_interface import UIStateMessage
from .ui_bridge import UIBridge
from .app_interface.ui_manager import UIManager
from .led_controller import LEDController

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_HERE = pathlib.Path(__file__).resolve().parent


class _ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] connected   clients={len(self.active)}")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        print(f"[WS] disconnected  clients={len(self.active)}")

    async def broadcast(self, data: dict) -> None:
        msg  = json.dumps(data)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

    def broadcast_sync(self, data: dict) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(data), self._loop)


_manager = _ConnectionManager()
_bridge  = UIBridge(ui_manager=UIManager(), led_controller=LEDController())
_bridge.register_state_callback(_manager.broadcast_sync)


def receive_ui_state(msg: dict) -> None:
    """Called by Sanskruti's navigation module at 2-5 Hz."""
    try:
        _bridge.on_ui_state(UIStateMessage.from_dict(msg))
    except Exception as e:
        print(f"[ws_server] receive_ui_state error: {e}")


def set_action_callback(fn) -> None:
    """Sanskruti registers here to receive UIActionMessages from the rider."""
    _bridge.register_action_callback(fn)


@app.websocket("/ws")
async def _ws_endpoint(websocket: WebSocket) -> None:
    _manager._loop = asyncio.get_event_loop()
    await _manager.connect(websocket)
    if _bridge.latest_state:
        await websocket.send_text(json.dumps(_bridge.latest_state.to_ws_dict()))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                d     = json.loads(raw)
                atype = d.get("action_type", "")
                p     = d.get("payload", {})
                if atype == "START_NAVIGATION":
                    _bridge.start_navigation(p.get("origin", ""), p.get("destination", ""))
                elif atype == "STOP_NAVIGATION":
                    _bridge.stop_navigation()
                elif atype == "REROUTE_REQUEST":
                    _bridge.request_reroute(p.get("reason", "user_request"))
            except Exception:
                pass
    except WebSocketDisconnect:
        _manager.disconnect(websocket)


@app.get("/")
def _root():
    """Serves web_ui/index.html. Checks embedded/ first, then project root."""
    for candidate in [
        _HERE / "web_ui" / "index.html",
        _HERE.parent / "web_ui" / "index.html",
    ]:
        if candidate.exists():
            return FileResponse(str(candidate))
    return {
        "error": "web_ui/index.html not found",
        "expected": str(_HERE.parent / "web_ui" / "index.html"),
    }


@app.post("/receive")
async def _receive(request: Request):
    """Accepts a UIStateMessage JSON body — used by test_input.py."""
    receive_ui_state(await request.json())
    return {"ok": True, "clients": len(_manager.active)}


@app.get("/test-push")
async def _test_push():
    """Pushes a fake UIStateMessage — for testing without Sanskruti running."""
    receive_ui_state({
        "session_id":               "test",
        "ts_ms":                    int(time.time() * 1000),
        "nav_mode":                 "OFFLINE",
        "position_mode":            "GPS",
        "next_instruction_text":    "In 200 m, turn right",
        "distance_to_next_m":       200,
        "confidence":               0.92,
        "off_route_flag":           False,
        "destination_reached_flag": False,
        "active_step_index":        2,
        "route_polyline": [
            [19.9960, 73.7840],
            [19.9965, 73.7852],
            [19.9972, 73.7865],
            [19.9975, 73.7878],
        ],
    })
    return {"pushed": True, "clients": len(_manager.active)}


@app.get("/position")
def _get_position():
    pos = _bridge.get_current_position()
    return pos if pos else {"error": "no state received yet"}


@app.get("/status")
def _get_status():
    s = _bridge.latest_state
    return {
        "clients":      len(_manager.active),
        "has_state":    s is not None,
        "nav_mode":     s.nav_mode.value if s else None,
        "instruction":  s.next_instruction_text if s else None,
        "polyline_pts": len(s.route_polyline) if s else 0,
    }


if __name__ == "__main__":
    print("=" * 50)
    print("Map UI:    http://localhost:8765/")
    print("WS:        ws://localhost:8765/ws")
    print("Test push: http://localhost:8765/test-push")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")