"""
Navigation confidence tracker
-----------------------------
Maintains a confidence score (0.0 to 1.0) for event-driven route progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import EventMessage
from .route_progress import ProgressUpdate


@dataclass(frozen=True)
class ConfidenceState:
    score: float
    last_event_ts_ms: Optional[int]
    match_streak: int
    mismatch_streak: int


class NavigationConfidenceTracker:
    """Tracks confidence using event quality and progress outcomes."""

    def __init__(
        self,
        initial_score: float = 0.7,
        decay_interval_ms: int = 5000,
        decay_per_interval: float = 0.03,
    ) -> None:
        if not (0.0 <= initial_score <= 1.0):
            raise ValueError("initial_score must be between 0.0 and 1.0")
        if decay_interval_ms <= 0:
            raise ValueError("decay_interval_ms must be > 0")
        if decay_per_interval < 0:
            raise ValueError("decay_per_interval must be >= 0")

        self._score = float(initial_score)
        self._decay_interval_ms = decay_interval_ms
        self._decay_per_interval = decay_per_interval

        self._last_event_ts_ms: Optional[int] = None
        self._match_streak = 0
        self._mismatch_streak = 0

    def get_score(self) -> float:
        return round(self._score, 4)

    def get_state(self) -> ConfidenceState:
        return ConfidenceState(
            score=self.get_score(),
            last_event_ts_ms=self._last_event_ts_ms,
            match_streak=self._match_streak,
            mismatch_streak=self._mismatch_streak,
        )

    def update_from_event(self, event: EventMessage, progress: ProgressUpdate) -> float:
        """Update score based on event confidence and whether step advanced."""
        self._last_event_ts_ms = event.ts_ms

        if progress.advanced:
            self._match_streak += 1
            self._mismatch_streak = 0

            gain = 0.12 * event.confidence
            gain += 0.02 * min(self._match_streak, 3)
            self._score = min(1.0, self._score + gain)
        else:
            self._mismatch_streak += 1
            self._match_streak = 0

            loss = 0.08 * (1.0 + (1.0 - event.confidence))
            loss += 0.03 * min(self._mismatch_streak, 4)
            self._score = max(0.0, self._score - loss)

        return self.get_score()

    def apply_time_decay(self, now_ts_ms: int) -> float:
        """Apply confidence decay when no recent events are observed."""
        if self._last_event_ts_ms is None:
            return self.get_score()

        if now_ts_ms <= self._last_event_ts_ms:
            return self.get_score()

        elapsed = now_ts_ms - self._last_event_ts_ms
        intervals = elapsed // self._decay_interval_ms
        if intervals <= 0:
            return self.get_score()

        decay = intervals * self._decay_per_interval
        self._score = max(0.0, self._score - decay)

        # Move reference time forward by full intervals so decay is not double counted.
        self._last_event_ts_ms += intervals * self._decay_interval_ms
        return self.get_score()
