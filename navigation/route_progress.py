"""
Route progress engine
---------------------
Advances route steps using event-based localization observations
instead of absolute coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import EventMessage, LandmarkClass, LocalizationEventType, TurnClass
from .route_processor import Route


@dataclass(frozen=True)
class ProgressUpdate:
    advanced: bool
    active_step_index: int
    destination_reached: bool
    reason: str


class RouteProgressEngine:
    """Tracks route progress from localization events."""

    def __init__(self) -> None:
        self._route: Optional[Route] = None
        self._active_step_index: int = 0

    def load_route(self, route: Route) -> None:
        self._route = route
        self._active_step_index = 0

    def reset(self) -> None:
        self._route = None
        self._active_step_index = 0

    def has_route(self) -> bool:
        return self._route is not None

    def get_expected_next_turn(self) -> Optional[TurnClass]:
        if self._route is None or self.is_destination_reached():
            return None
        step = self._route.steps[self._active_step_index]
        return self.infer_expected_turn_from_instruction(step.instruction)

    def get_distance_to_next_turn_m(self) -> Optional[float]:
        if self._route is None or self.is_destination_reached():
            return None
        step = self._route.steps[self._active_step_index]
        return float(step.distance_meters)

    def get_active_step_index(self) -> int:
        return self._active_step_index

    def is_destination_reached(self) -> bool:
        if self._route is None:
            return False
        return self._active_step_index >= len(self._route.steps)

    def process_event(self, event: EventMessage) -> ProgressUpdate:
        """Process one event and advance route if it matches active step."""
        if self._route is None:
            return ProgressUpdate(False, 0, False, "route_not_loaded")

        if self.is_destination_reached():
            return ProgressUpdate(
                False,
                self._active_step_index,
                True,
                "already_completed",
            )

        step = self._route.steps[self._active_step_index]
        step_text = step.instruction.lower()

        if self._event_matches_step(event, step_text):
            self._active_step_index += 1
            return ProgressUpdate(
                True,
                self._active_step_index,
                self.is_destination_reached(),
                "step_advanced",
            )

        return ProgressUpdate(
            False,
            self._active_step_index,
            self.is_destination_reached(),
            "no_match",
        )

    def _event_matches_step(self, event: EventMessage, step_text: str) -> bool:
        if event.event_type == LocalizationEventType.TURN:
            expected_turn = self.infer_expected_turn_from_instruction(step_text)
            return event.payload.turn_class == expected_turn

        if event.event_type == LocalizationEventType.SIGNBOARD:
            sign_text = event.payload.text.lower()
            expected_turn = self.infer_expected_turn_from_instruction(step_text)

            if expected_turn == TurnClass.LEFT and "left" in sign_text:
                return True
            if expected_turn == TurnClass.RIGHT and "right" in sign_text:
                return True
            if expected_turn == TurnClass.U_TURN and "u-turn" in sign_text:
                return True

            destination_label = (self._route.destination.label or "").lower()
            return bool(destination_label) and destination_label in sign_text

        if event.event_type == LocalizationEventType.LANDMARK:
            landmark_hint = self._landmark_to_hint(event.payload.landmark_class)
            return landmark_hint in step_text

        return False

    @staticmethod
    def infer_expected_turn_from_instruction(step_text: str) -> TurnClass:
        text = step_text.lower()
        if "u-turn" in text:
            return TurnClass.U_TURN
        if "slight left" in text:
            return TurnClass.SLIGHT_LEFT
        if "slight right" in text:
            return TurnClass.SLIGHT_RIGHT
        if "left" in text:
            return TurnClass.LEFT
        if "right" in text:
            return TurnClass.RIGHT
        return TurnClass.STRAIGHT

    @staticmethod
    def _landmark_to_hint(landmark_class: LandmarkClass) -> str:
        mapping = {
            LandmarkClass.TRAFFIC_LIGHT: "traffic light",
            LandmarkClass.BRIDGE: "bridge",
            LandmarkClass.FUEL_STATION: "fuel station",
            LandmarkClass.JUNCTION: "junction",
            LandmarkClass.ROUNDABOUT: "roundabout",
        }
        return mapping[landmark_class]
