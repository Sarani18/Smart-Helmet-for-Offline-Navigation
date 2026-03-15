"""
Navigation event validator
--------------------------
Validates incoming dictionaries from localization and UI and converts them
into typed contract dataclasses.
"""

from __future__ import annotations

from typing import Any, Dict

from .contracts import (
    EventMessage,
    LandmarkClass,
    LandmarkPayload,
    LocalizationEventType,
    RerouteRequestPayload,
    SignboardPayload,
    StartNavigationPayload,
    TurnClass,
    TurnPayload,
    UIActionMessage,
    UIActionType,
    EmptyPayload,
)


class ContractValidationError(ValueError):
    """Raised when an incoming payload fails schema validation."""


class NavigationContractValidator:
    """Validates and parses incoming payloads for navigation integration."""

    def parse_localization_event(self, data: Dict[str, Any]) -> EventMessage:
        self._require_fields(
            data,
            [
                "session_id",
                "event_id",
                "ts_ms",
                "event_type",
                "confidence",
                "payload",
            ],
            context="localization event",
        )

        session_id = self._as_non_empty_str(data["session_id"], "session_id")
        event_id = self._as_non_empty_str(data["event_id"], "event_id")
        ts_ms = self._as_non_negative_int(data["ts_ms"], "ts_ms")
        confidence = self._as_range_float(data["confidence"], "confidence", 0.0, 1.0)

        event_type = self._parse_enum(
            data["event_type"],
            LocalizationEventType,
            "event_type",
        )
        payload = self._parse_localization_payload(event_type, data["payload"])

        heading_deg = data.get("heading_deg")
        if heading_deg is not None:
            heading_deg = self._as_range_float(heading_deg, "heading_deg", 0.0, 360.0)

        speed_mps = data.get("speed_mps")
        if speed_mps is not None:
            speed_mps = self._as_non_negative_float(speed_mps, "speed_mps")

        return EventMessage(
            session_id=session_id,
            event_id=event_id,
            ts_ms=ts_ms,
            event_type=event_type,
            confidence=confidence,
            payload=payload,
            heading_deg=heading_deg,
            speed_mps=speed_mps,
        )

    def parse_ui_action(self, data: Dict[str, Any]) -> UIActionMessage:
        self._require_fields(
            data,
            ["session_id", "ts_ms", "action_type", "payload"],
            context="ui action",
        )

        session_id = self._as_non_empty_str(data["session_id"], "session_id")
        ts_ms = self._as_non_negative_int(data["ts_ms"], "ts_ms")
        action_type = self._parse_enum(data["action_type"], UIActionType, "action_type")
        payload = self._parse_ui_action_payload(action_type, data["payload"])

        return UIActionMessage(
            session_id=session_id,
            ts_ms=ts_ms,
            action_type=action_type,
            payload=payload,
        )

    def _parse_localization_payload(
        self,
        event_type: LocalizationEventType,
        payload: Any,
    ):
        if not isinstance(payload, dict):
            raise ContractValidationError("payload must be an object")

        if event_type == LocalizationEventType.TURN:
            self._require_fields(payload, ["turn_class"], context="TURN payload")
            turn_class = self._parse_enum(payload["turn_class"], TurnClass, "turn_class")
            return TurnPayload(turn_class=turn_class)

        if event_type == LocalizationEventType.LANDMARK:
            self._require_fields(payload, ["landmark_class"], context="LANDMARK payload")
            landmark_class = self._parse_enum(
                payload["landmark_class"],
                LandmarkClass,
                "landmark_class",
            )
            map_hint_name = payload.get("map_hint_name")
            if map_hint_name is not None:
                map_hint_name = self._as_non_empty_str(map_hint_name, "map_hint_name")
            return LandmarkPayload(
                landmark_class=landmark_class,
                map_hint_name=map_hint_name,
            )

        if event_type == LocalizationEventType.SIGNBOARD:
            self._require_fields(payload, ["text"], context="SIGNBOARD payload")
            text = self._as_non_empty_str(payload["text"], "text")
            direction_hint = payload.get("direction_hint")
            if direction_hint is not None:
                direction_hint = self._parse_enum(direction_hint, TurnClass, "direction_hint")
            return SignboardPayload(text=text, direction_hint=direction_hint)

        raise ContractValidationError(f"Unsupported event_type: {event_type}")

    def _parse_ui_action_payload(self, action_type: UIActionType, payload: Any):
        if not isinstance(payload, dict):
            raise ContractValidationError("payload must be an object")

        if action_type == UIActionType.START_NAVIGATION:
            self._require_fields(
                payload,
                ["origin", "destination"],
                context="START_NAVIGATION payload",
            )
            return StartNavigationPayload(
                origin=self._as_non_empty_str(payload["origin"], "origin"),
                destination=self._as_non_empty_str(payload["destination"], "destination"),
            )

        if action_type == UIActionType.REROUTE_REQUEST:
            self._require_fields(payload, ["reason"], context="REROUTE_REQUEST payload")
            return RerouteRequestPayload(
                reason=self._as_non_empty_str(payload["reason"], "reason")
            )

        if action_type == UIActionType.STOP_NAVIGATION:
            return EmptyPayload()

        raise ContractValidationError(f"Unsupported action_type: {action_type}")

    @staticmethod
    def _require_fields(data: Dict[str, Any], fields, context: str) -> None:
        missing = [field for field in fields if field not in data]
        if missing:
            joined = ", ".join(missing)
            raise ContractValidationError(f"Missing {context} fields: {joined}")

    @staticmethod
    def _parse_enum(raw: Any, enum_cls, field_name: str):
        if isinstance(raw, enum_cls):
            return raw
        if not isinstance(raw, str):
            raise ContractValidationError(f"{field_name} must be a string")
        try:
            return enum_cls(raw)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_cls)
            raise ContractValidationError(
                f"Invalid {field_name}: {raw}. Allowed: {allowed}"
            ) from exc

    @staticmethod
    def _as_non_empty_str(value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ContractValidationError(f"{field_name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _as_non_negative_int(value: Any, field_name: str) -> int:
        if not isinstance(value, int) or value < 0:
            raise ContractValidationError(f"{field_name} must be a non-negative integer")
        return value

    @staticmethod
    def _as_range_float(value: Any, field_name: str, low: float, high: float) -> float:
        if not isinstance(value, (int, float)):
            raise ContractValidationError(f"{field_name} must be numeric")
        numeric = float(value)
        if not (low <= numeric <= high):
            raise ContractValidationError(f"{field_name} must be between {low} and {high}")
        return numeric

    @staticmethod
    def _as_non_negative_float(value: Any, field_name: str) -> float:
        if not isinstance(value, (int, float)):
            raise ContractValidationError(f"{field_name} must be numeric")
        numeric = float(value)
        if numeric < 0:
            raise ContractValidationError(f"{field_name} must be non-negative")
        return numeric
