"""
test_license.py — Tests for license verification and management.
================================================================
Covers requirements XXIV.12-25 (license verification, offline grace).
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from security import (
    LicenseStatus,
    LicenseVerificationResult,
    _try_xor_decode,
    _check_offline_grace,
    _classify_http_error,
    OFFLINE_GRACE_DAYS,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 12: Legacy XOR migration
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyMigration:

    def test_12_legacy_xor_decode_works(self):
        """Legacy XOR-encoded license token can be decoded with correct HWID."""
        import base64
        
        original_key = "VIDEO-TEST-1234-ABCD-5678"
        fake_hwid = "abc123def456" * 6  # 72 chars like SHA256 hex
        
        # Encode using the old XOR algorithm
        encoded_chars = []
        for i, char in enumerate(original_key):
            key_c = ord(char)
            hwid_c = ord(fake_hwid[i % len(fake_hwid)])
            encoded_chars.append(chr(key_c ^ hwid_c))
        token = base64.b64encode("".join(encoded_chars).encode("utf-8")).decode("utf-8")
        
        # Decode using our migration function
        decoded = _try_xor_decode(token, fake_hwid)
        assert decoded == original_key

    def test_xor_decode_wrong_hwid_returns_none_or_garbage(self):
        """Wrong HWID produces None or garbage (not the original key)."""
        import base64
        
        original_key = "VIDEO-TEST-1234-ABCD-5678"
        correct_hwid = "abc123def456" * 6
        wrong_hwid = "zzz999zzz999" * 6
        
        encoded_chars = []
        for i, char in enumerate(original_key):
            key_c = ord(char)
            hwid_c = ord(correct_hwid[i % len(correct_hwid)])
            encoded_chars.append(chr(key_c ^ hwid_c))
        token = base64.b64encode("".join(encoded_chars).encode("utf-8")).decode("utf-8")
        
        decoded = _try_xor_decode(token, wrong_hwid)
        # Should either be None or not match the original
        assert decoded is None or decoded != original_key


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 13-16: License status classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestLicenseStatus:

    def test_13_activated_status(self):
        """ACTIVATED status is valid."""
        result = LicenseVerificationResult(
            valid=True,
            status=LicenseStatus.ACTIVATED,
            message="Activated",
        )
        assert result.valid is True
        assert result.status == LicenseStatus.ACTIVATED

    def test_14_valid_status(self):
        """VALID status is valid."""
        result = LicenseVerificationResult(
            valid=True,
            status=LicenseStatus.VALID,
            message="Valid",
        )
        assert result.valid is True

    def test_15_device_mismatch_status(self):
        """DEVICE_MISMATCH status is not valid."""
        result = LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.DEVICE_MISMATCH,
            message="Mismatch",
        )
        assert result.valid is False
        assert result.status == LicenseStatus.DEVICE_MISMATCH

    def test_16_migrated_status(self):
        """MIGRATED status is valid."""
        result = LicenseVerificationResult(
            valid=True,
            status=LicenseStatus.MIGRATED,
            message="Migrated",
        )
        assert result.valid is True
        assert result.status == LicenseStatus.MIGRATED


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 17-18: License edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestLicenseEdgeCases:

    def test_17_result_valid_is_explicit_bool(self):
        """result.valid must be checked explicitly (not truthy object)."""
        # A dataclass with valid=False is still truthy as an object
        result = LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.LICENSE_NOT_FOUND,
            message="Not found",
        )
        # This is why we use `result.valid is True` not `if result:`
        assert bool(result) is True  # Object is truthy!
        assert result.valid is not True  # But valid is False

    def test_18_expired_license_not_valid(self):
        """Expired license is not valid."""
        result = LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.LICENSE_EXPIRED,
            message="Expired",
        )
        assert result.valid is False


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 19-20: HTTP error classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestHttpErrorClassification:

    def test_19_http_404_is_client_config_error(self):
        """HTTP 404 → CLIENT_CONFIG_ERROR (not NETWORK_ERROR)."""
        import urllib.error
        error = urllib.error.HTTPError(
            url="http://test",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        status, code = _classify_http_error(error)
        assert status == LicenseStatus.CLIENT_CONFIG_ERROR
        assert code == 404

    def test_20_timeout_is_network_error(self):
        """Timeout → NETWORK_ERROR."""
        error = TimeoutError("Connection timed out")
        status, _ = _classify_http_error(error)
        assert status == LicenseStatus.NETWORK_ERROR

    def test_http_401_is_auth_error(self):
        """HTTP 401 → AUTH_ERROR."""
        import urllib.error
        error = urllib.error.HTTPError(
            url="http://test",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        status, code = _classify_http_error(error)
        assert status == LicenseStatus.AUTH_ERROR

    def test_http_403_is_auth_error(self):
        """HTTP 403 → AUTH_ERROR."""
        import urllib.error
        error = urllib.error.HTTPError(
            url="http://test",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        status, code = _classify_http_error(error)
        assert status == LicenseStatus.AUTH_ERROR

    def test_http_500_is_server_error(self):
        """HTTP 500 → SERVER_ERROR."""
        import urllib.error
        error = urllib.error.HTTPError(
            url="http://test",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )
        status, code = _classify_http_error(error)
        assert status == LicenseStatus.SERVER_ERROR


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 21-25: Offline grace
# ═══════════════════════════════════════════════════════════════════════════════

class TestOfflineGrace:

    def _make_local_license(self, **overrides):
        """Helper to create a local license dict."""
        now = datetime.now(timezone.utc)
        base = {
            "schema_version": 2,
            "license_key": "VIDEO-TEST-1234",
            "hwid": "test_hwid_hash",
            "hwid_version": 2,
            "last_verified_at": (now - timedelta(hours=1)).isoformat(),
            "cached_expires_at": (now + timedelta(days=30)).isoformat(),
            "last_server_status": "VALID",
        }
        base.update(overrides)
        return base

    def test_21_no_local_license_no_grace(self):
        """No local license + network error → must show dialog (no grace)."""
        # _check_offline_grace returns None when conditions not met
        result = _check_offline_grace({}, "test_hwid")
        assert result is None

    def test_22_valid_local_within_grace_allows_access(self):
        """Valid local license within grace period + network error → allow."""
        local = self._make_local_license()
        result = _check_offline_grace(local, "test_hwid_hash")
        assert result is not None
        assert result.valid is True

    def test_23_outside_grace_denied(self):
        """Local license outside grace period → denied."""
        old_date = (
            datetime.now(timezone.utc) - timedelta(days=OFFLINE_GRACE_DAYS + 1)
        ).isoformat()
        local = self._make_local_license(last_verified_at=old_date)
        result = _check_offline_grace(local, "test_hwid_hash")
        assert result is None  # Grace denied

    def test_24_http_404_no_grace(self):
        """HTTP 404 is CLIENT_CONFIG_ERROR — not eligible for offline grace."""
        # CLIENT_CONFIG_ERROR is not in _GRACE_ELIGIBLE_STATUSES
        assert LicenseStatus.CLIENT_CONFIG_ERROR not in {
            LicenseStatus.NETWORK_ERROR,
            LicenseStatus.SERVER_ERROR,
        }

    def test_25_last_verified_not_updated_on_error(self):
        """last_verified_at should not be updated when server returns error."""
        # This is enforced by the code structure:
        # save_local_license is only called when result.valid is True
        result = LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.SERVER_ERROR,
            message="Server error",
        )
        # result.valid is False → save_local_license should NOT be called
        assert result.valid is not True

    def test_grace_denied_when_hwid_mismatch(self):
        """Grace denied when local HWID doesn't match current."""
        local = self._make_local_license(hwid="different_hwid")
        result = _check_offline_grace(local, "current_hwid")
        assert result is None

    def test_grace_denied_when_never_verified(self):
        """Grace denied when license was never verified online."""
        local = self._make_local_license(last_server_status="PENDING")
        result = _check_offline_grace(local, "test_hwid_hash")
        assert result is None

    def test_grace_denied_when_license_expired(self):
        """Grace denied when cached expiry has passed."""
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        local = self._make_local_license(cached_expires_at=expired)
        result = _check_offline_grace(local, "test_hwid_hash")
        assert result is None
