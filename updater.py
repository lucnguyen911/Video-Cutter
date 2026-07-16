"""
updater.py — Module Tự động Cập nhật cho Video Factory
======================================================
Kiểm tra phiên bản mới nhất từ bảng `app_versions` trên Supabase,
tải bản cập nhật từ GitHub Release, và áp dụng bằng cơ chế ghi đè (patching).
"""

import json
import os
import sys
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from packaging.version import parse as parse_version

# Import credentials từ security.py (single source of truth)
from security import SUPABASE_URL, SUPABASE_KEY

# ═══════════════════════════════════════════════════════════════════════════════
#  HẰNG SỐ
# ═══════════════════════════════════════════════════════════════════════════════

CURRENT_VERSION = "1.0.0"
APP_ID = "video_factory"


# ═══════════════════════════════════════════════════════════════════════════════
#  HÀM TIỆN ÍCH
# ═══════════════════════════════════════════════════════════════════════════════

def get_app_dir() -> Path:
    """Trả về thư mục gốc của ứng dụng (hỗ trợ cả dev và PyInstaller onedir)."""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: sys.executable nằm trong thư mục dist/VideoFactory/
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent


def get_update_temp_dir() -> Path:
    """Trả về thư mục tạm lưu file update, nằm trong %APPDATA%/VideoFactory/updates."""
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    update_dir = Path(app_data) / "VideoFactory" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    return update_dir


# ═══════════════════════════════════════════════════════════════════════════════
#  KIỂM TRA CẬP NHẬT
# ═══════════════════════════════════════════════════════════════════════════════

def check_for_update() -> Optional[dict]:
    """
    Gọi API Supabase để kiểm tra phiên bản mới nhất của video_factory.

    Returns:
        dict chứa thông tin update nếu có bản mới, None nếu đã mới nhất hoặc lỗi.
        Keys: latest_version, download_url, changelog, update_type
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    url = f"{SUPABASE_URL}/rest/v1/app_versions?app_id=eq.{APP_ID}"
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        if not data:
            return None

        record = data[0]
        latest_version = record.get("latest_version", "")
        download_url = record.get("download_url", "")
        changelog = record.get("changelog", "")
        update_type = record.get("update_type", "optional")  # "optional" | "forced"

        if not latest_version:
            return None

        # So sánh phiên bản bằng packaging.version
        if parse_version(latest_version) > parse_version(CURRENT_VERSION):
            return {
                "latest_version": latest_version,
                "download_url": download_url,
                "changelog": changelog,
                "update_type": update_type,
            }

        return None  # Đã dùng bản mới nhất

    except Exception as e:
        print(f"[Updater] Lỗi kiểm tra cập nhật: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  TẢI BẢN CẬP NHẬT
# ═══════════════════════════════════════════════════════════════════════════════

def download_update(
    download_url: str,
    progress_callback=None,
) -> Optional[Path]:
    """
    Tải file .zip cập nhật từ URL (GitHub Release).

    Args:
        download_url: URL trực tiếp tới file .zip trên GitHub Release.
        progress_callback: Hàm callback(downloaded_bytes, total_bytes) để cập nhật tiến trình.

    Returns:
        Path tới file .zip đã tải, hoặc None nếu lỗi.
    """
    if not download_url:
        return None

    try:
        req = urllib.request.Request(download_url, method="GET")
        update_dir = get_update_temp_dir()
        ext = ".exe" if download_url.lower().endswith(".exe") else ".zip"
        zip_path = update_dir / f"update_latest{ext}"

        with urllib.request.urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192

            with open(zip_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

        return zip_path

    except Exception as e:
        print(f"[Updater] Lỗi tải bản cập nhật: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  ÁP DỤNG BẢN CẬP NHẬT (PATCHING)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_update(zip_path: Path) -> bool:
    """
    Giải nén file .zip update và ghi đè vào thư mục cài đặt hiện tại.
    Sau đó khởi động lại ứng dụng.

    Cơ chế: Tạo một batch script tạm để:
    1. Đợi process cũ thoát
    2. Copy file mới ghi đè
    3. Khởi chạy lại app
    4. Tự xóa batch script

    Args:
        zip_path: Đường dẫn tới file .zip cập nhật đã tải về.

    Returns:
        True nếu bắt đầu quá trình update thành công (app sẽ restart).
    """
    if not zip_path or not zip_path.exists():
        return False

    try:
        if zip_path.suffix.lower() == ".exe":
            current_app_dir = os.path.dirname(sys.executable)
            subprocess.Popen([str(zip_path), "/VERYSILENT", f"/DIR={current_app_dir}"])
            os._exit(0)
            return True

        app_dir = get_app_dir()
        update_dir = get_update_temp_dir()
        extract_dir = update_dir / "extracted"

        # Xóa thư mục extract cũ nếu có
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)

        # Giải nén
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # Tìm thư mục gốc trong zip (có thể có 1 thư mục con bọc ngoài)
        extracted_items = list(extract_dir.iterdir())
        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            source_dir = extracted_items[0]
        else:
            source_dir = extract_dir

        # Xác định đường dẫn exe hiện tại
        if getattr(sys, "frozen", False):
            exe_path = sys.executable
        else:
            exe_path = sys.argv[0]

        # Tạo batch script để thực hiện update sau khi app thoát
        batch_path = update_dir / "do_update.bat"
        batch_content = fr'''@echo off
chcp 65001 >nul
echo Dang cap nhat Video Cutter...
:: Doi process cu thoat (toi da 10 giay)
timeout /t 3 /nobreak >nul

:: Copy ghi de file moi vao thu muc cai dat
xcopy /s /e /y "{source_dir}\*" "{app_dir}\" >nul 2>&1

:: Khoi chay lai ung dung
start "" "{exe_path}"

:: Don dep file update tam
rmdir /s /q "{extract_dir}" >nul 2>&1
del "{zip_path}" >nul 2>&1

:: Tu xoa batch script nay
(goto) 2>nul & del "%~f0"
'''
        with open(batch_path, "w", encoding="utf-8") as f:
            f.write(batch_content)

        # Chạy batch script trong background và thoát app hiện tại
        if os.name == "nt":
            subprocess.Popen(
                ["cmd.exe", "/c", str(batch_path)],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
        else:
            subprocess.Popen(["bash", str(batch_path)])

        return True

    except Exception as e:
        print(f"[Updater] Lỗi áp dụng cập nhật: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  DIALOG THÔNG BÁO CẬP NHẬT (PyQt6)
# ═══════════════════════════════════════════════════════════════════════════════

def show_update_dialog(update_info: dict) -> bool:
    """
    Hiển thị dialog thông báo có bản cập nhật mới.
    Nếu update_type == "forced", không cho phép bỏ qua.

    Args:
        update_info: dict từ check_for_update()

    Returns:
        True nếu người dùng đồng ý cập nhật.
    """
    from PyQt6.QtWidgets import QMessageBox, QApplication

    latest_version = update_info.get("latest_version", "?")
    changelog = update_info.get("changelog", "Không có thông tin chi tiết.")
    update_type = update_info.get("update_type", "optional")
    is_forced = (update_type == "forced")

    title = "Cập nhật bắt buộc!" if is_forced else "Phiên bản mới khả dụng!"

    message = (
        f"Phiên bản hiện tại: v{CURRENT_VERSION}\n"
        f"Phiên bản mới:        v{latest_version}\n\n"
        f"{'─' * 40}\n"
        f"Có gì mới:\n{changelog}\n"
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
        btn_exit = msg_box.addButton("Thoát ứng dụng", QMessageBox.ButtonRole.RejectRole)
    else:
        msg_box.addButton("Cập nhật ngay", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton("Bỏ qua", QMessageBox.ButtonRole.RejectRole)

    result = msg_box.exec()

    # AcceptRole = 0, RejectRole = 1
    clicked = msg_box.clickedButton()
    button_role = msg_box.buttonRole(clicked)

    return button_role == QMessageBox.ButtonRole.AcceptRole


def show_download_progress_dialog(download_url: str) -> Optional[Path]:
    """
    Hiển thị dialog tiến trình tải update.

    Returns:
        Path tới file zip đã tải, hoặc None nếu lỗi.
    """
    from PyQt6.QtWidgets import QProgressDialog, QApplication
    from PyQt6.QtCore import Qt

    progress = QProgressDialog("Đang tải bản cập nhật...", "Hủy", 0, 100)
    progress.setWindowTitle("Tải cập nhật")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    was_cancelled = False

    def on_progress(downloaded, total):
        nonlocal was_cancelled
        if progress.wasCanceled():
            was_cancelled = True
            return
        percent = int(downloaded / total * 100) if total > 0 else 0
        progress.setValue(percent)
        progress.setLabelText(
            f"Đang tải: {downloaded / (1024*1024):.1f} MB / {total / (1024*1024):.1f} MB"
        )
        QApplication.processEvents()

    zip_path = download_update(download_url, progress_callback=on_progress)

    progress.close()

    if was_cancelled:
        # Xóa file tải dở nếu bị hủy
        if zip_path and zip_path.exists():
            zip_path.unlink(missing_ok=True)
        return None

    return zip_path


def run_update_check():
    """
    Hàm tổng hợp: kiểm tra update → hiện dialog → tải → áp dụng → restart.
    Được gọi từ main.py sau khi license check pass.

    Returns:
        True nếu app cần thoát để update, False nếu tiếp tục bình thường.
    """
    update_info = check_for_update()
    if not update_info:
        return False  # Không có bản mới, tiếp tục bình thường

    is_forced = (update_info.get("update_type") == "forced")

    # Hiển thị dialog hỏi user
    user_accepted = show_update_dialog(update_info)

    if not user_accepted:
        if is_forced:
            # Forced update mà từ chối → thoát app
            sys.exit(0)
        return False  # Optional update bị bỏ qua

    # Tải bản cập nhật
    zip_path = show_download_progress_dialog(update_info.get("download_url", ""))
    if not zip_path:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None,
            "Lỗi tải cập nhật",
            "Không thể tải bản cập nhật. Vui lòng thử lại sau."
        )
        if is_forced:
            sys.exit(0)
        return False

    # Áp dụng update và restart
    success = apply_update(zip_path)
    if success:
        return True  # Báo cho main.py biết cần thoát
    else:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None,
            "Lỗi cập nhật",
            "Không thể áp dụng bản cập nhật. Vui lòng thử lại sau."
        )
        if is_forced:
            sys.exit(0)
        return False
