import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from main import (
    VideoCutterApp,
    build_segment_intervals,
    read_segment_timeline,
    segment_layout_matches,
)


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@pytest.mark.skipif(not FFMPEG, reason="FFmpeg is not installed")
def test_ffmpeg_segment_csv_matches_forced_boundaries(tmp_path: Path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=11",
            "-c:v", "libx264", "-preset", "ultrafast", str(source),
        ],
        check=True,
    )

    segment_list = tmp_path / "segments.csv"
    app = SimpleNamespace(_get_bitrate_params=VideoCutterApp._get_bitrate_params)
    command = VideoCutterApp.build_scene_segment_command(
        app,
        ffmpeg_path=FFMPEG,
        video_path=source,
        temp_pattern=tmp_path / "scene_%03d.mp4",
        segment_times=[5.0, 6.0],
        max_seconds=5.0,
        duration=11.0,
        remove_audio=True,
        hardware_type="cpu",
        v_width=320,
        v_height=180,
        v_fps=30.0,
        segment_list_path=segment_list,
    )
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    actual = read_segment_timeline(segment_list)
    expected = build_segment_intervals([5.0, 6.0], 11.0)
    assert segment_layout_matches(actual, expected)
    assert len(list(tmp_path.glob("scene_*.mp4"))) == 3


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="FFmpeg/FFprobe is not installed")
def test_safe_interval_command_outputs_requested_clip(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "safe.mp4"
    subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=11",
            "-c:v", "libx264", "-preset", "ultrafast", str(source),
        ],
        check=True,
    )
    app = SimpleNamespace(_get_bitrate_params=VideoCutterApp._get_bitrate_params)
    command = VideoCutterApp.build_scene_interval_command(
        app,
        ffmpeg_path=FFMPEG,
        video_path=source,
        output_path=output,
        start=6.0,
        end=11.0,
        remove_audio=True,
        hardware_type="cpu",
        v_width=320,
        v_height=180,
        v_fps=30.0,
    )
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    duration = subprocess.run(
        [
            FFPROBE, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert float(duration.stdout.strip()) >= 4.95
