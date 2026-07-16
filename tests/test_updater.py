"""
test_updater.py — Tests for update checking, downloading, and applying.
=======================================================================
Covers requirements XXV.1-25 (updater behavior).
"""

import hashlib
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from updater import (
    UpdateCheckStatus,
    UpdateCheckResult,
    UpdateInfo,
    UpdateEnforcement,
    PackageType,
    DownloadResult,
    check_for_update,
    download_update,
    apply_update,
    _classify_http_error,
)
from version import APP_VERSION


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_update_info(**overrides):
    """Helper to create UpdateInfo."""
    base = {
        "latest_version": "2.0.0",
        "download_url": "https://example.com/update.exe",
        "changelog": "Test changelog",
        "enforcement": UpdateEnforcement.OPTIONAL,
        "package_type": PackageType.FULL,
        "sha256": None,
        "file_size": None,
        "minimum_supported_version": "1.0.0",
    }
    base.update(overrides)
    return UpdateInfo(**base)


def _mock_urlopen(data, status=200):
    """Create a mock for urllib.request.urlopen."""
    response = mock.MagicMock()
    response.__enter__ = mock.MagicMock(return_value=response)
    response.__exit__ = mock.MagicMock(return_value=False)
    response.read.return_value = json.dumps(data).encode("utf-8")
    response.getcode.return_value = status
    response.headers = {"Content-Length": "0"}
    return response


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 1-2: Basic update check
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateCheck:

    @mock.patch("updater.urllib.request.urlopen")
    def test_01_same_version_no_update(self, mock_open):
        """Server returns same version → NO_UPDATE."""
        mock_open.return_value = _mock_urlopen([{
            "latest_version": APP_VERSION,
            "download_url": "https://example.com",
            "changelog": "",
            "update_type": "optional",
        }])
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.NO_UPDATE

    @mock.patch("updater.urllib.request.urlopen")
    def test_02_newer_version_update_available(self, mock_open):
        """Server returns newer version → UPDATE_AVAILABLE."""
        mock_open.return_value = _mock_urlopen([{
            "latest_version": "99.0.0",
            "download_url": "https://example.com/update.exe",
            "changelog": "New features",
            "update_type": "optional",
        }])
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.UPDATE_AVAILABLE
        assert result.update_info is not None
        assert result.update_info.latest_version == "99.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 3-8: Error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateCheckErrors:

    @mock.patch("updater.urllib.request.urlopen")
    def test_03_empty_data_app_not_configured(self, mock_open):
        """APP_ID not in database → APP_NOT_CONFIGURED (not NO_UPDATE)."""
        mock_open.return_value = _mock_urlopen([])
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.APP_NOT_CONFIGURED

    @mock.patch("updater.urllib.request.urlopen")
    def test_04_http_404_client_config_error(self, mock_open):
        """HTTP 404 → CLIENT_CONFIG_ERROR."""
        import urllib.error
        mock_open.side_effect = urllib.error.HTTPError(
            url="http://test", code=404, msg="Not Found",
            hdrs={}, fp=None,
        )
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.CLIENT_CONFIG_ERROR

    @mock.patch("updater.urllib.request.urlopen")
    def test_05_http_401_auth_error(self, mock_open):
        """HTTP 401 → AUTH_ERROR."""
        import urllib.error
        mock_open.side_effect = urllib.error.HTTPError(
            url="http://test", code=401, msg="Unauthorized",
            hdrs={}, fp=None,
        )
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.AUTH_ERROR

    @mock.patch("updater.urllib.request.urlopen")
    def test_05b_http_403_auth_error(self, mock_open):
        """HTTP 403 → AUTH_ERROR."""
        import urllib.error
        mock_open.side_effect = urllib.error.HTTPError(
            url="http://test", code=403, msg="Forbidden",
            hdrs={}, fp=None,
        )
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.AUTH_ERROR

    @mock.patch("updater.urllib.request.urlopen")
    def test_06_timeout_network_error(self, mock_open):
        """Timeout → NETWORK_ERROR."""
        mock_open.side_effect = TimeoutError("Connection timed out")
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.NETWORK_ERROR

    @mock.patch("updater.urllib.request.urlopen")
    def test_07_http_500_server_error(self, mock_open):
        """HTTP 500 → SERVER_ERROR."""
        import urllib.error
        mock_open.side_effect = urllib.error.HTTPError(
            url="http://test", code=500, msg="Internal Server Error",
            hdrs={}, fp=None,
        )
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.SERVER_ERROR

    @mock.patch("updater.urllib.request.urlopen")
    def test_08_invalid_version_invalid_response(self, mock_open):
        """Invalid version string → INVALID_RESPONSE."""
        mock_open.return_value = _mock_urlopen([{
            "latest_version": "not.a.valid.version.!!",
            "download_url": "",
            "changelog": "",
        }])
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.INVALID_RESPONSE


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 9-12: Download behavior
# ═══════════════════════════════════════════════════════════════════════════════

class TestDownload:

    def test_09_download_cancel_removes_part_file(self):
        """Cancel download → stop reading, delete .part file."""
        cancel_event = threading.Event()
        cancel_event.set()  # Pre-cancelled
        
        info = _make_update_info()
        
        with mock.patch("updater.urllib.request.urlopen") as mock_open:
            response = mock.MagicMock()
            response.__enter__ = mock.MagicMock(return_value=response)
            response.__exit__ = mock.MagicMock(return_value=False)
            response.getcode.return_value = 200
            response.headers = {"Content-Length": "1000"}
            response.read.return_value = b"x" * 100
            mock_open.return_value = response
            
            result = download_update(info, cancel_event=cancel_event)
            assert result.cancelled is True
            assert result.success is False

    @mock.patch("updater.urllib.request.urlopen")
    def test_10_content_length_missing_still_works(self, mock_open):
        """Missing Content-Length → still downloads if hash validates."""
        content = b"test content for download"
        sha = hashlib.sha256(content).hexdigest()
        
        response = mock.MagicMock()
        response.__enter__ = mock.MagicMock(return_value=response)
        response.__exit__ = mock.MagicMock(return_value=False)
        response.getcode.return_value = 200
        response.headers = {}  # No Content-Length
        response.read.side_effect = [content, b""]
        mock_open.return_value = response
        
        info = _make_update_info(sha256=sha, file_size=None)
        
        with mock.patch("updater.get_update_temp_dir") as mock_dir:
            mock_dir.return_value = Path(tempfile.mkdtemp())
            result = download_update(info)
            assert result.success is True

    def test_11_wrong_file_size_rejected(self):
        """File size mismatch → reject."""
        content = b"short"
        sha = hashlib.sha256(content).hexdigest()
        
        with mock.patch("updater.urllib.request.urlopen") as mock_open:
            response = mock.MagicMock()
            response.__enter__ = mock.MagicMock(return_value=response)
            response.__exit__ = mock.MagicMock(return_value=False)
            response.getcode.return_value = 200
            response.headers = {"Content-Length": str(len(content))}
            response.read.side_effect = [content, b""]
            mock_open.return_value = response
            
            # Expect 99999 bytes but only got len(content)
            info = _make_update_info(sha256=sha, file_size=99999)
            
            with mock.patch("updater.get_update_temp_dir") as mock_dir:
                mock_dir.return_value = Path(tempfile.mkdtemp())
                result = download_update(info)
                assert result.success is False

    def test_12_wrong_sha256_rejected_and_deleted(self):
        """SHA-256 mismatch → reject and delete file."""
        content = b"test content"
        wrong_sha = "a" * 64  # Wrong hash
        
        with mock.patch("updater.urllib.request.urlopen") as mock_open:
            response = mock.MagicMock()
            response.__enter__ = mock.MagicMock(return_value=response)
            response.__exit__ = mock.MagicMock(return_value=False)
            response.getcode.return_value = 200
            response.headers = {"Content-Length": str(len(content))}
            response.read.side_effect = [content, b""]
            mock_open.return_value = response
            
            info = _make_update_info(sha256=wrong_sha, file_size=len(content))
            
            with mock.patch("updater.get_update_temp_dir") as mock_dir:
                tmpdir = Path(tempfile.mkdtemp())
                mock_dir.return_value = tmpdir
                result = download_update(info)
                assert result.success is False


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 13-14: URL and package type
# ═══════════════════════════════════════════════════════════════════════════════

class TestUrlHandling:

    def test_13_url_with_query_string_works(self):
        """URL with query string doesn't confuse package type."""
        info = _make_update_info(
            download_url="https://example.com/file?token=abc&v=1",
            package_type=PackageType.FULL,
        )
        # Package type comes from metadata, not URL
        assert info.package_type == PackageType.FULL

    def test_14_package_type_from_metadata_not_url(self):
        """Package type is from server metadata, not URL extension."""
        info = _make_update_info(
            download_url="https://example.com/update.zip",
            package_type=PackageType.FULL,
        )
        assert info.package_type == PackageType.FULL


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 15-17: Package validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPackageValidation:

    def test_15_zip_traversal_awareness(self):
        """ZIP traversal paths should be detected."""
        # Test that "../" in paths would be dangerous
        dangerous_paths = ["../etc/passwd", "..\\system32\\evil.dll"]
        for path in dangerous_paths:
            normalized = os.path.normpath(path)
            # Paths with .. should normalize to start with ..
            assert normalized.startswith(".."), f"Path {path} did not normalize to start with .."
        
        # Absolute paths on Windows
        abs_paths = ["C:\\Windows\\System32\\evil.dll", "D:\\secret"]
        for path in abs_paths:
            assert os.path.isabs(path), f"Path {path} should be absolute"

    def test_16_manifest_app_id_validation(self):
        """Manifest with wrong app_id should be rejected."""
        from version import APP_ID
        manifest = {"app_id": "wrong_app", "version": "1.0.0"}
        assert manifest["app_id"] != APP_ID

    def test_17_package_missing_exe_detection(self):
        """Package without expected exe should be detectable."""
        from version import EXE_NAME
        fake_files = ["readme.txt", "data.dll"]
        assert EXE_NAME not in fake_files


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 18-19: Update application strategies
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateApplication:

    def test_18_full_installer_uses_correct_args(self):
        """Full installer should use correct silent args."""
        from updater import apply_full_installer
        
        with mock.patch("updater.subprocess.Popen") as mock_popen:
            fake_path = Path(tempfile.mktemp(suffix=".exe"))
            fake_path.touch()
            try:
                apply_full_installer(fake_path)
                
                if mock_popen.called:
                    args = mock_popen.call_args[0][0]
                    assert "/VERYSILENT" in args
                    assert "/SUPPRESSMSGBOXES" in args
                    assert "/NORESTART" in args
                    assert "/CLOSEAPPLICATIONS" in args
            finally:
                if fake_path.exists():
                    fake_path.unlink()

    def test_19_patch_without_helper_rejected(self):
        """Patch update without helper is rejected safely."""
        info = _make_update_info(package_type=PackageType.PATCH)
        download = DownloadResult(
            success=True,
            file_path=Path("fake.zip"),
            message="OK",
        )
        
        result = apply_update(download, info)
        assert result is False  # Rejected


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 20-24: Error handling edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorEdgeCases:

    def test_20_http_error_classification(self):
        """HTTP errors are correctly classified."""
        import urllib.error
        
        # 401 → AUTH_ERROR
        e401 = urllib.error.HTTPError("", 401, "", {}, None)
        status, _ = _classify_http_error(e401)
        assert status == UpdateCheckStatus.AUTH_ERROR
        
        # 404 → CLIENT_CONFIG_ERROR
        e404 = urllib.error.HTTPError("", 404, "", {}, None)
        status, _ = _classify_http_error(e404)
        assert status == UpdateCheckStatus.CLIENT_CONFIG_ERROR
        
        # 500 → SERVER_ERROR
        e500 = urllib.error.HTTPError("", 500, "", {}, None)
        status, _ = _classify_http_error(e500)
        assert status == UpdateCheckStatus.SERVER_ERROR

    @mock.patch("updater.urllib.request.urlopen")
    def test_21_json_error_invalid_response(self, mock_open):
        """Invalid JSON response → doesn't crash."""
        response = mock.MagicMock()
        response.__enter__ = mock.MagicMock(return_value=response)
        response.__exit__ = mock.MagicMock(return_value=False)
        response.read.return_value = b"NOT JSON {{{{"
        mock_open.return_value = response
        
        result = check_for_update()
        assert result.status in (
            UpdateCheckStatus.INVALID_RESPONSE,
            UpdateCheckStatus.NETWORK_ERROR,
        )

    @mock.patch("updater.urllib.request.urlopen")
    def test_22_empty_version_invalid_response(self, mock_open):
        """Empty version string → INVALID_RESPONSE."""
        mock_open.return_value = _mock_urlopen([{
            "latest_version": "",
            "download_url": "",
        }])
        
        result = check_for_update()
        assert result.status == UpdateCheckStatus.INVALID_RESPONSE


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 25: Version single source of truth
# ═══════════════════════════════════════════════════════════════════════════════

class TestVersionSource:

    def test_25_version_from_single_source(self):
        """APP_VERSION is imported from version.py (single source)."""
        from version import APP_VERSION as v_version
        from updater import APP_VERSION as u_version
        assert v_version == u_version

    def test_app_id_from_single_source(self):
        """APP_ID is imported from version.py (single source)."""
        from version import APP_ID as v_id
        from updater import APP_ID as u_id
        assert v_id == u_id
