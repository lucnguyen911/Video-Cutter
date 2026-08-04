# tests/test_license.py
# Tests licensing validation, offline grace logic, and migration.

import os
import json
import base64
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest
import urllib.error

import security
from security import (
    check_license_on_startup,
    verify_license_online,
    save_local_license,
    load_local_license,
    get_license_file_path,
    LicenseVerificationResult
)

# Helper to mock urllib responses
def make_mock_response(status_code, body_dict):
    mock = MagicMock()
    mock.getcode.return_value = status_code
    mock.read.return_value = json.dumps(body_dict).encode("utf-8")
    mock.__enter__.return_value = mock
    return mock

def test_verify_license_online_success():
    mock_resp = make_mock_response(200, {
        "valid": True,
        "status": "VALID",
        "message": "Bản quyền hợp lệ.",
        "expired_at": "2029-12-31T23:59:59Z"
    })
    
    with patch("urllib.request.urlopen", MagicMock(return_value=mock_resp)):
        res = verify_license_online("TEST-KEY", "TEST-HWID")
        assert res.valid is True
        assert res.status == "VALID"
        assert res.expired_at == "2029-12-31T23:59:59Z"

def test_verify_license_online_errors():
    # 1. HTTP 404 -> CLIENT_CONFIG_ERROR
    err404 = urllib.error.HTTPError("url", 404, "Not Found", None, None)
    with patch("urllib.request.urlopen", MagicMock(side_effect=err404)):
        res = verify_license_online("KEY", "HWID")
        assert res.valid is False
        assert res.status == "CLIENT_CONFIG_ERROR"

    # 2. HTTP 401 -> AUTH_ERROR
    err401 = urllib.error.HTTPError("url", 401, "Unauthorized", None, None)
    with patch("urllib.request.urlopen", MagicMock(side_effect=err401)):
        res = verify_license_online("KEY", "HWID")
        assert res.valid is False
        assert res.status == "AUTH_ERROR"

    # 3. HTTP 500 -> SERVER_ERROR
    err500 = urllib.error.HTTPError("url", 500, "Internal Server Error", None, None)
    with patch("urllib.request.urlopen", MagicMock(side_effect=err500)):
        res = verify_license_online("KEY", "HWID")
        assert res.valid is False
        assert res.status == "SERVER_ERROR"

    # 4. URLError -> NETWORK_ERROR
    err_url = urllib.error.URLError("DNS failure")
    with patch("urllib.request.urlopen", MagicMock(side_effect=err_url)):
        res = verify_license_online("KEY", "HWID")
        assert res.valid is False
        assert res.status == "NETWORK_ERROR"

def test_offline_grace_authorized():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            # Set up local license that was verified 1 day ago
            last_verified = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
            cached_expires = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
            
            with patch("security.get_hwid", MagicMock(return_value="SAME-HWID")):
                save_local_license("KEY", "VALID", last_verified, cached_expires)
                
                # Mock online verification to fail with NETWORK_ERROR
                net_err = urllib.error.URLError("No internet connection")
                with patch("urllib.request.urlopen", MagicMock(side_effect=net_err)):
                    res, key = check_license_on_startup()
                    # Grace period should authorize startup
                    assert res.valid is True
                    assert res.status == "VALID"
                    assert key == "KEY"

def test_offline_grace_denied_past_3_days():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            # verified 4 days ago
            last_verified = (datetime.utcnow() - timedelta(days=4)).isoformat() + "Z"
            cached_expires = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
            
            with patch("security.get_hwid", MagicMock(return_value="SAME-HWID")):
                save_local_license("KEY", "VALID", last_verified, cached_expires)
                
                net_err = urllib.error.URLError("No internet connection")
                with patch("urllib.request.urlopen", MagicMock(side_effect=net_err)):
                    res, key = check_license_on_startup()
                    assert res.valid is False
                    assert res.status == "NETWORK_ERROR"

def test_offline_grace_denied_on_client_config_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            last_verified = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
            cached_expires = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
            
            with patch("security.get_hwid", MagicMock(return_value="SAME-HWID")):
                save_local_license("KEY", "VALID", last_verified, cached_expires)
                
                # HTTP 404 error returned online
                err404 = urllib.error.HTTPError("url", 404, "Not Found", None, None)
                with patch("urllib.request.urlopen", MagicMock(side_effect=err404)):
                    res, key = check_license_on_startup()
                    assert res.valid is False
                    assert res.status == "CLIENT_CONFIG_ERROR"

def test_legacy_license_migration():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"APPDATA": tmpdir}):
            # Set up legacy XOR license format
            legacy_dir = os.path.join(tmpdir, "VideoFactory")
            os.makedirs(legacy_dir, exist_ok=True)
            legacy_file = os.path.join(legacy_dir, "license.json")
            
            # XOR token construction with legacy HWID
            legacy_hwid = "LEGACY-HWID-HASH"
            key = "VIDEO-1234-5678-9000-1111"
            
            # XOR logic
            encoded_chars = []
            for i, char in enumerate(key):
                encoded_chars.append(chr(ord(char) ^ ord(legacy_hwid[i % len(legacy_hwid)])))
            obfuscated = base64.b64encode("".join(encoded_chars).encode('utf-8')).decode('utf-8')
            
            with open(legacy_file, "w", encoding="utf-8") as f:
                json.dump({"token": obfuscated}, f)
                
            # Mock get_legacy_hwid_candidates to return the correct candidate
            with patch("security.get_legacy_hwid_candidates", MagicMock(return_value=[legacy_hwid])):
                with patch("security.get_hwid", MagicMock(return_value="NEW-HWID-V2")):
                    
                    # Mock successful RPC migration response
                    mock_resp = make_mock_response(200, {
                        "valid": True,
                        "status": "MIGRATED",
                        "message": "Migration OK",
                        "expired_at": "2030-01-01T00:00:00Z"
                    })
                    
                    with patch("urllib.request.urlopen", MagicMock(return_value=mock_resp)):
                        res, key_out = check_license_on_startup()
                        assert res.valid is True
                        assert res.status == "VALID"
                        assert key_out == key
                        
                        # New DPAPI license file must be written
                        new_license = security._load_local_license_dict()
                        assert new_license is not None
                        assert new_license.get("license_key") == key
                        assert new_license.get("hwid") == "NEW-HWID-V2"
                        assert load_local_license() == key
                        
                        # Legacy file must be renamed to .bak
                        assert not os.path.exists(legacy_file)
                        assert os.path.exists(legacy_file + ".bak")
