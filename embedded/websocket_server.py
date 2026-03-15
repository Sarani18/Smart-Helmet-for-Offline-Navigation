"""
websocket_server.py
-------------------
FastAPI WebSocket server. Sits between the Python brain and the UI clients.

Inbound  (nav → this server):  receive_ui_state(msg_dict)
Outbound (this server → browser/Android): broadcasts UIStateMessage as JSON

Install once:  pip install fastapi uvicorn websockets
Run:           python -m embedded.websocket_server
"""

from __future__ import annotations
import asyncio, json, time
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .nav_interface import UIStateMessage, NavMode, PositionMode
from .ui_bridge import UIBridge
from .app_interface.ui_manager import UIManager
from .led_controller import LEDController

app = FastAPI(title="SmartHelmet Nav Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] connected  total={len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active: self.active.remove(ws)
        print(f"[WS] disconnected  total={len(self.active)}")

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        dead = []
        for ws in self.active:
            try: await ws.send_text(msg)
            except: dead.append(ws)
        for ws in dead: self.active.remove(ws)

    def broadcast_sync(self, data: dict):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(data), self._loop)

manager = ConnectionManager()
bridge  = UIBridge(ui_manager=UIManager(), led_controller=LEDController())
bridge.register_state_callback(manager.broadcast_sync)


def receive_ui_state(msg: dict) -> None:
    """
    Called by navigation module on every UIStateMessage.

    from embedded.websocket_server import receive_ui_state
    receive_ui_state({
        "session_id": "ride_001",
        "ts_ms": 1773571240000,
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "In 120 m, turn right",
        "distance_to_next_m": 120,
        "confidence": 0.92,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 3,
        "route_polyline": [[19.0760, 72.8777], [19.0768, 72.8790]]
    })
    """
    try:
        bridge.on_ui_state(UIStateMessage.from_dict(msg))
    except Exception as e:
        print(f"[receive_ui_state] error: {e}")


def set_action_callback(fn) -> None:
    """registers here to receive UIActionMessages from the rider."""
    bridge.register_action_callback(fn)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    manager._loop = asyncio.get_event_loop()
    await manager.connect(websocket)
    if bridge.latest_state:
        await websocket.send_text(json.dumps(bridge.latest_state.to_ws_dict()))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                d = json.loads(raw)
                atype = d.get("action_type", "")
                p = d.get("payload", {})
                if atype == "START_NAVIGATION":
                    bridge.start_navigation(p.get("origin",""), p.get("destination",""))
                elif atype == "STOP_NAVIGATION":
                    bridge.stop_navigation()
                elif atype == "REROUTE_REQUEST":
                    bridge.request_reroute(p.get("reason","user_request"))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/position")
def get_position():
    pos = bridge.get_current_position()
    return pos if pos else {"error": "no state received yet"}


@app.get("/status")
def get_status():
    s = bridge.latest_state
    return {
        "clients_connected": len(manager.active),
        "has_state":         s is not None,
        "nav_mode":          s.nav_mode.value if s else None,
        "instruction":       s.next_instruction_text if s else None,
        "polyline_points":   len(s.route_polyline) if s else 0,
    }


@app.get("/test-push")
async def test_push():
    """Test : GET http://localhost:8765/test-push"""
    receive_ui_state({
        "session_id": "test_session",
        "ts_ms": int(time.time() * 1000),
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "In 200 m, turn right",
        "distance_to_next_m": 200,
        "confidence": 0.92,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 2,
        "route_polyline": [
            [19.9960, 73.7840],[19.9965, 73.7852],
            [19.9972, 73.7865],[19.9975, 73.7878],
        ],
    })
    return {"pushed": True, "clients": len(manager.active)}


if __name__ == "__main__":
    print("="*55)
    print("SmartHelmet WebSocket Server")
    print("WS:    ws://localhost:8765/ws")
    print("Test:  http://localhost:8765/test-push")
    print("="*55)
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")