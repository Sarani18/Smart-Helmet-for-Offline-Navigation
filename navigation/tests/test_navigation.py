"""
Unit tests for the Navigation & Route Intelligence Module.
"""

import json
import os
import sys
import tempfile
import unittest

# Ensure repository root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from navigation.route_processor import RouteProcessor, Route
from navigation.map_manager import MapManager
from navigation.turn_extractor import TurnExtractor
from navigation.offline_cache import OfflineCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_route_data():
    return {
        "origin": {"lat": 19.076, "lon": 72.877, "label": "Home"},
        "destination": {"lat": 19.100, "lon": 72.900, "label": "Office"},
        "steps": [
            {"lat": 19.078, "lon": 72.879, "instruction": "Turn right", "distance": 300},
            {"lat": 19.085, "lon": 72.885, "instruction": "Go straight", "distance": 700},
            {"lat": 19.100, "lon": 72.900, "instruction": "Arrive", "distance": 500},
        ],
    }


def _sample_map_data():
    return {
        "segments": [
            {
                "id": "seg1",
                "name": "MG Road",
                "start": {"lat": 19.076, "lon": 72.877},
                "end": {"lat": 19.085, "lon": 72.885},
            }
        ]
    }


# ---------------------------------------------------------------------------
# RouteProcessor tests
# ---------------------------------------------------------------------------

class TestRouteProcessor(unittest.TestCase):

    def setUp(self):
        self.processor = RouteProcessor()

    def test_load_valid_route(self):
        route = self.processor.load_route(_sample_route_data())
        self.assertIsInstance(route, Route)
        self.assertEqual(len(route.steps), 3)
        self.assertAlmostEqual(route.total_distance_meters, 1500.0)

    def test_load_sets_current_route(self):
        self.processor.load_route(_sample_route_data())
        self.assertIsNotNone(self.processor.get_current_route())

    def test_load_strips_html_from_instruction(self):
        data = _sample_route_data()
        data["steps"][0]["instruction"] = "<b>Turn right</b>"
        route = self.processor.load_route(data)
        self.assertEqual(route.steps[0].instruction, "Turn right")

    def test_load_empty_steps_raises(self):
        data = _sample_route_data()
        data["steps"] = []
        with self.assertRaises(ValueError):
            self.processor.load_route(data)

    def test_advance_step_returns_first_step(self):
        self.processor.load_route(_sample_route_data())
        step = self.processor.advance_step()
        self.assertIsNotNone(step)
        self.assertEqual(step.instruction, "Turn right")
        self.assertEqual(len(self.processor.get_current_route().steps), 2)

    def test_revalidate_route_close_position(self):
        self.processor.load_route(_sample_route_data())
        # Very close to the first step waypoint
        result = self.processor.revalidate_route(19.078, 72.879)
        self.assertTrue(result)

    def test_revalidate_route_far_position(self):
        self.processor.load_route(_sample_route_data())
        # Far away (different city)
        result = self.processor.revalidate_route(28.6139, 77.2090)  # Delhi
        self.assertFalse(result)

    def test_no_current_route_returns_none(self):
        self.assertIsNone(self.processor.get_current_route())


# ---------------------------------------------------------------------------
# MapManager tests
# ---------------------------------------------------------------------------

class TestMapManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = MapManager(map_data_dir=self.tmpdir)

    def _write_map_file(self, data=None):
        path = os.path.join(self.tmpdir, "test_map.json")
        with open(path, "w") as f:
            json.dump(data or _sample_map_data(), f)
        return path

    def test_load_valid_map(self):
        path = self._write_map_file()
        self.assertTrue(self.manager.load_map(path))

    def test_load_missing_file(self):
        self.assertFalse(self.manager.load_map("/nonexistent/map.json"))

    def test_get_nearby_segments_within_radius(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        # Midpoint of seg1 is approx (19.0805, 72.881)
        segs = self.manager.get_nearby_segments(19.0805, 72.881, radius_meters=500)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["name"], "MG Road")

    def test_get_nearby_segments_outside_radius(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        segs = self.manager.get_nearby_segments(28.6139, 77.2090, radius_meters=100)
        self.assertEqual(len(segs), 0)

    def test_has_offline_coverage_true(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        self.assertTrue(self.manager.has_offline_coverage((19.0, 72.8, 19.2, 73.0)))

    def test_has_offline_coverage_false(self):
        path = self._write_map_file()
        self.manager.load_map(path)
        # Bounding box nowhere near Mumbai
        self.assertFalse(self.manager.has_offline_coverage((28.0, 76.0, 29.0, 78.0)))


# ---------------------------------------------------------------------------
# TurnExtractor tests
# ---------------------------------------------------------------------------

class TestTurnExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = TurnExtractor()

    def test_decode_polyline_simple(self):
        # Known encoded polyline for two points
        # Encoding of [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        coords = self.extractor.decode_polyline(encoded)
        self.assertEqual(len(coords), 3)
        self.assertAlmostEqual(coords[0][0], 38.5, places=4)
        self.assertAlmostEqual(coords[0][1], -120.2, places=4)

    def test_extract_turns_too_few_points(self):
        coords = [(19.0, 72.0), (19.1, 72.1)]
        self.assertEqual(self.extractor.extract_turns(coords), [])

    def test_extract_turns_straight(self):
        # Three collinear points going north – no turn expected
        coords = [(19.0, 72.0), (19.1, 72.0), (19.2, 72.0)]
        turns = self.extractor.extract_turns(coords)
        self.assertEqual(turns, [])

    def test_classify_turn_right(self):
        instruction = self.extractor._classify_turn(45)
        self.assertIn("right", instruction.lower())

    def test_classify_turn_left(self):
        instruction = self.extractor._classify_turn(-45)
        self.assertIn("left", instruction.lower())

    def test_classify_u_turn(self):
        instruction = self.extractor._classify_turn(175)
        self.assertIn("U-turn", instruction)

    def test_classify_slight_left(self):
        instruction = self.extractor._classify_turn(-10)
        self.assertEqual(instruction, "")  # below threshold → straight


# ---------------------------------------------------------------------------
# OfflineCache tests
# ---------------------------------------------------------------------------

class TestOfflineCache(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = OfflineCache(cache_dir=self.tmpdir)

    def test_save_and_load(self):
        data = _sample_route_data()
        self.assertTrue(self.cache.save_route("test_route", data))
        loaded = self.cache.load_route("test_route")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["origin"]["label"], "Home")

    def test_load_missing_returns_none(self):
        self.assertIsNone(self.cache.load_route("does_not_exist"))

    def test_is_cached(self):
        self.cache.save_route("my_route", {"key": "value"})
        self.assertTrue(self.cache.is_cached("my_route"))
        self.assertFalse(self.cache.is_cached("other_route"))

    def test_list_cached_routes(self):
        self.cache.save_route("route_a", {})
        self.cache.save_route("route_b", {})
        keys = self.cache.list_cached_routes()
        self.assertIn("route_a", keys)
        self.assertIn("route_b", keys)

    def test_delete_route(self):
        self.cache.save_route("temp_route", {})
        self.assertTrue(self.cache.delete_route("temp_route"))
        self.assertFalse(self.cache.is_cached("temp_route"))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.cache.delete_route("ghost_route"))


if __name__ == "__main__":
    unittest.main()
