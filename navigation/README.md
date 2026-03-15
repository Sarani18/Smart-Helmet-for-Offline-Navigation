# Navigation & Route Intelligence Module

**Owner:** Sanskruti Rajesh Ninawe

---

## Purpose

This module is the brain of the navigation system. It takes raw route data
from online map services (or from local offline storage) and transforms it into
clean, step-by-step riding instructions that are sent to the helmet's HUD.
Even when the internet is unavailable, this module ensures the rider can
continue following a pre-planned route.

---

## Files

| File | Responsibility |
|------|---------------|
| `route_processor.py` | Loads, validates, and manages the active route; advances steps as the rider progresses |
| `map_manager.py` | Loads offline map tiles/road segments; finds nearby roads; checks offline coverage |
| `turn_extractor.py` | Decodes Google-encoded polylines; detects direction changes; produces turn labels |
| `offline_cache.py` | Saves and loads full route data to/from local disk for GPS-denied operation |

---

## How It Works (Step by Step)

1. **Route loading** – `RouteProcessor.load_route()` receives a raw API
   response (as a Python dict) and parses it into a structured `Route` object
   containing an ordered list of `RouteStep` objects.

2. **Polyline decoding** – `TurnExtractor.decode_polyline()` converts the
   compact encoded polyline string (a format used by Google Maps, OSRM, etc.)
   into a list of GPS coordinates.

3. **Turn extraction** – `TurnExtractor.extract_turns()` walks through
   consecutive coordinate pairs, computes the change in bearing (direction),
   and classifies each change as *straight*, *slight left/right*, *turn
   left/right*, *sharp turn*, or *U-turn*.

4. **Offline storage** – Before the rider sets off, `OfflineCache.save_route()`
   writes the full decoded route to a JSON file on local storage.  If
   connectivity is lost mid-ride, `OfflineCache.load_route()` recovers it
   instantly.

5. **Map data** – `MapManager.load_map()` reads a local road-network file.
   During GPS-denied operation the localization module queries
   `MapManager.get_nearby_segments()` to snap the dead-reckoned position back
   onto a known road.

6. **Route revalidation** – As the rider moves, `RouteProcessor.revalidate_route()`
   checks that the current position is still within an acceptable corridor of
   the expected path.  If not, a re-route is triggered.

---

## Key Classes

### `RouteProcessor`
- `load_route(route_data)` → `Route`
- `get_current_route()` → `Route | None`
- `revalidate_route(lat, lon)` → `bool`
- `advance_step()` → `RouteStep | None`

### `MapManager`
- `load_map(map_file)` → `bool`
- `get_nearby_segments(lat, lon, radius_meters)` → `list`
- `has_offline_coverage(bounding_box)` → `bool`
- `prefetch_route_tiles(waypoints)` → `bool`

### `TurnExtractor`
- `decode_polyline(encoded)` → `list[(lat, lon)]`
- `extract_turns(coordinates)` → `list[str]`

### `OfflineCache`
- `save_route(key, data)` → `bool`
- `load_route(key)` → `dict | None`
- `list_cached_routes()` → `list[str]`
- `delete_route(key)` → `bool`
- `is_cached(key)` → `bool`

---

## Dependencies

- Python standard library only (`math`, `json`, `os`, `re`).
- No external packages are required for this module.
