"""
Turn Extractor
--------------
Decodes Google Encoded Polyline strings and extracts turn-by-turn manoeuvre
instructions from a sequence of coordinates.
"""

from __future__ import annotations

import math
from typing import List, Tuple


Coordinate = Tuple[float, float]  # (latitude, longitude)


class TurnExtractor:
    """
    Converts raw polyline data into a list of human-readable turn instructions.

    Responsibilities
    ----------------
    - Decode encoded polyline strings (Google Polyline Algorithm Format).
    - Compute the bearing change between consecutive segments.
    - Classify bearing changes into turn types (straight, slight/sharp
      left/right, U-turn).
    - Produce a clean list of manoeuvre strings ready for TTS or HUD display.
    """

    # Bearing-change thresholds (degrees)
    SLIGHT_THRESHOLD = 20
    NORMAL_THRESHOLD = 60
    SHARP_THRESHOLD = 120

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decode_polyline(self, encoded: str) -> List[Coordinate]:
        """
        Decode a Google-encoded polyline string into a list of
        ``(latitude, longitude)`` tuples.

        Parameters
        ----------
        encoded:
            The encoded polyline string (e.g. from a Maps API response).
        """
        coords: List[Coordinate] = []
        index = 0
        lat = 0
        lng = 0

        while index < len(encoded):
            # Decode latitude
            lat_result, index = self._decode_value(encoded, index)
            lat += lat_result
            # Decode longitude
            lng_result, index = self._decode_value(encoded, index)
            lng += lng_result
            coords.append((lat / 1e5, lng / 1e5))

        return coords

    def extract_turns(self, coordinates: List[Coordinate]) -> List[str]:
        """
        Given an ordered list of coordinates, return a list of turn
        instructions at each significant direction change.

        Parameters
        ----------
        coordinates:
            List of ``(lat, lon)`` tuples representing the decoded route.

        Returns
        -------
        List[str]
            Human-readable instruction for each detected manoeuvre point.
        """
        if len(coordinates) < 3:
            return []

        instructions: List[str] = []
        for i in range(1, len(coordinates) - 1):
            bearing_in = self._bearing(coordinates[i - 1], coordinates[i])
            bearing_out = self._bearing(coordinates[i], coordinates[i + 1])
            delta = self._normalise_delta(bearing_out - bearing_in)
            instruction = self._classify_turn(delta)
            if instruction:
                instructions.append(instruction)

        return instructions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_value(encoded: str, index: int) -> Tuple[int, int]:
        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        return (~result >> 1) if result & 1 else (result >> 1), index

    @staticmethod
    def _bearing(point_a: Coordinate, point_b: Coordinate) -> float:
        """Compute the initial bearing from *point_a* to *point_b* in degrees."""
        lat1 = math.radians(point_a[0])
        lat2 = math.radians(point_b[0])
        dlon = math.radians(point_b[1] - point_a[1])
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360

    @staticmethod
    def _normalise_delta(delta: float) -> float:
        """Wrap a bearing delta into the range [-180, 180]."""
        while delta > 180:
            delta -= 360
        while delta < -180:
            delta += 360
        return delta

    def _classify_turn(self, delta: float) -> str:
        """Return a human-readable instruction string for a bearing delta."""
        abs_delta = abs(delta)
        if abs_delta < self.SLIGHT_THRESHOLD:
            return ""  # straight – no instruction needed
        direction = "right" if delta > 0 else "left"
        if abs_delta < self.NORMAL_THRESHOLD:
            return f"Turn slightly {direction}"
        if abs_delta < self.SHARP_THRESHOLD:
            return f"Turn {direction}"
        if abs_delta < 170:
            return f"Turn sharply {direction}"
        return "Make a U-turn"
