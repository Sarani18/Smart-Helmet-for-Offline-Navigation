"""
Embedded Systems & Application Interface Module
------------------------------------------------
Owner: Priyal Jain

Covers the helmet-mounted firmware layer (Bluetooth, LED, instruction parser)
and the mobile-app UI layer (real-time feedback display, device management).
"""

from .bluetooth_comm import BluetoothComm
from .led_controller import LEDController, LEDPattern
from .instruction_parser import InstructionParser, ParsedInstruction, InstructionCode
from .app_interface.ui_manager import UIManager, NavDisplay
from .app_interface.device_manager import DeviceManager, HelmetDevice
from .nav_interface import (
    UIStateMessage, UIActionMessage,
    NavMode, PositionMode, UIActionType, TurnClass,
    StartNavigationPayload, RerouteRequestPayload,
)
from .ui_bridge import UIBridge
from .websocket_server import receive_ui_state, set_action_callback

__all__ = [
    "BluetoothComm",
    "InstructionParser", "ParsedInstruction", "InstructionCode",
    "LEDController", "LEDPattern",
    "UIStateMessage", "UIActionMessage",
    "NavMode", "PositionMode", "UIActionType", "TurnClass",
    "StartNavigationPayload", "RerouteRequestPayload",
    "UIBridge",
    "receive_ui_state", "set_action_callback",
    "UIManager", "NavDisplay",
    "DeviceManager", "HelmetDevice",
]