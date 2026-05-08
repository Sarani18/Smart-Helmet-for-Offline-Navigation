#!/usr/bin/env python3
"""
send_led_command.py

Send LED commands to ESP32 over WiFi from your laptop.
Usage:
  python send_led_command.py LEFT_NOW
  python send_led_command.py RIGHT_PREPARE
  python send_led_command.py CLEAR
  python send_led_command.py --ip 10.125.249.164 PING
  python send_led_command.py --scan PING
"""

import socket
import sys
import time

DEFAULT_ESP32_IP = "10.125.249.164"
PORT = 80
TIMEOUT = 2
FALLBACK_IPS = ["192.168.4.1"]


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None


def network_prefix(ip):
    if not ip:
        return None
    parts = ip.split('.')
    if len(parts) != 4:
        return None
    return '.'.join(parts[:3])


def scan_for_esp(prefix):
    if not prefix:
        return []
    print(f"Scanning subnet {prefix}.0/24 for ESP32 port {PORT}...\n")
    found = []
    for i in range(1, 255):
        addr = f"{prefix}.{i}"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.25)
            result = s.connect_ex((addr, PORT))
            s.close()
            if result == 0:
                found.append(addr)
                print(f"  Found open port 80 at {addr}")
        except Exception:
            pass
    return found


def try_send_command(cmd, ip):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((ip, PORT))
            s.sendall((cmd + "\n").encode("utf-8"))
            response = s.recv(1024).decode("utf-8").strip()
        print(f"✓ SENT: {cmd:20} | IP: {ip:15} | RESPONSE: {response}")
        return True
    except socket.timeout:
        print(f"✗ TIMEOUT: {cmd:20} | IP: {ip:15}")
        return False
    except ConnectionRefusedError:
        print(f"✗ REFUSED: {cmd:20} | IP: {ip:15}")
        return False
    except Exception as e:
        print(f"✗ ERROR:  {cmd:20} | IP: {ip:15} | {type(e).__name__}: {e}")
        return False


def send_command(cmd, ips):
    for ip in ips:
        if try_send_command(cmd, ip):
            return True
    print("✗ All IPs failed. Check ESP32 IP and network.")
    return False


def show_commands():
    print("\nAvailable commands:")
    print("  LEFT_NOW       - Left turn (yellow solid + green chase)")
    print("  LEFT_PREPARE   - Approaching left (yellow blink slow)")
    print("  LEFT_MISSED    - Missed left (yellow blink fast)")
    print("  RIGHT_NOW      - Right turn (yellow solid + green chase)")
    print("  RIGHT_PREPARE  - Approaching right (yellow blink slow)")
    print("  RIGHT_MISSED   - Missed right (yellow blink fast)")
    print("  HAZARD         - Both sides blink (danger/crash)")
    print("  ARRIVED        - Destination reached (green blink)")
    print("  CLEAR          - All LEDs off")
    print("  PING           - Test connection")
    print("  EXIT           - Quit interactive mode\n")


def parse_args():
    ips = [DEFAULT_ESP32_IP] + FALLBACK_IPS
    scan = False
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--ip", "-i") and len(sys.argv) > 2:
            ips = [sys.argv[2]] + FALLBACK_IPS
            return ips, sys.argv[3:], scan
        if sys.argv[1] == "--scan":
            scan = True
            return ips, sys.argv[2:], scan
        return ips, sys.argv[1:], scan
    return ips, [], scan


def main():
    ips, remaining, scan = parse_args()
    local_ip = get_local_ip()
    if local_ip:
        print(f"Local machine IP: {local_ip}")
        prefix = network_prefix(local_ip)
    else:
        prefix = None

    if scan and prefix:
        found = scan_for_esp(prefix)
        if found:
            ips = found + ips
        else:
            print("No additional ESP candidates found by scan.")

    print("\n" + "=" * 60)
    print("  SmartHelmet ESP32 TCP LED Command Sender")
    print("=" * 60)
    print(f"\nTarget ESP32 candidates: {ips}")

    if remaining:
        cmd = remaining[0].upper()
        print(f"\nSending command: {cmd}")
        send_command(cmd, ips)
        return

    show_commands()
    print("Commands: Type a command above or 'exit' to quit\n")
    try:
        while True:
            cmd = input(">> ").strip().upper()
            if cmd == "EXIT":
                print("Goodbye!\n")
                break
            if cmd:
                send_command(cmd, ips)
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!\n")


if __name__ == "__main__":
    main()
