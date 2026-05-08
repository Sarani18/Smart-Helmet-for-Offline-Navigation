"""
Send navigation LED commands from this machine to the ESP32 over Bluetooth Serial.

Pair the ESP32 Bluetooth device named SmartHelmet-LED first, then set the paired
COM port with --port or SMART_HELMET_BT_PORT.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from navigation.led_command_mapper import command_from_ui_state, normalize_led_command


def send_bluetooth(port: str, command: str, baudrate: int = 115200, timeout_s: float = 1.0) -> str:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyserial is required. Install it with: pip install pyserial") from exc

    command = normalize_led_command(command)
    with serial.Serial(port, baudrate, timeout=timeout_s, write_timeout=timeout_s) as link:
        link.write((command + "\n").encode("ascii"))
        link.flush()
        return link.readline().decode("ascii", errors="replace").strip()


def fetch_ui_state(api_url: str, session_id: str) -> dict[str, Any]:
    payload = json.dumps(
        {"session_id": session_id, "ts_ms": int(time.time() * 1000)}
    ).encode("utf-8")
    request = urllib.request.Request(
        api_url.rstrip("/") + "/api/navigation/ui/state",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.0) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["ui_state"]


def run_watch(args: argparse.Namespace) -> None:
    last_command: Optional[str] = None
    while True:
        try:
            ui_state = fetch_ui_state(args.api_url, args.session_id)
            command = command_from_ui_state(ui_state)
            if command != last_command:
                reply = send_bluetooth(args.port, command, args.baudrate)
                print(f"{command} -> {reply or 'NO_REPLY'}")
                last_command = command
        except (urllib.error.URLError, TimeoutError, KeyError, RuntimeError, ValueError) as exc:
            print(f"WARN: {exc}")
        time.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32 Bluetooth LED command sender")
    parser.add_argument("--port", required=True, help="Paired ESP32 serial port, for example COM6")
    parser.add_argument("--baudrate", type=int, default=115200)

    subparsers = parser.add_subparsers(dest="mode", required=True)

    send_parser = subparsers.add_parser("send", help="Send one LED command")
    send_parser.add_argument("command", help="STRAIGHT, LEFT_NOW, RIGHT_NOW, SOS_ON, ARRIVED, etc.")

    watch_parser = subparsers.add_parser("watch", help="Poll Navigation API and forward LED commands")
    watch_parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    watch_parser.add_argument("--session-id", required=True)
    watch_parser.add_argument("--interval", type=float, default=0.5)

    args = parser.parse_args()
    if args.mode == "send":
        reply = send_bluetooth(args.port, args.command, args.baudrate)
        print(reply or "NO_REPLY")
    else:
        run_watch(args)


if __name__ == "__main__":
    main()
