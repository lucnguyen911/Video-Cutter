"""Hardware capability probing and conservative batch auto-tuning.

The encoder list compiled into FFmpeg is not proof that the matching GPU and
driver work. This module runs a tiny real encode, identifies machine resources,
and caches a short parallel-throughput calibration.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path


PROFILE_SCHEMA = 2
MAX_PARALLEL_VIDEO_JOBS = 3


@dataclass(frozen=True)
class HardwareProfile:
    hardware_type: str = "cpu"
    encoder: str = "libx264"
    encoder_label: str = "CPU / libx264"
    logical_cpus: int = 1
    ram_gb: float = 0.0
    gpu_name: str = ""
    gpu_memory_mb: int = 0
    parallel_video_workers: int = 1
    calibrated: bool = False


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _run_quiet(command: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_creationflags(),
    )


def _ram_gb() -> float:
    if os.name != "nt":
        return 0.0

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


def _nvidia_info() -> tuple[str, int]:
    try:
        result = _run_quiet(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_line = result.stdout.splitlines()[0]
            name, memory = first_line.rsplit(",", 1)
            return name.strip(), int(float(memory.strip()))
    except Exception:
        pass
    return "", 0


def _encoder_options(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p2", "-tune", "hq", "-rc", "vbr", "-cq", "23"]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "speed", "-rc", "vbr_peak", "-qp_i", "23", "-qp_p", "23"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "veryfast", "-global_quality", "23"]
    return ["-c:v", "libx264", "-preset", "superfast", "-crf", "23", "-threads", "0"]


def probe_encoder(ffmpeg_path: str, encoder: str) -> bool:
    """Return True only when a real short encode succeeds on this machine."""
    null_output = "NUL" if os.name == "nt" else "/dev/null"
    command = [
        ffmpeg_path,
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=0.15",
        "-an", *_encoder_options(encoder), "-frames:v", "3", "-f", "null", null_output,
    ]
    try:
        return _run_quiet(command, timeout=10).returncode == 0
    except Exception:
        return False


def detect_best_encoder(ffmpeg_path: str) -> tuple[str, str, str]:
    candidates = (
        ("h264_nvenc", "nvidia", "NVIDIA NVENC"),
        ("h264_amf", "amd", "AMD AMF"),
        ("h264_qsv", "intel", "Intel Quick Sync"),
    )
    for encoder, hardware_type, label in candidates:
        if probe_encoder(ffmpeg_path, encoder):
            return encoder, hardware_type, label
    return "libx264", "cpu", "CPU / libx264"


def _profile_cache_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / "VideoCutter" / "hardware_profile.json"


def _profile_key(ffmpeg_path: str, encoder: str, gpu_name: str, gpu_memory_mb: int) -> str:
    try:
        ffmpeg_stamp = Path(ffmpeg_path).stat().st_mtime_ns
    except OSError:
        ffmpeg_stamp = 0
    return "|".join(
        [
            str(PROFILE_SCHEMA), platform.machine(), platform.processor(),
            str(os.cpu_count() or 1), encoder, gpu_name, str(gpu_memory_mb),
            str(ffmpeg_stamp),
        ]
    )


def _load_cached_workers(key: str) -> int | None:
    try:
        data = json.loads(_profile_cache_path().read_text(encoding="utf-8"))
        if data.get("key") == key:
            workers = int(data.get("parallel_video_workers", 0))
            if 1 <= workers <= MAX_PARALLEL_VIDEO_JOBS:
                return workers
    except Exception:
        pass
    return None


def _save_cached_workers(key: str, workers: int) -> None:
    try:
        path = _profile_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema": PROFILE_SCHEMA,
                    "key": key,
                    "parallel_video_workers": workers,
                    "created_at": int(time.time()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception:
        pass


def _benchmark_one(ffmpeg_path: str, encoder: str) -> bool:
    null_output = "NUL" if os.name == "nt" else "/dev/null"
    command = [
        ffmpeg_path,
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60:duration=1.5",
        "-an", *_encoder_options(encoder), "-f", "null", null_output,
    ]
    try:
        return _run_quiet(command, timeout=25).returncode == 0
    except Exception:
        return False


def _calibrate_parallel_workers(ffmpeg_path: str, encoder: str, ceiling: int) -> int:
    if ceiling <= 1:
        return 1

    best_workers = 1
    best_throughput = 0.0
    for workers in range(1, ceiling + 1):
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(lambda _index: _benchmark_one(ffmpeg_path, encoder), range(workers)))
        elapsed = max(time.perf_counter() - started, 0.001)
        if not all(results):
            break
        throughput = workers / elapsed
        if workers == 1 or throughput >= best_throughput * 1.12:
            best_workers = workers
            best_throughput = throughput
    return best_workers


def _worker_ceiling(hardware_type: str, logical_cpus: int, ram_gb: float, gpu_memory_mb: int) -> int:
    if hardware_type == "cpu":
        return 1
    if logical_cpus < 8 or (ram_gb and ram_gb < 12):
        return 1
    if hardware_type == "nvidia" and gpu_memory_mb >= 12000 and logical_cpus >= 12 and ram_gb >= 24:
        return 3
    if gpu_memory_mb >= 6000 or hardware_type in {"intel", "amd"}:
        return 2
    return 1


def build_hardware_profile(ffmpeg_path: str, calibrate: bool = True) -> HardwareProfile:
    encoder, hardware_type, label = detect_best_encoder(ffmpeg_path)
    logical_cpus = max(1, os.cpu_count() or 1)
    ram_gb = _ram_gb()
    gpu_name, gpu_memory_mb = _nvidia_info() if hardware_type == "nvidia" else ("", 0)
    ceiling = _worker_ceiling(hardware_type, logical_cpus, ram_gb, gpu_memory_mb)
    workers = ceiling
    calibrated = False

    is_high_end_nvidia = (
        hardware_type == "nvidia"
        and gpu_memory_mb >= 12000
        and logical_cpus >= 12
        and ram_gb >= 24
    )

    if is_high_end_nvidia:
        # Short synthetic calibration is dominated by FFmpeg process startup and
        # regularly underestimates multi-stream NVENC cards. The hardware tier
        # is a more reliable policy for a three-video batch.
        workers = ceiling
    elif calibrate and ceiling > 1:
        key = _profile_key(ffmpeg_path, encoder, gpu_name, gpu_memory_mb)
        cached_workers = _load_cached_workers(key)
        if cached_workers is None:
            workers = _calibrate_parallel_workers(ffmpeg_path, encoder, ceiling)
            _save_cached_workers(key, workers)
        else:
            workers = min(cached_workers, ceiling)
        calibrated = True

    return HardwareProfile(
        hardware_type=hardware_type,
        encoder=encoder,
        encoder_label=label,
        logical_cpus=logical_cpus,
        ram_gb=ram_gb,
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_memory_mb,
        parallel_video_workers=max(1, workers),
        calibrated=calibrated,
    )


def choose_parallel_video_workers(
    hardware_type: str,
    is_scene_cut: bool,
    uses_shared_sequence_names: bool,
    total_videos: int,
    profile: HardwareProfile | None = None,
) -> int:
    if total_videos < 2 or not is_scene_cut or uses_shared_sequence_names:
        return 1
    if hardware_type == "cpu":
        return 1
    configured = profile.parallel_video_workers if profile is not None else 2
    return min(max(1, configured), total_videos, MAX_PARALLEL_VIDEO_JOBS)


def profile_as_log_data(profile: HardwareProfile) -> dict:
    return asdict(profile)
