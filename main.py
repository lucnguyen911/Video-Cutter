import csv
import math
import ctypes
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import winsound
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox,
    QTextEdit, QProgressBar, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QVBoxLayout, QGridLayout, QHeaderView, QSplitter,
    QFileDialog, QMessageBox, QAbstractItemView, QDialog,
)
from PyQt6.QtCore import Qt, QTimer, QUrl, QSize
from PyQt6.QtGui import QCursor, QIcon, QPixmap, QDragEnterEvent, QDropEvent

from processing_policy import build_hardware_profile, choose_parallel_video_workers
from ui.theme import APP_STYLESHEET, build_stylesheet, _DARK_TOKENS, _LIGHT_TOKENS


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERNAL CONSTANTS (used for logic, never displayed directly)
# ═══════════════════════════════════════════════════════════════════════════════

CUT_FIXED = "fixed"
CUT_BY_SCENE = "scene"
CUT_TO_IMAGES = "images"
SMOOTH_TRIM_TAIL = "trim_tail"
SMOOTH_TRIM_HEAD = "trim_head"
OUTPUT_MODE_SPLIT_FOLDER  = 0
OUTPUT_MODE_MERGE_DEFAULT = 1
OUTPUT_MODE_MERGE_RENAME  = 2
MIN_BOUNDARY_GAP = 0.05
SHORT_FRAGMENT_THRESHOLD = 1.0
MAX_SHORT_FRAGMENT_EXTENSION = 2.0
SMART_SNAPSHOT_MIN_SETTLE = 0.2
SMART_SNAPSHOT_MAX_SETTLE = 0.7
SMART_SNAPSHOT_SAFETY_GAP = 0.15
SMART_SNAPSHOT_STABLE_SAMPLES = 2
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v"}

# ═══════════════════════════════════════════════════════════════════════════════
#  LANGUAGE DATA
# ═══════════════════════════════════════════════════════════════════════════════

LANG_DATA = {
    "vi": {
        # ── Title & Header ──
        "app_title": "Video Cutter",
        "app_subtitle": "Được phát triển bởi Lực Nguyễn",
        "tooltip_to_light": "Chuyển sang giao diện sáng",
        "tooltip_to_dark": "Chuyển sang giao diện tối",

        # ── Section 1: Input ──
        "section_input": "Đầu Vào",
        "btn_choose_files": "Chọn file",
        "btn_choose_folder": "Chọn thư mục",
        "btn_clear_all": "Xóa tất cả",
        "file_count": "Tổng: {count} file",
        "drop_placeholder": "Kéo thả file video hoặc thư mục vào Table này để nạp danh sách",
        "col_stt": "STT",
        "col_filename": "Tên file",
        "col_duration": "Thời lượng",
        "col_size": "Kích thước",
        "scanning": "Đang quét...",

        # ── Section 2: Output ──
        "section_output": "Đầu Ra",
        "output_dir_label": "Thư mục xuất:",
        "output_dir_placeholder": "Chưa chọn...",
        "btn_choose": "Chọn",
        "project_name_label": "Tên dự án:",
        "project_name_placeholder": "Tên dự án (tùy chọn)...",
        "output_mode_label": "Chế độ xuất:",
        "output_mode_split": "Tách Folder",
        "output_mode_merge_default": "Gộp Folder (Mặc định)",
        "output_mode_merge_rename": "Gộp Folder (Đổi tên)",
        "output_folder_label": "Số lượng folder:",
        "folder_unit": "folder",
        "remove_audio_label": "Xóa audio:",

        # ── Section 3: Settings ──
        "section_settings": "Cấu Hình",
        "cut_type_label": "Kiểu cắt:",
        "cut_fixed": "Cố định",
        "cut_by_scene": "Chuyển cảnh",
        "cut_to_images": "Ảnh theo cảnh",
        "duration_label": "Thời lượng (s):",
        "scene_params_label": "Thông số:",
        "min_label": "Min (s):",
        "max_label": "Max (s):",
        "threshold_label": "Threshold:",
        "smooth_label": "Làm mượt:",
        "smooth_seconds_unit": "giây",
        "smooth_trim_tail": "Cắt đuôi (Video trước)",
        "smooth_trim_head": "Cắt đầu (Video sau)",

        # ── Section 4: Controls ──
        "section_control": "ĐIỀU KHIỂN",
        "btn_start": "▶  Bắt đầu",
        "btn_cancel": "Hủy",
        "btn_open_output": "Mở thư mục kết quả",
        "progress_label": "Tiến trình:",

        # ── Section 5: Log ──
        "section_log": "⚙  Nhật ký xử lý",
        "btn_export_log": "💾  Xuất log",
        "btn_clear_log": "🗑  Xóa log",

        # ── Dialogs & Errors ──
        "msg_running": "Tool đang xử lý video.",
        "msg_running_title": "Đang chạy",
        "msg_complete_title": "Hoàn thành",
        "msg_error_title": "Lỗi",
        "msg_error_input_title": "Lỗi nhập liệu",
        "msg_cancelled_title": "Đã hủy",
        "msg_cancelled": "Đã hủy xử lý.",
        "msg_no_output_dir": "Chưa có thư mục kết quả để mở.",
        "msg_open_dir_error": "Không mở được thư mục kết quả: {error}",
        "msg_cancel_requested": "Đã yêu cầu hủy xử lý.",
        "msg_skip_cleanup": "Bỏ qua xóa dữ liệu tạm vì đường dẫn kết quả không hợp lệ.",
        "msg_cleanup_done": "Đã xóa dữ liệu tạm của tiến trình bị hủy.",
        "msg_no_videos": "Chưa thêm video nào vào danh sách.",
        "msg_file_not_found": "File không tồn tại: {name}",
        "msg_no_output_dir_selected": "Bạn chưa chọn thư mục xuất file.",
        "msg_folder_count_int": "Số lượng folder phải là số nguyên.",
        "msg_folder_count_min": "Số lượng folder phải lớn hơn hoặc bằng 1.",
        "msg_duration_number": "Thời lượng mỗi cảnh phải là số.",
        "msg_duration_positive": "Thời lượng mỗi cảnh phải lớn hơn 0.",
        "msg_scene_params_number": "Min, Max và Scene threshold phải là số.",
        "msg_image_threshold_number": "Scene threshold phải là số.",
        "msg_min_positive": "Min (s) phải lớn hơn 0.",
        "msg_max_gt_min": "Max (s) phải lớn hơn Min (s).",
        "msg_threshold_range": "Scene threshold phải lớn hơn 0 và nhỏ hơn 1.",
        "msg_smooth_number": "Số giây làm mượt phải là số.",
        "msg_smooth_positive": "Số giây làm mượt phải lớn hơn hoặc bằng 0.",
        "msg_smooth_mode_invalid": "Kiểu làm mượt không hợp lệ.",
        "msg_cut_type_invalid": "Kiểu cắt không hợp lệ.",
        "msg_no_folder_found": "Không có file video nào trong thư mục đã chọn.",
        "msg_no_folder_found_title": "Không tìm thấy",
        "msg_choose_video_title": "Chọn video",
        "msg_choose_folder_title": "Chọn thư mục chứa video",
        "msg_choose_output_title": "Chọn thư mục xuất file",

        # ── Log Messages ──
        "log_start": "Bắt đầu xử lý video.",
        "log_parallel_workers": "Tự tối ưu pipeline: xử lý tối đa {count} video song song.",
        "log_hardware_profile": "Bộ mã hóa: {encoder}; CPU logic: {cpus}; RAM: {ram:.1f} GB; GPU: {gpu}; worker: {workers}.",
        "log_parallel_duplicate_names": "Phát hiện tên video trùng nhau; chuyển về xử lý tuần tự để bảo vệ file đầu ra.",
        "log_video_elapsed": "Hoàn tất {name} trong {seconds:.2f} giây.",
        "log_batch_elapsed": "Tổng thời gian xử lý batch: {seconds:.2f} giây.",
        "log_input": "Video đầu vào: {path}",
        "log_output_dir": "Thư mục xuất: {path}",
        "log_cut_type": "Kiểu cắt: {type}",
        "log_folder_count": "Output folder count: {count}",
        "log_remove_audio": "Xóa audio: {status}",
        "log_duration": "Thời lượng video: {duration:.2f} giây",
        "log_invalid_duration": "Video không có thời lượng hợp lệ.",
        "log_segment_duration": "Thời lượng mỗi cảnh: {seconds} giây",
        "log_fixed_copy": "Chế độ cố định dùng -c copy để xử lý nhanh.",
        "log_scene_encode": "Chế độ chuyển cảnh encode lại để ép keyframe và cắt chính xác hơn.",
        "log_image_mode": "Chế độ ảnh thông minh: chọn frame ổn định sau chuyển cảnh.",
        "log_scanning_scene_scores": "Đang quét chuyển cảnh và độ ổn định khung hình...",
        "log_snapshot_count": "Số ảnh dự kiến xuất: {count}",
        "log_export_image": "Xuất ảnh {number:03d} tại {time:.3f}s -> {folder}/{file}",
        "log_missing_image_threshold": "Thiếu scene threshold để xuất ảnh.",
        "log_min_seconds": "Min seconds: {val}",
        "log_max_seconds": "Max seconds: {val}",
        "log_threshold": "Scene threshold: {val}",
        "log_smooth": "Làm mượt: {status}",
        "log_scanning_scenes": "Đang quét điểm chuyển cảnh...",
        "log_scene_count": "Số điểm chuyển cảnh phát hiện: {count}",
        "log_split_count": "Số split_times tạo ra: {count}",
        "log_smooth_seconds": "smooth_seconds: {val}",
        "log_smooth_mode": "Kiểu làm mượt: {mode}",
        "log_boundary_count": "Số boundary_times: {count}",
        "log_boundary_example": "Mốc {split:.3f}s -> {left:.3f}s, {right:.3f}s",
        "log_no_boundary": "Không có boundary_times hợp lệ, xử lý như không làm mượt.",
        "log_expected_segments": "Tổng số segment tạm dự kiến: {count}",
        "log_kept_segments": "Tổng số segment giữ dự kiến: {count}",
        "log_cutting": "Đang cắt video bằng một lệnh FFmpeg segment...",
        "log_segments_done": "FFmpeg đã tạo xong các segment tạm.",
        "log_actual_segments": "Số segment tạm thực tế: {count}",
        "log_segment_mismatch": "Bố cục segment tạm không khớp ({actual}/{expected}); chuyển sang cắt an toàn theo từng khoảng.",
        "log_segment_fallback": "Đang cắt lại {count} cảnh bằng mốc thời gian tuyệt đối để tránh lệch/xé cảnh.",
        "log_drop_smooth": "Bỏ segment làm mượt tạm {index}: {name}",
        "log_export_scene": "Xuất cảnh {number:03d} -> {folder}/{file}",
        "log_complete": "HOÀN THÀNH.",
        "log_kept_count": "Số segment giữ: {count}",
        "log_dropped_count": "Số segment bỏ do làm mượt: {count}",
        "log_exported_count": "Số file đã xuất: {count}",
        "log_result_folder": "Folder kết quả: {path}",
        "log_done_msg": "Đã cắt xong video.\n\nKết quả nằm tại:\n{path}",
        "log_cancelled": "Đã hủy xử lý.",
        "log_ffmpeg_error": "FFmpeg bị lỗi:\n{error}",
        "log_missing_fixed_duration": "Thiếu thời lượng cắt cố định.",
        "log_missing_scene_params": "Thiếu thông số cắt theo chuyển cảnh.",
        "log_no_segments": "Video không có segment hợp lệ.",
        "log_no_temp_files": "FFmpeg đã chạy xong nhưng không tạo file cảnh nào.",
        "log_batch_progress": "[{current}/{total}] Đang xử lý: {name}...",
        "log_batch_complete": "Đã xử lý xong tất cả {total} video.",
        "log_batch_done_msg": "Đã cắt xong {total} video.\n\nKết quả nằm tại:\n{path}",
        "log_batch_separate_done": "Đã cắt xong {total} video.\n\nKết quả nằm tại thư mục:\n{path}",
        "log_merged_output": "Thư mục gộp chung: {path}",
        "log_video_error": "Lỗi khi xử lý {name}: {error}",
    },
    "en": {
        # ── Title & Header ──
        "app_title": "Video Cutter",
        "app_subtitle": "Created by Lực Nguyễn",
        "tooltip_to_light": "Switch to light mode",
        "tooltip_to_dark": "Switch to dark mode",

        # ── Section 1: Input ──
        "section_input": "Input",
        "btn_choose_files": "Choose Files",
        "btn_choose_folder": "Choose Folder",
        "btn_clear_all": "Clear All",
        "file_count": "Total: {count} files",
        "drop_placeholder": "Drag & drop video files or folders into this table to load",
        "col_stt": "#",
        "col_filename": "File Name",
        "col_duration": "Duration",
        "col_size": "Size",
        "scanning": "Scanning...",

        # ── Section 2: Output ──
        "section_output": "Output",
        "output_dir_label": "Output Dir:",
        "output_dir_placeholder": "Not selected...",
        "btn_choose": "Browse",
        "project_name_label": "Project Name:",
        "project_name_placeholder": "Project name...",
        "output_mode_label": "Output Mode:",
        "output_mode_split": "Split Folder",
        "output_mode_merge_default": "Merge Folder (Default)",
        "output_mode_merge_rename": "Merge Folder (Rename)",
        "output_folder_label": "Folder Count:",
        "folder_unit": "folders",
        "remove_audio_label": "Remove Audio:",

        # ── Section 3: Settings ──
        "section_settings": "Settings",
        "cut_type_label": "Cut Type:",
        "cut_fixed": "Fixed Duration",
        "cut_by_scene": "Scene Detection",
        "cut_to_images": "Scene Snapshots",
        "duration_label": "Duration (s):",
        "scene_params_label": "Parameters:",
        "min_label": "Min (s):",
        "max_label": "Max (s):",
        "threshold_label": "Threshold:",
        "smooth_label": "Smoothing:",
        "smooth_seconds_unit": "sec",
        "smooth_trim_tail": "Trim Tail (Previous)",
        "smooth_trim_head": "Trim Head (Next)",

        # ── Section 4: Controls ──
        "section_control": "CONTROLS",
        "btn_start": "▶  Start",
        "btn_cancel": "Cancel",
        "btn_open_output": "Open Output Folder",
        "progress_label": "Progress:",

        # ── Section 5: Log ──
        "section_log": "⚙  Process Log",
        "btn_export_log": "💾  Export log",
        "btn_clear_log": "🗑  Clear log",

        # ── Dialogs & Errors ──
        "msg_running": "Tool is currently processing video.",
        "msg_running_title": "Running",
        "msg_complete_title": "Complete",
        "msg_error_title": "Error",
        "msg_error_input_title": "Input Error",
        "msg_cancelled_title": "Cancelled",
        "msg_cancelled": "Processing cancelled.",
        "msg_no_output_dir": "No output folder to open.",
        "msg_open_dir_error": "Cannot open output folder: {error}",
        "msg_cancel_requested": "Cancel requested.",
        "msg_skip_cleanup": "Skipping temp cleanup due to invalid output path.",
        "msg_cleanup_done": "Cleaned up temp data from cancelled process.",
        "msg_no_videos": "No videos added to the list.",
        "msg_file_not_found": "File not found: {name}",
        "msg_no_output_dir_selected": "Please select an output directory.",
        "msg_folder_count_int": "Folder count must be an integer.",
        "msg_folder_count_min": "Folder count must be at least 1.",
        "msg_duration_number": "Scene duration must be a number.",
        "msg_duration_positive": "Scene duration must be greater than 0.",
        "msg_scene_params_number": "Min, Max and Scene threshold must be numbers.",
        "msg_image_threshold_number": "Scene threshold must be a number.",
        "msg_min_positive": "Min (s) must be greater than 0.",
        "msg_max_gt_min": "Max (s) must be greater than Min (s).",
        "msg_threshold_range": "Scene threshold must be between 0 and 1.",
        "msg_smooth_number": "Smooth seconds must be a number.",
        "msg_smooth_positive": "Smooth seconds must be >= 0.",
        "msg_smooth_mode_invalid": "Invalid smoothing mode.",
        "msg_cut_type_invalid": "Invalid cut type.",
        "msg_no_folder_found": "No video files found in the selected folder.",
        "msg_no_folder_found_title": "Not Found",
        "msg_choose_video_title": "Choose Videos",
        "msg_choose_folder_title": "Choose folder with videos",
        "msg_choose_output_title": "Choose output folder",

        # ── Log Messages ──
        "log_start": "Starting video processing.",
        "log_parallel_workers": "Auto-tuned pipeline: processing up to {count} videos in parallel.",
        "log_hardware_profile": "Encoder: {encoder}; logical CPUs: {cpus}; RAM: {ram:.1f} GB; GPU: {gpu}; workers: {workers}.",
        "log_parallel_duplicate_names": "Duplicate video names detected; using serial processing to protect output files.",
        "log_video_elapsed": "Finished {name} in {seconds:.2f} seconds.",
        "log_batch_elapsed": "Total batch processing time: {seconds:.2f} seconds.",
        "log_input": "Input video: {path}",
        "log_output_dir": "Output dir: {path}",
        "log_cut_type": "Cut type: {type}",
        "log_folder_count": "Output folder count: {count}",
        "log_remove_audio": "Remove audio: {status}",
        "log_duration": "Video duration: {duration:.2f} seconds",
        "log_invalid_duration": "Video has no valid duration.",
        "log_segment_duration": "Segment duration: {seconds} seconds",
        "log_fixed_copy": "Fixed mode uses -c copy for fast processing.",
        "log_scene_encode": "Scene mode re-encodes to force keyframes for precise cuts.",
        "log_image_mode": "Smart image mode: selects a stable frame after each scene change.",
        "log_scanning_scene_scores": "Scanning scene changes and frame stability...",
        "log_snapshot_count": "Expected snapshots: {count}",
        "log_export_image": "Export image {number:03d} at {time:.3f}s -> {folder}/{file}",
        "log_missing_image_threshold": "Missing scene threshold for image export.",
        "log_min_seconds": "Min seconds: {val}",
        "log_max_seconds": "Max seconds: {val}",
        "log_threshold": "Scene threshold: {val}",
        "log_smooth": "Smoothing: {status}",
        "log_scanning_scenes": "Scanning scene changes...",
        "log_scene_count": "Scene changes detected: {count}",
        "log_split_count": "Split times generated: {count}",
        "log_smooth_seconds": "smooth_seconds: {val}",
        "log_smooth_mode": "Smooth mode: {mode}",
        "log_boundary_count": "Boundary times: {count}",
        "log_boundary_example": "Point {split:.3f}s -> {left:.3f}s, {right:.3f}s",
        "log_no_boundary": "No valid boundary times, processing without smoothing.",
        "log_expected_segments": "Expected temp segments: {count}",
        "log_kept_segments": "Expected kept segments: {count}",
        "log_cutting": "Cutting video with FFmpeg segment...",
        "log_segments_done": "FFmpeg finished creating temp segments.",
        "log_actual_segments": "Actual temp segments: {count}",
        "log_segment_mismatch": "Temp segment layout differs ({actual}/{expected}); switching to safe interval extraction.",
        "log_segment_fallback": "Re-cutting {count} scenes from absolute intervals to prevent shifted/torn scenes.",
        "log_drop_smooth": "Dropping smooth segment {index}: {name}",
        "log_export_scene": "Export scene {number:03d} -> {folder}/{file}",
        "log_complete": "COMPLETE.",
        "log_kept_count": "Segments kept: {count}",
        "log_dropped_count": "Segments dropped (smoothing): {count}",
        "log_exported_count": "Files exported: {count}",
        "log_result_folder": "Result folder: {path}",
        "log_done_msg": "Video cutting complete.\n\nResults at:\n{path}",
        "log_cancelled": "Processing cancelled.",
        "log_ffmpeg_error": "FFmpeg error:\n{error}",
        "log_missing_fixed_duration": "Missing fixed cut duration.",
        "log_missing_scene_params": "Missing scene cut parameters.",
        "log_no_segments": "Video has no valid segments.",
        "log_no_temp_files": "FFmpeg finished but created no scene files.",
        "log_batch_progress": "[{current}/{total}] Processing: {name}...",
        "log_batch_complete": "Finished processing all {total} videos.",
        "log_batch_done_msg": "Finished cutting {total} videos.\n\nResults at:\n{path}",
        "log_batch_separate_done": "Finished cutting {total} videos.\n\nResults at folder:\n{path}",
        "log_merged_output": "Merged output folder: {path}",
        "log_video_error": "Error processing {name}: {error}",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITY CLASSES & FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


class ProcessingCancelled(Exception):
    pass


def safe_filename(name: str) -> str:
    import re
    from pathlib import Path
    
    # 1. Lấy phần tên gốc của tệp/thư mục
    name = Path(name).stem
    
    # 2. CHỈ loại bỏ các ký tự thực sự bị cấm bởi hệ điều hành Windows/Linux
    # Các ký tự cấm gồm: \ / : * ? " < > | %
    name = re.sub(r'[\\/:*?"<>|%]', "", name)
    
    # 3. Chuẩn hóa khoảng trắng (giữ nguyên khoảng trắng để hiển thị đẹp, không ép thành dấu gạch dưới)
    name = name.strip()
    
    # Fallback nếu chuỗi trống
    if not name:
        name = "Folder_Output"
        
    return name


def resource_path(relative_path: str) -> Path:
    """Resolve a resource path for Python and PyInstaller onefile builds."""
    if getattr(sys, "_MEIPASS", None):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path


def find_ffmpeg_tools():
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        bundled_ffmpeg = exe_dir / "ffmpeg.exe"
        bundled_ffprobe = exe_dir / "ffprobe.exe"
        if bundled_ffmpeg.exists() and bundled_ffprobe.exists():
            return str(bundled_ffmpeg), str(bundled_ffprobe)
            
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError(
            "Cannot find ffmpeg or ffprobe. "
            "Please install FFmpeg and ensure it is on the system PATH."
        )

    return ffmpeg_path, ffprobe_path


def get_subprocess_creationflags():
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW

    return 0


def detect_hardware_graphics(ffmpeg_path: str) -> str:
    """Compatibility wrapper that verifies a real encoder, not only its name."""
    return build_hardware_profile(ffmpeg_path, calibrate=False).hardware_type


def parse_ffmpeg_time(value: str) -> float | None:
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


def run_ffmpeg_segment(
    command: list[str],
    duration: float,
    progress_callback,
    cancel_event: threading.Event | None = None,
    process_callback=None,
):
    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingCancelled("Processing cancelled.")

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=get_subprocess_creationflags(),
    )

    if process_callback is not None:
        process_callback(process)

    stderr_lines = []

    def collect_stderr():
        if process.stderr is None:
            return

        for line in process.stderr:
            stderr_lines.append(line)

    stderr_thread = threading.Thread(target=collect_stderr, daemon=True)
    stderr_thread.start()

    try:
        cancel_requested = False

        if process.stdout is not None:
            for raw_line in process.stdout:
                if cancel_event is not None and cancel_event.is_set():
                    cancel_requested = True
                    if process.poll() is None:
                        process.terminate()
                    break

                line = raw_line.strip()
                elapsed = None

                if line.startswith("out_time_ms="):
                    try:
                        elapsed = int(line.partition("=")[2]) / 1_000_000
                    except ValueError:
                        elapsed = None

                elif line.startswith("out_time="):
                    elapsed = parse_ffmpeg_time(line.partition("=")[2])

                if elapsed is not None and duration > 0:
                    progress_callback(max(0, min(elapsed / duration, 1)))

        if cancel_event is not None and cancel_event.is_set():
            cancel_requested = True

        if cancel_requested and process.poll() is None:
            process.terminate()

        try:
            return_code = process.wait(timeout=5 if cancel_requested else None)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait()

        stderr_thread.join(timeout=2)

    except Exception:
        if process.poll() is None:
            process.kill()
        stderr_thread.join(timeout=2)
        raise

    finally:
        if process_callback is not None:
            process_callback(None)

    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingCancelled("Processing cancelled.")

    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code,
            command,
            stderr="".join(stderr_lines),
        )


def get_video_properties(video_path: Path, ffprobe_path: str) -> dict:
    """Lấy duration, width, height, fps, pix_fmt, color_transfer trong MỘT lần gọi ffprobe."""
    import json as _json
    command = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,pix_fmt,color_transfer:format=duration",
        "-of", "json",
        str(video_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        creationflags=get_subprocess_creationflags(),
    )

    data = _json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    fmt = data.get("format", {})

    # Parse FPS từ r_frame_rate dạng "30000/1001"
    fps = 0.0
    r_fps = stream.get("r_frame_rate", "0/1")
    try:
        num, den = r_fps.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    return {
        "duration": float(fmt.get("duration", 0)),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "fps": round(fps, 3),
        "pix_fmt": stream.get("pix_fmt", ""),
        "color_transfer": stream.get("color_transfer", ""),
    }


def get_video_duration(video_path: Path, ffprobe_path: str) -> float:
    """Wrapper tương thích ngược — dùng get_video_properties bên trong."""
    props = get_video_properties(video_path, ffprobe_path)
    return props["duration"]


def normalize_split_times(split_times: list[float], duration: float) -> list[float]:
    normalized = {
        round(split_time, 3)
        for split_time in split_times
        if 0 < split_time < duration
    }

    return sorted(normalized)


def build_segment_intervals(
    segment_times: list[float],
    duration: float,
) -> list[tuple[float, float]]:
    """Convert ordered cut points into absolute [start, end] intervals."""
    points = [0.0, *normalize_split_times(segment_times, duration), duration]
    return [
        (round(start, 3), round(end, 3))
        for start, end in zip(points, points[1:])
        if end - start >= MIN_BOUNDARY_GAP
    ]


def build_kept_intervals(
    boundary_times: list[float],
    duration: float,
) -> list[tuple[float, float]]:
    """Build the clips retained around symmetric smooth-removal boundaries."""
    boundaries = normalize_split_times(boundary_times, duration)
    if len(boundaries) % 2:
        raise ValueError("Smooth boundary list must contain left/right pairs.")

    intervals = []
    start = 0.0
    for index in range(0, len(boundaries), 2):
        left, right = boundaries[index], boundaries[index + 1]
        if left <= start or right <= left:
            raise ValueError("Smooth boundaries overlap or are out of order.")
        intervals.append((round(start, 3), round(left, 3)))
        start = right
    if duration - start >= MIN_BOUNDARY_GAP:
        intervals.append((round(start, 3), round(duration, 3)))
    return intervals


def _stabilize_boundary_records(
    records: list[tuple[float, float, float]],
    duration: float,
    min_output_seconds: float,
    max_output_seconds: float,
) -> list[tuple[float, float, float]]:
    """Drop a nearby smooth boundary whenever it would create a tiny clip."""
    stable = list(records)
    if min_output_seconds <= 0 or duration < min_output_seconds:
        return stable

    def intervals_for(items):
        intervals = []
        start = 0.0
        for _split, left, right in items:
            if left > start:
                intervals.append((start, left))
            start = right
        if duration > start:
            intervals.append((start, duration))
        return intervals

    while stable:
        intervals = intervals_for(stable)
        short_indices = [
            index
            for index, (start, end) in enumerate(intervals)
            if end - start < min_output_seconds - 0.001
        ]
        if not short_indices:
            break

        short_index = min(
            short_indices,
            key=lambda index: intervals[index][1] - intervals[index][0],
        )
        removable = []
        if short_index > 0:
            removable.append(short_index - 1)
        if short_index < len(stable):
            removable.append(short_index)
        if not removable:
            break

        def removal_score(remove_index):
            candidate = stable[:remove_index] + stable[remove_index + 1:]
            candidate_intervals = intervals_for(candidate)
            durations = [end - start for start, end in candidate_intervals]
            remaining_short = sum(
                value < min_output_seconds - 0.001 for value in durations
            )
            overshoot = sum(
                max(0.0, value - max_output_seconds)
                for value in durations
            ) if max_output_seconds > 0 else 0.0
            return remaining_short, round(overshoot, 3), max(durations, default=duration)

        remove_index = min(removable, key=removal_score)
        stable.pop(remove_index)

    return stable


def read_segment_timeline(segment_list_path: Path) -> list[tuple[float, float]]:
    """Read FFmpeg's segment CSV without probing hundreds of files individually."""
    intervals = []
    try:
        with segment_list_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) < 3:
                    continue
                start, end = float(row[-2]), float(row[-1])
                intervals.append((start, end))
    except (OSError, ValueError):
        return []
    return intervals


def segment_layout_matches(
    actual_intervals: list[tuple[float, float]],
    expected_intervals: list[tuple[float, float]],
    tolerance: float = 0.20,
) -> bool:
    """Detect a missing/merged timestamp boundary before parity can shift."""
    if len(actual_intervals) != len(expected_intervals):
        return False
    for actual, expected in zip(actual_intervals, expected_intervals):
        actual_duration = actual[1] - actual[0]
        expected_duration = expected[1] - expected[0]
        if actual_duration <= 0 or abs(actual_duration - expected_duration) > tolerance:
            return False
    return True


def detect_scene_changes(
    video_path: Path,
    ffmpeg_path: str,
    threshold: float,
    cancel_event: threading.Event | None = None,
    process_callback=None,
    hardware_type: str = "cpu"
) -> list[float]:
    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingCancelled("Processing cancelled.")

    # Quét cảnh bằng CPU thuần — triệt tiêu độ trễ VRAM-to-RAM
    command = [
        ffmpeg_path,
        "-threads", "auto",
        "-hide_banner",
        "-i", str(video_path),
        "-filter:v",
        f"fps=10,scale=256:-1,select='gt(scene,{threshold})',showinfo",
        "-an", "-sn", "-dn",
        "-f", "null",
        "-",
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=get_subprocess_creationflags(),
    )

    if process_callback is not None:
        process_callback(process)

    try:
        _, stderr = process.communicate()
    finally:
        if process_callback is not None:
            process_callback(None)

    if cancel_event is not None and cancel_event.is_set():
        if process.poll() is None:
            process.terminate()
        raise ProcessingCancelled("Processing cancelled.")

    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode,
            command,
            stderr=stderr,
        )

    scene_times = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", stderr):
        scene_times.append(float(match.group(1)))

    return sorted(set(scene_times))


def detect_scene_scores(
    video_path: Path,
    ffmpeg_path: str,
    cancel_event: threading.Event | None = None,
    process_callback=None,
) -> list[tuple[float, float]]:
    """Return low-resolution scene scores for every 10 fps sample in one scan."""
    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingCancelled("Processing cancelled.")

    command = [
        ffmpeg_path,
        "-threads", "auto",
        "-hide_banner",
        "-i", str(video_path),
        "-filter:v",
        "fps=10,scale=256:-1,select='gte(scene,0)',metadata=print:key=lavfi.scene_score",
        "-an", "-sn", "-dn",
        "-f", "null",
        "-",
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=get_subprocess_creationflags(),
    )

    if process_callback is not None:
        process_callback(process)

    try:
        _, stderr = process.communicate()
    finally:
        if process_callback is not None:
            process_callback(None)

    if cancel_event is not None and cancel_event.is_set():
        if process.poll() is None:
            process.terminate()
        raise ProcessingCancelled("Processing cancelled.")

    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode,
            command,
            stderr=stderr,
        )

    scene_scores = []
    pending_time = None
    for line in stderr.splitlines():
        time_match = re.search(r"pts_time:([0-9]+(?:\.[0-9]+)?)", line)
        if time_match:
            pending_time = float(time_match.group(1))

        score_match = re.search(r"lavfi\.scene_score=([0-9]+(?:\.[0-9]+)?)", line)
        if score_match and pending_time is not None:
            scene_scores.append((pending_time, float(score_match.group(1))))
            pending_time = None

    return scene_scores


def build_smart_snapshot_times(
    scene_scores: list[tuple[float, float]],
    duration: float,
    threshold: float,
) -> list[float]:
    """Choose one stable snapshot per scene without crossing into the next scene."""
    if duration <= 0:
        return []

    scene_starts = [0.0]
    scene_starts.extend(
        time
        for time, score in scene_scores
        if score > threshold and 0 < time < duration
    )
    scene_starts = sorted({round(time, 3) for time in scene_starts})
    stable_score_limit = min(0.08, threshold * 0.5)
    snapshot_times = []

    for index, scene_start in enumerate(scene_starts):
        next_scene = (
            scene_starts[index + 1]
            if index + 1 < len(scene_starts)
            else duration
        )
        latest_safe_time = min(
            scene_start + SMART_SNAPSHOT_MAX_SETTLE,
            next_scene - SMART_SNAPSHOT_SAFETY_GAP,
            duration - SMART_SNAPSHOT_SAFETY_GAP,
        )
        earliest_settle_time = min(
            scene_start + SMART_SNAPSHOT_MIN_SETTLE,
            latest_safe_time,
        )
        stable_samples = 0
        selected_time = None

        for sample_time, score in scene_scores:
            if sample_time < earliest_settle_time:
                continue
            if sample_time > latest_safe_time:
                break

            if score <= stable_score_limit:
                stable_samples += 1
                if stable_samples >= SMART_SNAPSHOT_STABLE_SAMPLES:
                    selected_time = sample_time
                    break
            else:
                stable_samples = 0

        if selected_time is None:
            selected_time = latest_safe_time

        snapshot_times.append(round(max(scene_start, selected_time), 3))

    return snapshot_times


def format_snapshot_time(snapshot_time: float) -> str:
    hours = int(snapshot_time // 3600)
    minutes = int((snapshot_time % 3600) // 60)
    seconds = snapshot_time % 60
    return f"{hours:02d}-{minutes:02d}-{seconds:06.3f}"


def build_duration_split_times(duration: float, segment_seconds: float) -> list[float]:
    split_times = []
    index = 1

    while True:
        split_time = segment_seconds * index

        if split_time >= duration:
            break

        split_times.append(split_time)
        index += 1

    return normalize_split_times(split_times, duration)


def build_scene_split_times(
    scene_times: list[float],
    duration: float,
    min_seconds: float,
    max_seconds: float,
    smooth_seconds: float = 0.0,
) -> list[float]:
    """
    Chọn các điểm cắt sao cho FILE ĐẦU RA (sau smooth) nằm trong [min_seconds, max_seconds].

    Khi smooth bật, mỗi phân đoạn nội bộ mất 2*smooth_seconds (smooth ở cả 2 đầu).
    Phân đoạn đầu tiên chỉ mất smooth ở cuối, phân đoạn cuối chỉ mất smooth ở đầu.
    """
    scene_times = normalize_split_times(scene_times, duration)
    split_times = []
    start_time = 0.0

    # Khoảng cách thô (raw) giữa 2 split để output đạt đúng min/max.
    # Phân đoạn nội bộ bị trừ 2*smooth ở 2 đầu.
    # Phân đoạn đầu/cuối chỉ bị trừ 1*smooth.
    smooth_compensation = 2 * smooth_seconds
    raw_min = min_seconds + smooth_compensation
    raw_max = max_seconds + smooth_compensation

    # Phân đoạn đầu tiên chỉ mất smooth ở cuối (1*smooth thay vì 2*smooth),
    # nên cần raw ngắn hơn smooth_seconds so với nội bộ.
    first_raw_min = min_seconds + smooth_seconds
    first_raw_max = max_seconds + smooth_seconds

    is_first_segment = True

    while True:
        remaining = duration - start_time

        if is_first_segment:
            cur_min = first_raw_min
            cur_max = first_raw_max
        else:
            cur_min = raw_min
            cur_max = raw_max

        # Nếu phần còn lại đủ ngắn để là phân đoạn cuối hợp lệ, dừng.
        # Phân đoạn cuối chỉ mất smooth ở đầu (hoặc 0 nếu cũng là phân đoạn đầu).
        last_smooth_loss = smooth_seconds if split_times else 0.0
        last_output = remaining - last_smooth_loss
        if last_output <= max_seconds:
            break

        # Split phải cách cuối video đủ xa để boundary tồn tại:
        # split + smooth_seconds < duration → split < duration - smooth_seconds
        min_cut_time = start_time + cur_min
        max_cut_time = start_time + cur_max
        boundary_limit = duration - smooth_seconds - MIN_BOUNDARY_GAP if smooth_seconds > 0 else duration
        effective_max = min(max_cut_time, boundary_limit)

        if effective_max < min_cut_time:
            # Không thể đặt split hợp lệ → dừng, gộp phần còn lại
            break

        candidates = [
            scene_time
            for scene_time in scene_times
            if min_cut_time <= scene_time <= effective_max
        ]

        if candidates:
            split_time = candidates[-1]
        else:
            split_time = effective_max

        if split_time <= start_time:
            break

        # Kiểm tra: nếu cắt ở đây, phân đoạn cuối có bị quá ngắn không?
        tail = duration - split_time
        tail_output = tail - smooth_seconds  # phân đoạn cuối mất smooth ở đầu
        if tail_output < min_seconds and tail > 0:
            # Gộp phần dư vào phân đoạn hiện tại nếu không vượt max
            merged_raw = remaining
            merged_output = merged_raw - last_smooth_loss
            if merged_output <= max_seconds:
                # Gộp OK: không thêm split, dừng vòng lặp
                break

            # Gộp sẽ vượt max → tìm split sớm hơn để tail đủ dài.
            # Tail cần ít nhất min_seconds + smooth_seconds (raw)
            # → split tối đa = duration - min_seconds - smooth_seconds
            ideal_max_split = duration - min_seconds - smooth_seconds
            if ideal_max_split >= min_cut_time:
                ideal_max_split = min(ideal_max_split, effective_max)
                earlier_candidates = [
                    st for st in scene_times
                    if min_cut_time <= st <= ideal_max_split
                ]
                if earlier_candidates:
                    split_time = earlier_candidates[-1]
                else:
                    split_time = ideal_max_split
            # Nếu không thể tìm được split tốt hơn, giữ nguyên split ban đầu

        split_times.append(split_time)
        start_time = split_time
        is_first_segment = False

    normalized_splits = normalize_split_times(split_times, duration)
    nominal_records = [
        (
            split_time,
            round(split_time - smooth_seconds, 3),
            round(split_time + smooth_seconds, 3),
        )
        for split_time in normalized_splits
        if split_time - smooth_seconds > 0
        and split_time + smooth_seconds < duration
    ]
    stable_records = _stabilize_boundary_records(
        nominal_records,
        duration,
        min_seconds,
        max_seconds,
    )
    return [record[0] for record in stable_records]


def build_smooth_boundary_times(
    split_times: list[float],
    scene_times: list[float],
    duration: float,
    smooth_seconds: float,
    min_output_seconds: float = 0.0,
    short_fragment_threshold: float = SHORT_FRAGMENT_THRESHOLD,
    max_fragment_extension: float = MAX_SHORT_FRAGMENT_EXTENSION,
) -> tuple[list[float], list[tuple[float, float, float]]]:
    """
    Symmetric smooth: cut t seconds from BOTH sides of each scene boundary.
    The boundary left/right edges can be extended up to the nearest scene change
    to eliminate extremely short visual fragments near the smooth boundary region.

    min_output_seconds: thời lượng tối thiểu của file đầu ra.
    Short-shot cleanup KHÔNG ĐƯỢC làm một kept segment ngắn hơn giá trị này.
    Nếu vi phạm, fallback về nominal boundary.

    This function does not modify split_times.
    """
    if smooth_seconds <= 0:
        return [], []

    from bisect import bisect_left, bisect_right

    normalized_splits = normalize_split_times(split_times, duration)
    normalized_scenes = normalize_split_times(scene_times, duration)

    boundary_times = []
    examples = []
    last_boundary_right = 0.0

    for split_idx, split_time in enumerate(normalized_splits):
        nominal_left = round(split_time - smooth_seconds, 3)
        nominal_right = round(split_time + smooth_seconds, 3)

        adjusted_left = nominal_left
        adjusted_right = nominal_right

        # 4.1. Kiểm tra phía trái
        while True:
            idx = bisect_left(normalized_scenes, adjusted_left)
            if idx > 0:
                prev_scene = normalized_scenes[idx - 1]
                dist = adjusted_left - prev_scene
                ext = nominal_left - prev_scene
                if dist <= short_fragment_threshold and ext <= max_fragment_extension:
                    if prev_scene > 0:
                        adjusted_left = prev_scene
                    else:
                        break
                else:
                    break
            else:
                break

        # 4.2. Kiểm tra phía phải
        while True:
            idx = bisect_right(normalized_scenes, adjusted_right)
            if idx < len(normalized_scenes):
                next_scene = normalized_scenes[idx]
                dist = next_scene - adjusted_right
                ext = next_scene - nominal_right
                if dist <= short_fragment_threshold and ext <= max_fragment_extension:
                    if next_scene < duration:
                        adjusted_right = next_scene
                    else:
                        break
                else:
                    break
            else:
                break

        adjusted_left = round(adjusted_left, 3)
        adjusted_right = round(adjusted_right, 3)

        # ── Bảo vệ min_output_seconds ──
        # Kept segment phía TRƯỚC boundary này: [last_boundary_right .. left]
        # Nếu adjusted_left quá gần last_boundary_right, kept segment sẽ ngắn hơn min.
        kept_before_adjusted = round(adjusted_left - last_boundary_right, 3)
        kept_before_nominal = round(nominal_left - last_boundary_right, 3)

        # Kept segment phía SAU boundary này: [right .. next_left_or_duration]
        # next_left: nominal_left của split tiếp theo, hoặc duration nếu là split cuối.
        if split_idx + 1 < len(normalized_splits):
            next_nominal_left = round(normalized_splits[split_idx + 1] - smooth_seconds, 3)
        else:
            next_nominal_left = duration
        kept_after_adjusted = round(next_nominal_left - adjusted_right, 3)
        kept_after_nominal = round(next_nominal_left - nominal_right, 3)

        # Nếu adjusted boundary vi phạm min_output ở BẤT KỲ phía nào → fallback.
        use_adjusted = True
        if min_output_seconds > 0:
            if kept_before_adjusted < min_output_seconds:
                use_adjusted = False
            if kept_after_adjusted < min_output_seconds:
                use_adjusted = False

        adjusted_valid = (
            use_adjusted and
            adjusted_left > 0 and
            adjusted_right < duration and
            adjusted_right > adjusted_left and
            round(adjusted_right - adjusted_left, 3) >= MIN_BOUNDARY_GAP and
            round(adjusted_left - last_boundary_right, 3) >= MIN_BOUNDARY_GAP
        )

        if adjusted_valid:
            left = adjusted_left
            right = adjusted_right
        else:
            # Fallback to nominal boundary
            nominal_valid = (
                nominal_left > 0 and
                nominal_right < duration and
                nominal_right > nominal_left and
                round(nominal_right - nominal_left, 3) >= MIN_BOUNDARY_GAP and
                round(nominal_left - last_boundary_right, 3) >= MIN_BOUNDARY_GAP
            )
            # Kiểm tra min_output với nominal ở cả hai phía, kể cả đuôi video.
            if min_output_seconds > 0 and nominal_valid:
                if kept_before_nominal < min_output_seconds:
                    nominal_valid = False
                if kept_after_nominal < min_output_seconds:
                    nominal_valid = False

            if nominal_valid:
                left = nominal_left
                right = nominal_right
            else:
                continue

        boundary_times.extend([left, right])
        examples.append((split_time, left, right))
        last_boundary_right = right

    stable_examples = _stabilize_boundary_records(
        examples,
        duration,
        min_output_seconds,
        0.0,
    )
    stable_boundaries = [
        value
        for _split, left, right in stable_examples
        for value in (left, right)
    ]
    return normalize_split_times(stable_boundaries, duration), stable_examples


def format_split_times(split_times: list[float]) -> str:
    formatted_times = []

    for split_time in split_times:
        formatted_time = f"{split_time:.3f}".rstrip("0").rstrip(".")
        formatted_times.append(formatted_time)

    return ",".join(formatted_times)


def on_off(value: bool) -> str:
    return "ON" if value else "OFF"


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════


class VideoCutterApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(LANG_DATA["vi"]["app_title"])
        self.resize(1200, 820)
        self.setMinimumSize(1100, 750)
        self.setStyleSheet(APP_STYLESHEET)
        self.setAcceptDrops(True)
        self.load_window_icon()

        # ── Language & Theme ──
        self.current_lang = "vi"
        self.theme_is_dark = False

        # ── Data State (plain Python — no StringVar/BooleanVar) ──
        self.output_mode = OUTPUT_MODE_MERGE_DEFAULT
        self.cut_type = CUT_FIXED
        self.smooth_enabled = False
        self.remove_audio = False
        self.hardware_type = "cpu"

        # ── Processing State ──
        self.file_list: list[dict] = []
        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.current_process = None
        self.current_processes = set()
        self.process_lock = threading.Lock()
        self.current_output_dir = None
        self.last_output_dir = None

        self.build_ui()

        # Áp dụng màu thanh tiêu đề thương hiệu (Cam nhạt — cố định mọi theme)
        self.apply_branded_titlebar()

        # ── Multi-monitor startup flags ──
        self._startup_centered = False
        self._screen_signal_connected = False

        # ── Log queue polling timer ──
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.process_log_queue)
        self.log_timer.start(100)

    # ── Multi-monitor: Center on Startup ──

    def center_on_startup_screen(self):
        if self._startup_centered:
            return

        screen = QApplication.screenAt(QCursor.pos())

        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()

        max_width = max(1, int(available.width() * 0.95))
        max_height = max(1, int(available.height() * 0.95))

        current_width = min(self.width(), max_width)
        current_height = min(self.height(), max_height)

        if (
            current_width != self.width()
            or current_height != self.height()
        ):
            self.resize(current_width, current_height)

        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

        self._startup_centered = True

    def handle_screen_changed(self, screen):
        if screen is None:
            return

        available = screen.availableGeometry()

        max_width = max(1, int(available.width() * 0.95))
        max_height = max(1, int(available.height() * 0.95))

        new_width = min(self.width(), max_width)
        new_height = min(self.height(), max_height)

        if (
            new_width != self.width()
            or new_height != self.height()
        ):
            self.resize(new_width, new_height)

    def showEvent(self, event):
        super().showEvent(event)

        if self._screen_signal_connected:
            return

        window_handle = self.windowHandle()
        if window_handle is None:
            return

        window_handle.screenChanged.connect(self.handle_screen_changed)
        self._screen_signal_connected = True

    # ── Translation Helper ──

    def t(self, key: str) -> str:
        return LANG_DATA.get(self.current_lang, LANG_DATA["vi"]).get(key, key)

    # ── Icon ──

    def load_window_icon(self):
        icon_path = resource_path("icon_scissors.ico")

        if not icon_path.exists():
            return

        try:
            self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            return

    # ── Branded Title Bar (Windows DWM) ──

    def apply_branded_titlebar(self):
        """Đổi màu thanh tiêu đề Windows sang cam nhạt #FFD5A1 (brand color).

        Sử dụng Windows DWM API thông qua ctypes:
        - DWMWA_USE_IMMERSIVE_DARK_MODE (20) = 0  → Tắt dark mode cho title bar
        - DWMWA_CAPTION_COLOR (35) = 0x00A1D5FF   → Nền cam nhạt #FFD5A1 (BGR)
        - DWMWA_TEXT_COLOR (36) = 0x00202020       → Chữ xám đen #202020 (BGR)

        An toàn trên mọi OS nhờ kiểm tra platform + try/except.
        """
        if platform.system() != "Windows":
            return

        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi

            # 1. Tắt Immersive Dark Mode cho title bar (attribute 20)
            dark_mode = ctypes.c_int(0)  # 0 = False (Light)
            dwm.DwmSetWindowAttribute(
                hwnd, 20,
                ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)
            )

            # 2. Đổi màu nền title bar → Cam nhạt #FFD5A1 (BGR: 0x00A1D5FF)
            caption_color = ctypes.c_int(0x00A1D5FF)
            dwm.DwmSetWindowAttribute(
                hwnd, 35,
                ctypes.byref(caption_color), ctypes.sizeof(caption_color)
            )

            # 3. Đổi màu chữ title bar → Xám đen #202020 (BGR: 0x00202020)
            text_color = ctypes.c_int(0x00202020)
            dwm.DwmSetWindowAttribute(
                hwnd, 36,
                ctypes.byref(text_color), ctypes.sizeof(text_color)
            )
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  BUILD UI — Dashboard 2 Columns
    # ══════════════════════════════════════════════════════════════════════════

    def build_ui(self):
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        self.central_widget = central
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # ─────────────────────────────────────────────────────────────────────
        #  TITLE SECTION (Header bar)
        # ─────────────────────────────────────────────────────────────────────
        self.build_header(main_layout)

        # ─────────────────────────────────────────────────────────────────────
        #  BODY — QSplitter with 2 columns (50/50)
        # ─────────────────────────────────────────────────────────────────────
        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        body_splitter.setHandleWidth(12)
        body_splitter.setChildrenCollapsible(False)
        self.body_splitter = body_splitter

        # ── Left Column ──
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(8)
        self.left_column = left_widget

        # ── Right Column ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(8)
        self.right_column = right_widget

        body_splitter.addWidget(left_widget)
        body_splitter.addWidget(right_widget)
        body_splitter.setSizes([500, 500])
        body_splitter.setStretchFactor(0, 1)
        body_splitter.setStretchFactor(1, 1)
        main_layout.addWidget(body_splitter, stretch=1)

        # ═════════════════════════════════════════════════════════════════════
        #  SECTION 1: CẤU HÌNH ĐẦU VÀO (Left Column)
        # ═════════════════════════════════════════════════════════════════════
        self.build_section_input(left_layout)

        # ═════════════════════════════════════════════════════════════════════
        #  SECTION 4: ĐIỀU KHIỂN (Left Column, below Section 1)
        # ═════════════════════════════════════════════════════════════════════
        self.build_section_controls(left_layout)

        # ═════════════════════════════════════════════════════════════════════
        #  SECTION 2: CẤU HÌNH ĐẦU RA (Right Column)
        # ═════════════════════════════════════════════════════════════════════
        self.build_section_output(right_layout)

        # ═════════════════════════════════════════════════════════════════════
        #  SECTION 3: CẤU HÌNH THUẬT TOÁN CẮT (Right Column)
        # ═════════════════════════════════════════════════════════════════════
        self.build_section_settings(right_layout)

        # ═════════════════════════════════════════════════════════════════════
        #  SECTION 5: NHẬT KÝ XỬ LÝ (Right Column, expand)
        # ═════════════════════════════════════════════════════════════════════
        self.build_section_log(right_layout)

        # ── Initialize UI state ──
        self.update_cut_mode_ui()

    # ──────────────────────────────────────────────────────────────────────────
    #  HEADER
    # ──────────────────────────────────────────────────────────────────────────

    def build_header(self, parent_layout: QVBoxLayout):
        """Build the top header bar: Title/Subtitle (left) + Lang/Theme (right)."""
        header = QFrame()
        header.setObjectName("HeaderPanel")
        self.header_frame = header
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # ── Left: Logo + Title/Subtitle ──
        header_left_layout = QHBoxLayout()
        header_left_layout.setContentsMargins(0, 0, 0, 0)
        header_left_layout.setSpacing(12)

        # App Logo Widget
        self.logo_label = QLabel()
        self.logo_label.setObjectName("AppLogo")
        logo_path = resource_path("scissors.png")
        if not logo_path.exists():
            logo_path = resource_path("icon_scissors.ico")

        if logo_path.exists():
            if logo_path.suffix.lower() == ".ico":
                pix = QIcon(str(logo_path)).pixmap(128, 128)
            else:
                pix = QPixmap(str(logo_path))

            if not pix.isNull():
                scaled_pix = pix.scaled(
                    44, 44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.logo_label.setPixmap(scaled_pix)
                self.logo_label.setFixedSize(44, 44)
                self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                header_left_layout.addWidget(self.logo_label)

        title_block = QWidget()
        title_vbox = QVBoxLayout(title_block)
        title_vbox.setContentsMargins(0, 0, 0, 0)
        title_vbox.setSpacing(4)

        # Create title row layout for App Title
        title_row_layout = QHBoxLayout()
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(0)

        self.title_label = QLabel(self.t("app_title"))
        self.title_label.setObjectName("HeaderTitle")
        title_row_layout.addWidget(self.title_label)
        title_row_layout.addStretch()

        title_vbox.addLayout(title_row_layout)

        self.subtitle_label = QLabel(self.t("app_subtitle"))
        self.subtitle_label.setObjectName("HeaderSubtitle")
        title_vbox.addWidget(self.subtitle_label)

        # ── Gradient Divider Line (Cam nhạt → transparent) ──
        self.header_divider = QFrame()
        self.header_divider.setObjectName("HeaderDivider")
        self.header_divider.setFixedHeight(2)
        title_vbox.addWidget(self.header_divider)

        header_left_layout.addWidget(title_block)
        header_layout.addLayout(header_left_layout)
        header_layout.addStretch()

        # ── Right: Language ComboBox ──
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("HeaderLangMenu")
        self.lang_combo.addItems(["VI", "EN"])
        self.lang_combo.setCurrentText("VI")
        self.lang_combo.currentTextChanged.connect(self.change_language)
        header_layout.addWidget(self.lang_combo)

        # ── Right: Theme Toggle Button (SVG icon, 36×26) ──
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("ThemeToggleButton")
        self.theme_button.setFixedSize(36, 26)
        self.theme_button.setIconSize(QSize(18, 18))
        # Light mode init: hiển icon sun (click để chuyển sang Dark)
        self._icon_sun = QIcon(str(resource_path("assets/sun.svg")))
        self._icon_moon = QIcon(str(resource_path("assets/moon.svg")))
        self.theme_button.setIcon(self._icon_sun)
        self.theme_button.setToolTip(self.t("tooltip_to_dark"))
        self.theme_button.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.theme_button)

        parent_layout.addWidget(header)

    # ──────────────────────────────────────────────────────────────────────────
    #  SECTION 1: INPUT
    # ──────────────────────────────────────────────────────────────────────────

    def build_section_input(self, parent_layout: QVBoxLayout):
        section = QFrame()
        section.setObjectName("SectionPanel")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(14, 10, 14, 10)
        section_layout.setSpacing(6)

        self.section1_label = QLabel(self.t("section_input"))
        self.section1_label.setObjectName("SectionTitle")
        section_layout.addWidget(self.section1_label)

        # ── Button row ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_choose_files = QPushButton(self.t("btn_choose_files"))
        self.btn_choose_files.setObjectName("btn_add")
        self.btn_choose_files.setFixedHeight(30)
        self.btn_choose_files.clicked.connect(self.choose_files)
        btn_row.addWidget(self.btn_choose_files)

        self.btn_choose_folder = QPushButton(self.t("btn_choose_folder"))
        self.btn_choose_folder.setObjectName("btn_add")
        self.btn_choose_folder.setFixedHeight(30)
        self.btn_choose_folder.clicked.connect(self.choose_folder_to_scan)
        btn_row.addWidget(self.btn_choose_folder)

        self.btn_clear_all = QPushButton(self.t("btn_clear_all"))
        self.btn_clear_all.setObjectName("btn_remove")
        self.btn_clear_all.setFixedHeight(30)
        self.btn_clear_all.clicked.connect(self.clear_all_files)
        btn_row.addWidget(self.btn_clear_all)

        btn_row.addStretch()

        self.file_count_label = QLabel(self.t("file_count").format(count=0))
        self.file_count_label.setObjectName("FieldLabel")
        self.file_count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        btn_row.addWidget(self.file_count_label)

        section_layout.addLayout(btn_row)

        # ── Table Container Frame (Gánh viền và bo góc cách ly lỗi viewport) ──
        self.table_container = QFrame()
        self.table_container.setObjectName("TableContainer")
        table_grid = QGridLayout(self.table_container)
        table_grid.setContentsMargins(0, 0, 0, 0)
        table_grid.setSpacing(0)

        # ── File Table (QTableWidget) ──
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels([
            self.t("col_stt"),
            self.t("col_filename"),
            self.t("col_duration"),
            self.t("col_size"),
            "",
        ])
        self.file_table.setAlternatingRowColors(False)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setShowGrid(False)

        # Column sizing
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.file_table.setColumnWidth(0, 45)
        self.file_table.setColumnWidth(2, 90)
        self.file_table.setColumnWidth(3, 85)
        self.file_table.setColumnWidth(4, 40)

        # Đưa bảng vào ô lưới chính
        table_grid.addWidget(self.file_table, 0, 0)

        # ── Nhãn thông báo trống (Thiết kế lại nhiều dòng, căn giữa tuyệt đối) ──
        self.placeholder_label = QLabel()
        self.placeholder_label.setObjectName("TablePlaceholder")
        self.placeholder_label.setText(
            "<div style='text-align: center; line-height: 160%;'>"
            "<b>Kéo thả file video hoặc thư mục vào đây</b><br>"
            "<span>để tự động nạp danh sách xử lý</span>"
            "</div>"
        )
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Cho phép sự kiện kéo thả xuyên qua nhãn để nạp vào bảng phía dưới
        self.placeholder_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Đặt nhãn vào chung ô lưới với bảng để hệ thống tự động căn tâm
        table_grid.addWidget(self.placeholder_label, 0, 0)

        # Nạp Container vào Layout tổng của Section thay vì nạp trực tiếp bảng
        section_layout.addWidget(self.table_container, stretch=1)

        parent_layout.addWidget(section, stretch=1)
        self.refresh_file_table()

    # ──────────────────────────────────────────────────────────────────────────
    #  SECTION 2: OUTPUT
    # ──────────────────────────────────────────────────────────────────────────

    def build_section_output(self, parent_layout: QVBoxLayout):
        section = QFrame()
        section.setObjectName("SectionPanel")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(14, 10, 14, 10)
        section_layout.setSpacing(6)

        self.section2_label = QLabel(self.t("section_output"))
        self.section2_label.setObjectName("SectionTitle")
        section_layout.addWidget(self.section2_label)

        # ── Output directory row ──
        output_dir_row = QHBoxLayout()
        self.output_dir_label_widget = QLabel(self.t("output_dir_label"))
        self.output_dir_label_widget.setObjectName("FieldLabel")
        self.output_dir_label_widget.setFixedWidth(100)
        output_dir_row.addWidget(self.output_dir_label_widget)

        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText(self.t("output_dir_placeholder"))
        output_dir_row.addWidget(self.output_entry, stretch=1)

        self.btn_choose_output = QPushButton(self.t("btn_choose"))
        self.btn_choose_output.setObjectName("btn_browse")
        self.btn_choose_output.setFixedWidth(70)
        self.btn_choose_output.clicked.connect(self.choose_output_dir)
        output_dir_row.addWidget(self.btn_choose_output)

        section_layout.addLayout(output_dir_row)

        # ── Project name row ──
        project_row = QHBoxLayout()
        self.project_name_label_widget = QLabel(self.t("project_name_label"))
        self.project_name_label_widget.setObjectName("FieldLabel")
        self.project_name_label_widget.setFixedWidth(100)
        project_row.addWidget(self.project_name_label_widget)

        self.project_entry = QLineEdit()
        self.project_entry.setPlaceholderText(self.t("project_name_placeholder"))
        project_row.addWidget(self.project_entry, stretch=1)

        section_layout.addLayout(project_row)

        # ── Output mode row ──
        output_mode_row = QHBoxLayout()
        self.output_mode_label_widget = QLabel(self.t("output_mode_label"))
        self.output_mode_label_widget.setObjectName("FieldLabel")
        self.output_mode_label_widget.setFixedWidth(100)
        output_mode_row.addWidget(self.output_mode_label_widget)

        self.output_mode_menu = QComboBox()
        self.output_mode_menu.addItems([
            self.t("output_mode_split"),
            self.t("output_mode_merge_default"),
            self.t("output_mode_merge_rename"),
        ])
        self.output_mode_menu.setCurrentIndex(1)
        self.output_mode_menu.setFixedWidth(230)
        self.output_mode_menu.currentIndexChanged.connect(self._on_output_mode_changed)
        output_mode_row.addWidget(self.output_mode_menu)

        output_mode_row.addStretch()

        section_layout.addLayout(output_mode_row)

        # ── Folder count + Remove audio (combined row) ──
        opts_row = QHBoxLayout()
        self.output_folder_label_widget = QLabel(self.t("output_folder_label"))
        self.output_folder_label_widget.setObjectName("FieldLabel")
        self.output_folder_label_widget.setFixedWidth(100)
        opts_row.addWidget(self.output_folder_label_widget)

        self.output_folder_count_entry = QLineEdit("1")
        self.output_folder_count_entry.setObjectName("NumericInput")
        self.output_folder_count_entry.setFixedWidth(55)
        opts_row.addWidget(self.output_folder_count_entry)

        self.folder_unit_label = QLabel(self.t("folder_unit"))
        self.folder_unit_label.setObjectName("FieldLabel")
        opts_row.addWidget(self.folder_unit_label)

        opts_row.addSpacing(16)

        self.remove_audio_label_widget = QLabel(self.t("remove_audio_label"))
        self.remove_audio_label_widget.setObjectName("FieldLabel")
        opts_row.addWidget(self.remove_audio_label_widget)

        self.remove_audio_switch = QCheckBox()
        self.remove_audio_switch.setObjectName("ToggleSwitch")
        self.remove_audio_switch.stateChanged.connect(self._on_remove_audio_changed)
        opts_row.addWidget(self.remove_audio_switch)

        opts_row.addStretch()
        section_layout.addLayout(opts_row)

        parent_layout.addWidget(section)

    # ──────────────────────────────────────────────────────────────────────────
    #  SECTION 3: CUT SETTINGS
    # ──────────────────────────────────────────────────────────────────────────

    def build_section_settings(self, parent_layout: QVBoxLayout):
        _LBL_W = 110  # Trục dọc cố định cho mọi nhãn cột trái

        section = QFrame()
        section.setObjectName("SectionPanel")
        
        self.settings_grid_layout = QGridLayout(section)
        self.settings_grid_layout.setContentsMargins(15, 20, 15, 15)
        self.settings_grid_layout.setVerticalSpacing(25)
        self.settings_grid_layout.setHorizontalSpacing(10)

        self.section3_label = QLabel(self.t("section_settings"))
        self.section3_label.setObjectName("SectionTitle")
        self.settings_grid_layout.addWidget(self.section3_label, 0, 0, 1, 2)

        # ── Row 1: Kiểu cắt ──
        self.cut_type_label_widget = QLabel(self.t("cut_type_label"))
        self.cut_type_label_widget.setObjectName("FieldLabel")
        self.cut_type_label_widget.setFixedWidth(_LBL_W)
        self.cut_type_label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_grid_layout.addWidget(self.cut_type_label_widget, 1, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.cut_type_menu = QComboBox()
        self.cut_type_menu.addItems([
            self.t("cut_fixed"),
            self.t("cut_by_scene"),
            self.t("cut_to_images"),
        ])
        self.cut_type_menu.setFixedSize(180, 32)
        self.cut_type_menu.currentTextChanged.connect(self._on_cut_type_changed)
        self.settings_grid_layout.addWidget(self.cut_type_menu, 1, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # ── Row 2: Thời lượng (Fixed mode) ──
        self.duration_label_widget = QLabel(self.t("duration_label"))
        self.duration_label_widget.setObjectName("DurationLabel")
        self.duration_label_widget.setFixedWidth(_LBL_W)
        self.duration_label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_grid_layout.addWidget(self.duration_label_widget, 2, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.seconds_entry = QLineEdit("3")
        self.seconds_entry.setObjectName("DurationInput")
        self.seconds_entry.setFixedWidth(60)
        self.settings_grid_layout.addWidget(self.seconds_entry, 2, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # ── Row 3: Thông số (Scene mode) ──
        self.scene_params_label_widget = QLabel(self.t("scene_params_label"))
        self.scene_params_label_widget.setObjectName("FieldLabel")
        self.scene_params_label_widget.setFixedWidth(_LBL_W)
        self.scene_params_label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_grid_layout.addWidget(self.scene_params_label_widget, 3, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.scene_params_container = QWidget()
        scene_params_layout = QHBoxLayout(self.scene_params_container)
        scene_params_layout.setContentsMargins(0, 0, 0, 0)
        scene_params_layout.setSpacing(6)

        # Cụm nhỏ gọn: Min [__] s  •  Max [__] s  •  Threshold [__]
        self.min_label_widget = QLabel(self.t("min_label"))
        self.min_label_widget.setObjectName("FieldLabel")
        scene_params_layout.addWidget(self.min_label_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self.min_seconds_entry = QLineEdit("3")
        self.min_seconds_entry.setObjectName("NumericInput")
        self.min_seconds_entry.setFixedWidth(55)
        scene_params_layout.addWidget(self.min_seconds_entry, 0, Qt.AlignmentFlag.AlignVCenter)

        self.max_label_widget = QLabel(self.t("max_label"))
        self.max_label_widget.setObjectName("FieldLabel")
        scene_params_layout.addWidget(self.max_label_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self.max_seconds_entry = QLineEdit("5")
        self.max_seconds_entry.setObjectName("NumericInput")
        self.max_seconds_entry.setFixedWidth(55)
        scene_params_layout.addWidget(self.max_seconds_entry, 0, Qt.AlignmentFlag.AlignVCenter)

        self.threshold_label_widget = QLabel(self.t("threshold_label"))
        self.threshold_label_widget.setObjectName("FieldLabel")
        scene_params_layout.addWidget(self.threshold_label_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self.scene_threshold_entry = QLineEdit("0.35")
        self.scene_threshold_entry.setObjectName("NumericInput")
        self.scene_threshold_entry.setFixedWidth(65)
        scene_params_layout.addWidget(self.scene_threshold_entry, 0, Qt.AlignmentFlag.AlignVCenter)

        scene_params_layout.addStretch()
        self.settings_grid_layout.addWidget(self.scene_params_container, 3, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # ── Row 4: Làm mượt (Scene mode) ──
        self.smooth_label_widget = QLabel(self.t("smooth_label"))
        self.smooth_label_widget.setObjectName("SmoothLabel")
        self.smooth_label_widget.setFixedWidth(_LBL_W)
        self.smooth_label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_grid_layout.addWidget(self.smooth_label_widget, 4, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.smooth_container = QWidget()
        self.smooth_container.setObjectName("SmoothContainer")
        smooth_layout = QHBoxLayout(self.smooth_container)
        smooth_layout.setContentsMargins(0, 0, 0, 0)
        smooth_layout.setSpacing(6)

        self.smooth_switch = QCheckBox()
        self.smooth_switch.setObjectName("ToggleSwitch")
        self.smooth_switch.stateChanged.connect(self.update_smooth_ui)
        smooth_layout.addWidget(self.smooth_switch, 0, Qt.AlignmentFlag.AlignVCenter)

        self.smooth_seconds_entry = QLineEdit("0.5")
        self.smooth_seconds_entry.setObjectName("NumericInput")
        self.smooth_seconds_entry.setFixedWidth(65)
        self.smooth_seconds_entry.setVisible(False)
        smooth_layout.addWidget(self.smooth_seconds_entry, 0, Qt.AlignmentFlag.AlignVCenter)

        self.smooth_seconds_unit_label = QLabel(self.t("smooth_seconds_unit"))
        self.smooth_seconds_unit_label.setObjectName("FieldLabel")
        self.smooth_seconds_unit_label.setVisible(False)
        smooth_layout.addWidget(self.smooth_seconds_unit_label, 0, Qt.AlignmentFlag.AlignVCenter)

        smooth_layout.addStretch()
        self.smooth_container.setMinimumHeight(35)
        self.settings_grid_layout.addWidget(self.smooth_container, 4, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_grid_layout.setRowMinimumHeight(4, 35)

        # Stretch row 5 to push everything up
        self.settings_grid_layout.setRowStretch(5, 1)
        self.settings_grid_layout.setColumnStretch(1, 1)

        section.setFixedHeight(240)
        parent_layout.addWidget(section)

    # ──────────────────────────────────────────────────────────────────────────
    #  SECTION 4: CONTROLS
    # ──────────────────────────────────────────────────────────────────────────

    def build_section_controls(self, parent_layout: QVBoxLayout):
        # Plain QWidget with borderless/flat layout
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 4, 0, 4)
        section_layout.setSpacing(6)

        # Label kept for text refresh logic, but hidden by not adding it to layout
        self.section4_label = QLabel(self.t("section_control"))

        # ── Button row ──
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        self.start_button = QPushButton(self.t("btn_start"))
        self.start_button.setObjectName("btn_start")
        self.start_button.setFixedWidth(140)
        self.start_button.clicked.connect(self.start_processing)
        button_row.addWidget(self.start_button)

        self.cancel_button = QPushButton(self.t("btn_cancel"))
        self.cancel_button.setObjectName("btn_cancel")
        self.cancel_button.setFixedWidth(90)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        button_row.addWidget(self.cancel_button)

        self.open_output_button = QPushButton(self.t("btn_open_output"))
        self.open_output_button.setObjectName("btn_open_folder")
        self.open_output_button.setFixedWidth(170)
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self.open_last_output_dir)
        button_row.addWidget(self.open_output_button)

        button_row.addStretch()
        section_layout.addLayout(button_row)

        # ── Progress row ──
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.progress_text_label = QLabel(self.t("progress_label"))
        self.progress_text_label.setObjectName("ProgressLabel")
        self.progress_text_label.setFixedWidth(80)
        progress_row.addWidget(self.progress_text_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(16)
        progress_row.addWidget(self.progress_bar, stretch=1)

        self.progress_pct_label = QLabel("0%")
        self.progress_pct_label.setObjectName("ProgressValue")
        self.progress_pct_label.setFixedWidth(54)
        self.progress_pct_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progress_row.addWidget(self.progress_pct_label)

        section_layout.addLayout(progress_row)

        parent_layout.addWidget(section)

    # ──────────────────────────────────────────────────────────────────────────
    #  SECTION 5: LOG
    # ──────────────────────────────────────────────────────────────────────────

    def build_section_log(self, parent_layout: QVBoxLayout):
        section = QFrame()
        section.setObjectName("SectionPanel")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(14, 10, 14, 10)
        section_layout.setSpacing(6)

        # ── Header bar cho Section Log (Tiêu đề + Nút Xuất/Xóa log) ──
        log_header_layout = QHBoxLayout()
        log_header_layout.setContentsMargins(0, 0, 0, 0)
        log_header_layout.setSpacing(10)

        self.section5_label = QLabel(self.t("section_log"))
        self.section5_label.setObjectName("SectionTitle")
        log_header_layout.addWidget(self.section5_label)

        log_header_layout.addStretch()

        self.btn_export_log = QPushButton(self.t("btn_export_log"))
        self.btn_export_log.setObjectName("btn_export_log")
        self.btn_export_log.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export_log.clicked.connect(self.export_log)
        log_header_layout.addWidget(self.btn_export_log)

        self.btn_clear_log = QPushButton(self.t("btn_clear_log"))
        self.btn_clear_log.setObjectName("btn_clear_log")
        self.btn_clear_log.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_clear_log.clicked.connect(self.clear_log)
        log_header_layout.addWidget(self.btn_clear_log)

        section_layout.addLayout(log_header_layout)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("LogConsole")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(80)
        section_layout.addWidget(self.log_box, stretch=1)

        parent_layout.addWidget(section, stretch=1)

    def clear_log(self):
        """Xóa toàn bộ log hiển thị."""
        self.log_box.clear()

    def export_log(self):
        """Xuất nội dung log ra file text."""
        log_content = self.log_box.toPlainText()
        if not log_content.strip():
            QMessageBox.information(
                self,
                self.t("msg_complete_title"),
                "Không có nội dung nhật ký để xuất." if self.current_lang == "vi" else "No log content to export."
            )
            return

        default_filename = f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất Nhật Ký Xử Lý" if self.current_lang == "vi" else "Export Process Log",
            default_filename,
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(log_content)
                QMessageBox.information(
                    self,
                    self.t("msg_complete_title"),
                    f"Đã xuất log thành công tại:\n{file_path}" if self.current_lang == "vi" else f"Log exported successfully to:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    self.t("msg_error_title"),
                    f"Lỗi khi xuất log:\n{e}" if self.current_lang == "vi" else f"Error exporting log:\n{e}"
                )

    # ══════════════════════════════════════════════════════════════════════════
    #  LANGUAGE & THEME
    # ══════════════════════════════════════════════════════════════════════════

    def change_language(self, choice):
        if choice == "EN":
            self.current_lang = "en"
        else:
            self.current_lang = "vi"
        self.refresh_all_texts()

    def toggle_theme(self):
        """Toggle Dark ↔ Light mode, reload QSS + fix background leak."""
        if self.theme_is_dark:
            # ── Chuyển sang Light ──
            self.theme_is_dark = False
            new_stylesheet = build_stylesheet("light")
            self.setStyleSheet(new_stylesheet)
            self.theme_button.setIcon(self._icon_sun)
            self.theme_button.setToolTip(self.t("tooltip_to_dark"))
            # Giải phóng hoàn toàn inline style trên các container cha
            # để QSS global tự tiếp quản
            self.central_widget.setStyleSheet("")
            self.body_splitter.setStyleSheet("")
            self.left_column.setStyleSheet("")
            self.right_column.setStyleSheet("")
            self.header_frame.setStyleSheet("")
            self.title_label.setStyleSheet("")
            self.subtitle_label.setStyleSheet("")
            self.header_divider.setStyleSheet("")
        else:
            # ── Chuyển sang Dark ──
            self.theme_is_dark = True
            new_stylesheet = build_stylesheet("dark")
            self.setStyleSheet(new_stylesheet)
            self.theme_button.setIcon(self._icon_moon)
            self.theme_button.setToolTip(self.t("tooltip_to_light"))
            # Xóa inline style — để QSS global tiếp quản hoàn toàn
            self.central_widget.setStyleSheet("")
            self.body_splitter.setStyleSheet("")
            self.left_column.setStyleSheet("")
            self.right_column.setStyleSheet("")
            self.header_frame.setStyleSheet("")
            self.title_label.setStyleSheet("")
            self.subtitle_label.setStyleSheet("")
            self.header_divider.setStyleSheet("")

    def refresh_all_texts(self):
        """Update all displayed text to the current language."""
        # Title & Subtitle
        self.setWindowTitle(self.t("app_title"))
        self.title_label.setText(self.t("app_title"))
        self.subtitle_label.setText(self.t("app_subtitle"))

        # Language dropdown — sync display
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentText("VI" if self.current_lang == "vi" else "EN")
        self.lang_combo.blockSignals(False)

        # Section 1 — Input
        self.section1_label.setText(self.t("section_input"))
        self.btn_choose_files.setText(self.t("btn_choose_files"))
        self.btn_choose_folder.setText(self.t("btn_choose_folder"))
        self.btn_clear_all.setText(self.t("btn_clear_all"))
        self.file_count_label.setText(
            self.t("file_count").format(count=len(self.file_list)),
        )

        # Update table header labels
        self.file_table.setHorizontalHeaderLabels([
            self.t("col_stt"),
            self.t("col_filename"),
            self.t("col_duration"),
            self.t("col_size"),
            "",
        ])

        # Section 2 — Output
        self.section2_label.setText(self.t("section_output"))
        self.output_dir_label_widget.setText(self.t("output_dir_label"))
        self.output_entry.setPlaceholderText(self.t("output_dir_placeholder"))
        self.btn_choose_output.setText(self.t("btn_choose"))
        self.project_name_label_widget.setText(self.t("project_name_label"))
        self.project_entry.setPlaceholderText(self.t("project_name_placeholder"))
        self.output_mode_label_widget.setText(self.t("output_mode_label"))

        current_idx = self.output_mode_menu.currentIndex()
        self.output_mode_menu.blockSignals(True)
        self.output_mode_menu.clear()
        self.output_mode_menu.addItems([
            self.t("output_mode_split"),
            self.t("output_mode_merge_default"),
            self.t("output_mode_merge_rename"),
        ])
        self.output_mode_menu.setCurrentIndex(current_idx)
        self.output_mode_menu.blockSignals(False)

        self.output_folder_label_widget.setText(self.t("output_folder_label"))
        self.folder_unit_label.setText(self.t("folder_unit"))
        self.remove_audio_label_widget.setText(self.t("remove_audio_label"))

        # Section 3 — Settings
        self.section3_label.setText(self.t("section_settings"))
        self.cut_type_label_widget.setText(self.t("cut_type_label"))

        current_cut = self.cut_type
        self.cut_type_menu.blockSignals(True)
        self.cut_type_menu.clear()
        self.cut_type_menu.addItems([
            self.t("cut_fixed"),
            self.t("cut_by_scene"),
            self.t("cut_to_images"),
        ])
        cut_text = {
            CUT_FIXED: self.t("cut_fixed"),
            CUT_BY_SCENE: self.t("cut_by_scene"),
            CUT_TO_IMAGES: self.t("cut_to_images"),
        }.get(current_cut, self.t("cut_fixed"))
        self.cut_type_menu.setCurrentText(cut_text)
        self.cut_type_menu.blockSignals(False)

        self.duration_label_widget.setText(self.t("duration_label"))
        self.scene_params_label_widget.setText(self.t("scene_params_label"))
        self.min_label_widget.setText(self.t("min_label"))
        self.max_label_widget.setText(self.t("max_label"))
        self.threshold_label_widget.setText(self.t("threshold_label"))
        self.smooth_label_widget.setText(self.t("smooth_label"))
        self.smooth_seconds_unit_label.setText(self.t("smooth_seconds_unit"))

        # Section 4 — Controls
        self.section4_label.setText(self.t("section_control"))
        self.start_button.setText(self.t("btn_start"))
        self.cancel_button.setText(self.t("btn_cancel"))
        self.open_output_button.setText(self.t("btn_open_output"))
        self.progress_text_label.setText(self.t("progress_label"))

        # Section 5 — Log
        self.section5_label.setText(self.t("section_log"))
        self.btn_export_log.setText(self.t("btn_export_log"))
        self.btn_clear_log.setText(self.t("btn_clear_log"))

        # Refresh table
        self.refresh_file_table()

    # ══════════════════════════════════════════════════════════════════════════
    #  DROPDOWN COMMAND CALLBACKS (display text → internal value)
    # ══════════════════════════════════════════════════════════════════════════

    def _on_cut_type_changed(self, choice):
        if choice == self.t("cut_fixed"):
            self.cut_type = CUT_FIXED
        elif choice == self.t("cut_by_scene"):
            self.cut_type = CUT_BY_SCENE
        else:
            self.cut_type = CUT_TO_IMAGES
        self.update_cut_mode_ui()

    def _on_output_mode_changed(self, index):
        if index == 0:
            self.output_mode = OUTPUT_MODE_SPLIT_FOLDER
        elif index == 2:
            self.output_mode = OUTPUT_MODE_MERGE_RENAME
        else:
            self.output_mode = OUTPUT_MODE_MERGE_DEFAULT

    def _on_remove_audio_changed(self, state):
        self.remove_audio = (state == Qt.CheckState.Checked.value)

    # ══════════════════════════════════════════════════════════════════════════
    #  CUT MODE UI (show/hide fixed vs scene containers)
    # ══════════════════════════════════════════════════════════════════════════

    def update_cut_mode_ui(self, _=None):
        is_fixed = (self.cut_type == CUT_FIXED)
        is_scene = (self.cut_type == CUT_BY_SCENE)
        is_image_mode = (self.cut_type == CUT_TO_IMAGES)
        is_scene_based = is_scene or is_image_mode

        # Fixed Mode widgets
        self.duration_label_widget.setVisible(is_fixed)
        self.seconds_entry.setVisible(is_fixed)

        # Scene mode has Min/Max/Threshold and smoothing; image mode needs Threshold only.
        self.scene_params_label_widget.setVisible(is_scene_based)
        self.scene_params_container.setVisible(is_scene_based)
        self.min_label_widget.setVisible(is_scene)
        self.min_seconds_entry.setVisible(is_scene)
        self.max_label_widget.setVisible(is_scene)
        self.max_seconds_entry.setVisible(is_scene)
        self.threshold_label_widget.setVisible(is_scene_based)
        self.scene_threshold_entry.setVisible(is_scene_based)
        self.smooth_label_widget.setVisible(is_scene)
        self.smooth_container.setVisible(is_scene)

        self.update_smooth_ui()

    def update_smooth_ui(self, _=None):
        self.smooth_enabled = self.smooth_switch.isChecked()
        show = self.smooth_enabled and self.cut_type == CUT_BY_SCENE

        self.smooth_seconds_entry.setVisible(show)
        self.smooth_seconds_unit_label.setVisible(show)

    # ══════════════════════════════════════════════════════════════════════════
    #  DRAG & DROP
    # ══════════════════════════════════════════════════════════════════════════

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        video_files = []

        for url in urls:
            path = Path(url.toLocalFile())
            if path.is_dir():
                for ext in VIDEO_EXTENSIONS:
                    video_files.extend(path.glob(f"*{ext}"))
                    video_files.extend(path.glob(f"*{ext.upper()}"))
            elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                video_files.append(path)

        if video_files:
            self.add_files_to_list(sorted(set(video_files)))

    # ══════════════════════════════════════════════════════════════════════════
    #  FILE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def format_duration(self, seconds: float) -> str:
        if seconds < 0:
            return "N/A"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def format_file_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def add_files_to_list(self, paths: list):
        existing_paths = {f["path"] for f in self.file_list}
        new_files = []

        for path in paths:
            abs_path = str(Path(path).resolve())
            if abs_path in existing_paths:
                continue
            existing_paths.add(abs_path)

            try:
                size = Path(path).stat().st_size
            except OSError:
                size = 0

            new_files.append({
                "path": abs_path,
                "name": Path(path).name,
                "duration": -1.0,
                "size": size,
            })

        if not new_files:
            return

        self.file_list.extend(new_files)
        self.refresh_file_table()

        if not self.output_entry.text().strip() and self.file_list:
            first_path = Path(self.file_list[0]["path"])
            self.output_entry.setText(str(first_path.parent))

        threading.Thread(
            target=self._probe_durations,
            args=(new_files,),
            daemon=True,
        ).start()

    def _probe_durations(self, files: list):
        try:
            _, ffprobe_path = find_ffmpeg_tools()
        except RuntimeError:
            return

        for file_info in files:
            try:
                props = get_video_properties(
                    Path(file_info["path"]),
                    ffprobe_path,
                )
                file_info["duration"] = props["duration"]
                file_info["width"] = props["width"]
                file_info["height"] = props["height"]
                file_info["fps"] = props["fps"]
                file_info["pix_fmt"] = props["pix_fmt"]
                file_info["color_transfer"] = props["color_transfer"]
            except Exception:
                file_info["duration"] = -1.0

        QTimer.singleShot(0, self.refresh_file_table)

    def refresh_file_table(self):
        self.file_table.setRowCount(0)

        if not self.file_list:
            self.file_count_label.setText(
                self.t("file_count").format(count=0),
            )
            if hasattr(self, "placeholder_label"):
                self.placeholder_label.show()
            return

        if hasattr(self, "placeholder_label"):
            self.placeholder_label.hide()

        self.file_table.setRowCount(len(self.file_list))

        for index, file_info in enumerate(self.file_list):
            # STT
            stt_item = QTableWidgetItem(str(index + 1))
            stt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(index, 0, stt_item)

            # Filename
            name_item = QTableWidgetItem(file_info["name"])
            self.file_table.setItem(index, 1, name_item)

            # Duration
            duration_text = (
                self.format_duration(file_info["duration"])
                if file_info["duration"] >= 0
                else self.t("scanning")
            )
            dur_item = QTableWidgetItem(duration_text)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(index, 2, dur_item)

            # Size
            size_item = QTableWidgetItem(self.format_file_size(file_info["size"]))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_table.setItem(index, 3, size_item)

            # Remove button
            remove_btn = QPushButton("X")
            remove_btn.setObjectName("btn_remove")
            remove_btn.setFixedSize(28, 18)
            remove_btn.setStyleSheet("padding: 0px; margin: 0px; font-size: 11px; font-weight: bold; color: #ffffff;")
            remove_btn.clicked.connect(lambda checked, idx=index: self.remove_file(idx))
            self.file_table.setCellWidget(index, 4, remove_btn)

            self.file_table.setRowHeight(index, 26)

        self.file_count_label.setText(
            self.t("file_count").format(count=len(self.file_list)),
        )

    def remove_file(self, index: int):
        if 0 <= index < len(self.file_list):
            self.file_list.pop(index)
            self.refresh_file_table()

    def clear_all_files(self):
        self.file_list.clear()
        self.refresh_file_table()

    def choose_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.t("msg_choose_video_title"),
            "",
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.flv *.wmv *.m4v);;All files (*.*)",
        )

        if file_paths:
            self.add_files_to_list([Path(p) for p in file_paths])

    def choose_folder_to_scan(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            self.t("msg_choose_folder_title"),
        )

        if not folder_path:
            return

        folder = Path(folder_path)
        video_files = []
        for ext in VIDEO_EXTENSIONS:
            video_files.extend(folder.glob(f"*{ext}"))
            video_files.extend(folder.glob(f"*{ext.upper()}"))

        video_files = sorted(set(video_files))

        if video_files:
            self.add_files_to_list(video_files)
        else:
            QMessageBox.information(
                self,
                self.t("msg_no_folder_found_title"),
                self.t("msg_no_folder_found"),
            )

    def choose_output_dir(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            self.t("msg_choose_output_title"),
        )

        if folder_path:
            self.output_entry.setText(folder_path)

    # ══════════════════════════════════════════════════════════════════════════
    #  LOG / PROGRESS / PROCESS MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def log(self, message: str):
        self.log_queue.put(("log", message))

    def set_progress(self, value: float):
        self.log_queue.put(("progress", value))

    def set_current_process(self, process):
        with self.process_lock:
            self.current_processes = {
                active_process
                for active_process in self.current_processes
                if active_process.poll() is None
            }
            if process is not None:
                self.current_processes.add(process)
            self.current_process = next(iter(self.current_processes), None)

    def terminate_current_process(self):
        with self.process_lock:
            processes = list(self.current_processes)

        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.terminate()
            except Exception:
                continue

    def cancel_processing(self):
        if not (self.worker_thread and self.worker_thread.is_alive()):
            return

        if not self.cancel_event.is_set():
            self.cancel_event.set()
            self.log(self.t("msg_cancel_requested"))

        self.cancel_button.setEnabled(False)
        self.terminate_current_process()

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise ProcessingCancelled("Processing cancelled.")

    def cleanup_cancelled_output_dir(self):
        output_dir = self.current_output_dir

        if output_dir is None:
            return

        if not re.search(r"_cut_\d{8}_\d{6}$", output_dir.name):
            self.log(self.t("msg_skip_cleanup"))
            self.current_output_dir = None
            return

        try:
            if self.current_output_dir.exists():
                shutil.rmtree(self.current_output_dir, ignore_errors=True)
                self.log(self.t("msg_cleanup_done"))
        finally:
            if self.last_output_dir == output_dir:
                self.last_output_dir = None
            self.current_output_dir = None

    def open_last_output_dir(self):
        if self.last_output_dir is None or not self.last_output_dir.exists():
            self.log(self.t("msg_no_output_dir"))
            self.open_output_button.setEnabled(False)
            return

        try:
            os.startfile(str(self.last_output_dir))
        except Exception as error:
            error_message = self.t("msg_open_dir_error").format(error=error)
            self.log(error_message)
            QMessageBox.critical(self, self.t("msg_error_title"), error_message)

    def process_log_queue(self):
        try:
            while True:
                action, value = self.log_queue.get_nowait()

                if action == "log":
                    self.log_box.setReadOnly(False)
                    self.log_box.append(str(value))
                    self.log_box.setReadOnly(True)

                elif action == "progress":
                    pct = max(0, min(int(value * 1000), 1000))
                    self.progress_bar.setValue(pct)
                    self.progress_pct_label.setText(f"{int(value * 100)}%")

                elif action == "done":
                    # Play success sound
                    try:
                        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                    except Exception:
                        pass
                    self.start_button.setEnabled(True)
                    self.cancel_button.setEnabled(False)
                    if (
                        self.last_output_dir is not None
                        and self.last_output_dir.exists()
                    ):
                        self.open_output_button.setEnabled(True)
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle(self.t("msg_complete_title"))
                    msg_box.setIcon(QMessageBox.Icon.NoIcon)
                    msg_box.setWindowIcon(self.windowIcon())

                    num_videos = len(self.file_list)
                    output_path = str(self.last_output_dir) if self.last_output_dir else ""
                    T = _DARK_TOKENS if self.theme_is_dark else _LIGHT_TOKENS

                    if self.current_lang == "en":
                        title_text = f"🎉 Successfully cut {num_videos} {'videos' if num_videos > 1 else 'video'}!"
                    else:
                        title_text = f"🎉 Cắt thành công {num_videos} video!"

                    success_text = f"""
<div style="font-family: 'Arial'; padding: 5px 0px;">
    <span style="font-size: 14px; color: {T['TEXT_PRIMARY']}; font-weight: bold;">
        {title_text}
    </span>
</div>
"""
                    msg_box.setText(success_text)
                    msg_box.exec()

                elif action == "error":
                    # Play error sound
                    try:
                        winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
                    except Exception:
                        pass
                    self.start_button.setEnabled(True)
                    self.cancel_button.setEnabled(False)
                    self.open_output_button.setEnabled(False)
                    QMessageBox.critical(self, self.t("msg_error_title"), str(value))

                elif action == "cancelled":
                    self.start_button.setEnabled(True)
                    self.cancel_button.setEnabled(False)
                    self.open_output_button.setEnabled(False)
                    QMessageBox.information(
                        self, self.t("msg_cancelled_title"), str(value),
                    )

        except queue.Empty:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  VALIDATE INPUTS
    # ══════════════════════════════════════════════════════════════════════════

    def validate_inputs(self):
        if not self.file_list:
            raise ValueError(self.t("msg_no_videos"))

        for file_info in self.file_list:
            if not Path(file_info["path"]).exists():
                raise ValueError(
                    self.t("msg_file_not_found").format(
                        name=Path(file_info["path"]).name,
                    )
                )

        output_dir_text = self.output_entry.text().strip()
        cut_type = self.cut_type
        output_mode = self.output_mode
        project_name = self.project_entry.text().strip()

        if not output_dir_text:
            raise ValueError(self.t("msg_no_output_dir_selected"))

        output_dir = Path(output_dir_text)

        try:
            output_folder_count = int(self.output_folder_count_entry.text().strip())
        except ValueError:
            raise ValueError(self.t("msg_folder_count_int"))

        if output_folder_count < 1:
            raise ValueError(self.t("msg_folder_count_min"))

        segment_seconds = None
        min_seconds = None
        max_seconds = None
        scene_threshold = None
        smooth_enabled = False
        smooth_seconds = 0.0

        if cut_type == CUT_FIXED:
            try:
                segment_seconds = float(self.seconds_entry.text().strip())
            except ValueError:
                raise ValueError(self.t("msg_duration_number"))

            if segment_seconds <= 0:
                raise ValueError(self.t("msg_duration_positive"))

        elif cut_type == CUT_BY_SCENE:
            try:
                min_seconds = float(self.min_seconds_entry.text().strip())
                max_seconds = float(self.max_seconds_entry.text().strip())
                scene_threshold = float(self.scene_threshold_entry.text().strip())
            except ValueError:
                raise ValueError(self.t("msg_scene_params_number"))

            if min_seconds <= 0:
                raise ValueError(self.t("msg_min_positive"))

            if max_seconds <= min_seconds:
                raise ValueError(self.t("msg_max_gt_min"))

            if not 0 < scene_threshold < 1:
                raise ValueError(self.t("msg_threshold_range"))

            smooth_enabled = self.smooth_switch.isChecked()

            if smooth_enabled:
                try:
                    smooth_seconds = float(self.smooth_seconds_entry.text().strip())
                except ValueError:
                    raise ValueError(self.t("msg_smooth_number"))

                if smooth_seconds < 0:
                    raise ValueError(self.t("msg_smooth_positive"))

        elif cut_type == CUT_TO_IMAGES:
            try:
                scene_threshold = float(self.scene_threshold_entry.text().strip())
            except ValueError:
                raise ValueError(self.t("msg_image_threshold_number"))

            if not 0 < scene_threshold < 1:
                raise ValueError(self.t("msg_threshold_range"))

        else:
            raise ValueError(self.t("msg_cut_type_invalid"))

        return (
            output_dir,
            cut_type,
            segment_seconds,
            min_seconds,
            max_seconds,
            scene_threshold,
            output_folder_count,
            self.remove_audio,
            smooth_enabled,
            smooth_seconds,
            output_mode,
            project_name,
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  START PROCESSING (launches worker thread)
    # ══════════════════════════════════════════════════════════════════════════

    def start_processing(self):
        if self.worker_thread and self.worker_thread.is_alive():
            QMessageBox.warning(
                self, self.t("msg_running_title"), self.t("msg_running"),
            )
            return

        try:
            (
                output_dir,
                cut_type,
                segment_seconds,
                min_seconds,
                max_seconds,
                scene_threshold,
                output_folder_count,
                remove_audio,
                smooth_enabled,
                smooth_seconds,
                output_mode,
                project_name,
            ) = self.validate_inputs()
        except Exception as error:
            try:
                import winsound
                winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
            QMessageBox.critical(self, self.t("msg_error_input_title"), str(error))
            return

        self.cancel_event.clear()
        self.set_current_process(None)
        self.current_output_dir = None
        self.last_output_dir = None

        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.open_output_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_pct_label.setText("0%")

        self.log_box.setReadOnly(False)
        self.log_box.clear()
        self.log_box.setReadOnly(True)

        # Copy file list for thread safety (deep copy dicts to avoid race condition)
        import copy
        file_list_copy = [copy.copy(fi) for fi in self.file_list]

        self.worker_thread = threading.Thread(
            target=self.process_all_videos,
            args=(
                file_list_copy,
                output_dir,
                cut_type,
                segment_seconds,
                min_seconds,
                max_seconds,
                scene_threshold,
                output_folder_count,
                remove_audio,
                smooth_enabled,
                smooth_seconds,
                output_mode,
                project_name,
            ),
            daemon=True,
        )
        self.worker_thread.start()

    # ══════════════════════════════════════════════════════════════════════════
    #  BATCH PROCESSING ORCHESTRATOR
    # ══════════════════════════════════════════════════════════════════════════

    def process_all_videos(
        self,
        file_list_copy,
        output_dir,
        cut_type,
        segment_seconds,
        min_seconds,
        max_seconds,
        scene_threshold,
        output_folder_count,
        remove_audio,
        smooth_enabled,
        smooth_seconds,
        output_mode,
        project_name,
    ):
        total = len(file_list_copy)

        try:
            ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
        except RuntimeError as e:
            self.log_queue.put(("error", str(e)))
            return

        self.hardware_profile = build_hardware_profile(
            ffmpeg_path,
            calibrate=(cut_type == CUT_BY_SCENE and total > 1),
        )
        self.hardware_type = self.hardware_profile.hardware_type
        gpu_label = self.hardware_profile.gpu_name or "N/A"
        self.log(
            self.t("log_hardware_profile").format(
                encoder=self.hardware_profile.encoder_label,
                cpus=self.hardware_profile.logical_cpus,
                ram=self.hardware_profile.ram_gb,
                gpu=gpu_label,
                workers=self.hardware_profile.parallel_video_workers,
            )
        )

        # Determine the project output directory based on project name input
        if not project_name:
            # Scenario 1: Empty project name -> Create 'output' folder directly in the chosen output directory
            project_output_dir = output_dir / "output"
        else:
            # Scenario 2: Project name provided -> Create a folder with the project name directly
            safe_project_name = safe_filename(project_name)
            project_output_dir = output_dir / safe_project_name

        project_output_dir.mkdir(parents=True, exist_ok=True)
        self.current_output_dir = project_output_dir
        self.last_output_dir = project_output_dir

        # ── Setup for Merged modes (Mode 1 and Mode 2) ──
        merged_dir = None
        shared_output_folders = None
        # For Mode 2 (Merge Rename): per-folder sequential counters
        global_folder_counters = None

        is_merged = output_mode in (OUTPUT_MODE_MERGE_DEFAULT, OUTPUT_MODE_MERGE_RENAME)

        if is_merged:
            merged_dir = project_output_dir
            shared_output_folders = self.create_output_folders(
                merged_dir, output_folder_count,
            )
            self.log(self.t("log_merged_output").format(path=merged_dir))

            if output_mode == OUTPUT_MODE_MERGE_RENAME:
                global_folder_counters = {k: 0 for k in range(1, output_folder_count + 1)}

        total_exported = 0

        try:
            self.log(self.t("log_start"))
            batch_started_at = time.perf_counter()
            normalized_video_names = [
                safe_filename(Path(file_info["path"]).stem).casefold()
                for file_info in file_list_copy
            ]
            has_duplicate_video_names = (
                len(normalized_video_names) != len(set(normalized_video_names))
            )
            worker_count = choose_parallel_video_workers(
                self.hardware_type,
                cut_type == CUT_BY_SCENE,
                (
                    output_mode == OUTPUT_MODE_MERGE_RENAME
                    or has_duplicate_video_names
                ),
                total,
                profile=self.hardware_profile,
            )
            if worker_count > 1:
                self.log(
                    self.t("log_parallel_workers").format(count=worker_count),
                )
            elif has_duplicate_video_names and total > 1:
                self.log(self.t("log_parallel_duplicate_names"))

            progress_values = [0.0] * total
            progress_lock = threading.Lock()

            def make_progress_callback(video_index):
                def progress_cb(value):
                    bounded_value = max(0.0, min(float(value), 1.0))
                    with progress_lock:
                        progress_values[video_index] = max(
                            progress_values[video_index],
                            bounded_value,
                        )
                        overall_progress = sum(progress_values) / total
                    self.set_progress(overall_progress)

                return progress_cb

            def process_video_task(idx, file_info):
                self.check_cancelled()
                video_path = Path(file_info["path"])
                video_started_at = time.perf_counter()

                self.log(self.t("log_batch_progress").format(
                    current=idx + 1, total=total, name=video_path.name,
                ))

                progress_cb = make_progress_callback(idx)
                video_idx = idx + 1

                if output_mode == OUTPUT_MODE_SPLIT_FOLDER:
                    video_name_no_ext = safe_filename(video_path.stem)
                    video_parent_dir = project_output_dir / video_name_no_ext
                    video_parent_dir.mkdir(parents=True, exist_ok=True)
                    output_folders = self.create_output_folders(
                        video_parent_dir,
                        output_folder_count,
                    )
                    temp_base_dir = video_parent_dir
                    folder_counters = None
                else:
                    output_folders = shared_output_folders
                    temp_base_dir = merged_dir
                    folder_counters = global_folder_counters

                _counter, exported = self.process_single_video(
                    video_path=video_path,
                    cut_type=cut_type,
                    segment_seconds=segment_seconds,
                    min_seconds=min_seconds,
                    max_seconds=max_seconds,
                    scene_threshold=scene_threshold,
                    remove_audio=remove_audio,
                    smooth_enabled=smooth_enabled,
                    smooth_seconds=smooth_seconds,
                    ffmpeg_path=ffmpeg_path,
                    ffprobe_path=ffprobe_path,
                    output_folders=output_folders,
                    scene_counter_start=0,
                    output_folder_count=output_folder_count,
                    progress_callback=progress_cb,
                    temp_base_dir=temp_base_dir,
                    export_mode=output_mode,
                    video_idx=video_idx,
                    global_folder_counters=folder_counters,
                    file_info=file_info,
                )
                progress_cb(1.0)
                elapsed = time.perf_counter() - video_started_at
                self.log(
                    self.t("log_video_elapsed").format(
                        name=video_path.name,
                        seconds=elapsed,
                    ),
                )
                return exported

            futures = []
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="video-cutter",
            ) as executor:
                for idx, file_info in enumerate(file_list_copy):
                    self.check_cancelled()
                    video_path = Path(file_info["path"])
                    if not video_path.exists():
                        self.log(
                            self.t("msg_file_not_found").format(
                                name=video_path.name,
                            ),
                        )
                        make_progress_callback(idx)(1.0)
                        continue
                    futures.append(executor.submit(process_video_task, idx, file_info))

                try:
                    for future in as_completed(futures):
                        total_exported += future.result()
                except Exception:
                    for pending_future in futures:
                        pending_future.cancel()
                    self.terminate_current_process()
                    raise

            self.log(
                self.t("log_batch_elapsed").format(
                    seconds=time.perf_counter() - batch_started_at,
                ),
            )
            self.last_output_dir = project_output_dir

            # ── All videos done ──
            self.set_progress(1.0)
            self.log("")
            self.log(self.t("log_complete"))
            self.log(self.t("log_exported_count").format(count=total_exported))

            if is_merged:
                result_path = merged_dir
                self.log(self.t("log_result_folder").format(path=result_path))
                done_msg = self.t("log_batch_done_msg").format(
                    total=total, path=result_path,
                )
            else:
                result_path = project_output_dir
                done_msg = self.t("log_batch_separate_done").format(
                    total=total, path=result_path,
                )

            self.log_queue.put(("done", done_msg))

        except ProcessingCancelled:
            self.log(self.t("log_cancelled"))
            if output_mode == OUTPUT_MODE_SPLIT_FOLDER:
                self.cleanup_cancelled_output_dir()
            self.log_queue.put(("cancelled", self.t("msg_cancelled")))

        except subprocess.CalledProcessError as error:
            if self.cancel_event.is_set():
                self.log(self.t("log_cancelled"))
                if output_mode == OUTPUT_MODE_SPLIT_FOLDER:
                    self.cleanup_cancelled_output_dir()
                self.log_queue.put(("cancelled", self.t("msg_cancelled")))
                return

            error_text = error.stderr if error.stderr else str(error)
            self.log_queue.put((
                "error",
                self.t("log_ffmpeg_error").format(error=error_text),
            ))

        except Exception as error:
            if self.cancel_event.is_set():
                self.log(self.t("log_cancelled"))
                if output_mode == OUTPUT_MODE_SPLIT_FOLDER:
                    self.cleanup_cancelled_output_dir()
                self.log_queue.put(("cancelled", self.t("msg_cancelled")))
                return

            self.log_queue.put(("error", str(error)))

        finally:
            self.set_current_process(None)

    # ══════════════════════════════════════════════════════════════════════════
    #  PROCESS SINGLE VIDEO
    # ══════════════════════════════════════════════════════════════════════════

    def process_single_video_to_images(
        self,
        video_path: Path,
        scene_threshold: float | None,
        ffmpeg_path: str,
        ffprobe_path: str,
        output_folders: list[Path],
        scene_counter_start: int,
        output_folder_count: int,
        progress_callback,
        export_mode: int,
        global_folder_counters: dict | None,
        file_info: dict | None,
    ) -> tuple[int, int]:
        """Export one high-quality JPEG from the stable part of every detected scene."""
        if scene_threshold is None:
            raise RuntimeError(self.t("log_missing_image_threshold"))

        self.check_cancelled()
        self.log(self.t("log_input").format(path=video_path))
        self.log(self.t("log_cut_type").format(type=CUT_TO_IMAGES))
        self.log(self.t("log_image_mode"))
        self.log(self.t("log_threshold").format(val=scene_threshold))

        cached_info = file_info or {}
        duration = (
            cached_info.get("duration", -1.0)
            if cached_info.get("duration", -1.0) > 0
            else get_video_duration(video_path, ffprobe_path)
        )
        if duration <= 0:
            raise RuntimeError(self.t("log_invalid_duration"))

        self.log(self.t("log_duration").format(duration=duration))
        self.log(self.t("log_scanning_scene_scores"))
        progress_callback(0.02)
        scene_scores = detect_scene_scores(
            video_path,
            ffmpeg_path,
            self.cancel_event,
            self.set_current_process,
        )
        self.check_cancelled()
        progress_callback(0.20)

        scene_count = sum(1 for _, score in scene_scores if score > scene_threshold)
        snapshot_times = build_smart_snapshot_times(
            scene_scores,
            duration,
            scene_threshold,
        )
        self.log(self.t("log_scene_count").format(count=scene_count))
        self.log(self.t("log_snapshot_count").format(count=len(snapshot_times)))

        exported_count = 0
        scene_counter = scene_counter_start
        for snapshot_index, snapshot_time in enumerate(snapshot_times, start=1):
            self.check_cancelled()
            scene_counter += 1
            folder_target_idx = ((snapshot_index - 1) % output_folder_count) + 1
            target_dir = output_folders[folder_target_idx - 1]

            if export_mode == OUTPUT_MODE_MERGE_RENAME and global_folder_counters is not None:
                global_folder_counters[folder_target_idx] += 1
                sequence_number = global_folder_counters[folder_target_idx]
            else:
                sequence_number = snapshot_index

            output_file = target_dir / f"{sequence_number:03d}_{safe_filename(video_path.stem)}.jpg"
            command = self.build_snapshot_command(
                ffmpeg_path,
                video_path,
                snapshot_time,
                output_file,
            )
            run_ffmpeg_segment(
                command,
                duration,
                lambda _value: None,
                self.cancel_event,
                self.set_current_process,
            )

            if not output_file.exists():
                raise RuntimeError(f"FFmpeg did not create snapshot: {output_file.name}")

            self.log(
                self.t("log_export_image").format(
                    number=scene_counter,
                    time=snapshot_time,
                    folder=target_dir.name,
                    file=output_file.name,
                )
            )
            exported_count += 1
            progress_callback(0.20 + (snapshot_index / len(snapshot_times)) * 0.80)

        return scene_counter, exported_count
    def process_single_video(
        self,
        video_path: Path,
        cut_type: str,
        segment_seconds: float | None,
        min_seconds: float | None,
        max_seconds: float | None,
        scene_threshold: float | None,
        remove_audio: bool,
        smooth_enabled: bool,
        smooth_seconds: float,
        ffmpeg_path: str,
        ffprobe_path: str,
        output_folders: list[Path],
        scene_counter_start: int,
        output_folder_count: int,
        progress_callback,
        temp_base_dir: Path,
        export_mode: int = OUTPUT_MODE_MERGE_DEFAULT,
        video_idx: int = 1,
        global_folder_counters: dict | None = None,
        file_info: dict | None = None,
    ) -> tuple[int, int]:
        """
        Process a single video: detect cuts, run FFmpeg, distribute segments.
        Returns (final_scene_counter, exported_count).
        """
        video_name_clean = safe_filename(video_path.stem)
        
        if cut_type == CUT_TO_IMAGES:
            return self.process_single_video_to_images(
                video_path=video_path,
                scene_threshold=scene_threshold,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                output_folders=output_folders,
                scene_counter_start=scene_counter_start,
                output_folder_count=output_folder_count,
                progress_callback=progress_callback,
                export_mode=export_mode,
                global_folder_counters=global_folder_counters,
                file_info=file_info,
            )
        
        # Sinh chuỗi ID ngắn ngẫu nhiên để đảm bảo thư mục tạm an toàn tuyệt đối cho FFmpeg
        safe_temp_id = uuid.uuid4().hex[:8]
        temp_dir = temp_base_dir / f"temp_video_{video_idx}_{safe_temp_id}"

        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            self.check_cancelled()

            self.log(self.t("log_input").format(path=video_path))
            self.log(self.t("log_cut_type").format(type=cut_type))
            self.log(self.t("log_remove_audio").format(status=on_off(remove_audio)))

            # ── Lấy metadata từ cache (file_info) thay vì gọi ffprobe lần 2 ──
            duration = file_info.get("duration", -1.0) if file_info.get("duration", -1.0) > 0 else get_video_duration(video_path, ffprobe_path)
            v_width = file_info.get("width", 0)
            v_height = file_info.get("height", 0)
            v_fps = file_info.get("fps", 0.0)
            v_pix_fmt = file_info.get("pix_fmt", "")
            v_color_transfer = file_info.get("color_transfer", "")
            self.check_cancelled()
            self.log(self.t("log_duration").format(duration=duration))

            if duration <= 0:
                raise RuntimeError(self.t("log_invalid_duration"))

            temp_pattern = temp_dir / "scene_%03d.mp4"
            segment_list_path = temp_dir / "segments.csv"
            discard_smooth_segments = False
            dropped_smooth_segment_count = 0
            segment_progress_start = 0.05
            expected_segment_intervals = []
            planned_output_intervals = []

            if cut_type == CUT_FIXED:
                if segment_seconds is None:
                    raise RuntimeError(self.t("log_missing_fixed_duration"))

                expected_temp_segments = math.ceil(duration / segment_seconds)
                total_scenes = expected_temp_segments

                self.log(
                    self.t("log_segment_duration").format(seconds=segment_seconds),
                )
                self.log(self.t("log_fixed_copy"))

                segment_command = self.build_fixed_segment_command(
                    ffmpeg_path,
                    video_path,
                    temp_pattern,
                    segment_seconds,
                    remove_audio,
                )

            elif cut_type == CUT_BY_SCENE:
                if (
                    min_seconds is None
                    or max_seconds is None
                    or scene_threshold is None
                ):
                    raise RuntimeError(self.t("log_missing_scene_params"))

                # ── CHẶN LỖI MÀU HDR / 10-BIT (Chỉ Scene Mode) ──
                is_hdr_10bit = (
                    ("10" in v_pix_fmt) or
                    v_color_transfer.lower() in ("smpte2084", "arib-std-b67")
                )
                if is_hdr_10bit:
                    self.log(
                        f'<span style="color: #e6a817;">[BỎ QUA] Video HDR/10-bit chưa được hỗ trợ '
                        f'(pix_fmt={v_pix_fmt}, color_transfer={v_color_transfer}), '
                        f'bỏ qua để tránh lỗi màu.</span>'
                    )
                    return scene_counter_start, 0

                self.log(self.t("log_scene_encode"))
                self.log(self.t("log_min_seconds").format(val=min_seconds))
                self.log(self.t("log_max_seconds").format(val=max_seconds))
                self.log(self.t("log_threshold").format(val=scene_threshold))
                self.log(self.t("log_smooth").format(status=on_off(smooth_enabled)))
                self.log(self.t("log_scanning_scenes"))
                progress_callback(0.02)

                scene_times = detect_scene_changes(
                    video_path,
                    ffmpeg_path,
                    scene_threshold,
                    self.cancel_event,
                    self.set_current_process,
                    self.hardware_type,
                )
                self.check_cancelled()
                progress_callback(0.10)
                self.log(
                    self.t("log_scene_count").format(count=len(scene_times)),
                )

                split_times = build_scene_split_times(
                    scene_times,
                    duration,
                    min_seconds,
                    max_seconds,
                    smooth_seconds=smooth_seconds if smooth_enabled else 0.0,
                )
                split_times = normalize_split_times(split_times, duration)
                self.log(
                    self.t("log_split_count").format(count=len(split_times)),
                )

                segment_times = split_times

                if smooth_enabled:
                    self.log(
                        self.t("log_smooth_seconds").format(val=smooth_seconds),
                    )

                    boundary_times, boundary_examples = (
                        build_smooth_boundary_times(
                            split_times,
                            scene_times,
                            duration,
                            smooth_seconds,
                            min_output_seconds=min_seconds,
                        )
                    )
                    self.log(
                        self.t("log_boundary_count").format(
                            count=len(boundary_times),
                        ),
                    )

                    if boundary_examples:
                        for split_time, left, right in boundary_examples[:5]:
                            self.log(
                                self.t("log_boundary_example").format(
                                    split=split_time, left=left, right=right,
                                )
                            )

                    if boundary_times:
                        segment_times = boundary_times
                        discard_smooth_segments = True
                    else:
                        self.log(self.t("log_no_boundary"))

                expected_temp_segments = len(segment_times) + 1
                expected_segment_intervals = build_segment_intervals(
                    segment_times,
                    duration,
                )
                planned_output_intervals = (
                    build_kept_intervals(segment_times, duration)
                    if discard_smooth_segments
                    else expected_segment_intervals
                )
                total_scenes = (
                    sum(
                        1
                        for i in range(expected_temp_segments)
                        if i % 2 == 0
                    )
                    if discard_smooth_segments
                    else expected_temp_segments
                )
                segment_progress_start = 0.12

                segment_command = self.build_scene_segment_command(
                    ffmpeg_path,
                    video_path,
                    temp_pattern,
                    segment_times,
                    max_seconds,
                    duration,
                    remove_audio,
                    hardware_type=self.hardware_type,
                    v_width=v_width,
                    v_height=v_height,
                    v_fps=v_fps,
                    segment_list_path=segment_list_path,
                )

            else:
                raise RuntimeError(self.t("msg_cut_type_invalid"))

            if total_scenes <= 0:
                raise RuntimeError(self.t("log_no_segments"))

            self.log(
                self.t("log_expected_segments").format(
                    count=expected_temp_segments,
                ),
            )
            self.log(
                self.t("log_kept_segments").format(count=total_scenes),
            )
            self.log(self.t("log_cutting"))
            progress_callback(segment_progress_start)
            self.check_cancelled()

            def update_segment_progress(value):
                progress_callback(
                    segment_progress_start
                    + value * (0.75 - segment_progress_start)
                )

            run_ffmpeg_segment(
                segment_command,
                duration,
                update_segment_progress,
                self.cancel_event,
                self.set_current_process,
            )
            self.check_cancelled()
            progress_callback(0.75)
            self.log(self.t("log_segments_done"))

            temp_files = sorted(temp_dir.glob("scene_*.mp4"))
            self.log(
                self.t("log_actual_segments").format(count=len(temp_files)),
            )

            needs_safe_fallback = False
            if cut_type == CUT_BY_SCENE:
                actual_timeline = read_segment_timeline(segment_list_path)
                needs_safe_fallback = (
                    len(temp_files) != expected_temp_segments
                    or not segment_layout_matches(
                        actual_timeline,
                        expected_segment_intervals,
                    )
                )

            if needs_safe_fallback:
                self.log(
                    self.t("log_segment_mismatch").format(
                        actual=len(temp_files),
                        expected=expected_temp_segments,
                    )
                )
                self.log(
                    self.t("log_segment_fallback").format(
                        count=len(planned_output_intervals),
                    )
                )
                for temp_file in temp_dir.glob("scene_*.mp4"):
                    temp_file.unlink(missing_ok=True)
                segment_list_path.unlink(missing_ok=True)

                for interval_index, (start, end) in enumerate(
                    planned_output_intervals,
                    start=1,
                ):
                    self.check_cancelled()
                    output_path = temp_dir / f"scene_{interval_index:03d}.mp4"
                    interval_command = self.build_scene_interval_command(
                        ffmpeg_path=ffmpeg_path,
                        video_path=video_path,
                        output_path=output_path,
                        start=start,
                        end=end,
                        remove_audio=remove_audio,
                        hardware_type=self.hardware_type,
                        v_width=v_width,
                        v_height=v_height,
                        v_fps=v_fps,
                    )
                    run_ffmpeg_segment(
                        interval_command,
                        end - start,
                        lambda _value: None,
                        self.cancel_event,
                        self.set_current_process,
                    )

                temp_files = sorted(temp_dir.glob("scene_*.mp4"))
                discard_smooth_segments = False
                dropped_smooth_segment_count = max(
                    0,
                    expected_temp_segments - len(planned_output_intervals),
                )
                expected_temp_segments = len(planned_output_intervals)
                total_scenes = expected_temp_segments

            if not temp_files:
                raise RuntimeError(self.t("log_no_temp_files"))

            if len(temp_files) != expected_temp_segments:
                raise RuntimeError(
                    self.t("log_segment_mismatch").format(
                        actual=len(temp_files),
                        expected=expected_temp_segments,
                    )
                )

            exported_count = 0
            scene_counter = scene_counter_start

            for temp_index, temp_file in enumerate(temp_files):
                self.check_cancelled()

                if discard_smooth_segments and temp_index % 2 == 1:
                    dropped_smooth_segment_count += 1
                    self.log(
                        self.t("log_drop_smooth").format(
                            index=temp_index, name=temp_file.name,
                        )
                    )
                    progress_callback(
                        0.75 + ((temp_index + 1) / len(temp_files)) * 0.25,
                    )
                    continue

                scene_counter += 1
                scene_number = scene_counter
                # segment_idx within this video (1-indexed)
                segment_idx = exported_count + 1
                folder_target_idx = ((segment_idx - 1) % output_folder_count) + 1
                target_dir = output_folders[folder_target_idx - 1]

                # Determine output filename based on export mode
                if export_mode == OUTPUT_MODE_SPLIT_FOLDER:
                    # Mode 0: STT of this video's segment
                    stt_str = str(segment_idx).zfill(3)
                    output_file = target_dir / f"{stt_str}_{video_name_clean}.mp4"
                elif export_mode == OUTPUT_MODE_MERGE_RENAME:
                    # Mode 2: sequential per-folder counter
                    if global_folder_counters is not None:
                        global_folder_counters[folder_target_idx] += 1
                        seq_num = global_folder_counters[folder_target_idx]
                    else:
                        seq_num = segment_idx
                    stt_str = str(seq_num).zfill(3)
                    
                    
                    output_file = target_dir / f"{stt_str}_{video_name_clean}.mp4"
                else:
                    # Mode 1 (Merge Default): original segment index of this video
                    stt_str = str(segment_idx).zfill(3)
                    output_file = target_dir / f"{stt_str}_{video_name_clean}.mp4"

                self.log(
                    self.t("log_export_scene").format(
                        number=scene_number,
                        folder=target_dir.name,
                        file=output_file.name,
                    )
                )
                shutil.move(str(temp_file), str(output_file))

                exported_count += 1
                progress_callback(
                    0.75 + ((temp_index + 1) / len(temp_files)) * 0.25,
                )

            progress_callback(1.0)

            self.log(
                self.t("log_kept_count").format(
                    count=scene_counter - scene_counter_start,
                ),
            )
            if smooth_enabled:
                self.log(
                    self.t("log_dropped_count").format(
                        count=dropped_smooth_segment_count,
                    ),
                )
            self.log(
                self.t("log_exported_count").format(count=exported_count),
            )

            return scene_counter, exported_count

        finally:
            if temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ══════════════════════════════════════════════════════════════════════════
    #  FFMPEG COMMAND BUILDERS
    # ══════════════════════════════════════════════════════════════════════════

    def build_fixed_segment_command(
        self,
        ffmpeg_path: str,
        video_path: Path,
        temp_pattern: Path,
        segment_seconds: float,
        remove_audio: bool,
    ) -> list[str]:
        command = [
            ffmpeg_path,
            "-y",
            "-progress",
            "pipe:1",
            "-nostats",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
        ]

        if remove_audio:
            command += [
                "-an",
                "-c:v",
                "copy",
            ]
        else:
            command += [
                "-map",
                "0:a?",
                "-c",
                "copy",
            ]

        command += [
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            "-segment_start_number",
            "1",
            "-segment_format",
            "mp4",
            str(temp_pattern),
        ]

        return command

    @staticmethod
    def build_snapshot_command(
        ffmpeg_path: str,
        video_path: Path,
        snapshot_time: float,
        output_file: Path,
    ) -> list[str]:
        return [
            ffmpeg_path,
            "-threads", "auto",
            "-y",
            "-ss", f"{snapshot_time:.3f}",
            "-i", str(video_path),
            "-map", "0:v:0",
            "-frames:v", "1",
            "-q:v", "2",
            "-progress", "pipe:1",
            "-nostats",
            str(output_file),
        ]

    @staticmethod
    def _get_bitrate_params(width: int, height: int, fps: float, hardware_type: str) -> dict:
        """Ma trận bitrate động chuẩn YouTube dựa trên độ phân giải và FPS."""
        # Xác định tier dựa trên chiều rộng thực tế (landscape) hoặc chiều cao (portrait)
        res = max(width, height)
        high_fps = fps > 30

        if res >= 3840:  # 4K
            if high_fps:
                cq, bv, maxr = 21, "50M", "68M"
            else:
                cq, bv, maxr = 21, "35M", "50M"
            bufsize = "75M"
        elif res >= 2560:  # 1440p / 2K
            cq, bv, maxr, bufsize = 21, "20M", "30M", "45M"
        elif res >= 1920:  # 1080p
            if high_fps:
                cq, bv, maxr = 22, "15M", "22M"
            else:
                cq, bv, maxr = 22, "10M", "16M"
            bufsize = "30M"
        else:  # Dưới 1080p
            cq, bv, maxr, bufsize = 23, "6M", "10M", "15M"

        return {"cq": str(cq), "bv": bv, "maxrate": maxr, "bufsize": bufsize}

    def build_scene_segment_command(
        self,
        ffmpeg_path: str,
        video_path: Path,
        temp_pattern: Path,
        segment_times: list[float],
        max_seconds: float,
        duration: float,
        remove_audio: bool,
        hardware_type: str = "cpu",
        v_width: int = 0,
        v_height: int = 0,
        v_fps: float = 0.0,
        segment_list_path: Path | None = None,
    ) -> list[str]:
        # Khởi tạo khung xương lệnh gốc
        command = [
            ffmpeg_path,
            "-threads", "auto",
            "-y",
            "-progress", "pipe:1",
            "-nostats",
        ]

        # ── Tính toán bitrate động từ ma trận YouTube ──
        bp = self._get_bitrate_params(v_width, v_height, v_fps, hardware_type)

        # --- RẼ NHÁNH TẬP LỆNH MÃ HÓA THEO THIẾT BỊ PHẦN CỨNG ---
        if hardware_type == "nvidia":
            # ── TRƯỜNG HỢP 1: MÁY SỬ DỤNG CARD NVIDIA NVENC ──
            command += [
                "-hwaccel", "cuda",
                "-hwaccel_output_format", "cuda",
                "-threads", "auto",
                "-i", str(video_path),
                "-map", "0:v:0",
            ]
            if remove_audio: command += ["-an"]
            else: command += ["-map", "0:a?"]
            command += ["-sn", "-dn"]

            command += [
                "-c:v", "h264_nvenc",
                "-preset", "p2",             # Preset p2 ưu tiên tốc độ mã hóa tối đa
                "-tune", "hq",               # High Quality offline render
                "-rc", "vbr",
                "-cq", bp["cq"],             # Constant Quality động theo độ phân giải
                "-b:v", bp["bv"],            # Bitrate mục tiêu động
                "-maxrate", bp["maxrate"],   # Trần tối đa động
                "-bufsize", bp["bufsize"],   # Buffer size tối ưu
                "-forced-idr", "1",
                "-g", "60",
            ]
            if not remove_audio: command += ["-c:a", "copy"]

        elif hardware_type == "amd":
            # ── TRƯỜNG HỢP 2: MÁY SỬ DỤNG CARD AMD AMF ──
            # Giải mã bằng phần mềm để đảm bảo tương thích mọi đời card AMD
            command += [
                "-threads", "auto",
                "-i", str(video_path),
                "-map", "0:v:0",
            ]
            if remove_audio: command += ["-an"]
            else: command += ["-map", "0:a?"]
            command += ["-sn", "-dn"]

            command += [
                "-c:v", "h264_amf",
                "-rc", "vbr_peak",           # Chế độ Peak VBR thông minh của AMD
                "-quality", "speed",         # Ưu tiên tốc độ mã hóa tối đa
                "-b:v", bp["bv"],            # Bitrate mục tiêu động
                "-maxrate", bp["maxrate"],   # Trần tối đa động
                "-forced-idr", "1",
                "-g", "60",
            ]
            if not remove_audio: command += ["-c:a", "copy"]

        elif hardware_type == "intel":
            command += [
                "-threads", "auto",
                "-i", str(video_path),
                "-map", "0:v:0",
            ]
            if remove_audio: command += ["-an"]
            else: command += ["-map", "0:a?"]
            command += ["-sn", "-dn"]
            command += [
                "-c:v", "h264_qsv",
                "-preset", "veryfast",
                "-global_quality", bp["cq"],
                "-forced_idr", "1",
                "-g", "60",
            ]
            if not remove_audio: command += ["-c:a", "copy"]

        else:
            # ── TRƯỜNG HỢP 3: MÁY KHÔNG CÓ GPU HOẶC INTEL (DỰ PHÒNG AN TOÀN CPU) ──
            command += [
                "-threads", "auto",
                "-i", str(video_path),
                "-map", "0:v:0",
            ]
            if remove_audio: command += ["-an"]
            else: command += ["-map", "0:a?"]
            command += ["-sn", "-dn"]

            # Sử dụng thư viện libx264 phần mềm, crf 22 giữ độ nét tương đương bản gốc
            command += [
                "-c:v", "libx264",
                "-preset", "superfast",      # Tốc độ mã hóa CPU tối đa cho máy không GPU rời
                "-crf", "22",
            ]
            if not remove_audio: command += ["-c:a", "aac", "-b:a", "192k"] # Mã hóa audio an toàn bằng CPU

        # --- KHỐI LỆNH ĐỊNH HƯỚNG PHÂN CẢNH VÀ XUẤT ĐẦU RA PHÍA SAU GIỮ NGUYÊN ---
        segment_times_text = (
            format_split_times(segment_times)
            if segment_times
            else ""
        )

        if segment_times_text:
            command += [
                "-force_key_frames",
                segment_times_text,
            ]

        command += ["-f", "segment"]
        if segment_list_path is not None:
            command += [
                "-segment_list", str(segment_list_path),
                "-segment_list_type", "csv",
            ]
        if segment_times_text:
            command += [
                "-segment_times", segment_times_text,
                "-segment_time_delta", "0.05",
            ]
        else:
            command += ["-segment_time", str(max(duration + 1, max_seconds))]

        command += [
            "-reset_timestamps", "1",
            "-segment_start_number", "1",
            "-segment_format", "mp4",
            str(temp_pattern),
        ]

        return command

    def build_scene_interval_command(
        self,
        ffmpeg_path: str,
        video_path: Path,
        output_path: Path,
        start: float,
        end: float,
        remove_audio: bool,
        hardware_type: str = "cpu",
        v_width: int = 0,
        v_height: int = 0,
        v_fps: float = 0.0,
    ) -> list[str]:
        """Safe fallback: encode one explicit absolute interval."""
        duration = max(MIN_BOUNDARY_GAP, end - start)
        bp = self._get_bitrate_params(v_width, v_height, v_fps, hardware_type)
        command = [
            ffmpeg_path,
            "-y",
            "-progress", "pipe:1",
            "-nostats",
            "-ss", f"{start:.3f}",
            "-i", str(video_path),
            "-t", f"{duration:.3f}",
            "-map", "0:v:0",
        ]
        if remove_audio:
            command += ["-an"]
        else:
            command += ["-map", "0:a?"]
        command += ["-sn", "-dn"]

        if hardware_type == "nvidia":
            command += [
                "-c:v", "h264_nvenc", "-preset", "p2", "-tune", "hq",
                "-rc", "vbr", "-cq", bp["cq"], "-b:v", bp["bv"],
                "-maxrate", bp["maxrate"], "-bufsize", bp["bufsize"],
            ]
        elif hardware_type == "amd":
            command += [
                "-c:v", "h264_amf", "-rc", "vbr_peak", "-quality", "speed",
                "-b:v", bp["bv"], "-maxrate", bp["maxrate"],
            ]
        elif hardware_type == "intel":
            command += [
                "-c:v", "h264_qsv", "-preset", "veryfast",
                "-global_quality", bp["cq"],
            ]
        else:
            command += ["-c:v", "libx264", "-preset", "superfast", "-crf", "22"]

        if not remove_audio:
            command += ["-c:a", "aac", "-b:a", "192k"]
        command += [
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            str(output_path),
        ]
        return command

    def create_output_folders(
        self,
        project_output_dir: Path,
        output_folder_count: int,
    ) -> list[Path]:
        folders = []

        for folder_index in range(1, output_folder_count + 1):
            folder = project_output_dir / f"folder_{folder_index}"
            folder.mkdir(parents=True, exist_ok=True)
            folders.append(folder)

        return folders


if __name__ == "__main__":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app_icon_path = resource_path("icon_scissors.ico")
    if app_icon_path.exists():
        app.setWindowIcon(QIcon(str(app_icon_path)))

    # --- KIỂM TRA PENDING UPDATE MARKER ---
    from updater import verify_pending_update_marker, run_update_check
    verify_pending_update_marker()
    # --------------------------------------

    # --- CHỐT CHẶN BẢN QUYỀN ---
    from security import check_license_on_startup
    from license_dialog import LicenseDialog

    res, _ = check_license_on_startup()
    if res.valid is not True:
        dialog = LicenseDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
    # ---------------------------

    # --- KIỂM TRA CẬP NHẬT ---
    if getattr(sys, "frozen", False):
        need_restart = run_update_check()
        if need_restart:
            sys.exit(0)
    # ---------------------------

    window = VideoCutterApp()
    window.show()
    QTimer.singleShot(0, window.center_on_startup_screen)
    sys.exit(app.exec())

