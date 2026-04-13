from __future__ import annotations
from enum import Enum
from typing import Callable, Optional


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    SCANNING     = "scanning"
    CONNECTING   = "connecting"
    CONNECTED    = "connected"
    ERROR        = "error"


class BluetoothComm:
    def __init__(self) -> None:
        self._state          = ConnectionState.DISCONNECTED
        self._device_address: Optional[str]                       = None
        self._on_state_change: Optional[Callable[[ConnectionState], None]] = None
        self._on_data_received: Optional[Callable[[bytes], None]] = None

    def register_state_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        self._on_state_change = callback

    def register_data_callback(self, callback: Callable[[bytes], None]) -> None:
        self._on_data_received = callback

    def scan(self, timeout_seconds: float = 10.0) -> list:
        self._set_state(ConnectionState.SCANNING)
        # TODO: platform BLE scan
        self._set_state(ConnectionState.DISCONNECTED)
        return []

    def connect(self, device_address: str) -> bool:
        self._set_state(ConnectionState.CONNECTING)
        # TODO: platform BLE connect
        self._device_address = device_address
        self._set_state(ConnectionState.CONNECTED)
        return True

    def disconnect(self) -> None:
        self._device_address = None
        self._set_state(ConnectionState.DISCONNECTED)

    def send(self, data: bytes) -> bool:
        if self._state != ConnectionState.CONNECTED:
            return False
        # TODO: write BLE characteristic
        return True

    def receive(self, data: bytes) -> None:
        if self._on_data_received:
            self._on_data_received(data)

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def state(self) -> ConnectionState:
        return self._state

    def _set_state(self, new_state: ConnectionState) -> None:
        self._state = new_state
        if self._on_state_change:
            self._on_state_change(new_state)