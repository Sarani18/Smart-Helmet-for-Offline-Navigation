"""
Route Processor
---------------
Handles route loading, validation, and structured turn-by-turn instruction
generation from a decoded polyline or a list of waypoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Waypoint:
    """A single geographic coordinate on the route."""

    latitude: float
    longitude: float
    label: str = ""


@dataclass
class RouteStep:
    """One turn-by-turn instruction within a route."""

    instruction: str
    distance_meters: float
    waypoint: Waypoint


@dataclass
class Route:
    """Complete route containing an ordered list of steps."""

    origin: Waypoint
    destination: Waypoint
    steps: List[RouteStep] = field(default_factory=list)
    total_distance_meters: float = 0.0

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0


class RouteProcessor:
    """
    Processes raw route data from external maps APIs or cached files and
    converts it into a structured :class:`Route` ready for navigation.

    Responsibilities
    ----------------
    - Parse raw JSON route responses (e.g. from OSRM / OpenRouteService).
    - Validate that a route has at least an origin, a destination, and one step.
    - Generate clean, human-readable turn instructions.
    - Revalidate the active route when a network interruption is detected.
    """

    def __init__(self) -> None:
        self._current_route: Optional[Route] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_route(self, route_data: dict) -> Route:
        """
        Parse *route_data* (dict representation of an API response) and
        return a validated :class:`Route`.

        Parameters
        ----------
        route_data:
            Dictionary with keys ``origin``, ``destination``, and ``steps``.
            Each step must contain ``instruction``, ``distance``, ``lat``,
            and ``lon``.

        Returns
        -------
        Route
        """
        origin = Waypoint(
            latitude=route_data["origin"]["lat"],
            longitude=route_data["origin"]["lon"],
            label=route_data["origin"].get("label", "Origin"),
        )
        destination = Waypoint(
            latitude=route_data["destination"]["lat"],
            longitude=route_data["destination"]["lon"],
            label=route_data["destination"].get("label", "Destination"),
        )

        steps: List[RouteStep] = []
        total_distance = 0.0
        for raw_step in route_data.get("steps", []):
            wp = Waypoint(
                latitude=raw_step["lat"],
                longitude=raw_step["lon"],
            )
            step = RouteStep(
                instruction=self._clean_instruction(raw_step["instruction"]),
                distance_meters=float(raw_step["distance"]),
                waypoint=wp,
            )
            steps.append(step)
            total_distance += step.distance_meters

        route = Route(
            origin=origin,
            destination=destination,
            steps=steps,
            total_distance_meters=total_distance,
        )
        self._validate_route(route)
        self._current_route = route
        return route

    def get_current_route(self) -> Optional[Route]:
        """Return the currently active route, or *None* if none is loaded."""
        return self._current_route

    def revalidate_route(self, current_lat: float, current_lon: float) -> bool:
        """
        Check whether the rider's current position is still consistent with
        the loaded route.  Returns *True* if the route remains valid, *False*
        if a re-route is required.
        """
        if self._current_route is None:
            return False
        # Simplified proximity check against next step waypoint
        if not self._current_route.steps:
            return False
        next_wp = self._current_route.steps[0].waypoint
        distance = self._haversine(
            current_lat, current_lon, next_wp.latitude, next_wp.longitude
        )
        return distance < 500  # metres – acceptable corridor

    def advance_step(self) -> Optional[RouteStep]:
        """Remove and return the next step from the active route."""
        if self._current_route and self._current_route.steps:
            return self._current_route.steps.pop(0)
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_instruction(raw: str) -> str:
        """Trim and normalise a raw HTML instruction string."""
        import re

        text = re.sub(r"<[^>]+>", "", raw)  # strip HTML tags
        return text.strip()

    @staticmethod
    def _validate_route(route: Route) -> None:
        if route.is_empty:
            raise ValueError("Route contains no steps.")
        if route.total_distance_meters <= 0:
            raise ValueError("Route has zero or negative total distance.")

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return the great-circle distance in metres between two coordinates."""
        import math

        R = 6_371_000  # Earth radius in metres
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
