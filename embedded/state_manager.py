from __future__ import annotations

import copy
import queue
import threading
import time
from typing import Any, Dict, Optional


def now_ms() -> int:
    return int(time.time() * 1000)


class StateManager:
    """Thread-safe JSON state store with a bounded UI snapshot queue."""

    def __init__(self, ui_queue_size: int = 4) -> None:
        self._lock = threading.RLock()
        self._version = 0
        self._ui_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=ui_queue_size)
        self._state: Dict[str, Any] = {
            "version": 0,
            "updated_at": None,
            "route": {
                "session_id": None,
                "start": None,
                "end": None,
                "offline_map": None,
                "status": "idle",
                "instruction": None,
                "verified_position": None,
                "progress": None,
                "confidence": None,
            },
            "cv": {
                "candidate_position": None,
                "confidence": None,
                "status": "idle",
                "updated_at": None,
            },
            "dr": {
                "candidate_position": None,
                "heading": None,
                "speed": None,
                "phone_sensors": {},
                "status": "idle",
                "updated_at": None,
            },
            "ui": {
                "last_rendered_at": None,
                "queue_depth": 0,
                "status": "idle",
            },
            "bluetooth": {
                "connected": False,
                "last_command": None,
                "last_sent_at": None,
                "status": "idle",
            },
            "sos": {
                "active": False,
                "reason": None,
                "thresholds": {},
                "updated_at": None,
            },
        }

    def update(self, source: str, section: str, values: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if section not in self._state or not isinstance(self._state[section], dict):
                self._state[section] = {}
            self._state[section].update(copy.deepcopy(values))
            self._version += 1
            self._state["version"] = self._version
            self._state["updated_at"] = now_ms()
            snapshot = copy.deepcopy(self._state)

        print(f"[ui-sync] {source}->state section={section} version={snapshot['version']}")
        return snapshot

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def queue_ui_snapshot(self, source: str, snapshot: Optional[Dict[str, Any]] = None) -> bool:
        snap = copy.deepcopy(snapshot) if snapshot is not None else self.snapshot()
        queued = False
        try:
            self._ui_queue.put_nowait(snap)
            queued = True
        except queue.Full:
            try:
                self._ui_queue.get_nowait()
                self._ui_queue.put_nowait(snap)
                queued = True
                print(f"[ui-sync] state->ui dropped_stale version={snap.get('version')}")
            except queue.Empty:
                queued = False

        depth = self._ui_queue.qsize()
        with self._lock:
            self._state["ui"]["queue_depth"] = depth
        status = "queued" if queued else "dropped"
        print(f"[ui-sync] state->ui {status} source={source} version={snap.get('version')} queue_depth={depth}")
        return queued

    def get_ui_snapshot_nowait(self) -> Optional[Dict[str, Any]]:
        try:
            snap = self._ui_queue.get_nowait()
        except queue.Empty:
            return None

        with self._lock:
            self._state["ui"]["last_rendered_at"] = now_ms()
            self._state["ui"]["queue_depth"] = self._ui_queue.qsize()
        print(f"[ui-sync] ui_queue->render version={snap.get('version')}")
        return snap

    def ui_queue_depth(self) -> int:
        return self._ui_queue.qsize()
