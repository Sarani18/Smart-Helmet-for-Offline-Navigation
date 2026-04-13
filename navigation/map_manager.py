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
import math
import os
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Set, Tuple

TileFetcher = Callable[[str], Optional[bytes]]


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
        self._tiles_dir = os.path.join(map_data_dir, "tiles")
        self._default_zoom_levels = [14, 15]
        self._tile_url_template = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        self._request_timeout_s = 5.0
        self._user_agent = "SmartHelmetNavigation/1.0 (educational project)"
        self._max_cache_size_bytes = 200 * 1024 * 1024
        self._tile_fetcher: Optional[TileFetcher] = None
        self._session_tiles: Dict[str, Set[str]] = {}
        self._loaded_segments: List[Dict] = []
        os.makedirs(map_data_dir, exist_ok=True)
        os.makedirs(self._tiles_dir, exist_ok=True)

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

    def configure_tile_download(
        self,
        tile_url_template: Optional[str] = None,
        zoom_levels: Optional[List[int]] = None,
        request_timeout_s: Optional[float] = None,
        user_agent: Optional[str] = None,
        max_cache_size_mb: Optional[float] = None,
        tile_fetcher: Optional[TileFetcher] = None,
    ) -> None:
        """Configure tile source and optional custom fetcher for tests."""
        if tile_url_template:
            self._tile_url_template = tile_url_template
        if zoom_levels:
            filtered = sorted({int(z) for z in zoom_levels if 0 <= int(z) <= 20})
            if filtered:
                self._default_zoom_levels = filtered
        if request_timeout_s is not None and request_timeout_s > 0:
            self._request_timeout_s = float(request_timeout_s)
        if user_agent:
            self._user_agent = user_agent
        if max_cache_size_mb is not None and max_cache_size_mb > 0:
            self._max_cache_size_bytes = int(max_cache_size_mb * 1024 * 1024)
        self._tile_fetcher = tile_fetcher

    def prefetch_route_tiles(
        self,
        waypoints: List[Dict],
        zoom_levels: Optional[List[int]] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Download and cache map tiles covering the route bounding box.

        Returns *True* if all required tile writes succeeded or already exist.
        """
        if not waypoints:
            return False

        validated = []
        for wp in waypoints:
            if not isinstance(wp, dict) or "lat" not in wp or "lon" not in wp:
                continue
            try:
                validated.append((float(wp["lat"]), float(wp["lon"])))
            except (TypeError, ValueError):
                continue

        if len(validated) < 2:
            return False

        lats = [item[0] for item in validated]
        lons = [item[1] for item in validated]
        min_lat, min_lon, max_lat, max_lon = min(lats), min(lons), max(lats), max(lons)

        zooms = zoom_levels or list(self._default_zoom_levels)
        if not zooms:
            return False

        cached_for_session: Set[str] = set()
        all_ok = True
        for zoom in zooms:
            min_x, max_y = self._latlon_to_tile(min_lat, min_lon, zoom)
            max_x, min_y = self._latlon_to_tile(max_lat, max_lon, zoom)

            x_start, x_end = sorted((min_x, max_x))
            y_start, y_end = sorted((min_y, max_y))

            for x in range(x_start, x_end + 1):
                for y in range(y_start, y_end + 1):
                    if not self._ensure_tile_cached(zoom, x, y):
                        all_ok = False
                    cached_for_session.add(self._tile_path(zoom, x, y))

        if session_id and cached_for_session:
            existing = self._session_tiles.get(session_id, set())
            self._session_tiles[session_id] = existing.union(cached_for_session)

        self.enforce_cache_limits(protected_paths=cached_for_session)

        return all_ok

    def cached_tile_count(self) -> int:
        """Return number of cached tile image files."""
        count = 0
        for root, _, files in os.walk(self._tiles_dir):
            for name in files:
                if name.endswith(".png"):
                    count += 1
        return count

    def cache_size_bytes(self) -> int:
        """Return total byte size of all cached tile files."""
        total = 0
        for root, _, files in os.walk(self._tiles_dir):
            for name in files:
                if not name.endswith(".png"):
                    continue
                path = os.path.join(root, name)
                try:
                    total += os.path.getsize(path)
                except OSError:
                    continue
        return total

    def enforce_cache_limits(self, protected_paths: Optional[Set[str]] = None) -> int:
        """
        Enforce max cache size by evicting oldest tile files first.

        *protected_paths* can be used to avoid evicting tiles just prefetched
        in the current operation.
        """
        protected = protected_paths or set()
        current_size = self.cache_size_bytes()
        if current_size <= self._max_cache_size_bytes:
            return 0

        candidates = []
        for root, _, files in os.walk(self._tiles_dir):
            for name in files:
                if not name.endswith(".png"):
                    continue
                path = os.path.join(root, name)
                if path in protected:
                    continue
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                candidates.append((stat.st_mtime, stat.st_size, path))

        candidates.sort(key=lambda item: item[0])

        evicted = 0
        for _, size, path in candidates:
            if current_size <= self._max_cache_size_bytes:
                break
            if self._delete_tile_file(path):
                evicted += 1
                current_size -= size

        self._remove_empty_tile_dirs()
        self._prune_session_index()
        return evicted

    def evict_session_tiles(self, session_id: str) -> int:
        """Delete tiles recorded for a specific session and return deletion count."""
        if not session_id or session_id not in self._session_tiles:
            return 0

        deleted = 0
        for path in list(self._session_tiles.get(session_id, set())):
            if self._delete_tile_file(path):
                deleted += 1

        self._session_tiles.pop(session_id, None)
        self._remove_empty_tile_dirs()
        self._prune_session_index()
        return deleted

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tile_path(self, zoom: int, x: int, y: int) -> str:
        return os.path.join(self._tiles_dir, str(zoom), str(x), f"{y}.png")

    def _ensure_tile_cached(self, zoom: int, x: int, y: int) -> bool:
        tile_path = self._tile_path(zoom, x, y)
        if os.path.exists(tile_path):
            return True

        tile_url = self._tile_url_template.format(z=zoom, x=x, y=y)
        data = self._download_tile_bytes(tile_url)
        if not data:
            return False

        os.makedirs(os.path.dirname(tile_path), exist_ok=True)
        try:
            with open(tile_path, "wb") as fh:
                fh.write(data)
            return True
        except OSError:
            return False

    def _download_tile_bytes(self, tile_url: str) -> Optional[bytes]:
        if self._tile_fetcher is not None:
            try:
                return self._tile_fetcher(tile_url)
            except Exception:
                return None

        request = urllib.request.Request(tile_url, headers={"User-Agent": self._user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self._request_timeout_s) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            return None

    @staticmethod
    def _delete_tile_file(path: str) -> bool:
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except OSError:
            return False
        return False

    def _remove_empty_tile_dirs(self) -> None:
        for root, dirs, files in os.walk(self._tiles_dir, topdown=False):
            if root == self._tiles_dir:
                continue
            if dirs or files:
                continue
            try:
                os.rmdir(root)
            except OSError:
                continue

    def _prune_session_index(self) -> None:
        for session_id, paths in list(self._session_tiles.items()):
            existing = {path for path in paths if os.path.exists(path)}
            if existing:
                self._session_tiles[session_id] = existing
            else:
                self._session_tiles.pop(session_id, None)

    @staticmethod
    def _latlon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
        lat = max(min(lat, 85.05112878), -85.05112878)
        lon = ((lon + 180.0) % 360.0) - 180.0

        lat_rad = math.radians(lat)
        n = 2 ** zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)

        xtile = min(max(xtile, 0), n - 1)
        ytile = min(max(ytile, 0), n - 1)
        return xtile, ytile

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
