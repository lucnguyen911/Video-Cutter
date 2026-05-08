import math
import queue
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk


APP_TITLE = "Video Scene Cutter"
SPEED_FAST = "Nhanh - không encode lại"
SPEED_STANDARD = "Chuẩn - encode lại"


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
        self.speed_var = ctk.StringVar(value=SPEED_FAST)

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

        # Settings
        settings_row = ctk.CTkFrame(main_frame)
        settings_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(settings_row, text="Số giây mỗi cảnh:", width=140).pack(
            side="left", padx=(8, 6)
        )

        seconds_entry = ctk.CTkEntry(
            settings_row,
            textvariable=self.seconds_var,
            width=100,
        )
        seconds_entry.pack(side="left", padx=6)

        ctk.CTkLabel(settings_row, text="Chế độ xuất:", width=100).pack(
            side="left", padx=(24, 6)
        )

        mode_menu = ctk.CTkOptionMenu(
            settings_row,
            variable=self.mode_var,
            values=[
                "Tách cả cảnh lẻ và cảnh chẵn",
                "Chỉ lấy cảnh lẻ",
                "Chỉ lấy cảnh chẵn",
            ],
            width=240,
        )
        mode_menu.pack(side="left", padx=6)

        speed_row = ctk.CTkFrame(main_frame)
        speed_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(speed_row, text="Tốc độ xử lý:", width=140).pack(
            side="left", padx=(8, 6)
        )

        speed_menu = ctk.CTkOptionMenu(
            speed_row,
            variable=self.speed_var,
            values=[
                SPEED_FAST,
                SPEED_STANDARD,
            ],
            width=240,
        )
        speed_menu.pack(side="left", padx=6)

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

        if not video_path.exists():
            raise ValueError("Bạn chưa chọn video hợp lệ.")

        if not output_dir:
            raise ValueError("Bạn chưa chọn thư mục xuất file.")

        try:
            seconds = float(self.seconds_var.get().strip())
        except ValueError:
            raise ValueError("Số giây mỗi cảnh phải là số.")

        if seconds <= 0:
            raise ValueError("Số giây mỗi cảnh phải lớn hơn 0.")

        return video_path, output_dir, seconds

    def start_processing(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Đang chạy", "Tool đang xử lý video.")
            return

        try:
            video_path, output_dir, seconds = self.validate_inputs()
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
        speed_mode = self.speed_var.get()

        self.worker_thread = threading.Thread(
            target=self.process_video,
            args=(video_path, output_dir, seconds, mode, speed_mode),
            daemon=True,
        )
        self.worker_thread.start()

    def process_video(
        self,
        video_path: Path,
        output_dir: Path,
        segment_seconds: float,
        mode: str,
        speed_mode: str,
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
            self.log(f"So giay moi canh: {segment_seconds}")
            self.log(f"Che do: {mode}")
            self.log(f"Toc do xu ly: {speed_mode}")

            duration = get_video_duration(video_path, ffprobe_path)
            total_scenes = math.ceil(duration / segment_seconds)

            self.log(f"Thoi luong video: {duration:.2f} giay")
            self.log(f"Tong so canh du kien: {total_scenes}")

            if total_scenes <= 0:
                raise RuntimeError("Video khong co thoi luong hop le.")

            temp_pattern = temp_dir / "scene_%03d.mp4"
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

            if speed_mode == SPEED_FAST:
                codec_options = [
                    "-c",
                    "copy",
                ]
            else:
                codec_options = [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "23",
                    "-force_key_frames",
                    f"expr:gte(t,n_forced*{segment_seconds})",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                ]

            segment_options = [
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
            ]

            if speed_mode == SPEED_STANDARD:
                segment_options.extend(
                    [
                        "-segment_format_options",
                        "movflags=+faststart",
                    ]
                )

            segment_command = base_command + codec_options + segment_options + [
                str(temp_pattern)
            ]

            self.log("Dang cat video bang mot lenh FFmpeg segment...")
            self.set_progress(0.03)

            def update_segment_progress(value: float):
                self.set_progress(0.05 + value * 0.70)

            run_ffmpeg_segment(segment_command, duration, update_segment_progress)
            self.set_progress(0.75)
            self.log("FFmpeg da tao xong cac canh tam.")

            temp_files = sorted(temp_dir.glob("scene_*.mp4"))

            if not temp_files:
                raise RuntimeError("FFmpeg da chay xong nhung khong tao file canh nao.")

            self.log(f"So canh tam thuc te: {len(temp_files)}")

            if len(temp_files) != total_scenes:
                self.log(
                    f"Luu y: so canh tam ({len(temp_files)}) khac du kien ({total_scenes})."
                )

            exported_count = 0
            skipped_count = 0

            for index, temp_file in enumerate(temp_files, start=1):
                scene_number = index
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
                    self.set_progress(0.75 + (index / len(temp_files)) * 0.25)
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
                self.set_progress(0.75 + (index / len(temp_files)) * 0.25)

            self.set_progress(1)

            self.log("")
            self.log("HOAN THANH.")
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
