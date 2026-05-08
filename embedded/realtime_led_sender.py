#!/usr/bin/env python3
"""
realtime_led_sender.py
-----------------------
Real-time LED command sender for ESP32 smart helmet.

This script connects to the WebSocket server (ws://localhost:8765/ws) and listens
for navigation UI state messages. Based on the next_instruction_text and
distance_to_next_m, it sends appropriate LED commands to the ESP32 over TCP.

No timing required — reacts instantly to live CV/DR events.

Supported commands:
  CLEAR          – all LEDs off (straight, far from turn)
  LEFT_PREPARE   – left yellow blink (slow) — approaching left turn (<50m)
  LEFT_NOW       – left yellow solid + green chase — execute left turn (<10m)
  RIGHT_PREPARE  – right yellow blink (slow) — approaching right turn (<50m)
  RIGHT_NOW      – right yellow solid + green chase — execute right turn (<10m)
  HAZARD         – both yellow fast blink — off-route or low confidence
  ARRIVED        – both green slow blink — destination reached

Logic:
- If destination_reached_flag: ARRIVED
- If off_route_flag or confidence < 0.5: HAZARD
- Else, parse next_instruction_text:
  - "TURN LEFT" or "LEFT": LEFT_PREPARE if distance >10, LEFT_NOW if <=10
  - "TURN RIGHT" or "RIGHT": RIGHT_PREPARE/RIGHT_NOW
  - "STRAIGHT" or "CONTINUE": CLEAR
- Default: CLEAR

Run AFTER starting the navigation server and websocket server:
  Terminal 1:  python -m uvicorn navigation.server:app --port 8000
  Terminal 2:  python -m embedded.websocket_server
  Terminal 3:  python realtime_led_sender.py
"""

import asyncio
import json
import socket
import sys
import websockets
from websockets.exceptions import ConnectionClosed

# ============================================
# Config — Update ESP32 IP from Serial Monitor
# ============================================
DEFAULT_ESP32_IP = "10.125.249.164"  # Change to your ESP32's actual IP
FALLBACK_IPS = ["192.168.4.1"]
PORT = 80
TIMEOUT = 2

# WebSocket server
WS_URL = "ws://localhost:8765/ws"

# LED command logic
PREPARE_DISTANCE = 50  # meters to start prepare
NOW_DISTANCE = 10      # meters to execute turn
MIN_CONFIDENCE = 0.5   # below this, hazard


def try_send_command(cmd, ips, retries=3):
    for ip in ips:
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
                import time
                time.sleep(0.5)  # Wait before retry
    print(f"✗ All IPs failed for {cmd}")
    return False


def get_led_command(state):
    """Parse UI state and return LED command."""
    if state.get("destination_reached_flag"):
        return "ARRIVED"
    if state.get("off_route_flag") or state.get("confidence", 1.0) < MIN_CONFIDENCE:
        return "HAZARD"

    instruction = state.get("next_instruction_text", "").upper()
    distance = state.get("distance_to_next_m", float('inf'))

    if "LEFT" in instruction:
        if distance <= NOW_DISTANCE:
            return "LEFT_NOW"
        elif distance <= PREPARE_DISTANCE:
            return "LEFT_PREPARE"
    elif "RIGHT" in instruction:
        if distance <= NOW_DISTANCE:
            return "RIGHT_NOW"
        elif distance <= PREPARE_DISTANCE:
            return "RIGHT_PREPARE"
    elif "STRAIGHT" in instruction or "CONTINUE" in instruction:
        return "CLEAR"

    return "CLEAR"  # Default


async def websocket_listener():
    ips = [DEFAULT_ESP32_IP] + FALLBACK_IPS
    last_cmd = None

    print("\n" + "=" * 60)
    print("  SmartHelmet Real-Time LED Sender")
    print("  (WebSocket → ESP32 TCP)")
    print("=" * 60)
    print(f"WebSocket: {WS_URL}")
    print(f"ESP32 IPs: {ips}")
    print("\nListening for navigation events...\n")

    try:
        async with websockets.connect(WS_URL) as ws:
            async for message in ws:
                try:
                    data = json.loads(message)
                    if data.get("type") == "ui_state":
                        cmd = get_led_command(data)
                        if cmd != last_cmd:
                            print(f"Event: {data['next_instruction_text'][:30]:30} | Dist: {data['distance_to_next_m']:5.1f}m | Cmd: {cmd}")
                            try_send_command(cmd, ips)
                            last_cmd = cmd
                except json.JSONDecodeError:
                    pass
    except ConnectionClosed:
        print("WebSocket connection closed.")
    except Exception as e:
        print(f"WebSocket error: {e}")


def main():
    try:
        asyncio.run(websocket_listener())
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()