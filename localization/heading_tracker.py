"""
Heading Tracker
---------------
Maintains a continuous, smoothed estimate of the rider's heading (compass
bearing) from gyroscope and, optionally, magnetometer data.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional


class HeadingTracker:
    """
    Tracks and smooths the heading (yaw) of the rider's helmet over time.

    A simple moving-average filter is applied to raw yaw readings to
    produce a stable heading that is less susceptible to sensor noise.

    Responsibilities
    ----------------
    - Receive yaw readings (in degrees) from the sensor fusion module.
    - Apply a configurable moving-average window to smooth the heading.
    - Detect and ignore readings that represent sensor glitches
      (jumps larger than *spike_threshold*).
    - Return the current smoothed heading on demand.
    """

    def __init__(self, window_size: int = 10, spike_threshold: float = 90.0) -> None:
        """
        Parameters
        ----------
        window_size:
            Number of samples to include in the moving average.
        spike_threshold:
            Maximum accepted change between consecutive readings (degrees).
            Readings that exceed this are discarded as sensor glitches.
        """
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        self._window: Deque[float] = deque(maxlen=window_size)
        self._spike_threshold = spike_threshold
        self._last_raw: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, yaw_degrees: float) -> float:
        """
        Add a new raw yaw reading and return the current smoothed heading.

        Parameters
        ----------
        yaw_degrees:
            Raw yaw angle in degrees (0–360, clockwise from North).
        """
        yaw_degrees = yaw_degrees % 360

        if self._last_raw is not None:
            delta = abs(self._angular_diff(yaw_degrees, self._last_raw))
            if delta > self._spike_threshold:
                # Discard spike – return current smoothed value unchanged
                return self.get_heading()

        self._last_raw = yaw_degrees
        self._window.append(yaw_degrees)
        return self.get_heading()

    def get_heading(self) -> float:
        """
        Return the current smoothed heading in degrees [0, 360).

        Returns 0.0 if no readings have been received yet.
        """
        if not self._window:
            return 0.0
        return self._circular_mean(list(self._window))

    def reset(self) -> None:
        """Clear all stored readings and reset the tracker."""
        self._window.clear()
        self._last_raw = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _angular_diff(a: float, b: float) -> float:
        """Return the signed difference between two angles (degrees)."""
        diff = (a - b + 180) % 360 - 180
        return diff

    @staticmethod
    def _circular_mean(angles: list) -> float:
        """Compute the circular (angular) mean of a list of degree values."""
        import math

        sin_sum = sum(math.sin(math.radians(a)) for a in angles)
        cos_sum = sum(math.cos(math.radians(a)) for a in angles)
        mean_rad = math.atan2(sin_sum, cos_sum)
        return (math.degrees(mean_rad) + 360) % 360
