"""Runtime end-to-end integration checks for Navigation <-> Vision modules.

Expected runtime setup:
- Navigation server running on :8000
- Vision server running on :8001
"""

from __future__ import annotations

import sys
import time
from typing import Any, Dict

import httpx


NAV_BASE = "http://127.0.0.1:8000"
VISION_BASE = "http://127.0.0.1:8001"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _wait_for_health(client: httpx.Client, url: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            response = client.get(url, timeout=2.0)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code}, body={response.text}"
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Health check failed for {url}: {last_error}")


def _post_json(client: httpx.Client, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(url, json=payload, timeout=10.0)
    _assert(
        response.status_code == 200,
        f"POST {url} failed: {response.status_code} {response.text}",
    )
    return response.json()


def main() -> int:
    session_id = f"e2e_{int(time.time())}"
    now_ms = int(time.time() * 1000)

    route_data = {
        "origin": {"lat": 19.076, "lon": 72.877, "label": "Start"},
        "destination": {"lat": 19.101, "lon": 72.901, "label": "End"},
        "steps": [
            {
                "lat": 19.078,
                "lon": 72.879,
                "instruction": "Turn right",
                "distance": 300,
            },
            {
                "lat": 19.090,
                "lon": 72.890,
                "instruction": "Turn left",
                "distance": 450,
            },
        ],
    }

    with httpx.Client() as client:
        print("[1] Waiting for Navigation and Vision health...")
        _wait_for_health(client, f"{NAV_BASE}/health")
        _wait_for_health(client, f"{VISION_BASE}/docs")

        print("[2] Start navigation with live route data...")
        start_response = _post_json(
            client,
            f"{NAV_BASE}/api/navigation/ui/action",
            {
                "session_id": session_id,
                "ts_ms": now_ms,
                "action_type": "START_NAVIGATION",
                "payload": {"origin": "A", "destination": "B"},
                "route_data": route_data,
            },
        )
        _assert(start_response["accepted"] is True, "START_NAVIGATION should be accepted")
        _assert(start_response["reason"] == "route_loaded", "Route should load from live data")
        _assert(start_response.get("nav_hint") is not None, "Initial nav_hint expected")
        delivery = start_response.get("nav_hint_delivery", {})
        _assert(delivery.get("attempted") is True, "Nav hint delivery should be attempted")
        _assert(delivery.get("sent") is True, "Nav hint should be delivered to Vision")

        print("[3] Trigger vision frame processing (Vision -> Navigation visual events)...")
        frame_response = client.post(
            f"{VISION_BASE}/api/localization/frame",
            data={
                "session_id": session_id,
                "ts_ms": str(now_ms + 100),
            },
            files={
                "image": ("frame.jpg", b"fake_image_bytes", "image/jpeg"),
            },
            timeout=10.0,
        )
        _assert(frame_response.status_code == 200, f"Frame API failed: {frame_response.text}")
        _assert(frame_response.json().get("status") == "queued", "Frame should be queued")

        print("[4] Poll UI state until route progress advances...")
        advanced = False
        destination_reached = False
        last_state: Dict[str, Any] = {}

        deadline = time.time() + 12.0
        while time.time() < deadline:
            state_response = _post_json(
                client,
                f"{NAV_BASE}/api/navigation/ui/state",
                {"session_id": session_id, "ts_ms": int(time.time() * 1000)},
            )
            last_state = state_response["ui_state"]
            if last_state.get("active_step_index", 0) >= 1:
                advanced = True
            if last_state.get("destination_reached_flag"):
                destination_reached = True
            if advanced:
                break
            time.sleep(0.5)

        _assert(advanced, f"Route did not advance from visual events. Last UI state: {last_state}")
        _assert(destination_reached is False, "Should not reach destination with a single expected match")

        print("[5] Validate offline transition with hysteresis...")
        offline_1 = _post_json(
            client,
            f"{NAV_BASE}/api/navigation/connectivity/status",
            {
                "session_id": session_id,
                "ts_ms": now_ms + 2000,
                "network_available": False,
                "internet_reachable": False,
            },
        )
        offline_2 = _post_json(
            client,
            f"{NAV_BASE}/api/navigation/connectivity/status",
            {
                "session_id": session_id,
                "ts_ms": now_ms + 2200,
                "network_available": False,
                "internet_reachable": False,
            },
        )
        _assert(offline_1["status_changed"] is False, "First offline signal should not flip status")
        _assert(offline_2["status_changed"] is True, "Second offline signal should flip to OFFLINE")
        _assert(offline_2["network_status"] == "OFFLINE", "Network status should be OFFLINE")
        _assert(len(offline_2["commands"]) == 2, "Should emit 2 localization control commands")
        _assert(offline_2["commands"][0]["action"] == "START", "OFFLINE should START localization")

        print("[6] Validate online recovery with hysteresis...")
        online_1 = _post_json(
            client,
            f"{NAV_BASE}/api/navigation/connectivity/status",
            {
                "session_id": session_id,
                "ts_ms": now_ms + 2600,
                "network_available": True,
                "internet_reachable": True,
            },
        )
        online_2 = _post_json(
            client,
            f"{NAV_BASE}/api/navigation/connectivity/status",
            {
                "session_id": session_id,
                "ts_ms": now_ms + 2800,
                "network_available": True,
                "internet_reachable": True,
            },
        )
        _assert(online_1["status_changed"] is False, "First online signal should not flip status")
        _assert(online_2["status_changed"] is True, "Second online signal should flip to ONLINE")
        _assert(online_2["network_status"] == "ONLINE", "Network status should be ONLINE")
        _assert(len(online_2["commands"]) == 2, "Should emit 2 localization control commands")
        _assert(online_2["commands"][0]["action"] == "STOP", "ONLINE should STOP localization")

        print("[7] Validate route cache fallback on restart without live route data...")
        cache_start = _post_json(
            client,
            f"{NAV_BASE}/api/navigation/ui/action",
            {
                "session_id": session_id,
                "ts_ms": now_ms + 3200,
                "action_type": "START_NAVIGATION",
                "payload": {"origin": "A", "destination": "B"},
                "route_data": None,
            },
        )
        _assert(cache_start["accepted"] is True, "Cache START_NAVIGATION should be accepted")
        _assert(
            cache_start["reason"] == "route_loaded_from_cache",
            "Expected route_loaded_from_cache when no live route_data is provided",
        )

        print("[8] Validate bad payload handling...")
        bad_response = client.post(
            f"{NAV_BASE}/api/navigation/localization/visual-event",
            json={"session_id": session_id},
            timeout=10.0,
        )
        _assert(bad_response.status_code == 400, "Invalid payload should return HTTP 400")

    print("\nE2E RESULT: PASS")
    print(f"Session used: {session_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nE2E RESULT: FAIL -> {exc}")
        raise
