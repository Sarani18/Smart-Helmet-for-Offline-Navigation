"""
Communication Protocol, Application Integration & Performance Optimization
---------------------------------------------------------------------------
Owner: Jinesh Nanal

Defines the inter-device protocol, packet structure, sync management,
error handling, and application-level integration / performance testing.
"""

from .protocol import SmartHelmetProtocol, PacketType
from .packet_handler import PacketHandler
from .sync_manager import SyncManager

__all__ = ["SmartHelmetProtocol", "PacketType", "PacketHandler", "SyncManager"]
