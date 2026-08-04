# Tests for update metadata and one-shot pending markers.
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import updater
from dpapi_storage import save_secure_json
from updater import UpdateCheckStatus, UpdateCheckResult, UpdateInfo, check_for_update_logic, run_update_check, validate_install_dir, verify_pending_update_marker


def test_validate_install_dir():
    import shutil
    install = Path.cwd() / "_test_install_dir"
    shutil.rmtree(install, ignore_errors=True)
    try:
        install.mkdir()
        assert not validate_install_dir(install)
        (install / "Video_Cutter.exe").touch()
        assert validate_install_dir(install)
        temp_install = install / "temp_folder"
        temp_install.mkdir()
        (temp_install / "Video_Cutter.exe").touch()
        assert not validate_install_dir(temp_install)
    finally:
        shutil.rmtree(install, ignore_errors=True)

def _create_secure_marker(tmpdir, expected_dir, target_version):
    update_dir = Path(tmpdir) / "VideoCutter" / "updates"
    update_dir.mkdir(parents=True)
    installer = update_dir / "update_latest.exe"
    installer.touch()
    marker_path = Path(tmpdir) / "VideoCutter" / "pending_update.dat"
    marker = {
        "source_version": "1.0.0",
        "target_version": target_version,
        "expected_install_dir": str(expected_dir),
        "installer_path": str(installer),
    }
    save_secure_json(str(marker_path), marker, updater.PENDING_MARKER_ENTROPY)
    return marker_path, installer


def test_verify_pending_update_marker_success_cleans_marker_and_package():
    with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"APPDATA": tmpdir}):
        expected_dir = Path(tmpdir) / "Video Cutter"
        expected_dir.mkdir()
        marker_path, installer = _create_secure_marker(tmpdir, expected_dir, "1.0.1")
        with patch("updater.get_current_install_dir", MagicMock(return_value=expected_dir)), patch("updater.APP_VERSION", "1.0.1"):
            verify_pending_update_marker()
        assert not marker_path.exists()
        assert not installer.exists()


def test_verify_pending_update_marker_mismatch_is_cleared_to_prevent_loop():
    with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"APPDATA": tmpdir}):
        expected_dir = Path(tmpdir) / "Video Cutter"
        expected_dir.mkdir()
        marker_path, installer = _create_secure_marker(tmpdir, expected_dir, "1.0.1")
        with patch("updater.get_current_install_dir", MagicMock(return_value=expected_dir)), patch("updater.APP_VERSION", "1.0.0"):
            verify_pending_update_marker()
        assert not marker_path.exists()
        assert not installer.exists()


def test_check_for_update_errors():
    err404 = urllib.error.HTTPError("url", 404, "Not Found", None, None)
    with patch("urllib.request.urlopen", MagicMock(side_effect=err404)):
        assert check_for_update_logic("video_cutter", "1.0.0").status == UpdateCheckStatus.CLIENT_CONFIG_ERROR
    err502 = urllib.error.HTTPError("url", 502, "Bad Gateway", None, None)
    with patch("urllib.request.urlopen", MagicMock(side_effect=err502)):
        assert check_for_update_logic("video_cutter", "1.0.0").status == UpdateCheckStatus.SERVER_ERROR


def test_update_rejects_missing_integrity_metadata():
    response = MagicMock()
    response.read.return_value = b'[{"latest_version":"2.0.0","download_url":"https://example.com/app.exe","package_type":"full","sha256":null,"file_size":100}]'
    response.__enter__.return_value = response
    with patch("urllib.request.urlopen", MagicMock(return_value=response)):
        assert check_for_update_logic("video_cutter", "1.0.0").status == UpdateCheckStatus.INVALID_RESPONSE
class _FakeSignal:
    def connect(self, _callback):
        pass

class _FakeLoop:
    def exec(self):
        pass
    def quit(self):
        pass

def _forced_update_info():
    return UpdateInfo("2.0.0", None, "https://example.com/app.exe", "Required", "forced", "full", "a" * 64, 100)

def test_forced_update_closes_when_declined():
    result = UpdateCheckResult(UpdateCheckStatus.UPDATE_AVAILABLE, _forced_update_info(), "update")
    class Worker:
        def __init__(self, *_args):
            self.finished_signal = _FakeSignal()
            self.result = result
        def start(self):
            pass
    with patch.object(updater.sys, "frozen", True, create=True), patch("updater.UpdateCheckWorker", Worker), patch("updater.QEventLoop", _FakeLoop), patch("updater.show_update_dialog", return_value=False):
        assert run_update_check() is True

def test_forced_update_closes_when_download_fails():
    result = UpdateCheckResult(UpdateCheckStatus.UPDATE_AVAILABLE, _forced_update_info(), "update")
    class Worker:
        def __init__(self, *_args):
            self.finished_signal = _FakeSignal()
            self.result = result
        def start(self):
            pass
    with patch.object(updater.sys, "frozen", True, create=True), patch("updater.UpdateCheckWorker", Worker), patch("updater.QEventLoop", _FakeLoop), patch("updater.show_update_dialog", return_value=True), patch("updater.run_update_download", return_value=False), patch("updater.QMessageBox.warning"):
        assert run_update_check() is True


def test_google_drive_share_links_are_normalised_to_direct_downloads():
    file_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    share_url = f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"
    open_url = f"https://drive.google.com/open?id={file_id}"

    assert updater._extract_google_drive_file_id(share_url) == file_id
    assert updater._extract_google_drive_file_id(open_url) == file_id
    assert updater._extract_google_drive_file_id("https://attacker-drive.google.com/file/d/1234567890/view") is None
    assert updater._google_drive_download_url(file_id) == (
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    )


def test_google_drive_large_file_confirmation_form_is_supported():
    file_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    page = f'''<!doctype html><html><body>
        <form action="https://drive.usercontent.google.com/download" method="get">
          <input type="hidden" name="id" value="{file_id}">
          <input type="hidden" name="export" value="download">
          <input type="hidden" name="confirm" value="token123">
          <input type="hidden" name="uuid" value="abc123">
        </form>
    </body></html>'''.encode("utf-8")

    result = updater._google_drive_confirmation_url("https://drive.google.com/uc?id=" + file_id, page, file_id)
    assert result is not None
    assert result.startswith("https://drive.usercontent.google.com/download?")
    assert "confirm=token123" in result
    assert "uuid=abc123" in result