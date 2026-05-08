from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass
from typing import Optional, Protocol

from .nav_interface import PositionMode, UIStateMessage


VALID_ESP_COMMANDS = {
    "CLEAR",
    "STRAIGHT",
    "LEFT",
    "LEFT_NOW",
    "RIGHT",
    "RIGHT_NOW",
    "HAZARD",
    "SOS_ON",
    "SOS_OFF",
    "ARRIVED",
    "PING",
}


def normalize_esp_command(command: str) -> str:
    value = command.strip().upper()
    if value not in VALID_ESP_COMMANDS:
        raise ValueError(f"Unsupported ESP command: {command}")
    return value


def command_from_ui_state(state: UIStateMessage) -> str:
    """Translate the exact map instruction state into the ESP text protocol."""
    instruction = (state.next_instruction_text or "").lower()

    if "crash" in instruction or "sos" in instruction:
        return "SOS_ON"
    if state.off_route_flag:
        return "HAZARD"
    if state.destination_reached_flag or "arrive" in instruction or "destination" in instruction:
        return "ARRIVED"
    if state.position_mode == PositionMode.UNKNOWN:
        return "HAZARD"
    if "u-turn" in instruction or "u turn" in instruction or "u_turn" in instruction:
        return "RIGHT_NOW"
    if "right" in instruction:
        return "RIGHT"
    if "left" in instruction:
        return "LEFT"
    return "STRAIGHT"


class BluetoothWriter(Protocol):
    def send_line(self, line: str) -> bool:
        ...

    def close(self) -> None:
        ...


class SerialBluetoothWriter:
    """Writes newline-delimited ESP32 Bluetooth Serial commands to a paired COM port."""

    def __init__(self, port: str, baudrate: int = 115200, timeout_s: float = 1.0) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._serial = None

    def send_line(self, line: str) -> bool:
        try:
            if self._serial is None or not getattr(self._serial, "is_open", False):
                try:
                    import serial  # type: ignore[import-not-found]
                except ImportError as exc:
                    raise RuntimeError("pyserial is required: pip install pyserial") from exc

                self._serial = serial.Serial(
                    self._port,
                    self._baudrate,
                    timeout=self._timeout_s,
                    write_timeout=self._timeout_s,
                )

            self._serial.write((line + "\n").encode("ascii"))
            self._serial.flush()
            return True
        except Exception as exc:  # pragma: no cover - hardware dependent
            print(f"[ui-sync] bt->esp command={line} status=failed error={exc}")
            self.close()
            return False

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None


@dataclass
class BluetoothBridgeStatus:
    enabled: bool
    connected: bool
    last_command: Optional[str]
    last_error: Optional[str]


class BluetoothInstructionBridge:
    """
    Non-blocking bridge from map/UI instructions to the ESP32 Bluetooth link.

    The producer path calls ``publish_ui_state``. A background worker owns the
    serial port, so UI rendering and CV/DR navigation updates are never blocked
    by Bluetooth writes.
    """

    def __init__(
        self,
        writer: Optional[BluetoothWriter] = None,
        *,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        enabled: Optional[bool] = None,
        queue_size: int = 8,
    ) -> None:
        self._enabled = (
            enabled
            if enabled is not None
            else os.getenv("SMART_HELMET_BT_ENABLED", "1").strip().lower()
            not in {"0", "false", "no", "off"}
        )
        self._port = port or os.getenv("SMART_HELMET_BT_PORT")
        self._baudrate = int(baudrate or os.getenv("SMART_HELMET_BT_BAUD", "115200"))
        self._writer = writer
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._last_command: Optional[str] = None
        self._pending_command: Optional[str] = None
        self._last_error: Optional[str] = None
        self._connected = False

        if self._enabled and self._writer is None and self._port:
            self._writer = SerialBluetoothWriter(self._port, self._baudrate)

        self._thread: Optional[threading.Thread] = None
        if self._enabled and self._writer is not None:
            self._thread = threading.Thread(
                target=self._run,
                name="embedded-bt-instruction-bridge",
                daemon=True,
            )
            self._thread.start()
            target = self._port or "custom-writer"
            print(f"[ui-sync] bt bridge enabled target={target} baud={self._baudrate}")
        elif self._enabled:
            self._last_error = "SMART_HELMET_BT_PORT is not set"
            print("[ui-sync] bt bridge disabled reason=SMART_HELMET_BT_PORT_not_set")

    def publish_ui_state(self, state: UIStateMessage) -> Optional[str]:
        command = command_from_ui_state(state)
        if command == self._last_command or command == self._pending_command:
            return command
        if not self._enabled or self._writer is None:
            print(f"[ui-sync] state->bt command={command} status=skipped")
            return command

        try:
            self._queue.put_nowait(command)
            self._pending_command = command
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(command)
                self._pending_command = command
                print(f"[ui-sync] state->bt dropped_stale command={command}")
            except queue.Empty:
                self._last_error = "Bluetooth queue full"
                return command

        print(
            "[ui-sync] state->bt queued "
            f"instruction={state.next_instruction_text!r} command={command}"
        )
        return command

    def status(self) -> BluetoothBridgeStatus:
        return BluetoothBridgeStatus(
            enabled=self._enabled and self._writer is not None,
            connected=self._connected,
            last_command=self._last_command,
            last_error=self._last_error,
        )

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._writer is not None:
            self._writer.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                command = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                command = normalize_esp_command(command)
                sent = self._writer.send_line(command) if self._writer else False
                self._connected = bool(sent)
                if sent:
                    self._last_command = command
                    if self._pending_command == command:
                        self._pending_command = None
                    self._last_error = None
                    print(f"[ui-sync] bt->esp command={command} status=sent")
                else:
                    if self._pending_command == command:
                        self._pending_command = None
                    self._last_error = "writer returned False"
                    print(f"[ui-sync] bt->esp command={command} status=failed")
            except Exception as exc:
                if self._pending_command == command:
                    self._pending_command = None
                self._connected = False
                self._last_error = str(exc)
                print(f"[ui-sync] bt->esp command={command} status=failed error={exc}")
