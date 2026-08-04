# updater.py
# Revamped auto-update layer with QThread workers, integrity validation, and loop-prevention markers.

import os
import sys
import json
import hashlib
import logging
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import re
import http.cookiejar
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Optional, NamedTuple
from dataclasses import dataclass
from packaging.version import parse as parse_version
from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop, Qt
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication

from version import APP_ID, APP_NAME, APP_VERSION, EXE_NAME
from security import SUPABASE_URL, SUPABASE_KEY
from dpapi_storage import save_secure_json, load_secure_json

# Setup updater logger
def setup_updater_logger() -> logging.Logger:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(app_data, "VideoCutter", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("updater")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(log_dir, "updater.log"), encoding="utf-8")
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

updater_logger = setup_updater_logger()

PENDING_MARKER_ENTROPY = "VideoCutter-PendingUpdate-v1"
GOOGLE_DRIVE_HOSTS = frozenset({
    "drive.google.com",
    "docs.google.com",
    "drive.usercontent.google.com",
    "drive.googleusercontent.com",
})
GOOGLE_DRIVE_DOWNLOAD_HOSTS = frozenset({
    "drive.google.com",
    "drive.usercontent.google.com",
})
GOOGLE_DRIVE_HTML_LIMIT = 512 * 1024


class _GoogleDriveConfirmationParser(HTMLParser):
    """Extracts the confirmation form that Google Drive returns for large files."""

    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag.lower() == "form" and self.action is None:
            action = values.get("action")
            if action:
                self.action = action
        elif tag.lower() == "input":
            name = values.get("name")
            value = values.get("value")
            if name and value is not None:
                self.fields[name] = value
        elif tag.lower() == "a":
            href = values.get("href")
            if href:
                self.links.append(href)


class _OpenedUpdateDownload:
    """Context manager that closes the HTTP response after the downloader consumes it."""

    def __init__(self, response, prefix: bytes):
        self.response = response
        self.prefix = prefix

    def __enter__(self):
        return self.response, self.prefix

    def __exit__(self, exc_type, exc_value, traceback):
        self.response.close()
        return False

def get_pending_update_marker_path() -> Path:
    return Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "VideoCutter" / "pending_update.dat"

def _valid_sha256(value: object) -> bool:
    import re
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", value.strip()))

def _valid_download_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value.strip())
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None


def _normalised_host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower().rstrip(".")


def _is_google_drive_url(url: str) -> bool:
    return _normalised_host(url) in GOOGLE_DRIVE_HOSTS


def _extract_google_drive_file_id(url: str) -> Optional[str]:
    """Returns a public Drive file ID from supported share/download URL formats."""
    if not _is_google_drive_url(url):
        return None

    parsed = urllib.parse.urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    file_id = None
    if "d" in path_parts:
        index = path_parts.index("d")
        if index + 1 < len(path_parts):
            file_id = path_parts[index + 1]
    if not file_id:
        file_id = urllib.parse.parse_qs(parsed.query).get("id", [None])[0]

    if not isinstance(file_id, str):
        return None
    # Drive IDs are URL-safe and much longer than a normal short parameter.
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", file_id):
        return None
    return file_id


def _google_drive_download_url(file_id: str) -> str:
    query = urllib.parse.urlencode({"id": file_id, "export": "download", "confirm": "t"})
    return f"https://drive.usercontent.google.com/download?{query}"


def _read_prefix(response, limit: int = 4096) -> bytes:
    return response.read(limit)


def _looks_like_html(content_type: str, prefix: bytes) -> bool:
    if "text/html" in (content_type or "").lower():
        return True
    stripped = prefix.lstrip().lower()
    return stripped.startswith(b"<!doctype html") or stripped.startswith(b"<html")


def _read_google_drive_html(response, prefix: bytes) -> bytes:
    body = bytearray(prefix)
    while len(body) < GOOGLE_DRIVE_HTML_LIMIT:
        chunk = response.read(min(65536, GOOGLE_DRIVE_HTML_LIMIT - len(body)))
        if not chunk:
            break
        body.extend(chunk)
    return bytes(body)


def _google_drive_confirmation_url(page_url: str, page_body: bytes, file_id: str) -> Optional[str]:
    parser = _GoogleDriveConfirmationParser()
    try:
        parser.feed(page_body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception:
        return None

    candidates = []
    if parser.action:
        fields = dict(parser.fields)
        fields.setdefault("id", file_id)
        fields.setdefault("export", "download")
        fields.setdefault("confirm", "t")
        candidates.append(urllib.parse.urljoin(page_url, parser.action))
        candidate_query = urllib.parse.urlencode(fields)
        candidates[-1] = candidates[-1] + ("&" if "?" in candidates[-1] else "?") + candidate_query
    candidates.extend(urllib.parse.urljoin(page_url, href) for href in parser.links if "confirm=" in href)

    for candidate in candidates:
        parsed = urllib.parse.urlparse(candidate)
        if parsed.scheme == "https" and _normalised_host(candidate) in GOOGLE_DRIVE_DOWNLOAD_HOSTS:
            return candidate
    return None


def _open_update_download(url: str, headers: dict):
    """Opens an installer stream; handles Google Drive's large-file confirmation page."""
    file_id = _extract_google_drive_file_id(url)
    if not file_id:
        response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30)
        return _OpenedUpdateDownload(response, b"")

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    drive_url = _google_drive_download_url(file_id)
    response = opener.open(urllib.request.Request(drive_url, headers=headers), timeout=30)
    prefix = _read_prefix(response)
    if not _looks_like_html(response.headers.get("Content-Type", ""), prefix):
        return _OpenedUpdateDownload(response, prefix)

    page_url = response.geturl()
    page_body = _read_google_drive_html(response, prefix)
    response.close()
    confirmation_url = _google_drive_confirmation_url(page_url, page_body, file_id)
    if not confirmation_url:
        raise ValueError(
            "Google Drive không trả về file cài đặt. Hãy đặt quyền chia sẻ là 'Anyone with the link' "
            "và dùng link của đúng file .exe."
        )

    response = opener.open(urllib.request.Request(confirmation_url, headers=headers), timeout=30)
    prefix = _read_prefix(response)
    if _looks_like_html(response.headers.get("Content-Type", ""), prefix):
        response.close()
        raise ValueError(
            "Google Drive vẫn trả về trang HTML thay vì file cài đặt. Kiểm tra quyền chia sẻ hoặc file có bị Google chặn không."
        )
    return _OpenedUpdateDownload(response, prefix)
class UpdateCheckStatus(Enum):
    NO_UPDATE = "NO_UPDATE"
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    NETWORK_ERROR = "NETWORK_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    CLIENT_CONFIG_ERROR = "CLIENT_CONFIG_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    APP_NOT_CONFIGURED = "APP_NOT_CONFIGURED"

@dataclass
class UpdateInfo:
    latest_version: str
    minimum_supported_version: Optional[str]
    download_url: str
    changelog: str
    enforcement: str      # "optional" | "forced"
    package_type: str     # "full" | "patch"
    sha256: Optional[str]
    file_size: Optional[int]

@dataclass
class UpdateCheckResult:
    status: UpdateCheckStatus
    update_info: Optional[UpdateInfo]
    message: str
    http_status: Optional[int] = None

def get_current_install_dir() -> Path:
    """Returns parent folder of current executable. Raises if run from source during production check."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Production auto-update chỉ được chạy từ bản đóng gói.")
    current_exe = Path(sys.executable).resolve()
    return current_exe.parent

def get_update_temp_dir() -> Path:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    update_dir = Path(app_data) / "VideoCutter" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    return update_dir

def validate_install_dir(dir_path: Path) -> bool:
    """
    Validates install directory:
    - Path must exist and cannot be drive root, Windows directory, temp, python environment or .venv.
    - Path must contain EXE_NAME.
    """
    if not dir_path.exists():
        updater_logger.error(f"[UPDATER] Directory does not exist: {dir_path}")
        return False
        
    exe_file = dir_path / EXE_NAME
    if not exe_file.exists():
        updater_logger.error(f"[UPDATER] Executable not found in path: {exe_file}")
        return False
        
    if dir_path.parent == dir_path:
        updater_logger.error(f"[UPDATER] Cannot install in root drive: {dir_path}")
        return False
        
    path_lower = str(dir_path).lower()
    
    # Windows system directory check
    win_dir = os.environ.get("SystemRoot", "C:\\Windows").lower()
    if path_lower.startswith(win_dir) or "system32" in path_lower:
        updater_logger.error(f"[UPDATER] Cannot install in system folders: {dir_path}")
        return False
        
    # Temp folders
    if "temp" in path_lower or "tmp" in path_lower:
        updater_logger.error(f"[UPDATER] Cannot install in temporary folders: {dir_path}")
        return False
        
    # Python venv
    if "python" in path_lower or ".venv" in path_lower:
        updater_logger.error(f"[UPDATER] Cannot install in python/virtual environment folders: {dir_path}")
        return False
        
    return True

def check_for_update_logic(app_id: str, current_version: str) -> UpdateCheckResult:
    """Invokes Supabase app_versions API to fetch update metadata."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
    }

    query = urllib.parse.urlencode({"app_id": f"eq.{app_id}", "is_active": "eq.true", "order": "published_at.desc", "limit": "1"})
    url = f"{SUPABASE_URL}/rest/v1/app_versions?{query}"
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        if not data:
            return UpdateCheckResult(
                status=UpdateCheckStatus.APP_NOT_CONFIGURED,
                update_info=None,
                message="Ứng dụng chưa được cấu hình trên máy chủ cập nhật."
            )

        record = data[0]
        latest_version = record.get("latest_version", "").strip()
        download_url = record.get("download_url", "").strip()
        changelog = record.get("changelog", "")
        
        # enforcement mapping: supports both new 'enforcement' and legacy 'update_type'
        enforcement = record.get("enforcement", "").strip()
        if not enforcement:
            enforcement = record.get("update_type", "optional").strip()
        if enforcement not in ["optional", "forced"]:
            enforcement = "optional"
            
        package_type = record.get("package_type", "full").strip().lower()
        sha256 = record.get("sha256")
        file_size = record.get("file_size")
        
        if not latest_version or not download_url:
            return UpdateCheckResult(
                status=UpdateCheckStatus.INVALID_RESPONSE,
                update_info=None,
                message="Cấu hình phiên bản cập nhật trên máy chủ bị thiếu."
            )
            
        # Only full, integrity-pinned HTTPS installers are accepted.
        if package_type not in ["full", "installer"]:
            return UpdateCheckResult(UpdateCheckStatus.CLIENT_CONFIG_ERROR, None, "Chỉ hỗ trợ full installer.")
        if not _valid_download_url(download_url):
            return UpdateCheckResult(UpdateCheckStatus.INVALID_RESPONSE, None, "Đường dẫn tải bản cập nhật phải là HTTPS hợp lệ.")
        if not _valid_sha256(sha256):
            return UpdateCheckResult(UpdateCheckStatus.INVALID_RESPONSE, None, "Máy chủ phải cung cấp SHA-256 hợp lệ cho gói cập nhật.")
        if not isinstance(file_size, int) or file_size <= 0:
            return UpdateCheckResult(UpdateCheckStatus.INVALID_RESPONSE, None, "Máy chủ phải cung cấp kích thước hợp lệ cho gói cập nhật.")
        if parse_version(latest_version) > parse_version(current_version):
            info = UpdateInfo(
                latest_version=latest_version,
                minimum_supported_version=record.get("minimum_supported_version"),
                download_url=download_url,
                changelog=changelog,
                enforcement=enforcement,
                package_type=package_type,
                sha256=sha256,
                file_size=file_size
            )
            return UpdateCheckResult(
                status=UpdateCheckStatus.UPDATE_AVAILABLE,
                update_info=info,
                message="Có phiên bản mới khả dụng."
            )

        return UpdateCheckResult(
            status=UpdateCheckStatus.NO_UPDATE,
            update_info=None,
            message="Ứng dụng đã là phiên bản mới nhất."
        )

    except urllib.error.HTTPError as e:
        status_code = e.code
        if status_code in [401, 403]:
            return UpdateCheckResult(UpdateCheckStatus.AUTH_ERROR, None, f"Lỗi xác thực máy chủ cập nhật (HTTP {status_code}).", status_code)
        elif status_code in [400, 404]:
            return UpdateCheckResult(UpdateCheckStatus.CLIENT_CONFIG_ERROR, None, f"Lỗi cấu hình cập nhật (HTTP {status_code}).", status_code)
        else:
            return UpdateCheckResult(UpdateCheckStatus.SERVER_ERROR, None, f"Lỗi máy chủ cập nhật (HTTP {status_code}).", status_code)
            
    except urllib.error.URLError as e:
        return UpdateCheckResult(UpdateCheckStatus.NETWORK_ERROR, None, f"Lỗi kết nối mạng: {e.reason}")
        
    except Exception as e:
        return UpdateCheckResult(UpdateCheckStatus.NETWORK_ERROR, None, f"Lỗi không xác định: {e}")

class UpdateCheckWorker(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, app_id: str, current_version: str):
        super().__init__()
        self.app_id = app_id
        self.current_version = current_version
        self.result = None

    def run(self):
        self.result = check_for_update_logic(self.app_id, self.current_version)
        self.finished_signal.emit()

class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int, int) # downloaded, total
    finished = pyqtSignal(object)  # Emits Path on success or Exception on failure
    cancelled = pyqtSignal()

    def __init__(self, download_url: str, expected_hash: Optional[str], expected_size: Optional[int]):
        super().__init__()
        self.download_url = download_url
        self.expected_hash = expected_hash
        self.expected_size = expected_size
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not _valid_download_url(self.download_url) or not _valid_sha256(self.expected_hash) or not isinstance(self.expected_size, int) or self.expected_size <= 0:
            self.finished.emit(ValueError("Cấu hình gói cập nhật không đầy đủ hoặc không an toàn."))
            return
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
            "Accept": "application/octet-stream"
        }
        temp_dir = get_update_temp_dir()
        part_path = temp_dir / "update_latest.part"

        if part_path.exists():
            try: part_path.unlink()
            except Exception: pass

        try:
            with _open_update_download(self.download_url, headers) as opened:
                # _open_update_download returns (response, prefix); this form keeps the stream closed on all exits.
                response, prefix = opened
                status_code = response.getcode()
                if status_code not in [200, 201, 206]:
                    self.finished.emit(ValueError(f"Máy chủ trả mã HTTP không hợp lệ: {status_code}"))
                    return

                content_length = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536
                sha256_hash = hashlib.sha256()
                executable_header = bytearray()

                with open(part_path, "wb") as f:
                    if prefix:
                        f.write(prefix)
                        sha256_hash.update(prefix)
                        downloaded += len(prefix)
                        executable_header.extend(prefix[:2])
                        self.progress.emit(downloaded, content_length or self.expected_size)

                    while not self._is_cancelled:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        downloaded += len(chunk)
                        if len(executable_header) < 2:
                            executable_header.extend(chunk[:2 - len(executable_header)])
                        self.progress.emit(downloaded, content_length or self.expected_size)

            if self._is_cancelled:
                if part_path.exists():
                    try: part_path.unlink()
                    except Exception: pass
                self.cancelled.emit()
                return

            if downloaded != self.expected_size:
                if part_path.exists():
                    try: part_path.unlink()
                    except Exception: pass
                self.finished.emit(ValueError(f"Kích thước file tải về ({downloaded} B) không khớp cấu hình ({self.expected_size} B)."))
                return

            calc_hash = sha256_hash.hexdigest()
            if calc_hash.lower() != self.expected_hash.lower():
                if part_path.exists():
                    try: part_path.unlink()
                    except Exception: pass
                self.finished.emit(ValueError(f"Mã băm SHA-256 ({calc_hash}) không khớp cấu hình ({self.expected_hash})."))
                return

            if bytes(executable_header) != b"MZ":
                if part_path.exists():
                    try: part_path.unlink()
                    except Exception: pass
                self.finished.emit(ValueError("Tệp tải về không phải Windows installer hợp lệ (thiếu chữ ký MZ)."))
                return

            final_path = temp_dir / "update_latest.exe"
            if final_path.exists():
                try: final_path.unlink()
                except Exception: pass
            os.rename(part_path, final_path)
            self.finished.emit(final_path)

        except Exception as e:
            if part_path.exists():
                try: part_path.unlink()
                except Exception: pass
            self.finished.emit(e)
def apply_update(installer_path: Path, target_version: str) -> bool:
    """Writes update marker atomically and invokes the installer with /DIR arguments."""
    try:
        current_app_dir = get_current_install_dir()
    except Exception as e:
        updater_logger.error(f"[UPDATER] Directory fetch failed: {e}")
        return False

    if not validate_install_dir(current_app_dir):
        updater_logger.error(f"[UPDATER] Directory validation failed for {current_app_dir}")
        return False

    # Only a downloaded installer from our private update directory may run.
    try:
        trusted_update_dir = get_update_temp_dir().resolve()
        resolved_installer = installer_path.resolve()
        if resolved_installer.parent != trusted_update_dir or resolved_installer.suffix.lower() != ".exe" or not resolved_installer.is_file():
            updater_logger.error("[UPDATER] Refusing installer outside trusted update directory")
            return False
    except OSError as e:
        updater_logger.error(f"[UPDATER] Installer validation failed: {e}")
        return False

    # Write the protected marker before starting the installer.
    marker_path = get_pending_update_marker_path()
    marker_data = {
        "source_version": APP_VERSION,
        "target_version": target_version,
        "expected_install_dir": str(current_app_dir),
        "installer_path": str(installer_path),
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    try:
        save_secure_json(str(marker_path), marker_data, PENDING_MARKER_ENTROPY)
        updater_logger.info(f"[UPDATER] Write pending update marker to {marker_path}")
    except Exception as e:
        updater_logger.error(f"[UPDATER] Failed to write update marker: {e}")
        return False

    # Launch installer
    installer_args = [
        str(installer_path),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        f"/DIR={current_app_dir}",
    ]

    updater_logger.info(f"[UPDATER] current_version={APP_VERSION} target_version={target_version}")
    updater_logger.info(f"[UPDATER] current_install_dir={current_app_dir}")
    updater_logger.info(f"[UPDATER] installer_dir_argument={current_app_dir}")
    updater_logger.info("[UPDATER] hash_verified=True")

    try:
        subprocess.Popen(
            installer_args,
            cwd=str(installer_path.parent),
            close_fds=True,
        )
        updater_logger.info("[UPDATER] installer_started=True")
        logging.shutdown()
        os._exit(0)
    except Exception as e:
        updater_logger.error(f"[UPDATER] Failed to launch installer: {e}")
        # Clean up marker on failure
        if marker_path.exists():
            try: marker_path.unlink()
            except Exception: pass
        return False

def show_update_dialog(update_info: UpdateInfo, current_version: str) -> bool:
    is_forced = (update_info.enforcement == "forced")
    title = "Cập nhật bắt buộc!" if is_forced else "Phiên bản mới khả dụng!"
    message = (
        f"Phiên bản hiện tại: v{current_version}\n"
        f"Phiên bản mới:        v{update_info.latest_version}\n\n"
        f"{'─' * 40}\n"
        f"Có gì mới:\n{update_info.changelog}\n"
        f"{'─' * 40}\n\n"
    )

    if is_forced:
        message += "⚠ Đây là bản cập nhật bắt buộc. Bạn cần cập nhật để tiếp tục sử dụng."
    else:
        message += "Bạn có muốn cập nhật ngay bây giờ không?"

    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setIcon(QMessageBox.Icon.Information)

    if is_forced:
        msg_box.addButton("Cập nhật ngay", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton("Thoát ứng dụng", QMessageBox.ButtonRole.RejectRole)
    else:
        msg_box.addButton("Cập nhật ngay", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton("Bỏ qua", QMessageBox.ButtonRole.RejectRole)

    msg_box.exec()
    clicked = msg_box.clickedButton()
    button_role = msg_box.buttonRole(clicked)

    return button_role == QMessageBox.ButtonRole.AcceptRole

def run_update_download(update_info: UpdateInfo) -> bool:
    progress = QProgressDialog("Đang tải bản cập nhật...", "Hủy", 0, 100)
    progress.setWindowTitle("Tải cập nhật")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    
    worker = UpdateDownloadWorker(
        download_url=update_info.download_url,
        expected_hash=update_info.sha256,
        expected_size=update_info.file_size
    )
    
    loop = QEventLoop()
    download_result = None
    was_cancelled = False
    
    def on_progress(downloaded, total):
        percent = int(downloaded / total * 100) if total > 0 else 0
        progress.setValue(percent)
        progress.setLabelText(
            f"Đang tải: {downloaded / (1024*1024):.1f} MB / {total / (1024*1024):.1f} MB"
        )
        
    def on_finished(res):
        nonlocal download_result
        download_result = res
        loop.quit()
        
    def on_cancelled():
        nonlocal was_cancelled
        was_cancelled = True
        loop.quit()
        
    progress.canceled.connect(worker.cancel)
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.cancelled.connect(on_cancelled)
    
    worker.start()
    loop.exec()
    progress.close()
    
    if was_cancelled:
        updater_logger.info("[UPDATER] Update download cancelled by user.")
        return False
        
    if isinstance(download_result, Exception) or not download_result:
        error_msg = str(download_result) if isinstance(download_result, Exception) else "Lỗi không xác định."
        updater_logger.error(f"[UPDATER] Update download failed: {error_msg}")
        QMessageBox.warning(
            None,
            "Lỗi tải cập nhật",
            f"Không thể tải bản cập nhật. Chi tiết: {error_msg}"
        )
        return False
        
    return apply_update(download_result, update_info.latest_version)

def run_update_check() -> bool:
    """
    Checks for updates. If available, prompts user, downloads, and applies it.
    Returns True if update was launched and application should terminate.
    """
    if not getattr(sys, "frozen", False):
        return False # Bypass for source environment

    loop = QEventLoop()
    worker = UpdateCheckWorker(APP_ID, APP_VERSION)
    worker.finished_signal.connect(loop.quit)
    worker.start()
    loop.exec()
    
    result = worker.result
    if not result:
        return False
        
    if result.status == UpdateCheckStatus.UPDATE_AVAILABLE:
        update_info = result.update_info
        is_forced = (update_info.enforcement == "forced")
        
        user_accepted = show_update_dialog(update_info, APP_VERSION)
        if not user_accepted:
            if is_forced:
                updater_logger.info("[UPDATER] Mandatory update declined; application will close.")
                return True
            return False

        success = run_update_download(update_info)
        if is_forced and not success:
            updater_logger.warning("[UPDATER] Mandatory update was not completed; application will close.")
            QMessageBox.warning(None, "Cập nhật bắt buộc", "Không thể hoàn tất cập nhật. Ứng dụng sẽ đóng; vui lòng mở lại và thử cập nhật.")
            return True
        return success
        
    elif result.status == UpdateCheckStatus.NO_UPDATE:
        updater_logger.info(f"[UPDATER] No update needed: {result.message}")
    elif result.status == UpdateCheckStatus.NETWORK_ERROR:
        updater_logger.warning(f"[UPDATER] Check failed: NETWORK_ERROR - {result.message}")
    elif result.status in [UpdateCheckStatus.APP_NOT_CONFIGURED, UpdateCheckStatus.INVALID_RESPONSE]:
        updater_logger.error(f"[UPDATER] Config error on server: {result.status.value} - {result.message}")
    elif result.status in [UpdateCheckStatus.SERVER_ERROR, UpdateCheckStatus.CLIENT_CONFIG_ERROR, UpdateCheckStatus.AUTH_ERROR]:
        updater_logger.error(f"[UPDATER] Check failed: {result.status.value} - {result.message}")
    else:
        updater_logger.error(f"[UPDATER] Unhandled update check status: {result.status.value} - {result.message}")
        
    return False

def verify_pending_update_marker():
    """Confirm exactly one attempted install, then always clear its marker."""
    marker_path = get_pending_update_marker_path()
    if not marker_path.exists():
        return
    marker = load_secure_json(str(marker_path), PENDING_MARKER_ENTROPY)
    if not isinstance(marker, dict):
        updater_logger.error("[UPDATER] Invalid pending update marker; clearing it")
        try:
            marker_path.unlink()
        except OSError:
            pass
        return
    installer_path = marker.get("installer_path")
    try:
        source_version = marker.get("source_version")
        target_version = marker.get("target_version")
        expected_install_dir = marker.get("expected_install_dir")
        if not isinstance(target_version, str) or not isinstance(expected_install_dir, str):
            raise ValueError("marker is missing target version or install directory")
        actual_version = APP_VERSION
        try:
            actual_install_dir = str(get_current_install_dir())
        except Exception:
            actual_install_dir = str(Path(sys.executable).resolve().parent)
        version_match = actual_version == target_version
        path_match = os.path.normcase(os.path.normpath(actual_install_dir)) == os.path.normcase(os.path.normpath(expected_install_dir))
        updater_logger.info(f"[UPDATER] verify_pending_update: expected_version={target_version} actual_version={actual_version} version_match={version_match}")
        updater_logger.info(f"[UPDATER] verify_pending_update: expected_dir={expected_install_dir} actual_dir={actual_install_dir} path_match={path_match}")
        if version_match and path_match:
            updater_logger.info(f"[UPDATER] Update successful from {source_version} to {target_version} at {actual_install_dir}")
        else:
            updater_logger.error("[UPDATER] Update did not complete as expected; marker cleared to prevent update loop")
    except Exception as e:
        updater_logger.error(f"[UPDATER] Error verifying pending update marker: {e}")
    finally:
        try:
            marker_path.unlink()
        except OSError:
            pass
        if isinstance(installer_path, str) and installer_path:
            try:
                candidate = Path(installer_path).resolve()
                if candidate.parent == get_update_temp_dir().resolve() and candidate.is_file():
                    candidate.unlink()
            except OSError:
                pass