"""
Embedded Systems & Application Interface Module
------------------------------------------------
Owner: Priyal Jain

Covers the helmet-mounted firmware layer (Bluetooth, LED, instruction parser)
and the mobile-app UI layer (real-time feedback display, device management).
"""

from .bluetooth_comm import BluetoothComm
from .led_controller import LEDController
from .instruction_parser import InstructionParser
from .app_interface.ui_manager import UIManager
from .app_interface.device_manager import DeviceManager
from .position_bridge import PositionBridge, LocationUpdate, NavUpdate
__all__ = [
    "BluetoothComm",
    "LEDController",
    "InstructionParser",
    "UIManager",
    "DeviceManager",
]
