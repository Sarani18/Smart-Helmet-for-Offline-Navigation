"""
Map Matcher
-----------
Snaps a noisy dead-reckoned position onto the nearest road segment in the
locally loaded map data to reduce accumulated drift error.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .dead_reckoning import Position


class MapMatcher:
    """
    Projects an estimated GPS-denied position onto the closest known road
    segment, reducing dead-reckoning drift.

    Responsibilities
    ----------------
    - Accept a list of road segments (from :class:`~navigation.MapManager`).
    - For each new estimated position, find the nearest segment and compute
      the perpendicular foot (closest point on the segment).
    - Return the snapped coordinate and the distance to the matched segment
      (confidence proxy).
    - Flag positions that are too far from any known road as unmatched.
    """

    MAX_MATCH_DISTANCE = 50.0  # metres – beyond this the match is rejected

    def __init__(self, road_segments: Optional[List[Dict]] = None) -> None:
        self._segments: List[Dict] = road_segments or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_segments(self, road_segments: List[Dict]) -> None:
        """Replace the stored road segments (e.g. after loading a new map area)."""
        self._segments = road_segments

    def match(self, position: Position) -> Tuple[Optional[Position], float]:
        """
        Find the closest point on any road segment to *position*.

        Parameters
        ----------
        position:
            The estimated position from :class:`~localization.DeadReckoning`.

        Returns
        -------
        (matched_position, distance_meters)
            *matched_position* is *None* if no road is within
            :attr:`MAX_MATCH_DISTANCE`.  *distance_meters* is the distance
            to the nearest segment midpoint.
        """
        if not self._segments:
            return None, float("inf")

        best_point: Optional[Tuple[float, float]] = None
        best_distance = float("inf")

        for seg in self._segments:
            point, dist = self._closest_point_on_segment(
                position.latitude,
                position.longitude,
                seg["start"]["lat"],
                seg["start"]["lon"],
                seg["end"]["lat"],
                seg["end"]["lon"],
            )
            if dist < best_distance:
                best_distance = dist
                best_point = point

        if best_distance > self.MAX_MATCH_DISTANCE or best_point is None:
            return None, best_distance

        matched = Position(
            latitude=best_point[0],
            longitude=best_point[1],
            uncertainty_meters=best_distance,
        )
        return matched, best_distance

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _closest_point_on_segment(
        px: float,
        py: float,
        ax: float,
        ay: float,
        bx: float,
        by: float,
    ) -> Tuple[Tuple[float, float], float]:
        """
        Return (closest_point, distance_metres) for point P=(px,py) relative
        to segment A=(ax,ay)→B=(bx,by).
        Uses simple planar geometry (accurate enough for short segments).
        """
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            # Segment is a single point
            dist = MapMatcher._haversine(px, py, ax, ay)
            return (ax, ay), dist

        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
        foot_x = ax + t * dx
        foot_y = ay + t * dy
        dist = MapMatcher._haversine(px, py, foot_x, foot_y)
        return (foot_x, foot_y), dist

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
