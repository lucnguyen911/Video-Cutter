import math
import queue
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, filedialog, messagebox

import customtkinter as ctk


APP_TITLE = "Video Scene Cutter"
CUT_BY_DURATION = "Cắt theo thời lượng"
CUT_BY_SCENE_FAST = "Cắt theo chuyển cảnh nhanh"
CUT_BY_SCENE_ACCURATE = "Cắt theo chuyển cảnh chính xác"
SCENE_CUT_TYPES = {CUT_BY_SCENE_FAST, CUT_BY_SCENE_ACCURATE}
MIN_BOUNDARY_GAP = 0.01


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


def find_ffmpeg_tools():
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError(
            "Khong tim thay ffmpeg hoac ffprobe. "
            "Hay cai FFmpeg va dam bao ffmpeg chay duoc trong Terminal."
        )

    return ffmpeg_path, ffprobe_path


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
):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stderr_lines = []

    def collect_stderr():
        if process.stderr is None:
            return

        for line in process.stderr:
            stderr_lines.append(line)

    stderr_thread = threading.Thread(target=collect_stderr, daemon=True)
    stderr_thread.start()

    try:
        if process.stdout is not None:
            for raw_line in process.stdout:
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

        return_code = process.wait()
        stderr_thread.join(timeout=2)

    except Exception:
        process.kill()
        stderr_thread.join(timeout=2)
        raise

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
) -> list[float]:
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

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )

    scene_times = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr):
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
) -> tuple[list[float], list[tuple[float, float, float]]]:
    if smooth_seconds <= 0:
        return [], []

    boundary_times = []
    examples = []
    last_boundary_time = 0.0

    for split_time in normalize_split_times(split_times, duration):
        left = round(split_time - smooth_seconds, 3)
        right = round(split_time + smooth_seconds, 3)

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


class VideoCutterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("820x620")
        self.minsize(760, 560)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.video_path_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar()
        self.seconds_var = ctk.StringVar(value="3")
        self.mode_var = ctk.StringVar(value="Tách cả cảnh lẻ và cảnh chẵn")
        self.cut_type_var = ctk.StringVar(value=CUT_BY_DURATION)
        self.min_seconds_var = ctk.StringVar(value="2")
        self.max_seconds_var = ctk.StringVar(value="5")
        self.scene_threshold_var = ctk.StringVar(value="0.35")
        self.smooth_enabled_var = BooleanVar(value=False)
        self.smooth_seconds_var = ctk.StringVar(value="0.1")

        self.log_queue = queue.Queue()
        self.worker_thread = None

        self.build_ui()
        self.after(100, self.process_log_queue)

    def build_ui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        title_label = ctk.CTkLabel(
            main_frame,
            text="Video Scene Cutter",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(anchor="w", padx=16, pady=(16, 8))

        desc_label = ctk.CTkLabel(
            main_frame,
            text="Cắt video theo số giây mong muốn, tự động đánh số cảnh và tách cảnh lẻ/chẵn.",
            font=ctk.CTkFont(size=14),
        )
        desc_label.pack(anchor="w", padx=16, pady=(0, 16))

        # Video input
        video_row = ctk.CTkFrame(main_frame)
        video_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(video_row, text="Video đầu vào:", width=120).pack(
            side="left", padx=(8, 6)
        )

        video_entry = ctk.CTkEntry(video_row, textvariable=self.video_path_var)
        video_entry.pack(side="left", fill="x", expand=True, padx=6)

        ctk.CTkButton(
            video_row,
            text="Chọn video",
            width=120,
            command=self.choose_video,
        ).pack(side="left", padx=(6, 8))

        # Output folder
        output_row = ctk.CTkFrame(main_frame)
        output_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(output_row, text="Thư mục xuất:", width=120).pack(
            side="left", padx=(8, 6)
        )

        output_entry = ctk.CTkEntry(output_row, textvariable=self.output_dir_var)
        output_entry.pack(side="left", fill="x", expand=True, padx=6)

        ctk.CTkButton(
            output_row,
            text="Chọn thư mục",
            width=120,
            command=self.choose_output_dir,
        ).pack(side="left", padx=(6, 8))

        # Cut settings
        cut_type_row = ctk.CTkFrame(main_frame)
        cut_type_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(cut_type_row, text="Kiểu cắt:", width=140).pack(
            side="left", padx=(8, 6)
        )

        cut_type_menu = ctk.CTkOptionMenu(
            cut_type_row,
            variable=self.cut_type_var,
            values=[
                CUT_BY_DURATION,
                CUT_BY_SCENE_FAST,
                CUT_BY_SCENE_ACCURATE,
            ],
            command=self.update_cut_mode_ui,
            width=240,
        )
        cut_type_menu.pack(side="left", padx=6)

        accuracy_note = ctk.CTkLabel(
            main_frame,
            text=(
                "Cắt theo thời lượng dùng -c copy nhanh nhất. "
                "Chuyển cảnh nhanh dùng -c copy; chuyển cảnh chính xác encode lại."
            ),
            font=ctk.CTkFont(size=12),
        )
        accuracy_note.pack(anchor="w", padx=16, pady=(0, 4))

        self.duration_settings_row = ctk.CTkFrame(main_frame)
        self.duration_settings_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            self.duration_settings_row,
            text="Số giây mỗi cảnh:",
            width=140,
        ).pack(side="left", padx=(8, 6))

        self.seconds_entry = ctk.CTkEntry(
            self.duration_settings_row,
            textvariable=self.seconds_var,
            width=100,
        )
        self.seconds_entry.pack(side="left", padx=6)

        self.scene_settings_row = ctk.CTkFrame(main_frame)
        self.scene_settings_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            self.scene_settings_row,
            text="Min clip seconds:",
            width=140,
        ).pack(side="left", padx=(8, 6))

        self.min_seconds_entry = ctk.CTkEntry(
            self.scene_settings_row,
            textvariable=self.min_seconds_var,
            width=70,
        )
        self.min_seconds_entry.pack(side="left", padx=6)

        ctk.CTkLabel(
            self.scene_settings_row,
            text="Max clip seconds:",
            width=130,
        ).pack(side="left", padx=(18, 6))

        self.max_seconds_entry = ctk.CTkEntry(
            self.scene_settings_row,
            textvariable=self.max_seconds_var,
            width=70,
        )
        self.max_seconds_entry.pack(side="left", padx=6)

        ctk.CTkLabel(
            self.scene_settings_row,
            text="Scene threshold:",
            width=120,
        ).pack(side="left", padx=(18, 6))

        self.scene_threshold_entry = ctk.CTkEntry(
            self.scene_settings_row,
            textvariable=self.scene_threshold_var,
            width=70,
        )
        self.scene_threshold_entry.pack(side="left", padx=6)

        self.smooth_row = ctk.CTkFrame(main_frame)
        self.smooth_row.pack(fill="x", padx=16, pady=8)

        self.smooth_switch = ctk.CTkSwitch(
            self.smooth_row,
            text="Làm mượt",
            variable=self.smooth_enabled_var,
            command=self.update_cut_mode_ui,
        )
        self.smooth_switch.pack(side="left", padx=(8, 6))

        self.smooth_seconds_row = ctk.CTkFrame(main_frame)
        self.smooth_seconds_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            self.smooth_seconds_row,
            text="Vùng làm mượt quanh điểm cắt (giây):",
            width=260,
        ).pack(side="left", padx=(8, 6))

        self.smooth_seconds_entry = ctk.CTkEntry(
            self.smooth_seconds_row,
            textvariable=self.smooth_seconds_var,
            width=80,
        )
        self.smooth_seconds_entry.pack(side="left", padx=6)

        self.mode_row = ctk.CTkFrame(main_frame)
        self.mode_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(self.mode_row, text="Chế độ xuất:", width=140).pack(
            side="left", padx=(8, 6)
        )

        mode_menu = ctk.CTkOptionMenu(
            self.mode_row,
            variable=self.mode_var,
            values=[
                "Tách cả cảnh lẻ và cảnh chẵn",
                "Chỉ lấy cảnh lẻ",
                "Chỉ lấy cảnh chẵn",
            ],
            width=240,
        )
        mode_menu.pack(side="left", padx=6)
        self.update_cut_mode_ui()

        # Buttons
        button_row = ctk.CTkFrame(main_frame)
        button_row.pack(fill="x", padx=16, pady=12)

        self.start_button = ctk.CTkButton(
            button_row,
            text="Bắt đầu cắt video",
            height=40,
            command=self.start_processing,
        )
        self.start_button.pack(side="left", padx=8)

        self.progress_bar = ctk.CTkProgressBar(button_row)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=12)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(button_row, text="0%")
        self.progress_label.pack(side="left", padx=8)

        # Log
        log_label = ctk.CTkLabel(
            main_frame,
            text="Nhật ký xử lý:",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        log_label.pack(anchor="w", padx=16, pady=(8, 4))

        self.log_box = ctk.CTkTextbox(main_frame, height=260)
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def update_cut_mode_ui(self, _=None):
        is_scene_cut = self.cut_type_var.get() in SCENE_CUT_TYPES

        if is_scene_cut:
            if self.duration_settings_row.winfo_manager():
                self.duration_settings_row.pack_forget()

            if not self.scene_settings_row.winfo_manager():
                self.scene_settings_row.pack(
                    fill="x",
                    padx=16,
                    pady=8,
                    before=self.mode_row,
                )

            if not self.smooth_row.winfo_manager():
                self.smooth_row.pack(
                    fill="x",
                    padx=16,
                    pady=8,
                    before=self.mode_row,
                )

            if self.smooth_enabled_var.get():
                if not self.smooth_seconds_row.winfo_manager():
                    self.smooth_seconds_row.pack(
                        fill="x",
                        padx=16,
                        pady=8,
                        before=self.mode_row,
                    )
                self.smooth_seconds_entry.configure(state="normal")
            else:
                if self.smooth_seconds_row.winfo_manager():
                    self.smooth_seconds_row.pack_forget()
                self.smooth_seconds_entry.configure(state="disabled")

            self.seconds_entry.configure(state="disabled")
            self.min_seconds_entry.configure(state="normal")
            self.max_seconds_entry.configure(state="normal")
            self.scene_threshold_entry.configure(state="normal")
            self.smooth_switch.configure(state="normal")
        else:
            if self.scene_settings_row.winfo_manager():
                self.scene_settings_row.pack_forget()

            if self.smooth_row.winfo_manager():
                self.smooth_row.pack_forget()

            if self.smooth_seconds_row.winfo_manager():
                self.smooth_seconds_row.pack_forget()

            if not self.duration_settings_row.winfo_manager():
                self.duration_settings_row.pack(
                    fill="x",
                    padx=16,
                    pady=8,
                    before=self.mode_row,
                )

            self.seconds_entry.configure(state="normal")
            self.min_seconds_entry.configure(state="disabled")
            self.max_seconds_entry.configure(state="disabled")
            self.scene_threshold_entry.configure(state="disabled")
            self.smooth_switch.configure(state="disabled")
            self.smooth_seconds_entry.configure(state="disabled")

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
                    messagebox.showinfo("Hoàn thành", str(value))

                elif action == "error":
                    self.start_button.configure(state="normal")
                    messagebox.showerror("Lỗi", str(value))

        except queue.Empty:
            pass

        self.after(100, self.process_log_queue)

    def validate_inputs(self):
        video_path = Path(self.video_path_var.get().strip())
        output_dir = Path(self.output_dir_var.get().strip())
        cut_type = self.cut_type_var.get()

        if not video_path.exists():
            raise ValueError("Bạn chưa chọn video hợp lệ.")

        if not output_dir:
            raise ValueError("Bạn chưa chọn thư mục xuất file.")

        segment_seconds = None
        min_seconds = None
        max_seconds = None
        scene_threshold = None
        smooth_enabled = False
        smooth_seconds = 0.0

        if cut_type == CUT_BY_DURATION:
            try:
                segment_seconds = float(self.seconds_var.get().strip())
            except ValueError:
                raise ValueError("Số giây mỗi cảnh phải là số.")

            if segment_seconds <= 0:
                raise ValueError("Số giây mỗi cảnh phải lớn hơn 0.")

        elif cut_type in SCENE_CUT_TYPES:
            try:
                min_seconds = float(self.min_seconds_var.get().strip())
                max_seconds = float(self.max_seconds_var.get().strip())
                scene_threshold = float(self.scene_threshold_var.get().strip())
            except ValueError:
                raise ValueError(
                    "Min clip seconds, Max clip seconds và Scene threshold phải là số."
                )

            if min_seconds <= 0:
                raise ValueError("Min clip seconds phải lớn hơn 0.")

            if max_seconds <= min_seconds:
                raise ValueError("Max clip seconds phải lớn hơn Min clip seconds.")

            if not 0 < scene_threshold < 1:
                raise ValueError("Scene threshold phải lớn hơn 0 và nhỏ hơn 1.")

            smooth_enabled = bool(self.smooth_enabled_var.get())

            if smooth_enabled:
                try:
                    smooth_seconds = float(self.smooth_seconds_var.get().strip())
                except ValueError:
                    raise ValueError("Vùng làm mượt quanh điểm cắt phải là số.")

                if smooth_seconds < 0:
                    raise ValueError("Vùng làm mượt quanh điểm cắt phải lớn hơn hoặc bằng 0.")

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
            smooth_enabled,
            smooth_seconds,
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
                smooth_enabled,
                smooth_seconds,
            ) = self.validate_inputs()
        except Exception as error:
            messagebox.showerror("Lỗi nhập liệu", str(error))
            return

        self.start_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="0%")

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        mode = self.mode_var.get()

        self.worker_thread = threading.Thread(
            target=self.process_video,
            args=(
                video_path,
                output_dir,
                mode,
                cut_type,
                segment_seconds,
                min_seconds,
                max_seconds,
                scene_threshold,
                smooth_enabled,
                smooth_seconds,
            ),
            daemon=True,
        )
        self.worker_thread.start()

    def process_video(
        self,
        video_path: Path,
        output_dir: Path,
        mode: str,
        cut_type: str,
        segment_seconds: float | None,
        min_seconds: float | None,
        max_seconds: float | None,
        scene_threshold: float | None,
        smooth_enabled: bool,
        smooth_seconds: float,
    ):
        temp_dir = None

        try:
            ffmpeg_path, ffprobe_path = find_ffmpeg_tools()

            video_name = safe_filename(video_path.name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            project_output_dir = output_dir / f"{video_name}_cut_{timestamp}"
            project_output_dir.mkdir(parents=True, exist_ok=True)

            odd_dir = project_output_dir / "odd_scenes"
            even_dir = project_output_dir / "even_scenes"
            temp_dir = project_output_dir / "temp_scenes"
            temp_dir.mkdir(parents=True, exist_ok=True)

            if mode in ["Tách cả cảnh lẻ và cảnh chẵn", "Chỉ lấy cảnh lẻ"]:
                odd_dir.mkdir(parents=True, exist_ok=True)

            if mode in ["Tách cả cảnh lẻ và cảnh chẵn", "Chỉ lấy cảnh chẵn"]:
                even_dir.mkdir(parents=True, exist_ok=True)

            self.log("Bat dau xu ly video.")
            self.log(f"Video: {video_path}")
            self.log(f"Thu muc xuat: {project_output_dir}")
            self.log(f"Che do: {mode}")
            self.log(f"Kieu cat: {cut_type}")

            duration = get_video_duration(video_path, ffprobe_path)

            self.log(f"Thoi luong video: {duration:.2f} giay")

            if duration <= 0:
                raise RuntimeError("Video khong co thoi luong hop le.")

            temp_pattern = temp_dir / "scene_%03d.mp4"
            discard_smooth_segments = False
            base_command = [
                ffmpeg_path,
                "-y",
                "-progress",
                "pipe:1",
                "-nostats",
                "-i",
                str(video_path),

                "-map",
                "0:v:0",
                "-map",
                "0:a?",
            ]

            if cut_type == CUT_BY_DURATION:
                self.log(
                    "Che do cat theo thoi luong: dung -c copy, "
                    "nhanh nhat, co the lech nhe theo keyframe."
                )
                self.log(f"So giay moi canh: {segment_seconds}")
                total_scenes = math.ceil(duration / segment_seconds)
                expected_temp_segments = total_scenes
                segment_progress_start = 0.05
                self.log("Encoder dang dung: -c copy")
                segment_command = base_command + [
                    "-c",
                    "copy",
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
            else:
                if cut_type == CUT_BY_SCENE_FAST:
                    self.log(
                        "Che do chuyen canh nhanh: dung -c copy, "
                        "co the lech nhe theo keyframe."
                    )
                    self.log("Encoder dang dung: -c copy")
                else:
                    self.log(
                        "Che do chuyen canh chinh xac: "
                        "encode lai de ep keyframe tai diem cat."
                    )
                    self.log("Encoder dang dung: libx264")
                self.log(f"Min clip seconds: {min_seconds}")
                self.log(f"Max clip seconds: {max_seconds}")
                self.log(f"Threshold dang dung: {scene_threshold}")
                self.log("Dang quet diem chuyen canh...")
                self.set_progress(0.02)

                scene_times = detect_scene_changes(video_path, ffmpeg_path, scene_threshold)
                self.set_progress(0.10)
                self.log(f"So diem chuyen canh phat hien duoc: {len(scene_times)}")

                if scene_times:
                    split_times = build_scene_split_times(
                        scene_times,
                        duration,
                        min_seconds,
                        max_seconds,
                    )
                else:
                    self.log(
                        "Khong phat hien duoc chuyen canh, "
                        "fallback ve cat theo max seconds."
                    )
                    split_times = build_duration_split_times(duration, max_seconds)

                split_times = normalize_split_times(split_times, duration)
                self.log(f"So moc cat duoc tao ra: {len(split_times)}")

                segment_times = split_times

                if smooth_enabled:
                    self.log(f"smooth_seconds: {smooth_seconds}")

                    if smooth_seconds == 0:
                        self.log("Lam muot = 0, xu ly nhu khong lam muot.")
                    else:
                        boundary_times, boundary_examples = build_smooth_boundary_times(
                            split_times,
                            duration,
                            smooth_seconds,
                        )
                        self.log(
                            "So moc boundary sau khi tao left/right: "
                            f"{len(boundary_times)}"
                        )

                        for split_time, left, right in boundary_examples[:5]:
                            self.log(
                                "Scene boundary "
                                f"{split_time:.3f}s -> cut points "
                                f"{left:.3f}s and {right:.3f}s"
                            )

                        if boundary_times:
                            segment_times = boundary_times
                            discard_smooth_segments = True
                        else:
                            self.log(
                                "Khong tao duoc boundary hop le, "
                                "xu ly nhu khong lam muot."
                            )

                segment_times_text = format_split_times(segment_times)
                expected_temp_segments = len(segment_times) + 1
                total_scenes = (
                    sum(1 for index in range(expected_temp_segments) if index % 2 == 0)
                    if discard_smooth_segments
                    else expected_temp_segments
                )
                segment_progress_start = 0.12

                segment_time_args = (
                    [
                        "-segment_times",
                        segment_times_text,
                    ]
                    if segment_times
                    else [
                        "-segment_time",
                        str(max_seconds),
                    ]
                )

                if cut_type == CUT_BY_SCENE_FAST:
                    segment_command = (
                        base_command
                        + [
                            "-c",
                            "copy",
                            "-f",
                            "segment",
                        ]
                        + segment_time_args
                        + [
                            "-reset_timestamps",
                            "1",
                            "-segment_start_number",
                            "1",
                            "-segment_format",
                            "mp4",
                            str(temp_pattern),
                        ]
                    )
                else:
                    scene_encode_args = [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-crf",
                        "23",
                    ]
                    force_keyframe_args = (
                        [
                            "-force_key_frames",
                            segment_times_text,
                        ]
                        if segment_times
                        else []
                    )
                    audio_encode_args = [
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                    ]
                    accurate_segment_time_args = (
                        [
                            "-segment_times",
                            segment_times_text,
                            "-segment_time_delta",
                            "0.05",
                        ]
                        if segment_times
                        else [
                            "-segment_time",
                            str(max_seconds),
                        ]
                    )
                    segment_command = (
                        base_command
                        + scene_encode_args
                        + force_keyframe_args
                        + audio_encode_args
                        + [
                            "-f",
                            "segment",
                        ]
                        + accurate_segment_time_args
                        + [
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
                    )

            if total_scenes <= 0:
                raise RuntimeError("Video khong co thoi luong hop le.")

            self.log(f"Tong so canh du kien: {total_scenes}")
            self.log(f"Tong so segment tam du kien: {expected_temp_segments}")

            self.log("Dang cat video bang mot lenh FFmpeg segment...")
            self.set_progress(segment_progress_start)

            def update_segment_progress(value: float):
                self.set_progress(
                    segment_progress_start + value * (0.75 - segment_progress_start)
                )

            run_ffmpeg_segment(segment_command, duration, update_segment_progress)
            self.set_progress(0.75)
            self.log("FFmpeg da tao xong cac canh tam.")

            temp_files = sorted(temp_dir.glob("scene_*.mp4"))

            if not temp_files:
                raise RuntimeError("FFmpeg da chay xong nhung khong tao file canh nao.")

            self.log(f"So canh tam thuc te: {len(temp_files)}")

            if len(temp_files) != expected_temp_segments:
                self.log(
                    "Luu y: so segment tam "
                    f"({len(temp_files)}) khac du kien ({expected_temp_segments})."
                )

            exported_count = 0
            skipped_count = 0
            kept_segment_count = 0
            dropped_smooth_segment_count = 0

            for temp_index, temp_file in enumerate(temp_files):
                if discard_smooth_segments and temp_index % 2 == 1:
                    dropped_smooth_segment_count += 1
                    self.log(
                        "Bo segment lam muot tam "
                        f"{temp_index + 1:03d}: {temp_file.name}"
                    )
                    self.set_progress(
                        0.75 + ((temp_index + 1) / len(temp_files)) * 0.25
                    )
                    continue

                kept_segment_count += 1
                scene_number = kept_segment_count
                is_odd = scene_number % 2 == 1
                is_even = scene_number % 2 == 0

                should_export = False

                if mode == "Tách cả cảnh lẻ và cảnh chẵn":
                    should_export = True
                elif mode == "Chỉ lấy cảnh lẻ" and is_odd:
                    should_export = True
                elif mode == "Chỉ lấy cảnh chẵn" and is_even:
                    should_export = True

                if not should_export:
                    skipped_count += 1
                    self.log(f"Bo qua canh {scene_number:03d}")
                    self.set_progress(
                        0.75 + ((temp_index + 1) / len(temp_files)) * 0.25
                    )
                    continue

                if is_odd:
                    target_dir = odd_dir
                else:
                    target_dir = even_dir

                output_file = target_dir / f"{scene_number:03d}_{video_name}.mp4"

                self.log(
                    f"Chuyen canh {scene_number:03d} -> "
                    f"{target_dir.name}/{output_file.name}"
                )
                shutil.move(str(temp_file), str(output_file))

                exported_count += 1
                self.set_progress(
                    0.75 + ((temp_index + 1) / len(temp_files)) * 0.25
                )

            self.set_progress(1)

            self.log("")
            self.log("HOAN THANH.")
            self.log(f"So segment giu: {kept_segment_count}")
            self.log(f"So segment bo: {dropped_smooth_segment_count}")
            self.log(f"So canh da xuat: {exported_count}")
            self.log(f"So canh bo qua: {skipped_count}")
            self.log(f"Ket qua nam tai: {project_output_dir}")

            self.log_queue.put(
                (
                    "done",
                    f"Đã cắt xong video.\n\nKết quả nằm tại:\n{project_output_dir}",
                )
            )

        except subprocess.CalledProcessError as error:
            error_text = error.stderr if error.stderr else str(error)
            self.log_queue.put(("error", f"FFmpeg bị lỗi:\n{error_text}"))

        except Exception as error:
            self.log_queue.put(("error", str(error)))

        finally:
            if temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    app = VideoCutterApp()
    app.mainloop()
