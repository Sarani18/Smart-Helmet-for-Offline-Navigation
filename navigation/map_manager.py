"""
Map Manager
-----------
Handles loading and querying offline map tiles / road network data stored
locally on the device.  When network connectivity is available the manager
can pre-fetch tiles for a given route bounding-box and persist them for
later offline use.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple


class MapManager:
    """
    Manages the local offline map data store.

    Responsibilities
    ----------------
    - Load offline map data (road segments, tile metadata) from disk.
    - Retrieve road segments near a given coordinate for map-matching.
    - Pre-fetch and persist map tiles that cover a planned route's
      bounding box so that navigation can continue without connectivity.
    - Report whether a specific area has sufficient offline coverage.
    """

    def __init__(self, map_data_dir: str = "map_data") -> None:
        self._map_data_dir = map_data_dir
        self._loaded_segments: List[Dict] = []
        os.makedirs(map_data_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_map(self, map_file: str) -> bool:
        """
        Load road-segment data from a local GeoJSON-like file.

        Parameters
        ----------
        map_file:
            Path to a JSON file containing a ``segments`` array, where each
            segment has ``id``, ``start`` and ``end`` coordinate pairs, and a
            ``name`` field.

        Returns
        -------
        bool
            *True* on success, *False* if the file cannot be read.
        """
        try:
            with open(map_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._loaded_segments = data.get("segments", [])
            return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    def get_nearby_segments(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float = 100.0,
    ) -> List[Dict]:
        """
        Return road segments whose midpoint lies within *radius_meters* of the
        given coordinate.
        """
        results = []
        for seg in self._loaded_segments:
            mid_lat = (seg["start"]["lat"] + seg["end"]["lat"]) / 2
            mid_lon = (seg["start"]["lon"] + seg["end"]["lon"]) / 2
            dist = self._haversine(latitude, longitude, mid_lat, mid_lon)
            if dist <= radius_meters:
                results.append(seg)
        return results

    def has_offline_coverage(self, bounding_box: Tuple[float, float, float, float]) -> bool:
        """
        Return *True* if the local map data covers the area defined by
        *bounding_box* = (min_lat, min_lon, max_lat, max_lon).
        """
        min_lat, min_lon, max_lat, max_lon = bounding_box
        for seg in self._loaded_segments:
            seg_lat = (seg["start"]["lat"] + seg["end"]["lat"]) / 2
            seg_lon = (seg["start"]["lon"] + seg["end"]["lon"]) / 2
            if min_lat <= seg_lat <= max_lat and min_lon <= seg_lon <= max_lon:
                return True
        return False

    def prefetch_route_tiles(self, waypoints: List[Dict]) -> bool:
        """
        Placeholder for downloading and caching map tiles that cover the
        bounding box of *waypoints*.  In a real implementation this would call
        a tile server and write PNG/PBF files to :attr:`_map_data_dir`.

        Returns *True* to indicate the operation completed without error.
        """
        if not waypoints:
            return False
        # Compute bounding box
        lats = [wp["lat"] for wp in waypoints]
        lons = [wp["lon"] for wp in waypoints]
        _bbox = (min(lats), min(lons), max(lats), max(lons))
        # TODO: integrate with tile server download logic
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        import math

        R = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
