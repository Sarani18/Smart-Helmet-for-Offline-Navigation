"""
Unit tests for the Localization & Sensor Fusion Module.
"""

import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from localization.sensor_fusion import SensorFusion, IMUReading, Orientation
from localization.dead_reckoning import DeadReckoning, MotionSample, Position
from localization.heading_tracker import HeadingTracker
from localization.map_matching import MapMatcher


# ---------------------------------------------------------------------------
# SensorFusion tests
# ---------------------------------------------------------------------------

class TestSensorFusion(unittest.TestCase):

    def _make_reading(self, ax=0.0, ay=0.0, az=9.81,
                      gx=0.0, gy=0.0, gz=0.0, t=0.0):
        return IMUReading(ax, ay, az, gx, gy, gz, t)

    def test_first_update_returns_orientation(self):
        sf = SensorFusion()
        reading = self._make_reading(t=1.0)
        orient = sf.update(reading)
        self.assertIsInstance(orient, Orientation)

    def test_orientation_flat_surface(self):
        sf = SensorFusion()
        reading = self._make_reading(az=9.81, t=0.0)
        orient = sf.update(reading)
        # Flat: roll and pitch should be close to 0
        self.assertAlmostEqual(orient.roll, 0.0, places=3)
        self.assertAlmostEqual(orient.pitch, 0.0, places=3)

    def test_yaw_advances_with_gyro(self):
        sf = SensorFusion()
        sf.update(self._make_reading(t=0.0))
        # Rotate 90°/s for 1 second → yaw should increase
        orient = sf.update(self._make_reading(gz=90.0, t=1.0))
        self.assertGreater(orient.yaw, 0.0)

    def test_crash_not_detected_normal(self):
        sf = SensorFusion()
        sf.update(self._make_reading(t=0.0))
        self.assertFalse(sf.is_crash_detected())

    def test_crash_detected_extreme_roll(self):
        sf = SensorFusion()
        # Reading with heavy lateral acceleration simulating a fall
        sf.update(self._make_reading(ay=9.81, az=0.0, t=0.0))
        orient = sf.get_orientation()
        self.assertGreaterEqual(abs(orient.roll), 80.0)
        self.assertTrue(sf.is_crash_detected())

    def test_reset_clears_state(self):
        sf = SensorFusion()
        sf.update(self._make_reading(gz=90.0, t=0.0))
        sf.update(self._make_reading(gz=90.0, t=1.0))
        sf.reset()
        orient = sf.get_orientation()
        self.assertEqual(orient.yaw, 0.0)

    def test_invalid_alpha_raises(self):
        with self.assertRaises(ValueError):
            SensorFusion(alpha=1.5)


# ---------------------------------------------------------------------------
# DeadReckoning tests
# ---------------------------------------------------------------------------

class TestDeadReckoning(unittest.TestCase):

    def test_no_anchor_returns_none(self):
        dr = DeadReckoning()
        sample = MotionSample(speed_mps=10.0, heading_degrees=0.0, timestamp=1.0)
        self.assertIsNone(dr.update(sample))

    def test_anchor_sets_position(self):
        dr = DeadReckoning()
        dr.anchor(19.076, 72.877)
        pos = dr.get_position()
        self.assertAlmostEqual(pos.latitude, 19.076)
        self.assertAlmostEqual(pos.longitude, 72.877)
        self.assertEqual(pos.uncertainty_meters, 0.0)

    def test_moving_north_increases_latitude(self):
        dr = DeadReckoning()
        dr.anchor(19.076, 72.877)
        # Heading 0° = North; speed 10 m/s; 1 second → ~10 m north
        sample = MotionSample(speed_mps=10.0, heading_degrees=0.0, timestamp=0.0)
        dr.update(sample)  # initialise timestamp
        sample2 = MotionSample(speed_mps=10.0, heading_degrees=0.0, timestamp=1.0)
        pos = dr.update(sample2)
        self.assertGreater(pos.latitude, 19.076)

    def test_uncertainty_grows(self):
        dr = DeadReckoning()
        dr.anchor(19.076, 72.877)
        dr.update(MotionSample(10.0, 0.0, 0.0))
        pos = dr.update(MotionSample(10.0, 0.0, 1.0))
        self.assertGreater(pos.uncertainty_meters, 0.0)

    def test_anchor_resets_uncertainty(self):
        dr = DeadReckoning()
        dr.anchor(19.076, 72.877)
        dr.update(MotionSample(10.0, 0.0, 0.0))
        dr.update(MotionSample(10.0, 0.0, 1.0))
        dr.anchor(19.076, 72.877)  # re-anchor
        self.assertEqual(dr.get_position().uncertainty_meters, 0.0)

    def test_history_grows(self):
        dr = DeadReckoning()
        dr.anchor(19.0, 72.0)
        dr.update(MotionSample(10.0, 90.0, 0.0))
        dr.update(MotionSample(10.0, 90.0, 1.0))
        dr.update(MotionSample(10.0, 90.0, 2.0))
        self.assertEqual(len(dr.get_history()), 2)  # first call initialises dt only

    def test_reset_clears_state(self):
        dr = DeadReckoning()
        dr.anchor(19.0, 72.0)
        dr.update(MotionSample(10.0, 0.0, 1.0))
        dr.reset()
        self.assertIsNone(dr.get_position())
        self.assertEqual(dr.get_history(), [])


# ---------------------------------------------------------------------------
# HeadingTracker tests
# ---------------------------------------------------------------------------

class TestHeadingTracker(unittest.TestCase):

    def test_no_readings_returns_zero(self):
        ht = HeadingTracker()
        self.assertEqual(ht.get_heading(), 0.0)

    def test_single_reading(self):
        ht = HeadingTracker()
        heading = ht.update(90.0)
        self.assertAlmostEqual(heading, 90.0, places=1)

    def test_smoothing_multiple_readings(self):
        ht = HeadingTracker(window_size=3)
        ht.update(90.0)
        ht.update(90.0)
        heading = ht.update(90.0)
        self.assertAlmostEqual(heading, 90.0, places=1)

    def test_spike_rejected(self):
        ht = HeadingTracker(window_size=5, spike_threshold=45.0)
        for _ in range(4):
            ht.update(10.0)
        # A spike of 200° should be rejected
        heading_after_spike = ht.update(210.0)
        self.assertAlmostEqual(heading_after_spike, 10.0, places=1)

    def test_wraps_360(self):
        ht = HeadingTracker()
        heading = ht.update(361.0)
        self.assertAlmostEqual(heading, 1.0, places=1)

    def test_reset(self):
        ht = HeadingTracker()
        ht.update(270.0)
        ht.reset()
        self.assertEqual(ht.get_heading(), 0.0)

    def test_invalid_window_size(self):
        with self.assertRaises(ValueError):
            HeadingTracker(window_size=0)


# ---------------------------------------------------------------------------
# MapMatcher tests
# ---------------------------------------------------------------------------

class TestMapMatcher(unittest.TestCase):

    def _sample_segments(self):
        return [
            {
                "id": "seg1",
                "name": "Main St",
                "start": {"lat": 19.0760, "lon": 72.8770},
                "end":   {"lat": 19.0800, "lon": 72.8800},
            }
        ]

    def test_match_close_to_segment(self):
        mm = MapMatcher(self._sample_segments())
        pos = Position(latitude=19.0780, longitude=72.8785, uncertainty_meters=5.0)
        matched, dist = mm.match(pos)
        self.assertIsNotNone(matched)
        self.assertLess(dist, 50.0)

    def test_match_far_from_all_segments(self):
        mm = MapMatcher(self._sample_segments())
        pos = Position(latitude=28.6139, longitude=77.2090)  # Delhi
        matched, dist = mm.match(pos)
        self.assertIsNone(matched)

    def test_no_segments_returns_none(self):
        mm = MapMatcher([])
        pos = Position(latitude=19.0780, longitude=72.8785)
        matched, dist = mm.match(pos)
        self.assertIsNone(matched)
        self.assertEqual(dist, float("inf"))

    def test_update_segments(self):
        mm = MapMatcher([])
        mm.update_segments(self._sample_segments())
        pos = Position(latitude=19.0780, longitude=72.8785)
        matched, _ = mm.match(pos)
        self.assertIsNotNone(matched)


if __name__ == "__main__":
    unittest.main()
