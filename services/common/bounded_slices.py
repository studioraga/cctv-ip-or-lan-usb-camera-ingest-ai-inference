"""Bounded-slices utilities for streaming latency stability monitoring.

A bounded slice is a contiguous window where max(values) - min(values) stays
within a configured threshold.  The implementation uses the classic O(N)
sliding-window pattern with monotonic deques, so each sample is inserted and
removed at most once.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from typing import Deque, Iterable, Sequence


@dataclass(frozen=True)
class BoundedWindow:
    """Best contiguous bounded window in a latency sequence."""

    start: int
    end: int
    length: int
    min_value: float | None
    max_value: float | None
    variation: float | None


@dataclass(frozen=True)
class LatencyWindowSummary:
    """Summary emitted for one rolling latency window."""

    latency_kind: str
    threshold_ms: float
    sample_count: int
    min_ms: float | None
    max_ms: float | None
    variation_ms: float | None
    bounded_slice_count: int
    longest_stable_window: int
    latest_stable_window: int
    violation: bool

    def as_dict(self) -> dict[str, float | int | str | bool | None]:
        return {
            "latency_kind": self.latency_kind,
            "threshold_ms": self.threshold_ms,
            "sample_count": self.sample_count,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "variation_ms": self.variation_ms,
            "bounded_slice_count": self.bounded_slice_count,
            "longest_stable_window": self.longest_stable_window,
            "latest_stable_window": self.latest_stable_window,
            "violation": self.violation,
        }


def _validate_threshold(max_variation: float) -> None:
    if max_variation < 0 or not isfinite(max_variation):
        raise ValueError("max_variation must be a finite non-negative number")


def _validated_values(values: Iterable[float]) -> list[float]:
    out: list[float] = []
    for value in values:
        f = float(value)
        if not isfinite(f):
            raise ValueError(f"latency sample must be finite, got {value!r}")
        out.append(f)
    return out


def count_bounded_slices(values: Sequence[float] | Iterable[float], max_variation: float) -> int:
    """Count all contiguous bounded slices in O(N) time.

    Example:
        values=[22, 24, 23, 25, 40, 41, 39], max_variation=5 -> 16
    """

    _validate_threshold(max_variation)
    arr = _validated_values(values)
    min_q: Deque[int] = deque()
    max_q: Deque[int] = deque()
    left = 0
    count = 0

    for right, value in enumerate(arr):
        while min_q and arr[min_q[-1]] > value:
            min_q.pop()
        min_q.append(right)

        while max_q and arr[max_q[-1]] < value:
            max_q.pop()
        max_q.append(right)

        while min_q and max_q and arr[max_q[0]] - arr[min_q[0]] > max_variation:
            if min_q[0] == left:
                min_q.popleft()
            if max_q[0] == left:
                max_q.popleft()
            left += 1

        count += right - left + 1

    return count


def longest_bounded_window(values: Sequence[float] | Iterable[float], max_variation: float) -> BoundedWindow:
    """Return the longest bounded contiguous window in O(N) time."""

    _validate_threshold(max_variation)
    arr = _validated_values(values)
    if not arr:
        return BoundedWindow(0, 0, 0, None, None, None)

    min_q: Deque[int] = deque()
    max_q: Deque[int] = deque()
    left = 0
    best_start = 0
    best_end = 1

    for right, value in enumerate(arr):
        while min_q and arr[min_q[-1]] > value:
            min_q.pop()
        min_q.append(right)

        while max_q and arr[max_q[-1]] < value:
            max_q.pop()
        max_q.append(right)

        while min_q and max_q and arr[max_q[0]] - arr[min_q[0]] > max_variation:
            if min_q[0] == left:
                min_q.popleft()
            if max_q[0] == left:
                max_q.popleft()
            left += 1

        if right - left + 1 > best_end - best_start:
            best_start = left
            best_end = right + 1

    window = arr[best_start:best_end]
    min_v = min(window)
    max_v = max(window)
    return BoundedWindow(best_start, best_end, best_end - best_start, min_v, max_v, max_v - min_v)


def latest_bounded_window_length(values: Sequence[float] | Iterable[float], max_variation: float) -> int:
    """Return the bounded-window length that ends at the latest sample."""

    _validate_threshold(max_variation)
    arr = _validated_values(values)
    if not arr:
        return 0

    min_v = arr[-1]
    max_v = arr[-1]
    length = 0
    for value in reversed(arr):
        min_v = min(min_v, value)
        max_v = max(max_v, value)
        if max_v - min_v > max_variation:
            break
        length += 1
    return length


def summarize_latency_window(
    values: Sequence[float] | Iterable[float],
    max_variation_ms: float,
    latency_kind: str,
) -> LatencyWindowSummary:
    """Summarize a latency window for JSONL and Prometheus reporting."""

    _validate_threshold(max_variation_ms)
    arr = _validated_values(values)
    if not arr:
        return LatencyWindowSummary(
            latency_kind=latency_kind,
            threshold_ms=max_variation_ms,
            sample_count=0,
            min_ms=None,
            max_ms=None,
            variation_ms=None,
            bounded_slice_count=0,
            longest_stable_window=0,
            latest_stable_window=0,
            violation=False,
        )

    min_ms = min(arr)
    max_ms = max(arr)
    variation_ms = max_ms - min_ms
    longest = longest_bounded_window(arr, max_variation_ms)
    return LatencyWindowSummary(
        latency_kind=latency_kind,
        threshold_ms=max_variation_ms,
        sample_count=len(arr),
        min_ms=min_ms,
        max_ms=max_ms,
        variation_ms=variation_ms,
        bounded_slice_count=count_bounded_slices(arr, max_variation_ms),
        longest_stable_window=longest.length,
        latest_stable_window=latest_bounded_window_length(arr, max_variation_ms),
        violation=variation_ms > max_variation_ms,
    )


class BoundedLatencyMonitor:
    """Rolling latency monitor backed by a fixed-size deque."""

    def __init__(self, latency_kind: str, max_variation_ms: float, max_samples: int):
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        _validate_threshold(max_variation_ms)
        self.latency_kind = latency_kind
        self.max_variation_ms = max_variation_ms
        self.samples: Deque[float] = deque(maxlen=max_samples)

    def add(self, value_ms: float) -> None:
        value = float(value_ms)
        if not isfinite(value):
            raise ValueError(f"latency sample must be finite, got {value_ms!r}")
        if value < 0:
            raise ValueError(f"latency sample must be non-negative, got {value_ms!r}")
        self.samples.append(value)

    def summary(self) -> LatencyWindowSummary:
        return summarize_latency_window(list(self.samples), self.max_variation_ms, self.latency_kind)

    def clear(self) -> None:
        self.samples.clear()
