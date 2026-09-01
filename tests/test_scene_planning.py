from pathlib import Path

import pytest

from main import (
    build_kept_intervals,
    build_scene_split_times,
    build_segment_intervals,
    build_smooth_boundary_times,
    read_segment_timeline,
    segment_layout_matches,
)


def _durations(intervals):
    return [round(end - start, 3) for start, end in intervals]


@pytest.mark.parametrize("duration", [7.0, 12.5, 18.5, 4440.0])
def test_scene_planner_never_creates_sub_minimum_kept_clip(duration):
    scene_times = [round(value * 0.5, 3) for value in range(1, int(duration * 2))]
    splits = build_scene_split_times(
        scene_times,
        duration=duration,
        min_seconds=3.0,
        max_seconds=5.0,
        smooth_seconds=0.5,
    )
    boundaries, _examples = build_smooth_boundary_times(
        splits,
        scene_times,
        duration,
        smooth_seconds=0.5,
        min_output_seconds=3.0,
    )
    assert min(_durations(build_kept_intervals(boundaries, duration))) >= 3.0


def test_impossible_short_remainder_is_merged_instead_of_exported():
    splits = build_scene_split_times([], 6.5, 3.0, 5.0, smooth_seconds=0.5)
    boundaries, _ = build_smooth_boundary_times(
        splits, [], 6.5, 0.5, min_output_seconds=3.0,
    )
    assert _durations(build_kept_intervals(boundaries, 6.5)) == [6.5]


def test_segment_csv_detects_missing_boundary_before_parity_shift(tmp_path: Path):
    csv_path = tmp_path / "segments.csv"
    csv_path.write_text(
        "scene_001.mp4,0.000000,5.000000\n"
        "scene_002.mp4,5.000000,6.000000\n"
        "scene_003.mp4,6.000000,11.000000\n",
        encoding="utf-8",
    )
    actual = read_segment_timeline(csv_path)
    expected = build_segment_intervals([5.0, 5.5, 6.0], 11.0)
    assert not segment_layout_matches(actual, expected)


def test_segment_csv_accepts_expected_layout(tmp_path: Path):
    csv_path = tmp_path / "segments.csv"
    csv_path.write_text(
        "scene_001.mp4,0.000000,5.000000\n"
        "scene_002.mp4,5.000000,6.000000\n"
        "scene_003.mp4,6.000000,11.000000\n",
        encoding="utf-8",
    )
    assert segment_layout_matches(
        read_segment_timeline(csv_path),
        build_segment_intervals([5.0, 6.0], 11.0),
    )
