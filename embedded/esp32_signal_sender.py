"""
esp32_signal_sender.py
----------------------
Sends Wi-Fi HTTP commands to the ESP32 smart helmet LED board
(smart_helmet_wifi_led.ino) in sync with the test_input.py demo.

The demo plays 21 navigation steps, one every 2.5 s.
This script fires the matching LED command at each step's timestamp.

ESP32 endpoint:  GET http://<ESP32_IP>/command?cmd=<COMMAND>
Supported commands:
  CLEAR          – all LEDs off
  LEFT_PREPARE   – left yellow blink (slow, ~550 ms) — approaching left turn
  LEFT_NOW       – left yellow solid + green chase — execute left turn
  LEFT_MISSED    – left yellow fast blink — missed turn alert
  RIGHT_PREPARE  – right yellow blink (slow) — approaching right turn
  RIGHT_NOW      – right yellow solid + green chase — execute right turn
  RIGHT_MISSED   – right yellow fast blink — missed turn alert
  HAZARD         – both yellow fast blink — crash / off-route / blackout
  ARRIVED        – both green slow blink — destination reached

Run AFTER starting the demo server:
  Terminal 1:  python -m embedded.websocket_server
  Browser:     http://localhost:8765/
  Terminal 2:  python embedded/test_input.py
  Terminal 3:  python embedded/esp32_signal_sender.py
"""

import sys
import time

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

# ── Config — set ESP32's IP address here ────────────────────────────────────
ESP32_IP = "192.168.4.1"   # Default AP mode IP; change to STA IP if on same Wi-Fi
ESP32_URL = f"http://{ESP32_IP}/command"
TIMEOUT_S = 2              # Per-request timeout

# ── Demo timing ──────────────────────────────────────────────────────────────
# Each step in test_input.py is separated by 2.5 s.
# Key   = seconds from demo start when the command should fire.
# Value = ESP32 command string.
#
# Mapping logic per step:
#   STRAIGHT / no maneuver          → CLEAR
#   Approaching slight/full left    → LEFT_PREPARE  (2+ steps before turn)
#   Execute left turn               → LEFT_NOW
#   Approaching slight/full right   → RIGHT_PREPARE
#   Execute right turn              → RIGHT_NOW
#   Off-route / crash / blackout    → HAZARD
#   Arrived                         → ARRIVED
#
# Step index → t = step_index * 2.5 s
#
#  0  t= 0.0  STRAIGHT, head north-east from MIT WPU         → CLEAR
#  1  t= 2.5  SLIGHT_RIGHT onto NH-48 slip road (prepare)    → RIGHT_PREPARE
#  2  t= 5.0  RIGHT onto NH-48 main carriageway (execute)    → RIGHT_NOW
#  3  t= 7.5  STRAIGHT on NH-48 northbound                   → CLEAR
#  4  t=10.0  STRAIGHT — Shankar Chowk flyover               → CLEAR
#  5  t=12.5  GPS brief loss under flyover (ONLINE+VISUAL)   → CLEAR
#  6  t=15.0  Offline maps active, GPS restored              → CLEAR
#  7  t=17.5  SLIGHT_RIGHT — NH-48 curve near Iffco Metro    → RIGHT_PREPARE
#  8  t=20.0  STRAIGHT — NH-48 main stretch                  → CLEAR
#  9  t=22.5  STRAIGHT — Hero Honda Chowk                    → CLEAR
# 10  t=25.0  STRAIGHT — approaching Rajokri                 → CLEAR
# 11  t=27.5  GPS lost — CV localization active              → CLEAR
# 12  t=30.0  STRAIGHT — Vijit CV tracking                   → CLEAR
# 13  t=32.5  SLIGHT_LEFT — signal degraded, CV only         → LEFT_PREPARE
# 14  t=35.0  Complete blackout, last position held          → HAZARD
# 15  t=37.5  Signals restored, SLIGHT_RIGHT recalculated    → RIGHT_PREPARE
# 16  t=40.0  OFF ROUTE — missed exit, recalculating         → HAZARD
# 17  t=42.5  Rerouted — SLIGHT_LEFT near airport            → LEFT_PREPARE
# 18  t=45.0  CRASH DETECTED — SOS sent                      → HAZARD
# 19  t=47.5  SLIGHT_RIGHT — Pavillion Mall in 400 m         → RIGHT_PREPARE
# 20  t=50.0  ARRIVED at Pavillion Mall                      → ARRIVED

SIGNAL_SCHEDULE: dict[float, str] = {
     0.0: "CLEAR",
     2.5: "RIGHT_PREPARE",
     5.0: "RIGHT_NOW",
     7.5: "CLEAR",
    10.0: "CLEAR",
    12.5: "CLEAR",
    15.0: "CLEAR",
    17.5: "RIGHT_PREPARE",
    20.0: "CLEAR",
    22.5: "CLEAR",
    25.0: "CLEAR",
    27.5: "CLEAR",
    30.0: "CLEAR",
    32.5: "LEFT_PREPARE",
    35.0: "HAZARD",
    37.5: "RIGHT_PREPARE",
    40.0: "HAZARD",
    42.5: "LEFT_PREPARE",
    45.0: "HAZARD",
    47.5: "RIGHT_PREPARE",
    50.0: "ARRIVED",
}


def send_command(cmd: str) -> bool:
    """Send a command to the ESP32 via HTTP GET. Returns True on success."""
    try:
        r = requests.get(ESP32_URL, params={"cmd": cmd}, timeout=TIMEOUT_S)
        return r.status_code == 200 and r.json().get("ok", False)
    except Exception as exc:
        print(f"    [WARN] ESP32 unreachable: {exc}")
        return False


def ping_esp32() -> bool:
    """Check ESP32 is reachable before starting."""
    try:
        r = requests.get(f"http://{ESP32_IP}/health", timeout=TIMEOUT_S)
        return r.status_code == 200
    except Exception:
        return False


def main() -> None:
    print("\nSmartHelmet — ESP32 Signal Sender")
    print(f"Target:  {ESP32_URL}")
    print(f"Steps:   {len(SIGNAL_SCHEDULE)}  |  Demo duration: ~{max(SIGNAL_SCHEDULE):.0f} s\n")

    if not ping_esp32():
        print(f"  WARNING: ESP32 not reachable at {ESP32_IP}")
        print("  Options:")
        print("    • If ESP32 is in AP mode, connect your PC to Wi-Fi: SmartHelmet-ESP32-AP (pw: helmet1234)")
        print("    • If ESP32 joined your router, find its IP from Serial Monitor and update ESP32_IP")
        ans = input("  Continue anyway? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit(0)
    else:
        print("  ESP32 OK — starting in 3 s (start test_input.py now if not already running)\n")
        time.sleep(3)

    sorted_times = sorted(SIGNAL_SCHEDULE)
    demo_start = time.monotonic()

    for target_t in sorted_times:
        cmd = SIGNAL_SCHEDULE[target_t]
        elapsed = time.monotonic() - demo_start
        wait = target_t - elapsed
        if wait > 0:
            time.sleep(wait)

        actual_t = time.monotonic() - demo_start
        ok = send_command(cmd)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}]  t={actual_t:5.1f}s  → {cmd}")

    print("\nSchedule complete.")
    print("  ESP32 LEDs should now show ARRIVED (green blink).")
    print("  Send CLEAR to reset:  python -c \"import requests; requests.get('http://"
          + ESP32_IP + "/command?cmd=CLEAR')\"")


if __name__ == "__main__":
    main()
