import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from main import (
    CUT_BY_SCENE,
    OUTPUT_MODE_MERGE_RENAME,
    OUTPUT_MODE_SPLIT_FOLDER,
    VideoCutterApp,
)
from processing_policy import HardwareProfile


def _make_fake_app():
    app = SimpleNamespace()
    app.cancel_event = threading.Event()
    app.log_queue = queue.Queue()
    app.hardware_type = "cpu"
    app.current_output_dir = None
    app.last_output_dir = None
    app.active_jobs = 0
    app.max_active_jobs = 0
    app.active_jobs_lock = threading.Lock()

    templates = {
        "log_start": "start",
        "log_parallel_workers": "parallel {count}",
        "log_batch_progress": "{current}/{total} {name}",
        "log_video_elapsed": "{name} {seconds:.2f}",
        "log_batch_elapsed": "batch {seconds:.2f}",
        "log_complete": "complete",
        "log_exported_count": "exported {count}",
        "log_result_folder": "result {path}",
        "log_merged_output": "merged {path}",
        "log_batch_done_msg": "done {total} {path}",
        "log_batch_separate_done": "done {total} {path}",
        "msg_file_not_found": "missing {name}",
        "msg_cancelled": "cancelled",
        "log_cancelled": "cancelled",
        "log_ffmpeg_error": "ffmpeg {error}",
    }

    app.t = lambda key: templates.get(key, key)
    app.log = lambda message: app.log_queue.put(("log", message))
    app.set_progress = lambda _value: None
    app.set_current_process = lambda _process: None
    app.terminate_current_process = lambda: None
    app.cleanup_cancelled_output_dir = lambda: None

    def check_cancelled():
        if app.cancel_event.is_set():
            raise RuntimeError("cancelled")

    app.check_cancelled = check_cancelled

    def create_output_folders(parent, count):
        folders = []
        for index in range(1, count + 1):
            folder = parent / f"folder_{index}"
            folder.mkdir(parents=True, exist_ok=True)
            folders.append(folder)
        return folders

    app.create_output_folders = create_output_folders

    def process_single_video(**kwargs):
        with app.active_jobs_lock:
            app.active_jobs += 1
            app.max_active_jobs = max(app.max_active_jobs, app.active_jobs)
        try:
            kwargs["progress_callback"](0.5)
            time.sleep(0.05)
            kwargs["progress_callback"](1.0)
            return 1, 1
        finally:
            with app.active_jobs_lock:
                app.active_jobs -= 1

    app.process_single_video = process_single_video
    return app


def _run_batch(app, tmp_path, output_mode, duplicate_names=False):
    files = []
    for index in range(3):
        if duplicate_names:
            source_dir = tmp_path / f"source_{index}"
            source_dir.mkdir()
            video = source_dir / "video.mp4"
        else:
            video = tmp_path / f"video_{index}.mp4"
        video.write_bytes(b"test")
        files.append({"path": str(video), "duration": 10.0})

    with (
        patch("main.find_ffmpeg_tools", return_value=("ffmpeg", "ffprobe")),
        patch(
            "main.build_hardware_profile",
            return_value=HardwareProfile(
                hardware_type="nvidia",
                encoder="h264_nvenc",
                encoder_label="NVIDIA NVENC",
                logical_cpus=16,
                ram_gb=32.0,
                gpu_name="Test GPU",
                gpu_memory_mb=8192,
                parallel_video_workers=2,
                calibrated=True,
            ),
        ),
    ):
        VideoCutterApp.process_all_videos(
            app,
            files,
            tmp_path / "result",
            CUT_BY_SCENE,
            None,
            3.0,
            5.0,
            0.35,
            1,
            False,
            True,
            0.5,
            output_mode,
            "benchmark",
        )


def test_scene_batch_runs_two_videos_concurrently(tmp_path):
    app = _make_fake_app()
    _run_batch(app, tmp_path, OUTPUT_MODE_SPLIT_FOLDER)
    assert app.max_active_jobs == 2


def test_merge_rename_remains_serial_to_protect_shared_names(tmp_path):
    app = _make_fake_app()
    _run_batch(app, tmp_path, OUTPUT_MODE_MERGE_RENAME)
    assert app.max_active_jobs == 1


def test_duplicate_video_names_remain_serial(tmp_path):
    app = _make_fake_app()
    _run_batch(
        app,
        tmp_path,
        OUTPUT_MODE_SPLIT_FOLDER,
        duplicate_names=True,
    )
    assert app.max_active_jobs == 1
