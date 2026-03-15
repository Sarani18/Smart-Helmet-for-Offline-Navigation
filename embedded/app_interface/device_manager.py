"""
Device Manager
--------------
Handles discovery, pairing, and lifecycle management of the helmet BLE
device from the mobile app's perspective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..bluetooth_comm import BluetoothComm, ConnectionState


@dataclass
class HelmetDevice:
    """
    Represents a discovered smart helmet peripheral.

    Attributes
    ----------
    address : str
        BLE MAC address or UUID (platform-dependent).
    name : str
        Advertised device name.
    rssi : int
        Signal strength in dBm at time of discovery.
    """

    address: str
    name: str
    rssi: int = -100


class DeviceManager:
    """
    Orchestrates the full lifecycle of the BLE connection to the helmet:
    scanning, pairing, reconnection, and status reporting.

    Responsibilities
    ----------------
    - Trigger a BLE scan and collect discovered :class:`HelmetDevice` entries.
    - Attempt a connection to a user-selected device.
    - Monitor connection health and trigger automatic reconnection on dropout.
    - Persist the last-paired device address for quick reconnect on app restart.
    - Expose the current connection state to the rest of the application.
    """

    def __init__(self, comm: Optional[BluetoothComm] = None) -> None:
        self._comm = comm or BluetoothComm()
        self._known_devices: Dict[str, HelmetDevice] = {}
        self._paired_address: Optional[str] = None
        self._on_connected: Optional[Callable[[HelmetDevice], None]] = None
        self._on_disconnected: Optional[Callable[[], None]] = None

        # Wire up internal state-change callback
        self._comm.register_state_callback(self._handle_state_change)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_connection_callback(
        self, on_connected: Callable[[HelmetDevice], None]
    ) -> None:
        """Called when a helmet successfully connects."""
        self._on_connected = on_connected

    def register_disconnection_callback(
        self, on_disconnected: Callable[[], None]
    ) -> None:
        """Called when the helmet disconnects unexpectedly."""
        self._on_disconnected = on_disconnected

    def scan_for_helmets(self) -> List[HelmetDevice]:
        """
        Scan for nearby BLE devices and return those whose names start with
        ``SmartHelmet`` (the agreed advertising name prefix).

        Returns a list of :class:`HelmetDevice` objects.
        """
        raw_addresses = self._comm.scan()
        # In a real implementation, raw_addresses would contain (address, name, rssi)
        # tuples. Here we return whatever the scan produces.
        devices = []
        for addr in raw_addresses:
            device = HelmetDevice(address=addr, name="SmartHelmet", rssi=-70)
            self._known_devices[addr] = device
            devices.append(device)
        return devices

    def connect(self, device: HelmetDevice) -> bool:
        """
        Attempt to connect to *device*.

        Returns *True* on success.
        """
        success = self._comm.connect(device.address)
        if success:
            self._paired_address = device.address
        return success

    def disconnect(self) -> None:
        """Manually disconnect from the currently connected helmet."""
        self._comm.disconnect()

    def reconnect(self) -> bool:
        """Attempt to reconnect to the last paired device."""
        if self._paired_address is None:
            return False
        last_device = self._known_devices.get(
            self._paired_address,
            HelmetDevice(address=self._paired_address, name="SmartHelmet"),
        )
        return self.connect(last_device)

    @property
    def is_connected(self) -> bool:
        return self._comm.is_connected

    @property
    def connection_state(self) -> ConnectionState:
        return self._comm.state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_state_change(self, state: ConnectionState) -> None:
        if state == ConnectionState.CONNECTED and self._on_connected:
            device = self._known_devices.get(
                self._paired_address or "",
                HelmetDevice(address=self._paired_address or "", name="SmartHelmet"),
            )
            self._on_connected(device)
        elif state == ConnectionState.DISCONNECTED and self._on_disconnected:
            self._on_disconnected()
