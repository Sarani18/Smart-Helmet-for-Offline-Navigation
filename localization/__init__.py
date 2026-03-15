"""
Localization & Sensor Fusion Module
-------------------------------------
Owner: Vijit Ayush Pandey

Provides orientation estimation, heading tracking, dead reckoning, and
map-matching to maintain positional awareness when GPS is unavailable.
"""

from .sensor_fusion import SensorFusion
from .dead_reckoning import DeadReckoning
from .heading_tracker import HeadingTracker
from .map_matching import MapMatcher

__all__ = ["SensorFusion", "DeadReckoning", "HeadingTracker", "MapMatcher"]
