"""
Sensor Fusion
-------------
Combines accelerometer and gyroscope readings into a stable orientation
estimate using a complementary filter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class IMUReading:
    """
    Raw reading from an Inertial Measurement Unit (IMU).

    Attributes
    ----------
    accel_x, accel_y, accel_z : float
        Linear acceleration in m/s² along each axis.
    gyro_x, gyro_y, gyro_z : float
        Angular velocity in degrees/second around each axis.
    timestamp : float
        Unix timestamp (seconds) of this reading.
    """

    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    timestamp: float


@dataclass
class Orientation:
    """Euler angles describing the helmet's current orientation."""

    roll: float   # rotation around the forward axis (degrees)
    pitch: float  # rotation around the side axis (degrees)
    yaw: float    # rotation around the vertical axis / heading (degrees)


class SensorFusion:
    """
    Fuses accelerometer and gyroscope data into a smooth orientation estimate.

    A **complementary filter** is used: the high-frequency gyroscope
    integration is combined with the low-frequency, drift-free accelerometer
    tilt estimate.  The blend ratio is controlled by *alpha* (default 0.98).

    Responsibilities
    ----------------
    - Accept raw IMU readings and update the current orientation.
    - Apply a complementary filter to remove gyro drift over time.
    - Expose the latest roll / pitch / yaw for downstream modules.
    - Detect abnormal orientation (potential crash / fall).
    """

    CRASH_PITCH_THRESHOLD = 60.0  # degrees
    CRASH_ROLL_THRESHOLD = 75.0   # degrees

    def __init__(self, alpha: float = 0.98) -> None:
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between 0 and 1 (exclusive)")
        self._alpha = alpha
        self._orientation = Orientation(roll=0.0, pitch=0.0, yaw=0.0)
        self._last_timestamp: float | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, reading: IMUReading) -> Orientation:
        """
        Process a new IMU reading and return the updated orientation.

        Parameters
        ----------
        reading:
            Latest :class:`IMUReading` from the sensor hardware.
        """
        if self._last_timestamp is None:
            self._last_timestamp = reading.timestamp
            self._orientation = self._accel_orientation(reading)
            return self._orientation

        dt = reading.timestamp - self._last_timestamp
        if dt <= 0:
            return self._orientation
        self._last_timestamp = reading.timestamp

        # Gyroscope integration (degrees)
        gyro_roll = self._orientation.roll + reading.gyro_x * dt
        gyro_pitch = self._orientation.pitch + reading.gyro_y * dt
        gyro_yaw = self._orientation.yaw + reading.gyro_z * dt

        # Accelerometer tilt estimate
        accel = self._accel_orientation(reading)

        # Complementary filter: trust gyro for fast changes, accel for slow
        new_roll = self._alpha * gyro_roll + (1 - self._alpha) * accel.roll
        new_pitch = self._alpha * gyro_pitch + (1 - self._alpha) * accel.pitch
        # Yaw cannot be corrected from accelerometer alone – use gyro only
        new_yaw = gyro_yaw % 360

        self._orientation = Orientation(
            roll=new_roll, pitch=new_pitch, yaw=new_yaw
        )
        return self._orientation

    def get_orientation(self) -> Orientation:
        """Return the most recently computed orientation."""
        return self._orientation

    def is_crash_detected(self) -> bool:
        """
        Return *True* if the current orientation exceeds the thresholds that
        indicate a potential crash or fall.
        """
        return (
            abs(self._orientation.pitch) > self.CRASH_PITCH_THRESHOLD
            or abs(self._orientation.roll) > self.CRASH_ROLL_THRESHOLD
        )

    def reset(self) -> None:
        """Reset the filter state (e.g. after a detected crash is cleared)."""
        self._orientation = Orientation(roll=0.0, pitch=0.0, yaw=0.0)
        self._last_timestamp = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _accel_orientation(reading: IMUReading) -> Orientation:
        """Compute roll and pitch from raw accelerometer values."""
        ax, ay, az = reading.accel_x, reading.accel_y, reading.accel_z
        roll = math.degrees(math.atan2(ay, az))
        pitch = math.degrees(math.atan2(-ax, math.sqrt(ay**2 + az**2)))
        return Orientation(roll=roll, pitch=pitch, yaw=0.0)
