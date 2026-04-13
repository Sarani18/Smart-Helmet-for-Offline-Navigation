"""
nav_interface.py
----------------
Data models that match the Integration Considerations spec exactly.
These are the ONLY message types  embedded module cares about.

Incoming from brain →  module:  UIStateMessage  (2-5 Hz)
Outgoing from this module → brain:  UIActionMessage (on user action)
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class NavMode(Enum):
    ONLINE   = "ONLINE"
    OFFLINE  = "OFFLINE"
    DEGRADED = "DEGRADED"


class PositionMode(Enum):
    GPS     = "GPS"
    VISUAL  = "VISUAL"
    UNKNOWN = "UNKNOWN"


class UIActionType(Enum):
    START_NAVIGATION = "START_NAVIGATION"
    STOP_NAVIGATION  = "STOP_NAVIGATION"
    REROUTE_REQUEST  = "REROUTE_REQUEST"


class TurnClass(Enum):
    SLIGHT_LEFT  = "SLIGHT_LEFT"
    LEFT         = "LEFT"
    SLIGHT_RIGHT = "SLIGHT_RIGHT"
    RIGHT        = "RIGHT"
    U_TURN       = "U_TURN"
    STRAIGHT     = "STRAIGHT"


@dataclass
class UIStateMessage:
    session_id:               str
    ts_ms:                    int
    nav_mode:                 NavMode
    position_mode:            PositionMode
    next_instruction_text:    str
    distance_to_next_m:       float
    confidence:               float
    off_route_flag:           bool
    destination_reached_flag: bool
    active_step_index:        int
    route_polyline:           list[list[float]]  # [[lat, lon], ...]

    @classmethod
    def from_dict(cls, d: dict) -> "UIStateMessage":
        return cls(
            session_id               = d["session_id"],
            ts_ms                    = int(d["ts_ms"]),
            nav_mode                 = NavMode(d["nav_mode"]),
            position_mode            = PositionMode(d["position_mode"]),
            next_instruction_text    = d["next_instruction_text"],
            distance_to_next_m       = float(d["distance_to_next_m"]),
            confidence               = float(d["confidence"]),
            off_route_flag           = bool(d["off_route_flag"]),
            destination_reached_flag = bool(d["destination_reached_flag"]),
            active_step_index        = int(d["active_step_index"]),
            route_polyline           = d.get("route_polyline", []),
        )

    def current_lat(self) -> Optional[float]:
        return self.route_polyline[-1][0] if self.route_polyline else None

    def current_lng(self) -> Optional[float]:
        return self.route_polyline[-1][1] if self.route_polyline else None

    def to_ws_dict(self) -> dict:
        return {
            "type":                    "ui_state",
            "session_id":              self.session_id,
            "ts_ms":                   self.ts_ms,
            "nav_mode":                self.nav_mode.value,
            "position_mode":           self.position_mode.value,
            "next_instruction_text":   self.next_instruction_text,
            "distance_to_next_m":      self.distance_to_next_m,
            "confidence":              round(self.confidence, 3),
            "off_route_flag":          self.off_route_flag,
            "destination_reached_flag":self.destination_reached_flag,
            "active_step_index":       self.active_step_index,
            "route_polyline":          self.route_polyline,
            "lat":                     self.current_lat(),
            "lng":                     self.current_lng(),
        }


@dataclass
class StartNavigationPayload:
    origin:      str
    destination: str


@dataclass
class RerouteRequestPayload:
    reason: str


@dataclass
class UIActionMessage:
    session_id:  str
    ts_ms:       int
    action_type: UIActionType
    payload:     StartNavigationPayload | RerouteRequestPayload | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "session_id":  self.session_id,
            "ts_ms":       self.ts_ms,
            "action_type": self.action_type.value,
        }
        if isinstance(self.payload, StartNavigationPayload):
            d["payload"] = {"origin": self.payload.origin,
                            "destination": self.payload.destination}
        elif isinstance(self.payload, RerouteRequestPayload):
            d["payload"] = {"reason": self.payload.reason}
        else:
            d["payload"] = {}
        return d