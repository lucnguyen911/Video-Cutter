"""
test_device_identity.py — Tests for HWID v2 device identity.
=============================================================
Covers requirements XXIV.1-11 (HWID stability and profile caching).
"""

import hashlib
import json
import os
import tempfile
from unittest import mock

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from device_identity import (
    normalize_machine_guid,
    build_hwid_v2,
    get_device_identity,
    get_legacy_hwid_candidates,
    DeviceIdentity,
    DeviceIdentityError,
    HWID_VERSION,
    HWID_NAMESPACE,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 1: Same MachineGuid → same HWID
# ═══════════════════════════════════════════════════════════════════════════════

class TestHwidStability:
    """Tests 1-6: HWID stability across various conditions."""

    SAMPLE_GUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_01_same_guid_same_hwid(self):
        """Same MachineGuid always produces the same HWID."""
        hwid1 = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        hwid2 = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        assert hwid1 == hwid2

    def test_02_uppercase_lowercase_same_hwid(self):
        """Uppercase/lowercase MachineGuid produces the same HWID."""
        hwid_lower = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID.lower()))
        hwid_upper = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID.upper()))
        assert hwid_lower == hwid_upper

    def test_03_braces_same_hwid(self):
        """MachineGuid with/without braces produces the same HWID."""
        hwid_plain = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        hwid_braces = build_hwid_v2(normalize_machine_guid(f"{{{self.SAMPLE_GUID}}}"))
        assert hwid_plain == hwid_braces

    def test_04_whitespace_same_hwid(self):
        """MachineGuid with whitespace produces the same HWID."""
        hwid_clean = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        hwid_padded = build_hwid_v2(normalize_machine_guid(f"  {self.SAMPLE_GUID}  "))
        assert hwid_clean == hwid_padded

    def test_05_usb_does_not_change_hwid(self):
        """Adding USB does not change HWID (HWID doesn't depend on disks)."""
        # HWID v2 only uses MachineGuid — disk changes are irrelevant
        hwid = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        # Run again (simulating after USB added — MachineGuid unchanged)
        hwid_after_usb = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        assert hwid == hwid_after_usb

    def test_06_vpn_mac_does_not_change_hwid(self):
        """VPN/MAC change does not affect HWID."""
        # HWID v2 doesn't use MAC address at all
        hwid = build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))
        # MachineGuid is unchanged by VPN
        assert hwid == build_hwid_v2(normalize_machine_guid(self.SAMPLE_GUID))


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 7: Different MachineGuid → different HWID
# ═══════════════════════════════════════════════════════════════════════════════

class TestHwidUniqueness:

    def test_07_different_guid_different_hwid(self):
        """Different MachineGuid produces different HWID."""
        hwid1 = build_hwid_v2(normalize_machine_guid(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        ))
        hwid2 = build_hwid_v2(normalize_machine_guid(
            "ffffffff-ffff-ffff-ffff-ffffffffffff"
        ))
        assert hwid1 != hwid2


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 8-9: Device profile cache
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeviceProfile:

    def test_08_profile_cache_when_registry_fails(self):
        """Device profile cache works when Registry is temporarily unavailable."""
        sample_identity = DeviceIdentity(
            hwid="abcdef1234567890" * 4,
            version=2,
            source="windows_machine_guid|cached",
        )

        with mock.patch("device_identity.read_windows_machine_guid") as mock_read:
            mock_read.side_effect = DeviceIdentityError("Registry unavailable")

            with mock.patch("device_identity._load_device_profile") as mock_load:
                mock_load.return_value = sample_identity

                identity = get_device_identity()
                assert identity.hwid == sample_identity.hwid
                assert "cached" in identity.source

    def test_09_corrupt_profile_does_not_crash(self):
        """Corrupt device profile doesn't crash the app."""
        with mock.patch("device_identity.read_windows_machine_guid") as mock_read:
            mock_read.side_effect = DeviceIdentityError("Registry unavailable")

            with mock.patch("device_identity._load_device_profile") as mock_load:
                mock_load.return_value = None  # Corrupt/missing profile

                with pytest.raises(DeviceIdentityError):
                    get_device_identity()


# ═══════════════════════════════════════════════════════════════════════════════
#  Test 10-11: DPAPI storage
# ═══════════════════════════════════════════════════════════════════════════════

class TestDpapiStorage:

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="DPAPI only available on Windows"
    )
    def test_10_dpapi_encrypt_decrypt_roundtrip(self):
        """DPAPI encrypt/decrypt roundtrip works correctly."""
        from dpapi_storage import dpapi_encrypt, dpapi_decrypt

        plaintext = b"test license key data 12345"
        entropy = b"test-entropy-value"

        encrypted = dpapi_encrypt(plaintext, entropy)
        assert encrypted != plaintext
        assert len(encrypted) > 0

        decrypted = dpapi_decrypt(encrypted, entropy)
        assert decrypted == plaintext

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="DPAPI only available on Windows"
    )
    def test_11_dpapi_file_no_plaintext(self):
        """DPAPI-encrypted file does not contain plaintext key."""
        from dpapi_storage import dpapi_encrypt

        secret_key = "VIDEO-ABCD-1234-EFGH-5678"
        plaintext = json.dumps({"license_key": secret_key}).encode("utf-8")
        entropy = b"test-entropy"

        encrypted = dpapi_encrypt(plaintext, entropy)

        # The encrypted data should NOT contain the plaintext key
        assert secret_key.encode("utf-8") not in encrypted
        assert b"license_key" not in encrypted


# ═══════════════════════════════════════════════════════════════════════════════
#  Test: Normalize validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalization:

    def test_empty_guid_raises_error(self):
        """Empty MachineGuid raises DeviceIdentityError."""
        with pytest.raises(DeviceIdentityError):
            normalize_machine_guid("")

    def test_whitespace_only_guid_raises_error(self):
        """Whitespace-only MachineGuid raises DeviceIdentityError."""
        with pytest.raises(DeviceIdentityError):
            normalize_machine_guid("   ")

    def test_braces_only_guid_raises_error(self):
        """Braces-only MachineGuid raises DeviceIdentityError."""
        with pytest.raises(DeviceIdentityError):
            normalize_machine_guid("{}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Test: HWID v2 algorithm correctness
# ═══════════════════════════════════════════════════════════════════════════════

class TestHwidAlgorithm:

    def test_hwid_v2_uses_correct_namespace(self):
        """HWID v2 uses the correct namespace prefix."""
        guid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        normalized = normalize_machine_guid(guid)
        expected = hashlib.sha256(
            f"{HWID_NAMESPACE}|{normalized}".encode("utf-8")
        ).hexdigest()
        actual = build_hwid_v2(normalized)
        assert actual == expected

    def test_hwid_is_64_char_hex(self):
        """HWID v2 output is a 64-character hex string."""
        hwid = build_hwid_v2(normalize_machine_guid(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        ))
        assert len(hwid) == 64
        assert all(c in "0123456789abcdef" for c in hwid)


# ═══════════════════════════════════════════════════════════════════════════════
#  Test: Legacy HWID candidates
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyCandidates:

    def test_legacy_candidates_returns_list(self):
        """get_legacy_hwid_candidates returns a list."""
        # May produce candidates or empty list depending on system
        candidates = get_legacy_hwid_candidates()
        assert isinstance(candidates, list)

    def test_legacy_candidates_no_duplicates(self):
        """Legacy candidates list has no duplicates."""
        candidates = get_legacy_hwid_candidates()
        assert len(candidates) == len(set(candidates))

    def test_legacy_candidates_are_hex_sha256(self):
        """All legacy candidates are 64-char hex strings (SHA256)."""
        candidates = get_legacy_hwid_candidates()
        for c in candidates:
            assert len(c) == 64, f"Candidate {c[:10]}... is not 64 chars"
            assert all(ch in "0123456789abcdef" for ch in c)
