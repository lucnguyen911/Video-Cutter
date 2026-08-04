# tests/test_device_identity.py
# Tests HWID v2 generation logic, registry and powershell queries, and fallback.

import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest

import device_identity
from device_identity import (
    get_windows_machine_guid,
    get_motherboard_uuid_powershell,
    build_hwid_v2,
    get_device_identity,
    get_legacy_hwid_candidates,
    DeviceIdentity
)

def test_hwid_v2_determinism():
    guid = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    mb_uuid = "e0021a80-0c30-11e2-b883-00262d0dfde0"
    
    h1 = build_hwid_v2(guid, mb_uuid)
    h2 = build_hwid_v2(guid, mb_uuid)
    assert h1 == h2
    
    # Different guid or motherboard_uuid must produce different hwid
    h3 = build_hwid_v2(guid, "different-mb-uuid")
    assert h1 != h3

def test_get_device_identity_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            profile_path = device_identity.get_profile_path()
            assert not os.path.exists(profile_path)
            
            with patch("device_identity.get_windows_machine_guid", return_guid := MagicMock(return_value="12345678-abcd-efab-cdef-123456789abc")):
                with patch("device_identity.get_motherboard_uuid_powershell", return_mb := MagicMock(return_value="e0021a80-0c30-11e2-b883-00262d0dfde0")):
                    identity = get_device_identity()
                    assert isinstance(identity, DeviceIdentity)
                    assert identity.version == 3
                    assert identity.source == "motherboard_uuid"
                    
                    # Check profile was written
                    assert os.path.exists(profile_path)
                    
                    # Verify that next time it loads from profile rather than registry
                    return_guid.reset_mock()
                    return_mb.reset_mock()
                    identity_cached = get_device_identity()
                    assert identity_cached.hwid == identity.hwid
                    return_guid.assert_not_called()
                    return_mb.assert_not_called()

def test_get_device_identity_fallback_on_query_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            profile_path = device_identity.get_profile_path()
            
            # Step 1: Initialize profile successfully
            with patch("device_identity.get_windows_machine_guid", MagicMock(return_value="ok-guid")):
                with patch("device_identity.get_motherboard_uuid_powershell", MagicMock(return_value="ok-mb-uuid")):
                    identity_first = get_device_identity()
                
            # Step 2: Queries fail but cache is present. Should return cached.
            with patch("device_identity.get_windows_machine_guid", MagicMock(return_value="")):
                with patch("device_identity.get_motherboard_uuid_powershell", MagicMock(return_value="")):
                    identity_second = get_device_identity()
                    assert identity_second.hwid == identity_first.hwid

def test_get_device_identity_corrupt_cache_recovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            profile_path = device_identity.get_profile_path()
            
            # Write corrupted file to cache
            os.makedirs(os.path.dirname(profile_path), exist_ok=True)
            with open(profile_path, "wb") as f:
                f.write(b"corrupted binary data")
                
            # Should not crash, should query registry and regenerate cached file
            with patch("device_identity.get_windows_machine_guid", return_guid := MagicMock(return_value="recovered-guid")):
                with patch("device_identity.get_motherboard_uuid_powershell", return_mb := MagicMock(return_value="recovered-mb-uuid")):
                    identity = get_device_identity()
                    assert identity.hwid == device_identity.build_hwid_v3("recovered-mb-uuid", "motherboard_uuid")
                    return_guid.assert_not_called()
                    return_mb.assert_called_once()
                    
                    # Verify cache is healthy again
                    return_guid.reset_mock()
                    return_mb.reset_mock()
                    identity_cached = get_device_identity()
                    assert identity_cached.hwid == identity.hwid
                    return_guid.assert_not_called()
                    return_mb.assert_not_called()

def test_legacy_hwid_candidates():
    candidates = get_legacy_hwid_candidates()
    assert isinstance(candidates, list)
    assert len(candidates) > 0
    for c in candidates:
        assert len(c) == 64 # SHA-256 length
