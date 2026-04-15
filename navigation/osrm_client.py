"""
OSRM routing client for the Navigation Control System.
-------------------------------------------------------
Converts user-supplied place-name strings into a structured route_data dict
that NavigationAPIService.ingest_ui_action() accepts.

Flow:
  1. Nominatim geocoding  →  (lat, lon) for origin and destination
  2. OSRM route request   →  legs, steps, geometry
  3. Format conversion    →  NCS route_data dict

Uses Python stdlib only (urllib, json) — no extra pip dependencies.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"
USER_AGENT    = "SmartHelmetNavigation/1.0 (educational project)"
TIMEOUT_S     = 12   # seconds per HTTP call


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode(place: str) -> Optional[Tuple[float, float]]:
    """
    Return (lat, lon) for *place* via Nominatim OSM geocoder.
    Returns None if the place cannot be found or network call fails.
    """
    params = urllib.parse.urlencode({
        "q":      place,
        "format": "json",
        "limit":  1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OSRM step → human-readable instruction
# ---------------------------------------------------------------------------

def _maneuver_to_instruction(osrm_step: Dict[str, Any]) -> str:
    """Convert one OSRM route step into a short navigation instruction."""
    maneuver = osrm_step.get("maneuver", {})
    mtype    = maneuver.get("type", "")
    modifier = maneuver.get("modifier", "")
    name     = osrm_step.get("name", "").strip()
    on       = f" on {name}" if name else ""

    if mtype == "depart":
        dir_map = {
            "right":       "right",
            "slight right":"right",
            "sharp right": "right",
            "left":        "left",
            "slight left": "left",
            "sharp left":  "left",
            "straight":    "straight",
            "uturn":       "south",
        }
        direction = dir_map.get(modifier, modifier)
        return f"Head {direction}{on}" if direction else f"Start{on}"

    if mtype == "arrive":
        return "Arrive at destination"

    if mtype in ("turn", "new name", "on ramp", "off ramp"):
        if modifier in ("right", "slight right", "sharp right"):
            return f"Turn right{on}"
        if modifier in ("left", "slight left", "sharp left"):
            return f"Turn left{on}"
        if modifier == "uturn":
            return "Make a U-turn"
        return f"Continue straight{on}"

    if mtype in ("merge", "fork"):
        return f"Keep {modifier}{on}" if modifier else f"Continue{on}"

    if mtype in ("roundabout", "rotary"):
        exit_num = maneuver.get("exit", "")
        return f"Enter roundabout, take exit {exit_num}" if exit_num else "Enter roundabout"

    if mtype == "end of road":
        if modifier in ("right", "slight right", "sharp right"):
            return f"Turn right{on}"
        if modifier in ("left", "slight left", "sharp left"):
            return f"Turn left{on}"

    return f"Continue{on}" if name else "Continue"


# ---------------------------------------------------------------------------
# Main route-fetch function
# ---------------------------------------------------------------------------

def fetch_route(origin: str, destination: str) -> Optional[Dict[str, Any]]:
    """
    Geocode *origin* and *destination*, fetch the driving route from OSRM,
    and return a dict in the NCS route_data format:

        {
            "origin":      {"lat": float, "lon": float, "label": str},
            "destination": {"lat": float, "lon": float, "label": str},
            "steps": [
                {"lat": float, "lon": float, "instruction": str, "distance": float},
                ...
            ],
        }

    Returns None if geocoding or the OSRM call fails.
    """
    # 1. Geocode ---------------------------------------------------------
    origin_ll = geocode(origin)
    if origin_ll is None:
        return None

    dest_ll = geocode(destination)
    if dest_ll is None:
        return None

    o_lat, o_lon = origin_ll
    d_lat, d_lon = dest_ll

    # 2. OSRM request  (expects lon,lat ordering) -------------------------
    coords = f"{o_lon},{o_lat};{d_lon},{d_lat}"
    url = (
        f"{OSRM_BASE_URL}/{coords}"
        "?overview=full&geometries=geojson&steps=true&annotations=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    if data.get("code") != "Ok" or not data.get("routes"):
        return None

    route = data["routes"][0]

    # 3. Extract full geometry (geojson coordinates are [lon, lat]) --------
    geom_coords: List[Tuple[float, float]] = []
    for lon_lat in route.get("geometry", {}).get("coordinates", []):
        geom_coords.append((float(lon_lat[1]), float(lon_lat[0])))  # → (lat, lon)

    # 4. Extract turn steps from OSRM legs --------------------------------
    turn_steps: List[Dict[str, Any]] = []
    for leg in route.get("legs", []):
        for osrm_step in leg.get("steps", []):
            loc  = osrm_step.get("maneuver", {}).get("location", [o_lon, o_lat])
            dist = float(osrm_step.get("distance", 0.0))
            if dist < 0.5 and osrm_step.get("maneuver", {}).get("type") not in ("arrive",):
                # Skip zero-distance phantom steps (except arrive)
                continue
            turn_steps.append({
                "lat":         float(loc[1]),   # OSRM location is [lon, lat]
                "lon":         float(loc[0]),
                "instruction": _maneuver_to_instruction(osrm_step),
                "distance":    max(dist, 1.0),  # RouteProcessor requires > 0
            })

    # 5. Enrich steps with intermediate geometry points -------------------
    # This gives UIStateMessage.route_polyline enough coordinates for a
    # smooth map polyline while keeping only real turn steps for route_progress.
    # Strategy: interleave geometry points between consecutive turn steps.
    steps = _enrich_steps_with_geometry(turn_steps, geom_coords)

    # 6. Fallback: if OSRM gave no steps, make a minimal 2-step route -----
    if not steps:
        steps = [
            {
                "lat": o_lat, "lon": o_lon,
                "instruction": "Head towards destination",
                "distance": max(route.get("distance", 1000.0), 1.0),
            },
            {
                "lat": d_lat, "lon": d_lon,
                "instruction": "Arrive at destination",
                "distance": 1.0,
            },
        ]

    return {
        "origin":      {"lat": o_lat, "lon": o_lon, "label": origin},
        "destination": {"lat": d_lat, "lon": d_lon, "label": destination},
        "steps":       steps,
    }


# ---------------------------------------------------------------------------
# Geometry enrichment
# ---------------------------------------------------------------------------

def _enrich_steps_with_geometry(
    turn_steps: List[Dict[str, Any]],
    geom_coords: List[Tuple[float, float]],
) -> List[Dict[str, Any]]:
    """
    Interleave full-geometry coordinates between turn steps so that
    api_service._extract_route_polyline() produces a smooth route_polyline.

    Turn steps keep their original instructions and distances.
    Geometry-only waypoints get instruction="Follow route" and distance=1.
    route_progress ignores "Follow route" steps (no keyword match).
    """
    if not turn_steps:
        return []

    if len(geom_coords) < 3:
        # Not enough geometry to enrich — return turn steps as-is
        return turn_steps

    enriched: List[Dict[str, Any]] = []

    # Build a set of (rounded lat, rounded lon) for each turn step so we can
    # detect which geometry points coincide with a maneuver location.
    turn_locs = {
        (round(s["lat"], 4), round(s["lon"], 4))
        for s in turn_steps
    }

    turn_iter = iter(turn_steps)
    next_turn = next(turn_iter, None)

    for g_lat, g_lon in geom_coords:
        g_key = (round(g_lat, 4), round(g_lon, 4))

        if next_turn and g_key == (round(next_turn["lat"], 4), round(next_turn["lon"], 4)):
            # This geometry point coincides with a turn — emit the turn step
            enriched.append(next_turn)
            next_turn = next(turn_iter, None)
        elif g_key not in turn_locs:
            # Intermediate geometry point — emit as a pass-through waypoint
            enriched.append({
                "lat":         g_lat,
                "lon":         g_lon,
                "instruction": "Follow route",
                "distance":    1.0,
            })

    # Append any remaining turn steps not matched in geometry
    if next_turn:
        enriched.append(next_turn)
    for remaining in turn_iter:
        enriched.append(remaining)

    return enriched
