import asyncio
import logging
import os
import queue
import threading
from typing import Any, Dict, Optional

import httpx

from .led_command_mapper import (
    command_from_instruction,
    command_from_ui_state,
    describe_ui_state,
    normalize_led_command,
)

logger = logging.getLogger("navigation_hardware")

class BluetoothSerialLEDTransport:
    """Background serial writer for ESP32 Bluetooth SPP COM ports."""

    def __init__(self, port: str, baudrate: int = 115200, timeout_s: float = 1.0) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="smart-helmet-bt-led",
            daemon=True,
        )
        self._thread.start()

    def send(self, command: str) -> bool:
        command = normalize_led_command(command)
        try:
            self._queue.put_nowait(command)
            return True
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(command)
                return True
            except queue.Empty:
                return False

    def close(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        serial_module = None
        link = None

        while not self._stop.is_set():
            try:
                command = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                if serial_module is None:
                    import serial as serial_module  # type: ignore[import-not-found,no-redef]

                if link is None or not getattr(link, "is_open", False):
                    link = serial_module.Serial(
                        self._port,
                        self._baudrate,
                        timeout=self._timeout_s,
                        write_timeout=self._timeout_s,
                    )

                link.write((command + "\n").encode("ascii"))
                link.flush()
                reply = link.readline().decode("ascii", errors="replace").strip()
                logger.info("[HW] Bluetooth LED command sent: %s reply=%s", command, reply or "NO_REPLY")
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.warning("[HW] Bluetooth LED send failed on %s: %s", self._port, exc)
                if link is not None:
                    try:
                        link.close()
                    except Exception:
                        pass
                link = None


class HardwareService:
    """
    Manages communication with the Smart Helmet ESP32 LED hardware.
    Maps navigation instructions and system states to specific LED patterns.
    """

    def __init__(
        self,
        esp32_ip: str = "10.100.30.164",
        transport: Optional[str] = None,
        bluetooth_port: Optional[str] = None,
        bluetooth_baudrate: Optional[int] = None,
    ):
        self.esp32_ip = esp32_ip
        self.base_url = f"http://{esp32_ip}/command"
        self.last_command: Optional[str] = None
        self._disabled = False
        self.transport = (transport or os.getenv("SMART_HELMET_LED_TRANSPORT", "http")).strip().lower()
        self.bluetooth_port = bluetooth_port or os.getenv("SMART_HELMET_BT_PORT")
        self.bluetooth_baudrate = int(
            bluetooth_baudrate
            or os.getenv("SMART_HELMET_BT_BAUD", "115200")
        )
        self._bt_transport: Optional[BluetoothSerialLEDTransport] = None

        if self.transport == "bluetooth":
            if self.bluetooth_port:
                self._bt_transport = BluetoothSerialLEDTransport(
                    port=self.bluetooth_port,
                    baudrate=self.bluetooth_baudrate,
                )
                logger.info(
                    "[HW] Bluetooth LED transport enabled on %s @ %s",
                    self.bluetooth_port,
                    self.bluetooth_baudrate,
                )
            else:
                logger.warning("[HW] SMART_HELMET_LED_TRANSPORT=bluetooth but SMART_HELMET_BT_PORT is not set")

    async def update_from_ui_state(self, ui_state: Dict[str, Any]) -> None:
        command = command_from_ui_state(ui_state)
        logger.debug("[HW] LED mapping %s -> %s", describe_ui_state(ui_state), command)
        await self.send_command(command)

    async def update_from_instruction(self, instruction: str, is_gps_failed: bool = False):
        """
        Maps a text instruction (e.g., 'Turn Right') to an ESP32 command.
        """
        command = command_from_instruction(instruction, is_gps_failed=is_gps_failed)

        # Suppress redundant commands
        if command == self.last_command:
            return

        await self.send_command(command)

    async def send_command(self, cmd: str):
        """Dispatches the command to the ESP32 hardware."""
        cmd = normalize_led_command(cmd)
        if self._disabled:
            return
        if cmd == self.last_command:
            return

        if self.transport in {"disabled", "off", "none"}:
            logger.debug("[HW] LED transport disabled; dropping %s", cmd)
            return

        if self.transport == "bluetooth":
            if self._bt_transport is None:
                logger.debug("[HW] Bluetooth LED transport unavailable; dropping %s", cmd)
                return
            queued = self._bt_transport.send(cmd)
            if queued:
                logger.info("[HW] Bluetooth LED queued: %s", cmd)
                self.last_command = cmd
            else:
                logger.warning("[HW] Bluetooth LED queue full; dropped %s", cmd)
            await asyncio.sleep(0)
            return

        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                params = {"cmd": cmd}
                resp = await client.get(self.base_url, params=params)
                
                if resp.status_code == 200:
                    logger.info(f"[HW] Signal Sent: {cmd}")
                    self.last_command = cmd
                else:
                    logger.warning(f"[HW] ESP32 rejected command {cmd}: HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"[HW] ESP32 unreachable at {self.esp32_ip}. Error: {e}")
            # We don't log errors at 'warning' level here because 
            # the hardware might not be connected during every test.

    def set_ip(self, ip: str):
        self.esp32_ip = ip
        self.base_url = f"http://{ip}/command"
        logger.info(f"[HW] ESP32 Target Updated: {ip}")

    def close(self) -> None:
        if self._bt_transport is not None:
            self._bt_transport.close()
