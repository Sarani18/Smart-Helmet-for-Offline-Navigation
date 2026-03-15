"""
Sync Manager
------------
Keeps the mobile application and helmet device state synchronised,
monitors link health via heartbeats, and manages GPS-mode switching.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .protocol import PacketType, SmartHelmetProtocol
from .packet_handler import PacketHandler


@dataclass
class SystemState:
    """
    Snapshot of the overall system state shared between app and helmet.

    Attributes
    ----------
    gps_active : bool
        Whether the GPS receiver has a current fix.
    speed_kph : float
        Latest speed reading in km/h.
    sequence_counter : int
        Most recent outgoing sequence number.
    last_heartbeat : float
        Unix timestamp of the last successful heartbeat exchange.
    link_healthy : bool
        *True* if a heartbeat was received within the timeout window.
    """

    gps_active: bool = True
    speed_kph: float = 0.0
    sequence_counter: int = 0
    last_heartbeat: float = field(default_factory=time.time)
    link_healthy: bool = True


class SyncManager:
    """
    Orchestrates state synchronisation between the app and helmet:

    - Sends periodic heartbeats and marks the link unhealthy if no reply
      arrives within *heartbeat_timeout* seconds.
    - Notifies the application when GPS mode changes (active ↔ lost).
    - Coordinates a graceful reconnect when the link is declared unhealthy.

    Responsibilities
    ----------------
    - Periodic heartbeat send/receive.
    - GPS active / lost mode switching and notification.
    - Link-health monitoring and automatic reconnect trigger.
    - State export for performance logging.
    """

    HEARTBEAT_INTERVAL = 2.0   # seconds between heartbeat sends
    HEARTBEAT_TIMEOUT = 6.0    # seconds before link declared unhealthy

    def __init__(
        self,
        handler: Optional[PacketHandler] = None,
        protocol: Optional[SmartHelmetProtocol] = None,
    ) -> None:
        self._handler = handler or PacketHandler(protocol)
        self._state = SystemState(last_heartbeat=time.time())
        self._last_heartbeat_sent: float = 0.0
        self._on_gps_change: Optional[Callable[[bool], None]] = None
        self._on_link_unhealthy: Optional[Callable[[], None]] = None

        # Register internal handlers
        self._handler.register_handler(PacketType.HEARTBEAT, self._on_heartbeat_received)
        self._handler.register_handler(PacketType.GPS_STATUS, self._on_gps_packet)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_gps_change_callback(
        self, callback: Callable[[bool], None]
    ) -> None:
        """Called with *True* / *False* when GPS status changes."""
        self._on_gps_change = callback

    def register_link_unhealthy_callback(self, callback: Callable[[], None]) -> None:
        """Called when the heartbeat timeout is exceeded."""
        self._on_link_unhealthy = callback

    def tick(self) -> None:
        """
        Call this method regularly (e.g. once per second from a timer).
        It manages heartbeat sending and health-check logic.
        """
        now = time.time()

        # Send heartbeat if interval elapsed
        if now - self._last_heartbeat_sent >= self.HEARTBEAT_INTERVAL:
            self._handler.enqueue(PacketType.HEARTBEAT)
            self._last_heartbeat_sent = now

        # Check for heartbeat timeout
        if now - self._state.last_heartbeat > self.HEARTBEAT_TIMEOUT:
            if self._state.link_healthy:
                self._state.link_healthy = False
                if self._on_link_unhealthy:
                    self._on_link_unhealthy()

        # Retry any unacknowledged packets
        self._handler.retry_pending()

    def notify_gps_change(self, gps_active: bool) -> None:
        """
        Call this when the GPS acquisition status changes.
        Encodes and enqueues a GPS_STATUS packet for the helmet.
        """
        if gps_active == self._state.gps_active:
            return  # no change – nothing to do
        self._state.gps_active = gps_active
        payload = bytes([0x01 if gps_active else 0x00, 0x00, 0x00])
        self._handler.enqueue(PacketType.GPS_STATUS, payload)
        if self._on_gps_change:
            self._on_gps_change(gps_active)

    def update_speed(self, speed_kph: float) -> None:
        """Enqueue a speed update packet and store the latest value."""
        self._state.speed_kph = speed_kph
        speed_int = min(int(speed_kph * 10), 0xFFFF)  # 0.1 km/h resolution, max 6553.5
        payload = bytes([
            (speed_int >> 8) & 0xFF,
            speed_int & 0xFF,
            0x00,
        ])
        self._handler.enqueue(PacketType.SPEED_UPDATE, payload)

    def get_state(self) -> SystemState:
        """Return a snapshot of the current system state."""
        return SystemState(**self._state.__dict__)

    @property
    def packet_handler(self) -> PacketHandler:
        """Expose the underlying :class:`PacketHandler` for integration."""
        return self._handler

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_heartbeat_received(self, packet) -> None:
        self._state.last_heartbeat = time.time()
        self._state.link_healthy = True

    def _on_gps_packet(self, packet) -> None:
        gps_active = packet.payload[0] == 0x01
        if gps_active != self._state.gps_active:
            self._state.gps_active = gps_active
            if self._on_gps_change:
                self._on_gps_change(gps_active)
