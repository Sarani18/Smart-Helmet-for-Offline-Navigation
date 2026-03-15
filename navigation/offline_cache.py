"""
Offline Cache
-------------
Persists and retrieves planned routes so that navigation can continue
without any network connectivity.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional


class OfflineCache:
    """
    Stores serialised route data on the local filesystem so the app can
    fall back to cached data when the network is unavailable.

    Responsibilities
    ----------------
    - Save a fully decoded route (as a JSON-serialisable dictionary) under
      a human-friendly route key.
    - Load a previously saved route by key.
    - List all cached route keys.
    - Evict (delete) cached routes that are no longer needed.
    """

    def __init__(self, cache_dir: str = "route_cache") -> None:
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_route(self, route_key: str, route_data: Dict) -> bool:
        """
        Persist *route_data* under *route_key*.

        Parameters
        ----------
        route_key:
            A unique identifier for this route (e.g. ``"home_to_office"``).
        route_data:
            JSON-serialisable dictionary representing the complete route.

        Returns
        -------
        bool
            *True* if the data was written successfully.
        """
        path = self._route_path(route_key)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(route_data, fh, indent=2)
            return True
        except OSError:
            return False

    def load_route(self, route_key: str) -> Optional[Dict]:
        """
        Return the cached route dictionary for *route_key*, or *None* if
        it does not exist.
        """
        path = self._route_path(route_key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def list_cached_routes(self) -> List[str]:
        """Return a list of all route keys currently stored in the cache."""
        return [
            fname[:-5]  # strip ".json"
            for fname in os.listdir(self._cache_dir)
            if fname.endswith(".json")
        ]

    def delete_route(self, route_key: str) -> bool:
        """
        Remove the cached file for *route_key*.

        Returns *True* if the file was deleted, *False* if it did not exist.
        """
        path = self._route_path(route_key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def is_cached(self, route_key: str) -> bool:
        """Return *True* if a cache entry exists for *route_key*."""
        return os.path.exists(self._route_path(route_key))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _route_path(self, route_key: str) -> str:
        safe_key = route_key.replace(os.sep, "_").replace("/", "_")
        return os.path.join(self._cache_dir, f"{safe_key}.json")
