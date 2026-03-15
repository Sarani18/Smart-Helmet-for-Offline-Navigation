"""
test_input.py
-------------
Streams simulated UIStateMessages to the map UI.

HOW TO USE — three steps:
  1. Terminal 1:  python -m embedded.websocket_server
  2. Browser:     open http://localhost:8765/
  3. Terminal 2:  python test_input.py

The script checks the server is alive, waits until the browser is
connected (clients > 0), then sends each GPS step every 1.5 seconds.
"""

import time
import sys

try:
    import requests
except ImportError:
    print("Missing dependency. Run:  pip install requests")
    sys.exit(1)

SERVER = "http://localhost:8765"

ROUTE = [
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "Go straight",
        "distance_to_next_m": 350,
        "confidence": 0.95,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 0,
        "route_polyline": [
            [19.9960, 73.7840],
            [19.9965, 73.7845],
            [19.9970, 73.7852],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "Go straight",
        "distance_to_next_m": 280,
        "confidence": 0.93,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 0,
        "route_polyline": [
            [19.9960, 73.7840],
            [19.9965, 73.7845],
            [19.9970, 73.7852],
            [19.9975, 73.7860],
            [19.9980, 73.7868],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "In 200 m, turn right",
        "distance_to_next_m": 200,
        "confidence": 0.91,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 1,
        "route_polyline": [
            [19.9960, 73.7840],
            [19.9970, 73.7852],
            [19.9980, 73.7868],
            [19.9988, 73.7878],
            [19.9993, 73.7890],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "Turn right",
        "distance_to_next_m": 50,
        "confidence": 0.96,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 1,
        "route_polyline": [
            [19.9960, 73.7840],
            [19.9980, 73.7868],
            [19.9993, 73.7890],
            [19.9998, 73.7902],
            [20.0002, 73.7915],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "Go straight",
        "distance_to_next_m": 400,
        "confidence": 0.94,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 2,
        "route_polyline": [
            [19.9960, 73.7840],
            [19.9993, 73.7890],
            [20.0002, 73.7915],
            [20.0005, 73.7930],
            [20.0008, 73.7948],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "VISUAL",
        "next_instruction_text": "In 150 m, turn left",
        "distance_to_next_m": 150,
        "confidence": 0.78,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 3,
        "route_polyline": [
            [19.9960, 73.7840],
            [20.0002, 73.7915],
            [20.0008, 73.7948],
            [20.0012, 73.7960],
            [20.0016, 73.7972],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "VISUAL",
        "next_instruction_text": "Turn left",
        "distance_to_next_m": 40,
        "confidence": 0.82,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 3,
        "route_polyline": [
            [19.9960, 73.7840],
            [20.0008, 73.7948],
            [20.0016, 73.7972],
            [20.0020, 73.7981],
            [20.0024, 73.7990],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "Go straight",
        "distance_to_next_m": 300,
        "confidence": 0.90,
        "off_route_flag": False,
        "destination_reached_flag": False,
        "active_step_index": 4,
        "route_polyline": [
            [19.9960, 73.7840],
            [20.0016, 73.7972],
            [20.0024, 73.7990],
            [20.0020, 73.8005],
            [20.0015, 73.8018],
        ],
    },
    {
        "session_id": "ride_test_001",
        "nav_mode": "OFFLINE",
        "position_mode": "GPS",
        "next_instruction_text": "You have arrived",
        "distance_to_next_m": 0,
        "confidence": 0.99,
        "off_route_flag": False,
        "destination_reached_flag": True,
        "active_step_index": 5,
        "route_polyline": [
            [19.9960, 73.7840],
            [20.0024, 73.7990],
            [20.0015, 73.8018],
            [20.0010, 73.8030],
            [20.0005, 73.8038],
        ],
    },
]


def check_server() -> bool:
    """Return True if the server is reachable."""
    try:
        r = requests.get(f"{SERVER}/status", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def connected_clients() -> int:
    """Return how many browser/app clients are currently connected."""
    try:
        r = requests.get(f"{SERVER}/status", timeout=3)
        return r.json().get("clients", 0)
    except Exception:
        return 0


def send(payload: dict) -> bool:
    payload["ts_ms"] = int(time.time() * 1000)
    try:
        r = requests.post(f"{SERVER}/receive", json=payload, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    # ── Step 1: verify server is running ─────────────────────────────────────
    print("Checking server...")
    if not check_server():
        print(f"\n  ERROR: Cannot reach {SERVER}")
        print("  Make sure Terminal 1 is running:")
        print("    python -m embedded.websocket_server\n")
        sys.exit(1)
    print(f"  Server OK at {SERVER}")

    # ── Step 2: wait for browser to connect ───────────────────────────────────
    print(f"\n  Open your browser at http://localhost:8765/")
    print("  Waiting for browser to connect", end="", flush=True)
    for _ in range(30):           # wait up to 30 seconds
        if connected_clients() > 0:
            break
        print(".", end="", flush=True)
        time.sleep(1)
    else:
        print("\n\n  No browser connected after 30 s.")
        print("  Open http://localhost:8765/ in Chrome/Edge, then re-run this script.\n")
        sys.exit(1)

    print(f"\n  Browser connected ({connected_clients()} client(s)). Starting stream...\n")
    print("-" * 55)

    # ── Step 3: stream GPS steps ──────────────────────────────────────────────
    for i, step in enumerate(ROUTE):
        pos    = step["route_polyline"][-1]
        ok     = send(step)
        status = "OK  " if ok else "FAIL"
        print(
            f"  [{status}]  step {i + 1:02}/{len(ROUTE)}"
            f"  lat={pos[0]:.4f}  lng={pos[1]:.4f}"
            f"  →  {step['next_instruction_text']}"
        )
        if i < len(ROUTE) - 1:
            time.sleep(1.5)

    print("\n  Route complete. Watch the map — blue dot should be at the final position.")