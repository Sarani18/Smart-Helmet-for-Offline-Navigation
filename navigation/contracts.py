"""
Navigation contracts
--------------------
Shared message and enum definitions used for integration between
localization, navigation, and UI modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union


class LocalizationEventType(str, Enum):
    TURN = "TURN"
    LANDMARK = "LANDMARK"
    SIGNBOARD = "SIGNBOARD"


class TurnClass(str, Enum):
    SLIGHT_LEFT = "SLIGHT_LEFT"
    LEFT = "LEFT"
    SLIGHT_RIGHT = "SLIGHT_RIGHT"
    RIGHT = "RIGHT"
    U_TURN = "U_TURN"
    STRAIGHT = "STRAIGHT"


class LandmarkClass(str, Enum):
    TRAFFIC_LIGHT = "TRAFFIC_LIGHT"
    BRIDGE = "BRIDGE"
    FUEL_STATION = "FUEL_STATION"
    JUNCTION = "JUNCTION"
    ROUNDABOUT = "ROUNDABOUT"


class NavMode(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


class PositionMode(str, Enum):
    GPS = "GPS"
    VISUAL = "VISUAL"
    UNKNOWN = "UNKNOWN"


class NetworkStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class LocalizationModuleType(str, Enum):
    VISUAL = "VISUAL"
    DEAD_RECKONING = "DEAD_RECKONING"


class LocalizationControlAction(str, Enum):
    START = "START"
    STOP = "STOP"


class UIActionType(str, Enum):
    START_NAVIGATION = "START_NAVIGATION"
    STOP_NAVIGATION = "STOP_NAVIGATION"
    REROUTE_REQUEST = "REROUTE_REQUEST"


@dataclass(frozen=True)
class TurnPayload:
    turn_class: TurnClass


@dataclass(frozen=True)
class LandmarkPayload:
    landmark_class: LandmarkClass
    map_hint_name: Optional[str] = None


@dataclass(frozen=True)
class SignboardPayload:
    text: str
    direction_hint: Optional[TurnClass] = None


LocalizationPayload = Union[TurnPayload, LandmarkPayload, SignboardPayload]


@dataclass(frozen=True)
class EventMessage:
    session_id: str
    event_id: str
    ts_ms: int
    event_type: LocalizationEventType
    confidence: float
    payload: LocalizationPayload
    heading_deg: Optional[float] = None
    speed_mps: Optional[float] = None


@dataclass(frozen=True)
class NavHintMessage:
    session_id: str
    ts_ms: int
    expected_next_turn: TurnClass
    distance_to_next_turn_m: float


@dataclass(frozen=True)
class UIStateMessage:
    session_id: str
    ts_ms: int
    nav_mode: NavMode
    position_mode: PositionMode
    next_instruction_text: str
    distance_to_next_m: float
    confidence: float
    off_route_flag: bool
    destination_reached_flag: bool
    active_step_index: int
    route_polyline: List[Tuple[float, float]] = field(default_factory=list)
    is_emergency: bool = False


@dataclass(frozen=True)
class StartNavigationPayload:
    origin: str
    destination: str


@dataclass(frozen=True)
class RerouteRequestPayload:
    reason: str


@dataclass(frozen=True)
class EmptyPayload:
    pass


UIActionPayload = Union[StartNavigationPayload, RerouteRequestPayload, EmptyPayload]


@dataclass(frozen=True)
class UIActionMessage:
    session_id: str
    ts_ms: int
    action_type: UIActionType
    payload: UIActionPayload


@dataclass(frozen=True)
class ConnectivityStatusMessage:
    session_id: str
    ts_ms: int
    network_available: bool
    internet_reachable: bool


@dataclass(frozen=True)
class LocalizationControlMessage:
    session_id: str
    ts_ms: int
    module: LocalizationModuleType
    action: LocalizationControlAction
    reason: str
