"""
Localization event pipeline
---------------------------
Ingests validated localization events and provides a stable stream for
navigation logic by handling duplicates, staleness checks, and
timestamp-based reordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, List, Set
from collections import deque

from .contracts import EventMessage


@dataclass(frozen=True)
class EventIngestResult:
    accepted: bool
    reason: str


class LocalizationEventPipeline:
    """
    Handles localization event stream quality before route processing.

    Behavior
    --------
    - Drops duplicate ``event_id`` values.
    - Rejects stale events older than ``max_staleness_ms``.
    - Buffers accepted events and releases them in timestamp order.
    - Uses ``reorder_window_ms`` to tolerate slightly out-of-order arrivals.
    """

    def __init__(
        self,
        max_staleness_ms: int = 1500,
        reorder_window_ms: int = 300,
        seen_cache_size: int = 5000,
    ) -> None:
        if max_staleness_ms < 0:
            raise ValueError("max_staleness_ms must be >= 0")
        if reorder_window_ms < 0:
            raise ValueError("reorder_window_ms must be >= 0")
        if seen_cache_size <= 0:
            raise ValueError("seen_cache_size must be > 0")

        self._max_staleness_ms = max_staleness_ms
        self._reorder_window_ms = reorder_window_ms
        self._seen_cache_size = seen_cache_size

        self._buffer: List[EventMessage] = []
        self._seen_ids: Set[str] = set()
        self._seen_order: Deque[str] = deque()

    def ingest(self, event: EventMessage, now_ts_ms: int) -> EventIngestResult:
        """Ingest one validated event into the pipeline."""
        if event.event_id in self._seen_ids:
            return EventIngestResult(False, "duplicate_event_id")

        if now_ts_ms - event.ts_ms > self._max_staleness_ms:
            return EventIngestResult(False, "stale_event")

        self._buffer.append(event)
        self._buffer.sort(key=lambda item: item.ts_ms)
        self._mark_seen(event.event_id)
        return EventIngestResult(True, "accepted")

    def pop_ready(self, now_ts_ms: int) -> List[EventMessage]:
        """
        Pop events ready for processing.

        An event is ready if it is older than the reorder cutoff:
        ``event.ts_ms <= now_ts_ms - reorder_window_ms``.
        """
        if not self._buffer:
            return []

        cutoff = now_ts_ms - self._reorder_window_ms
        ready_count = 0
        for event in self._buffer:
            if event.ts_ms <= cutoff:
                ready_count += 1
            else:
                break

        if ready_count == 0:
            return []

        ready = self._buffer[:ready_count]
        self._buffer = self._buffer[ready_count:]
        return ready

    def flush_all(self) -> List[EventMessage]:
        """Return all buffered events in timestamp order and clear buffer."""
        all_events = list(self._buffer)
        self._buffer.clear()
        return all_events

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    def _mark_seen(self, event_id: str) -> None:
        self._seen_ids.add(event_id)
        self._seen_order.append(event_id)

        while len(self._seen_order) > self._seen_cache_size:
            oldest = self._seen_order.popleft()
            self._seen_ids.discard(oldest)
