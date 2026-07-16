"""
updater.py — Auto-update module for Video Cutter.
==================================================
Checks for updates via Supabase `app_versions`, downloads packages safely,
and applies updates using the Inno Setup full installer method.

Key changes from v1:
  - Structured error results (not None for everything)
  - HTTP error classification (404 ≠ network error)
  - SHA-256 + file size verification
  - Download on QThread with real cancel support
  - No xcopy/batch patching
  - Full installer as default strategy
  - Update policy cache
"""

import hashlib
import json
import logging
import os
import sys
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from packaging.version import parse as parse_version, InvalidVersion

from version import APP_ID, APP_VERSION, APP_NAME, EXE_NAME, APPDATA_FOLDER
from security import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("updater")

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

CONNECT_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 300  # 5 minutes for large downloads
DOWNLOAD_CHUNK_SIZE = 65536  # 64KB


# ═══════════════════════════════════════════════════════════════════════════════
#  ENUMS & DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class UpdateCheckStatus(str, Enum):
    NO_UPDATE = "NO_UPDATE"
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    NETWORK_ERROR = "NETWORK_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    CLIENT_CONFIG_ERROR = "CLIENT_CONFIG_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    APP_NOT_CONFIGURED = "APP_NOT_CONFIGURED"


class UpdateEnforcement(str, Enum):
    OPTIONAL = "optional"
    FORCED = "forced"


class PackageType(str, Enum):
    FULL = "full"
    PATCH = "patch"


@dataclass
class UpdateInfo:
    latest_version: str
    download_url: str
    changelog: str
    enforcement: UpdateEnforcement
    package_type: PackageType
    sha256: Optional[str]
    file_size: Optional[int]
    minimum_supported_version: Optional[str]


@dataclass
class UpdateCheckResult:
    status: UpdateCheckStatus
    update_info: Optional[UpdateInfo]
    message: str
    http_status: Optional[int] = None


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[Path]
    message: str
    cancelled: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
#  HTTP ERROR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_http_error(e: Exception) -> tuple:
    """Classify HTTP/network exception → (UpdateCheckStatus, http_code)."""
    if isinstance(e, urllib.error.HTTPError):
        code = e.code
        if code in (401, 403):
            return UpdateCheckStatus.AUTH_ERROR, code
        elif code == 404:
            return UpdateCheckStatus.CLIENT_CONFIG_ERROR, code
        elif code >= 500:
            return UpdateCheckStatus.SERVER_ERROR, code
        else:
            return UpdateCheckStatus.SERVER_ERROR, code
    elif isinstance(e, urllib.error.URLError):
        return UpdateCheckStatus.NETWORK_ERROR, 0
    elif isinstance(e, (TimeoutError, OSError)):
        return UpdateCheckStatus.NETWORK_ERROR, 0
    else:
        return UpdateCheckStatus.NETWORK_ERROR, 0


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_app_dir() -> Path:
    """Return the application root directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent


def get_update_temp_dir() -> Path:
    """Return the temp directory for downloads."""
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    update_dir = Path(app_data) / APPDATA_FOLDER / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    return update_dir


def get_update_cache_path() -> Path:
    """Return path to update policy cache file."""
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    return Path(app_data) / APPDATA_FOLDER / "update_policy.json"


def _save_update_policy_cache(update_info: UpdateInfo) -> None:
    """Save update policy cache atomically."""
    cache = {
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "minimum_supported_version": update_info.minimum_supported_version,
        "latest_version": update_info.latest_version,
        "enforcement": update_info.enforcement.value,
    }
    path = get_update_cache_path()
    tmp_path = str(path) + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception as e:
        logger.warning(f"[UPDATER] failed to save update policy cache: {e}")


def _load_update_policy_cache() -> Optional[dict]:
    """Load update policy cache."""
    path = get_update_cache_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  CHECK FOR UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

def check_for_update() -> UpdateCheckResult:
    """
    Check Supabase `app_versions` table for a newer version.
    
    Returns:
        UpdateCheckResult with proper status (never returns None).
        
    Error handling:
        - Empty table → APP_NOT_CONFIGURED (not NO_UPDATE)
        - HTTP 404 → CLIENT_CONFIG_ERROR
        - HTTP 401/403 → AUTH_ERROR
        - Invalid version → INVALID_RESPONSE
        - Network error → NETWORK_ERROR
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    
    url = f"{SUPABASE_URL}/rest/v1/app_versions?app_id=eq.{APP_ID}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    
    try:
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        if not data:
            # No row for this APP_ID
            logger.warning(f"[UPDATER] no row found for app_id={APP_ID}")
            return UpdateCheckResult(
                status=UpdateCheckStatus.APP_NOT_CONFIGURED,
                update_info=None,
                message=f"Ứng dụng '{APP_ID}' chưa được cấu hình trên máy chủ.",
            )
        
        record = data[0]
        latest_version = record.get("latest_version", "")
        
        if not latest_version:
            logger.warning("[UPDATER] latest_version is empty")
            return UpdateCheckResult(
                status=UpdateCheckStatus.INVALID_RESPONSE,
                update_info=None,
                message="Máy chủ trả về phiên bản rỗng.",
            )
        
        # Validate version string
        try:
            latest_parsed = parse_version(latest_version)
            current_parsed = parse_version(APP_VERSION)
        except InvalidVersion:
            logger.error(f"[UPDATER] invalid version string: {latest_version}")
            return UpdateCheckResult(
                status=UpdateCheckStatus.INVALID_RESPONSE,
                update_info=None,
                message=f"Phiên bản từ máy chủ không hợp lệ: {latest_version}",
            )
        
        # Parse enforcement (backward compatibility with update_type)
        raw_enforcement = record.get("enforcement") or record.get("update_type", "optional")
        try:
            enforcement = UpdateEnforcement(raw_enforcement)
        except ValueError:
            enforcement = UpdateEnforcement.OPTIONAL
            logger.warning(f"[UPDATER] unknown enforcement value: {raw_enforcement}")
        
        # Parse package_type
        raw_package_type = record.get("package_type", "full")
        try:
            package_type = PackageType(raw_package_type)
        except ValueError:
            package_type = PackageType.FULL
        
        # Parse file_size
        file_size = record.get("file_size")
        if file_size is not None:
            try:
                file_size = int(file_size)
            except (ValueError, TypeError):
                file_size = None
        
        update_info = UpdateInfo(
            latest_version=latest_version,
            download_url=record.get("download_url", ""),
            changelog=record.get("changelog", "Không có thông tin chi tiết."),
            enforcement=enforcement,
            package_type=package_type,
            sha256=record.get("sha256"),
            file_size=file_size,
            minimum_supported_version=record.get("minimum_supported_version"),
        )
        
        # Save policy cache
        _save_update_policy_cache(update_info)
        
        if latest_parsed > current_parsed:
            logger.info(
                f"[UPDATER] check status=UPDATE_AVAILABLE "
                f"current={APP_VERSION} target={latest_version}"
            )
            return UpdateCheckResult(
                status=UpdateCheckStatus.UPDATE_AVAILABLE,
                update_info=update_info,
                message=f"Có phiên bản mới: v{latest_version}",
            )
        else:
            logger.info(f"[UPDATER] check status=NO_UPDATE current={APP_VERSION}")
            return UpdateCheckResult(
                status=UpdateCheckStatus.NO_UPDATE,
                update_info=None,
                message=f"Bạn đang dùng phiên bản mới nhất (v{APP_VERSION}).",
            )
    
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        error_status, http_code = _classify_http_error(e)
        logger.error(f"[UPDATER] check error: {type(e).__name__} http={http_code}")
        return UpdateCheckResult(
            status=error_status,
            update_info=None,
            message=f"Lỗi kiểm tra cập nhật: {type(e).__name__}",
            http_status=http_code or None,
        )
    except json.JSONDecodeError:
        logger.error("[UPDATER] invalid JSON response from server")
        return UpdateCheckResult(
            status=UpdateCheckStatus.INVALID_RESPONSE,
            update_info=None,
            message="Máy chủ trả về dữ liệu không hợp lệ.",
        )
    except Exception as e:
        logger.error(f"[UPDATER] unexpected error: {type(e).__name__}: {e}")
        return UpdateCheckResult(
            status=UpdateCheckStatus.NETWORK_ERROR,
            update_info=None,
            message=f"Lỗi không xác định: {type(e).__name__}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

def download_update(
    update_info: UpdateInfo,
    cancel_event: Optional[threading.Event] = None,
    progress_callback=None,
) -> DownloadResult:
    """
    Download update package safely.
    
    Features:
        - Downloads to .part file first
        - SHA-256 verification
        - File size verification
        - Real cancel support via threading.Event
        - User-Agent header
        - Proper timeout
        
    Args:
        update_info: Update info with URL, sha256, file_size.
        cancel_event: Set this event to cancel download.
        progress_callback: callback(downloaded_bytes, total_bytes)
        
    Returns:
        DownloadResult with success status and file path.
    """
    download_url = update_info.download_url
    if not download_url:
        return DownloadResult(
            success=False, file_path=None,
            message="URL tải xuống không hợp lệ.",
        )
    
    update_dir = get_update_temp_dir()
    
    # Determine file extension from package_type metadata (not URL)
    if update_info.package_type == PackageType.FULL:
        ext = ".exe"
    else:
        ext = ".zip"
    
    final_path = update_dir / f"update_v{update_info.latest_version}{ext}"
    part_path = update_dir / f"update_v{update_info.latest_version}{ext}.part"
    
    # Clean up any previous partial download
    if part_path.exists():
        part_path.unlink()
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/octet-stream",
    }
    
    req = urllib.request.Request(download_url, headers=headers, method="GET")
    hasher = hashlib.sha256()
    downloaded = 0
    
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
            http_status = response.getcode()
            if http_status != 200:
                return DownloadResult(
                    success=False, file_path=None,
                    message=f"Server trả về HTTP {http_status}.",
                )
            
            content_length = response.headers.get("Content-Length")
            total_size = int(content_length) if content_length else 0
            
            with open(part_path, "wb") as f:
                while True:
                    # Check cancel
                    if cancel_event and cancel_event.is_set():
                        logger.info("[UPDATER] download cancelled by user")
                        f.close()
                        if part_path.exists():
                            part_path.unlink()
                        return DownloadResult(
                            success=False, file_path=None,
                            message="Đã hủy tải xuống.",
                            cancelled=True,
                        )
                    
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)
        
        logger.info(f"[UPDATER] download completed: {downloaded} bytes")
        
        # Verify file size
        if update_info.file_size and update_info.file_size > 0:
            if downloaded != update_info.file_size:
                logger.error(
                    f"[UPDATER] file size mismatch: "
                    f"expected={update_info.file_size} actual={downloaded}"
                )
                part_path.unlink(missing_ok=True)
                return DownloadResult(
                    success=False, file_path=None,
                    message="Kích thước file tải về không khớp với dữ liệu máy chủ.",
                )
        
        # Verify SHA-256
        computed_sha256 = hasher.hexdigest()
        if update_info.sha256:
            if computed_sha256.lower() != update_info.sha256.lower():
                logger.error(
                    f"[UPDATER] sha256 mismatch: "
                    f"expected={update_info.sha256[:16]}... "
                    f"actual={computed_sha256[:16]}..."
                )
                part_path.unlink(missing_ok=True)
                return DownloadResult(
                    success=False, file_path=None,
                    message="Mã hash SHA-256 không khớp. File có thể bị hỏng hoặc bị thay đổi.",
                )
            logger.info(f"[UPDATER] download sha256 verified=True")
        else:
            logger.warning("[UPDATER] no sha256 from server, skipping hash verification")
        
        # Rename .part to final
        if final_path.exists():
            final_path.unlink()
        part_path.rename(final_path)
        
        logger.info(f"[UPDATER] package_type={update_info.package_type.value}")
        return DownloadResult(
            success=True,
            file_path=final_path,
            message="Tải bản cập nhật thành công.",
        )
    
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        logger.error(f"[UPDATER] download error: {type(e).__name__}: {e}")
        part_path.unlink(missing_ok=True)
        return DownloadResult(
            success=False, file_path=None,
            message=f"Lỗi tải bản cập nhật: {type(e).__name__}",
        )
    except Exception as e:
        logger.error(f"[UPDATER] unexpected download error: {type(e).__name__}: {e}")
        part_path.unlink(missing_ok=True)
        return DownloadResult(
            success=False, file_path=None,
            message=f"Lỗi không xác định khi tải: {type(e).__name__}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  APPLY UPDATE — FULL INSTALLER
# ═══════════════════════════════════════════════════════════════════════════════

def apply_full_installer(installer_path: Path) -> bool:
    """
    Launch the Inno Setup installer for a full update.
    
    The installer handles:
        - UAC elevation
        - Closing the running app
        - File replacement
        - Restart
    
    Args:
        installer_path: Path to the .exe installer.
        
    Returns:
        True if the installer was launched successfully (app should exit).
    """
    if not installer_path.exists():
        logger.error(f"[UPDATER] installer not found: {installer_path}")
        return False
    
    args = [
        str(installer_path),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        f"/LOG={get_update_temp_dir() / 'installer.log'}",
    ]
    
    logger.info(f"[UPDATER] launching installer: {installer_path.name}")
    
    try:
        subprocess.Popen(
            args,
            creationflags=(
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            ),
            close_fds=True,
        )
        return True
    except Exception as e:
        logger.error(f"[UPDATER] failed to launch installer: {type(e).__name__}: {e}")
        return False


def apply_update(download_result: DownloadResult, update_info: UpdateInfo) -> bool:
    """
    Apply a downloaded update package.
    
    For full packages (default): launch Inno Setup installer.
    For patch packages: REJECT (not safe without helper + rollback).
    
    Args:
        download_result: Result from download_update().
        update_info: Update info with package_type.
        
    Returns:
        True if update was applied/launched (app should exit).
    """
    if not download_result.success or not download_result.file_path:
        return False
    
    if update_info.package_type == PackageType.PATCH:
        logger.warning("[UPDATER] patch update rejected: safe helper not available")
        return False
    
    # Full installer
    return apply_full_installer(download_result.file_path)


# ═══════════════════════════════════════════════════════════════════════════════
#  QT WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_qthread_classes():
    """Lazy import PyQt6 to avoid import at module level for testing."""
    from PyQt6.QtCore import QThread, pyqtSignal
    
    class UpdateCheckWorker(QThread):
        """Worker thread for checking updates."""
        finished = pyqtSignal(object)  # UpdateCheckResult
        
        def run(self):
            result = check_for_update()
            self.finished.emit(result)
    
    class UpdateDownloadWorker(QThread):
        """Worker thread for downloading updates."""
        finished = pyqtSignal(object)    # DownloadResult
        progress = pyqtSignal(int, int)  # (downloaded, total)
        
        def __init__(self, update_info: UpdateInfo, parent=None):
            super().__init__(parent)
            self._update_info = update_info
            self._cancel_event = threading.Event()
        
        def run(self):
            result = download_update(
                self._update_info,
                cancel_event=self._cancel_event,
                progress_callback=lambda d, t: self.progress.emit(d, t),
            )
            self.finished.emit(result)
        
        def cancel(self):
            """Request download cancellation."""
            self._cancel_event.set()
    
    return UpdateCheckWorker, UpdateDownloadWorker


# These will be imported by main.py
try:
    UpdateCheckWorker, UpdateDownloadWorker = _get_qthread_classes()
except ImportError:
    # PyQt6 not available (e.g., during testing)
    UpdateCheckWorker = None
    UpdateDownloadWorker = None


# ═══════════════════════════════════════════════════════════════════════════════
#  UPDATE DIALOG (PyQt6)
# ═══════════════════════════════════════════════════════════════════════════════

def show_update_dialog(update_info: UpdateInfo) -> bool:
    """
    Show update notification dialog.
    
    For forced updates: user must update or exit.
    For optional updates: user can skip.
    
    Returns:
        True if user accepted the update.
    """
    from PyQt6.QtWidgets import QMessageBox

    is_forced = (update_info.enforcement == UpdateEnforcement.FORCED)
    
    title = "Cập nhật bắt buộc!" if is_forced else "Phiên bản mới khả dụng!"
    
    message = (
        f"Phiên bản hiện tại: v{APP_VERSION}\n"
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


def show_download_progress_dialog(update_info: UpdateInfo) -> Optional[DownloadResult]:
    """
    Show download progress dialog with real cancel support.
    Runs download on a worker thread.
    
    Returns:
        DownloadResult, or None if cancelled.
    """
    from PyQt6.QtWidgets import QProgressDialog
    from PyQt6.QtCore import Qt, QEventLoop
    
    progress = QProgressDialog("Đang tải bản cập nhật...", "Hủy", 0, 100)
    progress.setWindowTitle("Tải cập nhật")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    
    download_result_holder = [None]
    cancel_event = threading.Event()
    loop = QEventLoop()
    
    worker = UpdateDownloadWorker.__new__(UpdateDownloadWorker)
    from PyQt6.QtCore import QThread
    QThread.__init__(worker)
    worker._update_info = update_info
    worker._cancel_event = cancel_event
    
    def on_progress(downloaded, total):
        if progress.wasCanceled():
            cancel_event.set()
            return
        percent = int(downloaded / total * 100) if total > 0 else 0
        progress.setValue(percent)
        progress.setLabelText(
            f"Đang tải: {downloaded / (1024*1024):.1f} MB "
            f"/ {total / (1024*1024):.1f} MB"
        )
    
    def on_finished(result):
        download_result_holder[0] = result
        progress.close()
        loop.quit()
    
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    
    progress.canceled.connect(lambda: cancel_event.set())
    
    worker.start()
    loop.exec()
    
    result = download_result_holder[0]
    if result and result.cancelled:
        return None
    return result


def show_update_error_dialog(result: UpdateCheckResult) -> None:
    """Show a dialog for update check errors (not just silently ignore)."""
    from PyQt6.QtWidgets import QMessageBox
    
    status_text = {
        UpdateCheckStatus.NETWORK_ERROR: "Lỗi kết nối mạng",
        UpdateCheckStatus.SERVER_ERROR: "Máy chủ cập nhật tạm thời lỗi",
        UpdateCheckStatus.CLIENT_CONFIG_ERROR: "Lỗi cấu hình cập nhật",
        UpdateCheckStatus.AUTH_ERROR: "Lỗi xác thực với máy chủ cập nhật",
        UpdateCheckStatus.INVALID_RESPONSE: "Dữ liệu cập nhật không hợp lệ",
        UpdateCheckStatus.APP_NOT_CONFIGURED: "Ứng dụng chưa được cấu hình cập nhật",
    }
    
    title = status_text.get(result.status, "Lỗi kiểm tra cập nhật")
    
    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(result.message)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.addButton("Tiếp tục", QMessageBox.ButtonRole.AcceptRole)
    msg_box.exec()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN UPDATE FLOW (called from main.py)
# ═══════════════════════════════════════════════════════════════════════════════

def run_update_check() -> bool:
    """
    Synchronous update check flow for backward compatibility.
    Called from main.py startup.
    
    Returns:
        True if app needs to exit for update, False to continue.
    """
    result = check_for_update()
    
    if result.status == UpdateCheckStatus.NO_UPDATE:
        return False
    
    if result.status == UpdateCheckStatus.UPDATE_AVAILABLE:
        update_info = result.update_info
        
        # Reject patch updates
        if update_info.package_type == PackageType.PATCH:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                None, "Cập nhật",
                "Bản cập nhật này yêu cầu full installer. "
                "Vui lòng tải bản cài đặt đầy đủ từ trang chủ.",
            )
            if update_info.enforcement == UpdateEnforcement.FORCED:
                sys.exit(0)
            return False
        
        is_forced = (update_info.enforcement == UpdateEnforcement.FORCED)
        user_accepted = show_update_dialog(update_info)
        
        if not user_accepted:
            if is_forced:
                sys.exit(0)
            return False
        
        # Download
        dl_result = show_download_progress_dialog(update_info)
        if not dl_result or not dl_result.success:
            from PyQt6.QtWidgets import QMessageBox
            msg = dl_result.message if dl_result else "Không thể tải bản cập nhật."
            QMessageBox.warning(None, "Lỗi tải cập nhật", msg)
            if is_forced:
                sys.exit(0)
            return False
        
        # Apply
        success = apply_update(dl_result, update_info)
        if success:
            return True
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                None, "Lỗi cập nhật",
                "Không thể áp dụng bản cập nhật. Vui lòng thử lại sau.",
            )
            if is_forced:
                sys.exit(0)
            return False
    
    # Error statuses — show error, don't claim "no update"
    if result.status in (
        UpdateCheckStatus.NETWORK_ERROR,
        UpdateCheckStatus.SERVER_ERROR,
    ):
        # Network/server errors: log and continue (don't block user)
        logger.warning(
            f"[UPDATER] update check failed with {result.status.value}, continuing"
        )
        # Check cached policy for forced minimum version
        cache = _load_update_policy_cache()
        if cache:
            min_ver = cache.get("minimum_supported_version")
            if min_ver:
                try:
                    if parse_version(APP_VERSION) < parse_version(min_ver):
                        show_update_error_dialog(result)
                except Exception:
                    pass
        return False
    
    if result.status in (
        UpdateCheckStatus.CLIENT_CONFIG_ERROR,
        UpdateCheckStatus.AUTH_ERROR,
        UpdateCheckStatus.INVALID_RESPONSE,
        UpdateCheckStatus.APP_NOT_CONFIGURED,
    ):
        # Config errors: show warning but don't block
        show_update_error_dialog(result)
        return False
    
    return False
