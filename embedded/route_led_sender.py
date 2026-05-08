#!/usr/bin/env python3
"""
route_led_sender.py
--------------------
Sends TCP commands to the ESP32 smart helmet LED board in sync with
map update events from the CV/DR localization module.

This script listens for navigation events (e.g., "left turn approaching",
"right turn now", "arrived") and sends the corresponding LED commands
to the ESP32 over the local hotspot network (no internet required).

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

Run AFTER starting the localization module and map server:
  Terminal 1:  python -m embedded.websocket_server
  Browser:     http://localhost:8765/
  Terminal 2:  python embedded/test_input.py  # or your CV/DR module
  Terminal 3:  python route_led_sender.py
"""

import socket
import sys
import time

# ============================================
# Config — Update ESP32 IP from Serial Monitor
# ============================================
DEFAULT_ESP32_IP = "10.125.249.164"  # Change to your ESP32's actual IP
FALLBACK_IPS = ["192.168.4.1"]
PORT = 80
TIMEOUT = 2

# ============================================
# Route Event Schedule for Shaniwar Wada to Pune Metro Stations
# ============================================
# This is a SAMPLE schedule based on a typical route from Shaniwar Wada
# to Civil Court Metro Station in Pune. Update with your actual CV/DR
# module event timings and turn types.
#
# Key = seconds from route start when the event should fire
# Value = ESP32 command string
#
# Mapping from CV/DR events:
#   "straight" / no maneuver          → CLEAR
#   "left approaching"                → LEFT_PREPARE
#   "left now"                        → LEFT_NOW
#   "right approaching"               → RIGHT_PREPARE
#   "right now"                       → RIGHT_NOW
#   "off-route" / "crash"             → HAZARD
#   "arrived"                         → ARRIVED
#
# Estimated route: Shaniwar Wada → Tilak Road → Civil Court Metro
# - Start straight
# - Left turn approaching at 30s
# - Left turn execute at 35s
# - Straight for a bit
# - Right turn approaching at 60s
# - Right turn execute at 65s
# - Arrive at 90s

SIGNAL_SCHEDULE: dict[float, str] = {
     0.0: "CLEAR",          # Start: straight from Shaniwar Wada
    10.0: "CLEAR",          # Continue straight
    20.0: "CLEAR",          # Still straight
    30.0: "LEFT_PREPARE",   # Approaching left turn onto Tilak Road
    35.0: "LEFT_NOW",       # Execute left turn
    40.0: "CLEAR",          # Straight on Tilak Road
    50.0: "CLEAR",          # Continue straight
    60.0: "RIGHT_PREPARE",  # Approaching right turn to Civil Court
    65.0: "RIGHT_NOW",      # Execute right turn
    70.0: "CLEAR",          # Straight to metro station
    80.0: "CLEAR",          # Approaching destination
    90.0: "ARRIVED",        # Arrived at Civil Court Metro
}


def try_send_command(cmd, ip, retries=3):
    for attempt in range(retries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TIMEOUT)
                s.connect((ip, PORT))
                s.sendall((cmd + "\n").encode("utf-8"))
                response = s.recv(1024).decode("utf-8").strip()
            print(f"✓ SENT: {cmd:20} | IP: {ip:15} | RESPONSE: {response}")
            return True
        except socket.timeout:
            print(f"✗ TIMEOUT: {cmd:20} | IP: {ip:15} | Attempt {attempt+1}/{retries}")
        except ConnectionRefusedError:
            print(f"✗ REFUSED: {cmd:20} | IP: {ip:15} | Attempt {attempt+1}/{retries}")
        except Exception as e:
            print(f"✗ ERROR:  {cmd:20} | IP: {ip:15} | {type(e).__name__}: {e} | Attempt {attempt+1}/{retries}")
        if attempt < retries - 1:
            time.sleep(1)  # Wait 1s before retry
    return False


def send_command(cmd, ips):
    for ip in ips:
        if try_send_command(cmd, ip):
            return True
    print("✗ All IPs failed. Check ESP32 IP and network.")
    return False


def ping_esp32(ips):
    """Check ESP32 is reachable before starting."""
    return send_command("PING", ips)


def main():
    ips = [DEFAULT_ESP32_IP] + FALLBACK_IPS
    print("\n" + "=" * 60)
    print("  SmartHelmet Route LED Sender")
    print("  (Shaniwar Wada to Pune Metro Stations)")
    print("=" * 60)
    print(f"\nTarget ESP32 candidates: {ips}")
    print(f"Route steps: {len(SIGNAL_SCHEDULE)} | Duration: ~{max(SIGNAL_SCHEDULE):.0f} s\n")

    if not ping_esp32(ips):
        print("  WARNING: ESP32 not reachable")
        print("  Options:")
        print("    • Check ESP32 IP in Serial Monitor")
        print("    • Ensure laptop and ESP32 are on same hotspot")
        ans = input("  Continue anyway? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit(0)
    else:
        print("  ESP32 OK — starting route in 3 s\n")
        time.sleep(3)

    sorted_times = sorted(SIGNAL_SCHEDULE)
    route_start = time.monotonic()

    for target_t in sorted_times:
        cmd = SIGNAL_SCHEDULE[target_t]
        elapsed = time.monotonic() - route_start
        wait = target_t - elapsed
        if wait > 0:
            time.sleep(wait)

        actual_t = time.monotonic() - route_start
        ok = send_command(cmd, ips)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}]  t={actual_t:5.1f}s  → {cmd}")

    print("\nRoute complete.")
    print("  ESP32 LEDs should now show ARRIVED (green blink).")
    print("  Send CLEAR to reset: python send_led_command.py CLEAR")


if __name__ == "__main__":
    main()
