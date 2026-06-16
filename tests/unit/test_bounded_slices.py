import pytest

from services.common.bounded_slices import (
    BoundedLatencyMonitor,
    count_bounded_slices,
    latest_bounded_window_length,
    longest_bounded_window,
    summarize_latency_window,
)


def brute_count(values, threshold):
    count = 0
    for left in range(len(values)):
        cur_min = values[left]
        cur_max = values[left]
        for right in range(left, len(values)):
            cur_min = min(cur_min, values[right])
            cur_max = max(cur_max, values[right])
            if cur_max - cur_min <= threshold:
                count += 1
    return count


def test_example_video_latency_sequence():
    values = [22, 24, 23, 25, 40, 41, 39]
    assert count_bounded_slices(values, 5) == 16
    best = longest_bounded_window(values, 5)
    assert (best.start, best.end, best.length) == (0, 4, 4)
    assert latest_bounded_window_length(values, 5) == 3


def test_empty_and_singleton_sequences():
    assert count_bounded_slices([], 5) == 0
    assert longest_bounded_window([], 5).length == 0
    assert count_bounded_slices([22], 5) == 1
    assert longest_bounded_window([22], 5).length == 1


def test_all_equal_sequence_has_all_slices_valid():
    values = [33, 33, 33, 33]
    assert count_bounded_slices(values, 0) == 10
    assert longest_bounded_window(values, 0).length == 4


@pytest.mark.parametrize(
    "values,threshold",
    [
        ([1, 2, 3, 4, 5], 2),
        ([5, 1, 2, 8, 7, 7], 3),
        ([10, 10, 15, 11, 12, 30], 5),
        ([0.5, 0.7, 1.1, 6.2, 6.3], 0.6),
    ],
)
def test_matches_bruteforce(values, threshold):
    assert count_bounded_slices(values, threshold) == brute_count(values, threshold)


def test_latency_summary_reports_violation_and_stable_windows():
    summary = summarize_latency_window([22, 24, 23, 25, 40, 41, 39], 5, "frame_gap_ms")
    assert summary.sample_count == 7
    assert summary.bounded_slice_count == 16
    assert summary.longest_stable_window == 4
    assert summary.latest_stable_window == 3
    assert summary.violation is True
    assert summary.as_dict()["latency_kind"] == "frame_gap_ms"


def test_streaming_monitor_rolls_window():
    monitor = BoundedLatencyMonitor("frame_gap_ms", max_variation_ms=5, max_samples=3)
    for value in [22, 24, 23, 25]:
        monitor.add(value)
    summary = monitor.summary()
    assert summary.sample_count == 3
    assert summary.min_ms == 23
    assert summary.max_ms == 25
    assert summary.violation is False


def test_invalid_threshold_and_samples_rejected():
    with pytest.raises(ValueError):
        count_bounded_slices([1, 2], -1)
    with pytest.raises(ValueError):
        BoundedLatencyMonitor("frame_gap_ms", 5, 0)
    monitor = BoundedLatencyMonitor("frame_gap_ms", 5, 3)
    with pytest.raises(ValueError):
        monitor.add(-1)
