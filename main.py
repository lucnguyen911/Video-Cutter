import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, filedialog, messagebox

import customtkinter as ctk


APP_TITLE = "Video Auto Cut by Lực Nguyễn"
CUT_FIXED = "Cố định"
CUT_BY_SCENE = "Chuyển cảnh"
SMOOTH_TRIM_TAIL = "Cắt đuôi (Video trước)"
SMOOTH_TRIM_HEAD = "Cắt đầu (Video sau)"
MIN_BOUNDARY_GAP = 0.05

BG_COLOR = "#f6f7f9"
SECTION_COLOR = "#ffffff"
SECTION_BORDER_COLOR = "#e5e7eb"
TEXT_COLOR = "#1f2937"
MUTED_TEXT_COLOR = "#374151"
PRIMARY_COLOR = "#2f6fed"
PRIMARY_HOVER_COLOR = "#255fd2"
SUCCESS_COLOR = "#22a06b"
SUCCESS_HOVER_COLOR = "#1b8758"
CANCEL_COLOR = "#6b7280"
CANCEL_HOVER_COLOR = "#b94a48"
LOG_BG_COLOR = "#111827"
LOG_TEXT_COLOR = "#e5e7eb"
FONT_SIZE = 14
TITLE_FONT_SIZE = 23
LOG_FONT_SIZE = 13


class ProcessingCancelled(Exception):
    pass


def safe_filename(name: str) -> str:
    """
    Chuyen ten video thanh ten file an toan:
    - bo ky tu dac biet
    - thay khoang trang bang dau gach duoi
    """
    name = Path(name).stem
    name = name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9_\-]", "", name)

    if not name:
        name = "video"

    return name


def resource_path(relative_path: str) -> Path:
    """Resolve a resource path for Python and PyInstaller onefile builds."""
    if getattr(sys, "_MEIPASS", None):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path


def find_ffmpeg_tools():
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError(
            "Khong tim thay ffmpeg hoac ffprobe. "
            "Hay cai FFmpeg va dam bao ffmpeg chay duoc trong Terminal."
        )

    return ffmpeg_path, ffprobe_path


def get_subprocess_creationflags():
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW

    return 0


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
        raise ProcessingCancelled("Đã hủy xử lý.")

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
        raise ProcessingCancelled("Đã hủy xử lý.")

    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code,
            command,
            stderr="".join(stderr_lines),
        )


def get_video_duration(video_path: Path, ffprobe_path: str) -> float:
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
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

    return float(result.stdout.strip())


def normalize_split_times(split_times: list[float], duration: float) -> list[float]:
    normalized = {
        round(split_time, 3)
        for split_time in split_times
        if 0 < split_time < duration
    }

    return sorted(normalized)


def detect_scene_changes(
    video_path: Path,
    ffmpeg_path: str,
    threshold: float,
    cancel_event: threading.Event | None = None,
    process_callback=None,
) -> list[float]:
    if cancel_event is not None and cancel_event.is_set():
        raise ProcessingCancelled("Đã hủy xử lý.")

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-i",
        str(video_path),
        "-filter:v",
        f"select='gt(scene,{threshold})',showinfo",
        "-an",
        "-f",
        "null",
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
        raise ProcessingCancelled("Đã hủy xử lý.")

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
) -> list[float]:
    scene_times = normalize_split_times(scene_times, duration)
    split_times = []
    start_time = 0.0

    while duration - start_time > max_seconds:
        min_cut_time = start_time + min_seconds
        max_cut_time = start_time + max_seconds
        candidates = [
            scene_time
            for scene_time in scene_times
            if min_cut_time <= scene_time <= max_cut_time
        ]

        if candidates:
            split_time = candidates[-1]
        else:
            split_time = max_cut_time

        if split_time <= start_time:
            break

        split_times.append(split_time)
        start_time = split_time

    if 0 < duration - start_time < min_seconds and split_times:
        split_times.pop()

    return normalize_split_times(split_times, duration)


def build_smooth_boundary_times(
    split_times: list[float],
    duration: float,
    smooth_seconds: float,
    smooth_mode: str,
) -> tuple[list[float], list[tuple[float, float, float]]]:
    if smooth_seconds <= 0:
        return [], []

    boundary_times = []
    examples = []
    last_boundary_time = 0.0

    for split_time in normalize_split_times(split_times, duration):
        if smooth_mode == SMOOTH_TRIM_HEAD:
            left = round(split_time, 3)
            right = round(split_time + smooth_seconds, 3)
        else:
            left = round(split_time - smooth_seconds, 3)
            right = round(split_time, 3)

        if left <= 0 or right >= duration or right <= left:
            continue

        if left - last_boundary_time < MIN_BOUNDARY_GAP:
            continue

        if right - left < MIN_BOUNDARY_GAP:
            continue

        boundary_times.extend([left, right])
        examples.append((split_time, left, right))
        last_boundary_time = right

    return normalize_split_times(boundary_times, duration), examples


def format_split_times(split_times: list[float]) -> str:
    formatted_times = []

    for split_time in split_times:
        formatted_time = f"{split_time:.3f}".rstrip("0").rstrip(".")
        formatted_times.append(formatted_time)

    return ",".join(formatted_times)


def on_off(value: bool) -> str:
    return "ON" if value else "OFF"


class VideoCutterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("940x760")
        self.minsize(860, 700)

        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=BG_COLOR)
        self.load_window_icon()

        self.video_path_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar()
        self.cut_type_var = ctk.StringVar(value=CUT_FIXED)
        self.seconds_var = ctk.StringVar(value="3")
        self.min_seconds_var = ctk.StringVar(value="2")
        self.max_seconds_var = ctk.StringVar(value="5")
        self.scene_threshold_var = ctk.StringVar(value="0.35")
        self.output_folder_count_var = ctk.StringVar(value="1")
        self.remove_audio_var = BooleanVar(value=False)
        self.smooth_enabled_var = BooleanVar(value=False)
        self.smooth_seconds_var = ctk.StringVar(value="0.5")
        self.smooth_mode_var = ctk.StringVar(value=SMOOTH_TRIM_TAIL)

        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.current_process = None
        self.process_lock = threading.Lock()
        self.current_output_dir = None
        self.last_output_dir = None

        self.build_ui()
        self.after(100, self.process_log_queue)

    def load_window_icon(self):
        icon_path = resource_path("icon_scissors.ico")

        if not icon_path.exists():
            return

        try:
            self.iconbitmap(str(icon_path))
        except Exception:
            return

    def create_section_frame(self, parent):
        section = ctk.CTkFrame(
            parent,
            fg_color=SECTION_COLOR,
            border_width=1,
            border_color=SECTION_BORDER_COLOR,
            corner_radius=10,
        )
        section.pack(fill="x", pady=(0, 8))
        return section

    def create_field_row(self, parent, label_text: str, label_width: int = 130):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=6)

        ctk.CTkLabel(
            row,
            text=label_text,
            width=label_width,
            anchor="w",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 10))

        return row

    def style_entry(self, entry):
        entry.configure(
            height=32,
            fg_color="#ffffff",
            border_color="#d1d5db",
            text_color=TEXT_COLOR,
            placeholder_text_color="#94a3b8",
            font=ctk.CTkFont(size=FONT_SIZE),
            corner_radius=7,
        )

    def style_option_menu(self, menu):
        menu.configure(
            height=32,
            fg_color="#ffffff",
            button_color="#e5e7eb",
            button_hover_color="#d1d5db",
            text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
            dropdown_font=ctk.CTkFont(size=FONT_SIZE),
            dropdown_fg_color="#ffffff",
            dropdown_hover_color="#eef2ff",
            dropdown_text_color=TEXT_COLOR,
            corner_radius=7,
            dynamic_resizing=False,
        )

    def style_primary_option_menu(self, menu):
        menu.configure(
            height=34,
            fg_color="#3498DB",
            button_color="#3498DB",
            button_hover_color="#3498DB",
            text_color="white",
            font=ctk.CTkFont(size=FONT_SIZE, weight="bold"),
            dropdown_font=ctk.CTkFont(size=FONT_SIZE),
            dropdown_fg_color="white",
            dropdown_hover_color="#EAF3FF",
            dropdown_text_color="#111827",
            corner_radius=8,
            dynamic_resizing=False,
        )

    def add_cut_type_dropdown_arrow(self):
        def hide_default_arrow():
            try:
                self.cut_type_menu._canvas.itemconfigure(
                    "dropdown_arrow",
                    state="hidden",
                )
            except Exception:
                return

        hide_default_arrow()
        self.after_idle(hide_default_arrow)

        self.cut_type_arrow_label = ctk.CTkLabel(
            self.cut_type_menu,
            text="▼",
            width=28,
            height=24,
            fg_color="#3498DB",
            text_color="white",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.cut_type_arrow_label.place(relx=1.0, rely=0.5, x=-17, y=0, anchor="center")
        self.cut_type_arrow_label.bind(
            "<Button-1>",
            lambda event: self.cut_type_menu._clicked(event),
        )

    def create_path_section(
        self,
        parent,
        row_label: str,
        variable,
        placeholder: str,
        button_text: str,
        button_color: str,
        button_hover_color: str,
        command,
    ):
        section = self.create_section_frame(parent)

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            row,
            text=row_label,
            width=130,
            anchor="w",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 10))

        entry = ctk.CTkEntry(
            row,
            textvariable=variable,
            placeholder_text=placeholder,
        )
        self.style_entry(entry)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 12))

        ctk.CTkButton(
            row,
            text=button_text,
            width=120,
            height=32,
            fg_color=button_color,
            hover_color=button_hover_color,
            font=ctk.CTkFont(size=FONT_SIZE),
            corner_radius=7,
            command=command,
        ).pack(side="left")

        return section

    def build_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0)
        main_frame.pack(fill="both", expand=True, padx=14, pady=12)

        title_section = ctk.CTkFrame(main_frame, fg_color=BG_COLOR, corner_radius=0)
        title_section.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(
            title_section,
            text=APP_TITLE,
            anchor="center",
            justify="center",
            text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=TITLE_FONT_SIZE, weight="bold"),
        ).pack(fill="x")

        self.create_path_section(
            main_frame,
            "Video đầu vào:",
            self.video_path_var,
            "Chưa chọn video...",
            "Chọn video",
            PRIMARY_COLOR,
            PRIMARY_HOVER_COLOR,
            self.choose_video,
        )

        self.create_path_section(
            main_frame,
            "Thư mục xuất:",
            self.output_dir_var,
            "Chưa chọn thư mục...",
            "Chọn thư mục",
            SUCCESS_COLOR,
            SUCCESS_HOVER_COLOR,
            self.choose_output_dir,
        )

        settings_section = self.create_section_frame(main_frame)

        cut_type_row = self.create_field_row(settings_section, "Kiểu cắt:")
        self.cut_type_menu = ctk.CTkOptionMenu(
            cut_type_row,
            variable=self.cut_type_var,
            values=[CUT_FIXED, CUT_BY_SCENE],
            command=self.update_cut_mode_ui,
            width=250,
        )
        self.style_primary_option_menu(self.cut_type_menu)
        self.cut_type_menu.pack(side="left")
        self.add_cut_type_dropdown_arrow()

        self.duration_settings_row = self.create_field_row(
            settings_section,
            "Thời lượng (s):",
        )
        self.seconds_entry = ctk.CTkEntry(
            self.duration_settings_row,
            textvariable=self.seconds_var,
            width=100,
        )
        self.style_entry(self.seconds_entry)
        self.seconds_entry.pack(side="left")

        self.scene_settings_row = self.create_field_row(settings_section, "Min (s):")

        self.min_seconds_entry = ctk.CTkEntry(
            self.scene_settings_row,
            textvariable=self.min_seconds_var,
            width=86,
        )
        self.style_entry(self.min_seconds_entry)
        self.min_seconds_entry.pack(side="left", padx=(0, 18))

        ctk.CTkLabel(
            self.scene_settings_row,
            text="Max (s):",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 8))
        self.max_seconds_entry = ctk.CTkEntry(
            self.scene_settings_row,
            textvariable=self.max_seconds_var,
            width=86,
        )
        self.style_entry(self.max_seconds_entry)
        self.max_seconds_entry.pack(side="left", padx=(0, 18))

        ctk.CTkLabel(
            self.scene_settings_row,
            text="Scene threshold:",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 8))
        self.scene_threshold_entry = ctk.CTkEntry(
            self.scene_settings_row,
            textvariable=self.scene_threshold_var,
            width=86,
        )
        self.style_entry(self.scene_threshold_entry)
        self.scene_threshold_entry.pack(side="left")

        self.smooth_row = self.create_field_row(settings_section, "Làm mượt:")
        self.smooth_switch = ctk.CTkSwitch(
            self.smooth_row,
            text="",
            variable=self.smooth_enabled_var,
            command=self.update_smooth_ui,
            width=70,
            progress_color=PRIMARY_COLOR,
        )
        self.smooth_switch.pack(side="left")

        self.smooth_settings_frame = ctk.CTkFrame(
            self.smooth_row,
            fg_color="transparent",
        )
        self.smooth_settings_frame.pack(side="left", padx=(14, 0))

        self.smooth_seconds_entry = ctk.CTkEntry(
            self.smooth_settings_frame,
            textvariable=self.smooth_seconds_var,
            width=86,
        )
        self.style_entry(self.smooth_seconds_entry)
        self.smooth_seconds_entry.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            self.smooth_settings_frame,
            text="giây",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 12))

        self.smooth_mode_menu = ctk.CTkOptionMenu(
            self.smooth_settings_frame,
            variable=self.smooth_mode_var,
            values=[SMOOTH_TRIM_TAIL, SMOOTH_TRIM_HEAD],
            width=210,
        )
        self.style_option_menu(self.smooth_mode_menu)
        self.smooth_mode_menu.pack(side="left")

        output_section = self.create_section_frame(main_frame)

        self.output_options_row = self.create_field_row(output_section, "Output:")
        self.output_folder_count_entry = ctk.CTkEntry(
            self.output_options_row,
            textvariable=self.output_folder_count_var,
            width=86,
        )
        self.style_entry(self.output_folder_count_entry)
        self.output_folder_count_entry.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            self.output_options_row,
            text="folder",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 50))

        ctk.CTkLabel(
            self.output_options_row,
            text="Xóa audio:",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 10))

        self.remove_audio_switch = ctk.CTkSwitch(
            self.output_options_row,
            text="",
            variable=self.remove_audio_var,
            width=54,
            switch_width=46,
            switch_height=22,
            fg_color="#d1d5db",
            progress_color=PRIMARY_COLOR,
            button_color="#ffffff",
            button_hover_color="#f3f4f6",
        )
        self.remove_audio_switch.pack(side="left")

        control_section = self.create_section_frame(main_frame)

        button_row = ctk.CTkFrame(control_section, fg_color="transparent")
        button_row.pack(fill="x", padx=14, pady=(10, 8))

        self.start_button = ctk.CTkButton(
            button_row,
            text="Bắt đầu",
            width=112,
            height=34,
            fg_color=PRIMARY_COLOR,
            hover_color=PRIMARY_HOVER_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE, weight="bold"),
            corner_radius=7,
            command=self.start_processing,
        )
        self.start_button.pack(side="left", padx=(0, 12))

        self.cancel_button = ctk.CTkButton(
            button_row,
            text="Hủy",
            width=86,
            height=34,
            fg_color=CANCEL_COLOR,
            hover_color=CANCEL_HOVER_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
            corner_radius=7,
            state="disabled",
            command=self.cancel_processing,
        )
        self.cancel_button.pack(side="left")

        self.open_output_button = ctk.CTkButton(
            button_row,
            text="Mở thư mục kết quả",
            width=160,
            height=34,
            fg_color="#4b5563",
            hover_color="#374151",
            font=ctk.CTkFont(size=FONT_SIZE),
            corner_radius=7,
            state="disabled",
            command=self.open_last_output_dir,
        )
        self.open_output_button.pack(side="left", padx=(12, 0))

        progress_row = ctk.CTkFrame(control_section, fg_color="transparent")
        progress_row.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            progress_row,
            text="Tiến trình:",
            width=130,
            anchor="w",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(side="left", padx=(0, 12))

        self.progress_bar = ctk.CTkProgressBar(
            progress_row,
            progress_color=PRIMARY_COLOR,
            fg_color="#dbeafe",
            height=12,
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_row,
            text="0%",
            width=54,
            anchor="e",
            text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE, weight="normal"),
        )
        self.progress_label.pack(side="left")

        log_section = ctk.CTkFrame(
            main_frame,
            fg_color=SECTION_COLOR,
            border_width=1,
            border_color=SECTION_BORDER_COLOR,
            corner_radius=10,
        )
        log_section.pack(fill="both", expand=True)

        ctk.CTkLabel(
            log_section,
            text="Nhật ký xử lý:",
            anchor="w",
            text_color=MUTED_TEXT_COLOR,
            font=ctk.CTkFont(size=FONT_SIZE),
        ).pack(fill="x", padx=14, pady=(10, 4))

        self.log_box = ctk.CTkTextbox(
            log_section,
            height=210,
            fg_color=LOG_BG_COLOR,
            text_color=LOG_TEXT_COLOR,
            border_width=1,
            border_color="#1f2937",
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=LOG_FONT_SIZE),
        )
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self.log_box.configure(state="disabled")

        self.update_cut_mode_ui()

    def update_smooth_ui(self):
        is_scene_cut = self.cut_type_var.get() == CUT_BY_SCENE
        show_smooth_settings = is_scene_cut and self.smooth_enabled_var.get()

        if show_smooth_settings:
            if not self.smooth_settings_frame.winfo_manager():
                self.smooth_settings_frame.pack(side="left", padx=(14, 0))
            self.smooth_seconds_entry.configure(state="normal")
            self.smooth_mode_menu.configure(state="normal")
        else:
            if self.smooth_settings_frame.winfo_manager():
                self.smooth_settings_frame.pack_forget()
            self.smooth_seconds_entry.configure(state="disabled")
            self.smooth_mode_menu.configure(state="disabled")

    def update_cut_mode_ui(self, _=None):
        is_scene_cut = self.cut_type_var.get() == CUT_BY_SCENE

        if is_scene_cut:
            if self.duration_settings_row.winfo_manager():
                self.duration_settings_row.pack_forget()

            if not self.scene_settings_row.winfo_manager():
                self.scene_settings_row.pack(fill="x", padx=18, pady=(8, 10))

            if not self.smooth_row.winfo_manager():
                self.smooth_row.pack(fill="x", padx=18, pady=(8, 10))

            self.min_seconds_entry.configure(state="normal")
            self.max_seconds_entry.configure(state="normal")
            self.scene_threshold_entry.configure(state="normal")
            self.smooth_switch.configure(state="normal")

        else:
            if self.scene_settings_row.winfo_manager():
                self.scene_settings_row.pack_forget()

            if self.smooth_row.winfo_manager():
                self.smooth_row.pack_forget()

            if not self.duration_settings_row.winfo_manager():
                self.duration_settings_row.pack(fill="x", padx=18, pady=(8, 10))

            self.seconds_entry.configure(state="normal")
            self.min_seconds_entry.configure(state="disabled")
            self.max_seconds_entry.configure(state="disabled")
            self.scene_threshold_entry.configure(state="disabled")
            self.smooth_switch.configure(state="disabled")

        self.update_smooth_ui()

    def choose_video(self):
        file_path = filedialog.askopenfilename(
            title="Chọn video",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"),
                ("All files", "*.*"),
            ],
        )

        if file_path:
            self.video_path_var.set(file_path)

            if not self.output_dir_var.get():
                self.output_dir_var.set(str(Path(file_path).parent / "output"))

    def choose_output_dir(self):
        folder_path = filedialog.askdirectory(title="Chọn thư mục xuất file")

        if folder_path:
            self.output_dir_var.set(folder_path)

    def log(self, message: str):
        self.log_queue.put(("log", message))

    def set_progress(self, value: float):
        self.log_queue.put(("progress", value))

    def set_current_process(self, process):
        with self.process_lock:
            self.current_process = process

    def terminate_current_process(self):
        with self.process_lock:
            process = self.current_process

        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                return

    def cancel_processing(self):
        if not (self.worker_thread and self.worker_thread.is_alive()):
            return

        if not self.cancel_event.is_set():
            self.cancel_event.set()
            self.log("Đã yêu cầu hủy xử lý.")

        self.cancel_button.configure(state="disabled")
        self.terminate_current_process()

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise ProcessingCancelled("Đã hủy xử lý.")

    def cleanup_cancelled_output_dir(self):
        output_dir = self.current_output_dir

        if output_dir is None:
            return

        if not re.search(r"_cut_\d{8}_\d{6}$", output_dir.name):
            self.log("Bỏ qua xóa dữ liệu tạm vì đường dẫn kết quả không hợp lệ.")
            self.current_output_dir = None
            return

        try:
            if self.current_output_dir.exists():
                shutil.rmtree(self.current_output_dir, ignore_errors=True)
                self.log("Đã xóa dữ liệu tạm của tiến trình bị hủy.")
        finally:
            if self.last_output_dir == output_dir:
                self.last_output_dir = None
            self.current_output_dir = None

    def open_last_output_dir(self):
        if self.last_output_dir is None or not self.last_output_dir.exists():
            self.log("Chưa có thư mục kết quả để mở.")
            self.open_output_button.configure(state="disabled")
            return

        try:
            os.startfile(str(self.last_output_dir))
        except Exception as error:
            error_message = f"Không mở được thư mục kết quả: {error}"
            self.log(error_message)
            messagebox.showerror("Lỗi", error_message)

    def process_log_queue(self):
        try:
            while True:
                action, value = self.log_queue.get_nowait()

                if action == "log":
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", value + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")

                elif action == "progress":
                    self.progress_bar.set(value)
                    self.progress_label.configure(text=f"{int(value * 100)}%")

                elif action == "done":
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if self.last_output_dir is not None and self.last_output_dir.exists():
                        self.open_output_button.configure(state="normal")
                    messagebox.showinfo("Hoàn thành", str(value))

                elif action == "error":
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.open_output_button.configure(state="disabled")
                    messagebox.showerror("Lỗi", str(value))

                elif action == "cancelled":
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.open_output_button.configure(state="disabled")
                    messagebox.showinfo("Đã hủy", str(value))

        except queue.Empty:
            pass

        self.after(100, self.process_log_queue)

    def validate_inputs(self):
        video_path_text = self.video_path_var.get().strip()
        output_dir_text = self.output_dir_var.get().strip()
        cut_type = self.cut_type_var.get()

        if not video_path_text:
            raise ValueError("Bạn chưa chọn video.")

        video_path = Path(video_path_text)
        if not video_path.exists():
            raise ValueError("Bạn chưa chọn video hợp lệ.")

        if not output_dir_text:
            raise ValueError("Bạn chưa chọn thư mục xuất file.")

        output_dir = Path(output_dir_text)

        try:
            output_folder_count = int(self.output_folder_count_var.get().strip())
        except ValueError:
            raise ValueError("Output folder phải là số nguyên.")

        if output_folder_count < 1:
            raise ValueError("Output folder phải lớn hơn hoặc bằng 1.")

        segment_seconds = None
        min_seconds = None
        max_seconds = None
        scene_threshold = None
        smooth_enabled = False
        smooth_seconds = 0.0
        smooth_mode = self.smooth_mode_var.get()

        if cut_type == CUT_FIXED:
            try:
                segment_seconds = float(self.seconds_var.get().strip())
            except ValueError:
                raise ValueError("Thời lượng mỗi cảnh phải là số.")

            if segment_seconds <= 0:
                raise ValueError("Thời lượng mỗi cảnh phải lớn hơn 0.")

        elif cut_type == CUT_BY_SCENE:
            try:
                min_seconds = float(self.min_seconds_var.get().strip())
                max_seconds = float(self.max_seconds_var.get().strip())
                scene_threshold = float(self.scene_threshold_var.get().strip())
            except ValueError:
                raise ValueError("Min, Max và Scene threshold phải là số.")

            if min_seconds <= 0:
                raise ValueError("Min (s) phải lớn hơn 0.")

            if max_seconds <= min_seconds:
                raise ValueError("Max (s) phải lớn hơn Min (s).")

            if not 0 < scene_threshold < 1:
                raise ValueError("Scene threshold phải lớn hơn 0 và nhỏ hơn 1.")

            smooth_enabled = bool(self.smooth_enabled_var.get())

            if smooth_enabled:
                try:
                    smooth_seconds = float(self.smooth_seconds_var.get().strip())
                except ValueError:
                    raise ValueError("Số giây làm mượt phải là số.")

                if smooth_seconds < 0:
                    raise ValueError("Số giây làm mượt phải lớn hơn hoặc bằng 0.")

                if smooth_mode not in [SMOOTH_TRIM_TAIL, SMOOTH_TRIM_HEAD]:
                    raise ValueError("Kiểu làm mượt không hợp lệ.")

        else:
            raise ValueError("Kiểu cắt không hợp lệ.")

        return (
            video_path,
            output_dir,
            cut_type,
            segment_seconds,
            min_seconds,
            max_seconds,
            scene_threshold,
            output_folder_count,
            bool(self.remove_audio_var.get()),
            smooth_enabled,
            smooth_seconds,
            smooth_mode,
        )

    def start_processing(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Đang chạy", "Tool đang xử lý video.")
            return

        try:
            (
                video_path,
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
                smooth_mode,
            ) = self.validate_inputs()
        except Exception as error:
            messagebox.showerror("Lỗi nhập liệu", str(error))
            return

        self.cancel_event.clear()
        self.set_current_process(None)
        self.current_output_dir = None
        self.last_output_dir = None

        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.open_output_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="0%")

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        self.worker_thread = threading.Thread(
            target=self.process_video,
            args=(
                video_path,
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
                smooth_mode,
            ),
            daemon=True,
        )
        self.worker_thread.start()

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

    def build_scene_segment_command(
        self,
        ffmpeg_path: str,
        video_path: Path,
        temp_pattern: Path,
        segment_times: list[float],
        max_seconds: float,
        duration: float,
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
            command += ["-an"]
        else:
            command += ["-map", "0:a?"]

        command += [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
        ]

        if segment_times:
            segment_times_text = format_split_times(segment_times)
            command += ["-force_key_frames", segment_times_text]

        if not remove_audio:
            command += [
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]

        command += ["-f", "segment"]

        if segment_times:
            command += [
                "-segment_times",
                format_split_times(segment_times),
                "-segment_time_delta",
                "0.05",
            ]
        else:
            command += [
                "-segment_time",
                str(max(duration + 1, max_seconds)),
            ]

        command += [
            "-reset_timestamps",
            "1",
            "-segment_start_number",
            "1",
            "-segment_format",
            "mp4",
            "-segment_format_options",
            "movflags=+faststart",
            str(temp_pattern),
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

    def process_video(
        self,
        video_path: Path,
        output_dir: Path,
        cut_type: str,
        segment_seconds: float | None,
        min_seconds: float | None,
        max_seconds: float | None,
        scene_threshold: float | None,
        output_folder_count: int,
        remove_audio: bool,
        smooth_enabled: bool,
        smooth_seconds: float,
        smooth_mode: str,
    ):
        temp_dir = None

        try:
            ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
            self.check_cancelled()

            video_name = safe_filename(video_path.name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            project_output_dir = output_dir / f"{video_name}_cut_{timestamp}"
            project_output_dir.mkdir(parents=True, exist_ok=True)
            self.current_output_dir = project_output_dir

            temp_dir = project_output_dir / "temp_scenes"
            temp_dir.mkdir(parents=True, exist_ok=True)

            output_folders = self.create_output_folders(
                project_output_dir,
                output_folder_count,
            )

            self.log("Bắt đầu xử lý video.")
            self.log(f"Video đầu vào: {video_path}")
            self.log(f"Thư mục xuất: {project_output_dir}")
            self.log(f"Kiểu cắt: {cut_type}")
            self.log(f"Output folder count: {output_folder_count}")
            self.log(f"Xóa audio: {on_off(remove_audio)}")

            duration = get_video_duration(video_path, ffprobe_path)
            self.check_cancelled()
            self.log(f"Thời lượng video: {duration:.2f} giây")

            if duration <= 0:
                raise RuntimeError("Video không có thời lượng hợp lệ.")

            temp_pattern = temp_dir / "scene_%03d.mp4"
            discard_smooth_segments = False
            dropped_smooth_segment_count = 0
            segment_progress_start = 0.05

            if cut_type == CUT_FIXED:
                if segment_seconds is None:
                    raise RuntimeError("Thiếu thời lượng cắt cố định.")

                expected_temp_segments = math.ceil(duration / segment_seconds)
                total_scenes = expected_temp_segments

                self.log(f"Thời lượng mỗi cảnh: {segment_seconds} giây")
                self.log("Chế độ cố định dùng -c copy để xử lý nhanh.")

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
                    raise RuntimeError("Thiếu thông số cắt theo chuyển cảnh.")

                self.log("Chế độ chuyển cảnh encode lại để ép keyframe và cắt chính xác hơn.")
                self.log(f"Min seconds: {min_seconds}")
                self.log(f"Max seconds: {max_seconds}")
                self.log(f"Scene threshold: {scene_threshold}")
                self.log(f"Làm mượt: {on_off(smooth_enabled)}")
                self.log("Đang quét điểm chuyển cảnh...")
                self.set_progress(0.02)

                scene_times = detect_scene_changes(
                    video_path,
                    ffmpeg_path,
                    scene_threshold,
                    self.cancel_event,
                    self.set_current_process,
                )
                self.check_cancelled()
                self.set_progress(0.10)
                self.log(f"Số điểm chuyển cảnh phát hiện: {len(scene_times)}")

                split_times = build_scene_split_times(
                    scene_times,
                    duration,
                    min_seconds,
                    max_seconds,
                )
                split_times = normalize_split_times(split_times, duration)
                self.log(f"Số split_times tạo ra: {len(split_times)}")

                segment_times = split_times

                if smooth_enabled:
                    self.log(f"smooth_seconds: {smooth_seconds}")
                    self.log(f"Kiểu làm mượt: {smooth_mode}")

                    boundary_times, boundary_examples = build_smooth_boundary_times(
                        split_times,
                        duration,
                        smooth_seconds,
                        smooth_mode,
                    )
                    self.log(f"Số boundary_times: {len(boundary_times)}")

                    if boundary_examples:
                        for split_time, left, right in boundary_examples[:5]:
                            self.log(
                                f"Mốc {split_time:.3f}s -> "
                                f"{left:.3f}s, {right:.3f}s"
                            )

                    if boundary_times:
                        segment_times = boundary_times
                        discard_smooth_segments = True
                    else:
                        self.log(
                            "Không có boundary_times hợp lệ, xử lý như không làm mượt."
                        )

                expected_temp_segments = len(segment_times) + 1
                total_scenes = (
                    sum(1 for index in range(expected_temp_segments) if index % 2 == 0)
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
                )

            else:
                raise RuntimeError("Kiểu cắt không hợp lệ.")

            if total_scenes <= 0:
                raise RuntimeError("Video không có segment hợp lệ.")

            self.log(f"Tổng số segment tạm dự kiến: {expected_temp_segments}")
            self.log(f"Tổng số segment giữ dự kiến: {total_scenes}")
            self.log("Đang cắt video bằng một lệnh FFmpeg segment...")
            self.set_progress(segment_progress_start)
            self.check_cancelled()

            def update_segment_progress(value: float):
                self.set_progress(
                    segment_progress_start + value * (0.75 - segment_progress_start)
                )

            run_ffmpeg_segment(
                segment_command,
                duration,
                update_segment_progress,
                self.cancel_event,
                self.set_current_process,
            )
            self.check_cancelled()
            self.set_progress(0.75)
            self.log("FFmpeg đã tạo xong các segment tạm.")

            temp_files = sorted(temp_dir.glob("scene_*.mp4"))

            if not temp_files:
                raise RuntimeError("FFmpeg đã chạy xong nhưng không tạo file cảnh nào.")

            self.log(f"Số segment tạm thực tế: {len(temp_files)}")

            if len(temp_files) != expected_temp_segments:
                self.log(
                    "Lưu ý: số segment tạm "
                    f"({len(temp_files)}) khác dự kiến ({expected_temp_segments})."
                )

            exported_count = 0
            kept_segment_count = 0

            for temp_index, temp_file in enumerate(temp_files):
                self.check_cancelled()

                if discard_smooth_segments and temp_index % 2 == 1:
                    dropped_smooth_segment_count += 1
                    self.log(f"Bỏ segment làm mượt tạm {temp_index}: {temp_file.name}")
                    self.set_progress(
                        0.75 + ((temp_index + 1) / len(temp_files)) * 0.25
                    )
                    continue

                kept_segment_count += 1
                scene_number = kept_segment_count
                folder_index = ((scene_number - 1) % output_folder_count) + 1
                target_dir = output_folders[folder_index - 1]
                output_file = target_dir / f"{scene_number:03d}_{video_name}.mp4"

                self.log(
                    f"Xuất cảnh {scene_number:03d} -> "
                    f"{target_dir.name}/{output_file.name}"
                )
                shutil.move(str(temp_file), str(output_file))

                exported_count += 1
                self.set_progress(
                    0.75 + ((temp_index + 1) / len(temp_files)) * 0.25
                )

            self.set_progress(1)

            self.log("")
            self.log("HOÀN THÀNH.")
            self.log(f"Số segment giữ: {kept_segment_count}")
            if smooth_enabled:
                self.log(f"Số segment bỏ do làm mượt: {dropped_smooth_segment_count}")
            self.log(f"Số file đã xuất: {exported_count}")
            self.log(f"Folder kết quả: {project_output_dir}")
            self.last_output_dir = project_output_dir

            self.log_queue.put(
                (
                    "done",
                    f"Đã cắt xong video.\n\nKết quả nằm tại:\n{project_output_dir}",
                )
            )

        except ProcessingCancelled:
            self.log("Đã hủy xử lý.")
            self.cleanup_cancelled_output_dir()
            self.log_queue.put(("cancelled", "Đã hủy xử lý."))

        except subprocess.CalledProcessError as error:
            if self.cancel_event.is_set():
                self.log("Đã hủy xử lý.")
                self.cleanup_cancelled_output_dir()
                self.log_queue.put(("cancelled", "Đã hủy xử lý."))
                return

            error_text = error.stderr if error.stderr else str(error)
            self.log_queue.put(("error", f"FFmpeg bị lỗi:\n{error_text}"))

        except Exception as error:
            if self.cancel_event.is_set():
                self.log("Đã hủy xử lý.")
                self.cleanup_cancelled_output_dir()
                self.log_queue.put(("cancelled", "Đã hủy xử lý."))
                return

            self.log_queue.put(("error", str(error)))

        finally:
            self.set_current_process(None)

            if temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    app = VideoCutterApp()
    app.mainloop()
