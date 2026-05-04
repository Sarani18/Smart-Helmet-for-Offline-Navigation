"""
Dead Reckoning
--------------
Estimates the rider's current position by integrating speed and heading
when GPS signal is unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Position:
    """Geographic position with an associated uncertainty radius."""

    latitude: float
    longitude: float
    uncertainty_meters: float = 0.0


@dataclass
class MotionSample:
    """
    A single motion measurement used for dead-reckoning integration.

    Attributes
    ----------
    speed_mps : float
        Speed in metres per second.
    heading_degrees : float
        True heading (0–360°, clockwise from North).
    timestamp : float
        Unix timestamp when the sample was captured.
    """

    speed_mps: float
    heading_degrees: float
    timestamp: float


class DeadReckoning:
    """
    Maintains an estimated position by integrating successive motion samples.

    When GPS is available the estimate is corrected (anchored) by calling
    :meth:`anchor`.  During GPS loss the estimate drifts, and
    :attr:`uncertainty_meters` grows proportionally to account for the
    accumulating error.

    Responsibilities
    ----------------
    - Accept new speed/heading samples and update the estimated position.
    - Track accumulated drift uncertainty.
    - Accept GPS anchor updates to reset drift.
    - Provide the current estimated position for navigation and map-matching.
    """

    # How much uncertainty (metres) grows per metre travelled without GPS.
    DRIFT_RATE = 0.02  # 2 % of distance travelled

    def __init__(self) -> None:
        self._position: Optional[Position] = None
        self._last_timestamp: Optional[float] = None
        self._history: List[Position] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def anchor(self, latitude: float, longitude: float) -> None:
        """
        Set the current known position from a GPS fix and reset
        uncertainty to zero.
        """
        self._position = Position(
            latitude=latitude,
            longitude=longitude,
            uncertainty_meters=0.0,
        )
        self._last_timestamp = None  # force dt reset on next sample

    def update(self, sample: MotionSample) -> Optional[Position]:
        """
        Integrate a new *sample* and return the updated estimated position.

        Returns *None* if :meth:`anchor` has not been called yet.
        """
        if self._position is None:
            return None

        if self._last_timestamp is None:
            self._last_timestamp = sample.timestamp
            return self._position

        dt = sample.timestamp - self._last_timestamp
        if dt <= 0:
            return self._position
        self._last_timestamp = sample.timestamp

        # Distance travelled since last sample
        distance = sample.speed_mps * dt  # metres

        # Decompose into lat/lon displacements
        heading_rad = math.radians(sample.heading_degrees)
        delta_lat = (distance * math.cos(heading_rad)) / 111_320  # 1° lat ≈ 111 320 m
        delta_lon = (
            distance
            * math.sin(heading_rad)
            / (111_320 * math.cos(math.radians(self._position.latitude)))
        )

        new_uncertainty = self._position.uncertainty_meters + distance * self.DRIFT_RATE

        self._position = Position(
            latitude=self._position.latitude + delta_lat,
            longitude=self._position.longitude + delta_lon,
            uncertainty_meters=new_uncertainty,
        )
        self._history.append(self._position)
        return self._position

    def get_position(self) -> Optional[Position]:
        """Return the latest estimated position."""
        return self._position

    def get_history(self) -> List[Position]:
        """Return the full list of positions recorded since the last anchor."""
        return list(self._history)

    def reset(self) -> None:
        """Clear the internal state (e.g. at the start of a new journey)."""
        self._position = None
        self._last_timestamp = None
        self._history.clear()
