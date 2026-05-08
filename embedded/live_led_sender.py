#!/usr/bin/env python3
"""
live_led_sender.py
--------------------
Reads CV/DR simulation output from stdin (pipe from simulation_driver.py)
and sends LED commands to ESP32 based on navigation instructions.

Usage:
  python simulation_driver.py | python live_led_sender.py

This script parses the live output and sends commands when:
- "HEAD LEFT" or "TURN LEFT" with distance <=50m → LEFT_PREPARE
- "HEAD LEFT" or "TURN LEFT" with distance <=10m → LEFT_NOW
- "HEAD RIGHT" or "TURN RIGHT" with distance <=50m → RIGHT_PREPARE
- "HEAD RIGHT" or "TURN RIGHT" with distance <=10m → RIGHT_NOW
- "CONTINUE STRAIGHT" → CLEAR
- "Scene: LEFT" → LEFT_NOW (if not already sent)
- "Scene: RIGHT" → RIGHT_NOW (if not already sent)
- "JUNCTION" → HAZARD (briefly)
- Destination reached logic if needed

Commands are sent only when state changes to avoid spam.
"""

import socket
import sys
import re
import time

# ============================================
# Config — Update ESP32 IP from Serial Monitor
# ============================================
DEFAULT_ESP32_IP = "10.125.249.164"  # Change to your ESP32's actual IP
FALLBACK_IPS = ["192.168.4.1"]
PORT = 80
TIMEOUT = 2

# LED command logic
PREPARE_DISTANCE = 50  # meters to start prepare
NOW_DISTANCE = 10      # meters to execute turn

# State tracking
last_cmd = None
last_turn_type = None  # 'LEFT' or 'RIGHT'
last_distance = float('inf')

def try_send_command(cmd, ips, retries=3):
    global last_cmd
    if cmd == last_cmd:
        return  # Don't spam same command
    for ip in ips:
        for attempt in range(retries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(TIMEOUT)
                    s.connect((ip, PORT))
                    s.sendall((cmd + "\n").encode("utf-8"))
                    response = s.recv(1024).decode("utf-8").strip()
                print(f"✓ SENT: {cmd:20} | IP: {ip:15} | RESPONSE: {response}")
                last_cmd = cmd
                return True
            except socket.timeout:
                print(f"✗ TIMEOUT: {cmd:20} | IP: {ip:15} | Attempt {attempt+1}/{retries}")
            except ConnectionRefusedError:
                print(f"✗ REFUSED: {cmd:20} | IP: {ip:15} | Attempt {attempt+1}/{retries}")
            except Exception as e:
                print(f"✗ ERROR:  {cmd:20} | IP: {ip:15} | {type(e).__name__}: {e} | Attempt {attempt+1}/{retries}")
            if attempt < retries - 1:
                time.sleep(0.5)  # Wait before retry
    print(f"✗ All IPs failed for {cmd}")


def parse_nav_line(line):
    """Parse navigation line like '[NAV] │ NAV: HEAD LEFT ON PAUD ROAD (in 56m)'"""
    match = re.search(r'NAV:\s*(.+?)\s*\(in\s+(\d+)m\)', line)
    if match:
        instruction = match.group(1).strip().upper()
        distance = int(match.group(2))
        return instruction, distance
    return None, None


def parse_cv_line(line):
    """Parse CV line like '[CV] F# 15 │ Scene: LEFT │ Δhdg: -90.0° │ conf: 88%'"""
    if 'Scene:' in line:
        scene_match = re.search(r'Scene:\s*(\w+)', line)
        if scene_match:
            scene = scene_match.group(1).upper()
            return scene
    if 'JUNCTION' in line:
        return 'JUNCTION'
    return None


def get_led_command(instruction, distance, scene):
    global last_turn_type, last_distance

    # Handle JUNCTION
    if scene == 'JUNCTION':
        return 'HAZARD'

    # Handle scene detection (actual turn execution)
    if scene == 'LEFT':
        last_turn_type = 'LEFT'
        return 'LEFT_NOW'
    elif scene == 'RIGHT':
        last_turn_type = 'RIGHT'
        return 'RIGHT_NOW'

    # Handle navigation instructions
    if instruction:
        if 'LEFT' in instruction:
            last_turn_type = 'LEFT'
            if distance <= NOW_DISTANCE:
                return 'LEFT_NOW'
            elif distance <= PREPARE_DISTANCE:
                return 'LEFT_PREPARE'
        elif 'RIGHT' in instruction:
            last_turn_type = 'RIGHT'
            if distance <= NOW_DISTANCE:
                return 'RIGHT_NOW'
            elif distance <= PREPARE_DISTANCE:
                return 'RIGHT_PREPARE'
        elif 'CONTINUE' in instruction or 'STRAIGHT' in instruction:
            return 'CLEAR'

    # Default
    return None


def main():
    ips = [DEFAULT_ESP32_IP] + FALLBACK_IPS
    print("\n" + "=" * 60)
    print("  SmartHelmet Live LED Sender")
    print("  (Reads from simulation_driver.py pipe)")
    print("=" * 60)
    print(f"ESP32 IPs: {ips}")
    print("Parsing navigation output...\n")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            # Parse NAV lines
            instruction, distance = parse_nav_line(line)
            if instruction and distance is not None:
                cmd = get_led_command(instruction, distance, None)
                if cmd:
                    try_send_command(cmd, ips)

            # Parse CV lines
            scene = parse_cv_line(line)
            if scene:
                cmd = get_led_command(None, None, scene)
                if cmd:
                    try_send_command(cmd, ips)

    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()