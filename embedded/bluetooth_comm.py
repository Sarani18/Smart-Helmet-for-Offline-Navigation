"""
Bluetooth Communication
-----------------------
Manages the Bluetooth connection between the mobile application and the
helmet-mounted microcontroller.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class BluetoothComm:
    """
    Abstraction layer for BLE (Bluetooth Low Energy) communication between
    the smartphone app and the helmet device.

    Responsibilities
    ----------------
    - Scan for and connect to the helmet BLE peripheral.
    - Send encoded instruction packets to the helmet.
    - Receive status / acknowledgement packets from the helmet.
    - Manage reconnection logic on signal loss.
    - Notify the application layer via callbacks on connection state changes.
    """

    def __init__(self) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._device_address: Optional[str] = None
        self._on_state_change: Optional[Callable[[ConnectionState], None]] = None
        self._on_data_received: Optional[Callable[[bytes], None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_state_callback(
        self, callback: Callable[[ConnectionState], None]
    ) -> None:
        """Register a function to be called whenever the connection state changes."""
        self._on_state_change = callback

    def register_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """Register a function to be called whenever data arrives from the helmet."""
        self._on_data_received = callback

    def scan(self, timeout_seconds: float = 10.0) -> list:
        """
        Scan for BLE devices and return a list of discovered device addresses.
        In production this calls the platform BLE API; here it returns a stub.
        """
        self._set_state(ConnectionState.SCANNING)
        # TODO: integrate with platform BLE scan (e.g. bleak / Android BLE API)
        self._set_state(ConnectionState.DISCONNECTED)
        return []

    def connect(self, device_address: str) -> bool:
        """
        Attempt to connect to the helmet at *device_address*.

        Returns *True* on success, *False* on failure.
        """
        self._set_state(ConnectionState.CONNECTING)
        # TODO: integrate with platform BLE connect
        self._device_address = device_address
        self._set_state(ConnectionState.CONNECTED)
        return True

    def disconnect(self) -> None:
        """Gracefully disconnect from the helmet."""
        self._device_address = None
        self._set_state(ConnectionState.DISCONNECTED)

    def send(self, data: bytes) -> bool:
        """
        Send raw bytes to the connected helmet device.

        Returns *True* if the write was accepted, *False* otherwise.
        """
        if self._state != ConnectionState.CONNECTED:
            return False
        # TODO: write characteristic via BLE library
        return True

    def receive(self, data: bytes) -> None:
        """
        Called internally when the BLE notification handler receives data.
        Forwards the raw bytes to the registered data callback.
        """
        if self._on_data_received:
            self._on_data_received(data)

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def state(self) -> ConnectionState:
        return self._state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_state(self, new_state: ConnectionState) -> None:
        self._state = new_state
        if self._on_state_change:
            self._on_state_change(new_state)
