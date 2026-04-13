"""
Tests for the Dead Reckoning service.
Verifies sensor processing, position prediction, and API endpoints.
"""

import math
import time
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from main import (
    DeadReckoningEngine,
    SensorReading,
    SensorType,
    SensorBatch,
)


class TestDeadReckoningEngine(unittest.TestCase):
    """Unit tests for the core DR algorithm."""

    def setUp(self):
        self.engine = DeadReckoningEngine()
        self.engine.running = True

    # ------------------------------------------------------------------
    # Anchor tests
    # ------------------------------------------------------------------
    def test_anchor_sets_position(self):
        self.engine.anchor(19.076, 72.877, speed_mps=10.0, bearing_deg=45.0)
        self.assertAlmostEqual(self.engine.latitude, 19.076)
        self.assertAlmostEqual(self.engine.longitude, 72.877)
        self.assertEqual(self.engine.uncertainty_m, 0.0)
        self.assertAlmostEqual(self.engine.speed_mps, 10.0)
        self.assertAlmostEqual(self.engine.heading_deg, 45.0)

    def test_anchor_resets_uncertainty(self):
        self.engine.anchor(19.0, 72.0)
        self.engine.uncertainty_m = 50.0
        self.engine.anchor(19.1, 72.1)
        self.assertEqual(self.engine.uncertainty_m, 0.0)

    # ------------------------------------------------------------------
    # Accelerometer processing
    # ------------------------------------------------------------------
    def test_accelerometer_flat_surface(self):
        """Phone lying flat: az≈9.81 → roll≈0, pitch≈0."""
        reading = SensorReading(
            sensor_type=SensorType.ACCELEROMETER,
            values=[0.0, 0.0, 9.81],
            timestamp_ns=1_000_000_000,
        )
        self.engine.process_reading(reading)
        self.assertAlmostEqual(self.engine.roll, 0.0, places=1)
        self.assertAlmostEqual(self.engine.pitch, 0.0, places=1)

    def test_accelerometer_tilted(self):
        """Phone tilted sideways: ay≈9.81 → roll≈90°."""
        reading = SensorReading(
            sensor_type=SensorType.ACCELEROMETER,
            values=[0.0, 9.81, 0.0],
            timestamp_ns=1_000_000_000,
        )
        self.engine.process_reading(reading)
        self.assertAlmostEqual(abs(self.engine.roll), 90.0, places=0)

    # ------------------------------------------------------------------
    # Gyroscope processing
    # ------------------------------------------------------------------
    def test_gyroscope_yaw_integration(self):
        """Rotating at 1 rad/s around z-axis for 1 second → yaw increases ~57°."""
        self.engine.anchor(19.0, 72.0)

        # First reading to initialise timestamp
        r1 = SensorReading(
            sensor_type=SensorType.GYROSCOPE,
            values=[0.0, 0.0, 1.0],  # rad/s
            timestamp_ns=1_000_000_000,
        )
        self.engine.process_reading(r1)

        # Second reading 1 second later
        r2 = SensorReading(
            sensor_type=SensorType.GYROSCOPE,
            values=[0.0, 0.0, 1.0],
            timestamp_ns=2_000_000_000,
        )
        self.engine.process_reading(r2)

        expected_yaw_change = math.degrees(1.0)  # ~57.3°
        self.assertAlmostEqual(self.engine.yaw, expected_yaw_change, places=0)

    # ------------------------------------------------------------------
    # Position advancement (dead reckoning core)
    # ------------------------------------------------------------------
    def test_moving_north_increases_latitude(self):
        """Speed 10 m/s heading North (0°) for 1s → latitude increases."""
        self.engine.anchor(19.076, 72.877, speed_mps=10.0, bearing_deg=0.0)
        self.engine._last_position_ts = 100.0

        self.engine._advance_position(101.0)
        self.assertGreater(self.engine.latitude, 19.076)
        self.assertAlmostEqual(self.engine.longitude, 72.877, places=5)

    def test_moving_east_increases_longitude(self):
        """Speed 10 m/s heading East (90°) for 1s → longitude increases."""
        self.engine.anchor(19.076, 72.877, speed_mps=10.0, bearing_deg=90.0)
        self.engine._last_position_ts = 100.0

        self.engine._advance_position(101.0)
        self.assertAlmostEqual(self.engine.latitude, 19.076, places=5)
        self.assertGreater(self.engine.longitude, 72.877)

    def test_uncertainty_grows_with_distance(self):
        """Uncertainty increases proportionally to distance travelled."""
        self.engine.anchor(19.076, 72.877, speed_mps=10.0, bearing_deg=0.0)
        self.engine._last_position_ts = 100.0

        self.engine._advance_position(101.0)
        # 10 m/s × 1s = 10m → uncertainty = 10 × 0.02 = 0.2m
        self.assertAlmostEqual(self.engine.uncertainty_m, 0.2, places=2)

    def test_no_movement_no_position_change(self):
        """Zero speed → position should not change."""
        self.engine.anchor(19.076, 72.877, speed_mps=0.0, bearing_deg=0.0)
        self.engine._last_position_ts = 100.0

        self.engine._advance_position(101.0)
        self.assertAlmostEqual(self.engine.latitude, 19.076)
        self.assertAlmostEqual(self.engine.longitude, 72.877)

    # ------------------------------------------------------------------
    # Heading smoothing
    # ------------------------------------------------------------------
    def test_heading_smoothing_stable(self):
        """Consistent heading readings → smooth heading matches."""
        for _ in range(10):
            self.engine._update_heading(90.0)
        self.assertAlmostEqual(self.engine.heading_deg, 90.0, places=1)

    def test_heading_spike_rejected(self):
        """A sudden 180° spike should be rejected."""
        for _ in range(5):
            self.engine._update_heading(10.0)
        self.engine._update_heading(200.0)  # spike
        self.assertAlmostEqual(self.engine.heading_deg, 10.0, places=0)

    # ------------------------------------------------------------------
    # Step counter
    # ------------------------------------------------------------------
    def test_step_counter_increments(self):
        self.engine._last_position_ts = 100.0
        r1 = SensorReading(
            sensor_type=SensorType.STEP_COUNTER,
            values=[1000],
            timestamp_ns=100_000_000_000,
        )
        self.engine.process_reading(r1)
        self.assertEqual(self.engine.step_count, 0)  # first reading initialises

        r2 = SensorReading(
            sensor_type=SensorType.STEP_COUNTER,
            values=[1005],
            timestamp_ns=105_000_000_000,
        )
        self.engine.process_reading(r2)
        self.assertEqual(self.engine.step_count, 5)

    # ------------------------------------------------------------------
    # GPS Speed
    # ------------------------------------------------------------------
    def test_gps_speed_updates(self):
        r = SensorReading(
            sensor_type=SensorType.GPS_SPEED,
            values=[15.5],
            timestamp_ns=1_000_000_000,
        )
        self.engine.process_reading(r)
        self.assertAlmostEqual(self.engine.speed_mps, 15.5)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    def test_reset_clears_state(self):
        self.engine.anchor(19.0, 72.0, speed_mps=10.0, bearing_deg=90.0)
        self.engine.reset()
        self.assertIsNone(self.engine.latitude)
        self.assertIsNone(self.engine.longitude)
        self.assertEqual(self.engine.speed_mps, 0.0)
        self.assertEqual(self.engine.heading_deg, 0.0)

    # ------------------------------------------------------------------
    # Full pipeline: sensor batch → position prediction
    # ------------------------------------------------------------------
    def test_full_pipeline_north_travel(self):
        """
        Simulate a simple scenario:
        1. Anchor at known GPS position with speed and heading
        2. Feed gyroscope readings (heading = 0° / North)
        3. After two gyro readings (to establish dt), position advances
        4. Verify latitude increased
        """
        # Step 1: Anchor with speed 10 m/s heading North
        self.engine.anchor(19.076, 72.877, speed_mps=10.0, bearing_deg=0.0)

        base_ns = 1_000_000_000  # 1 second in nanoseconds

        # Step 2: Feed accelerometer (flat)
        self.engine.process_reading(SensorReading(
            sensor_type=SensorType.ACCELEROMETER,
            values=[0.0, 0.0, 9.81],
            timestamp_ns=base_ns,
        ))

        # Step 3: First gyroscope reading — initialises _last_gyro_ts
        self.engine.process_reading(SensorReading(
            sensor_type=SensorType.GYROSCOPE,
            values=[0.0, 0.0, 0.0],
            timestamp_ns=base_ns,
        ))

        # Step 4: Second gyro 1s later — triggers _advance_position but
        #         _last_position_ts was just set, so this computes dt > 0
        self.engine.process_reading(SensorReading(
            sensor_type=SensorType.GYROSCOPE,
            values=[0.0, 0.0, 0.0],
            timestamp_ns=base_ns + 1_000_000_000,
        ))

        # Step 5: Third gyro 1s later — now dt is definitely > 0 and
        #         position advances by speed × dt = 10 m
        self.engine.process_reading(SensorReading(
            sensor_type=SensorType.GYROSCOPE,
            values=[0.0, 0.0, 0.0],
            timestamp_ns=base_ns + 2_000_000_000,
        ))

        # Verify position moved north
        self.assertGreater(self.engine.latitude, 19.076)
        self.assertGreater(self.engine.uncertainty_m, 0.0)


class TestHelperMethods(unittest.TestCase):
    """Test utility/math helpers."""

    def test_angular_diff_same(self):
        self.assertAlmostEqual(DeadReckoningEngine._angular_diff(10, 10), 0.0)

    def test_angular_diff_across_360(self):
        diff = DeadReckoningEngine._angular_diff(5, 355)
        self.assertAlmostEqual(diff, 10.0)

    def test_angular_diff_negative(self):
        diff = DeadReckoningEngine._angular_diff(355, 5)
        self.assertAlmostEqual(diff, -10.0)

    def test_circular_mean_uniform(self):
        mean = DeadReckoningEngine._circular_mean([90, 90, 90])
        self.assertAlmostEqual(mean, 90.0, places=1)

    def test_circular_mean_wrapping(self):
        mean = DeadReckoningEngine._circular_mean([350, 10])
        self.assertAlmostEqual(mean, 0.0, places=0)


if __name__ == "__main__":
    unittest.main()
