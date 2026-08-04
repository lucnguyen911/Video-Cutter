# security.py
# Revamped license protection layer with DPAPI, strict offline grace, and RPC transaction support.

import os
import sys
import json
import base64
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Tuple, Optional, List

from version import APP_ID, APP_NAME, APP_VERSION
from dpapi_storage import save_secure_json, load_secure_json
from device_identity import get_hwid, get_legacy_hwid_candidates, get_hwid_upgrade_candidates, get_device_identity, HWID_VERSION

# Supabase Credentials (from original security.py)
SUPABASE_URL = "https://owskwezrldwlerywsfex.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im93c2t3ZXpybGR3bGVyeXdzZmV4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIzMTAxMDMsImV4cCI6MjA5Nzg4NjEwM30.DPmF5hoQl-FhuNhAladxHUmIYctWjb7J1c5YpkHHTLQ"

# Setup security logger
def setup_security_logger() -> logging.Logger:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(app_data, "VideoCutter", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("security")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(log_dir, "security.log"), encoding="utf-8")
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

security_logger = setup_security_logger()

@dataclass
class LicenseVerificationResult:
    valid: bool
    status: str
    message: str
    expired_at: Optional[str] = None

def mask_hwid(hwid: str) -> str:
    if len(hwid) > 12:
        return f"{hwid[:6]}...{hwid[-5:]}"
    return hwid

def get_license_file_path() -> str:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(app_data, "VideoCutter", "license.json")

def save_local_license(key: str, status: str = "VALID", last_verified_at: Optional[str] = None, cached_expires_at: Optional[str] = None, last_seen_at: Optional[str] = None) -> None:
    path = get_license_file_path()
    hwid = get_hwid()
    if not last_verified_at:
        last_verified_at = datetime.now(timezone.utc).isoformat()
    data = {
        "schema_version": 3,
        "license_key": key,
        "hwid": hwid,
        "hwid_version": HWID_VERSION,
        "last_verified_at": last_verified_at,
        "last_seen_at": last_seen_at or last_verified_at,
        "cached_expires_at": cached_expires_at,
        "last_server_status": status
    }
    save_secure_json(path, data, "VideoCutter-License-v2")

def load_local_license() -> str:
    """Reads license key string from secure local storage. Returns empty string if missing/corrupt."""
    path = get_license_file_path()
    data = load_secure_json(path, "VideoCutter-License-v2")
    if data and isinstance(data, dict):
        return data.get("license_key", "").strip()
    return ""

def _load_local_license_dict() -> Optional[dict]:
    """Internal helper to load the full license dictionary securely."""
    path = get_license_file_path()
    return load_secure_json(path, "VideoCutter-License-v2")

def verify_license_online(key: str, hwid: str, candidates: Optional[List[str]] = None) -> LicenseVerificationResult:
    """Verifies the license online using the transactional RPC on Supabase."""
    key = key.strip()
    if not key:
        return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Vui lòng nhập Key kích hoạt.")
        
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "p_license_key": key,
        "p_hwid_v3": hwid,
        "p_hwid_version": HWID_VERSION,
        "p_legacy_candidates": candidates or [],
        "p_app_version": APP_VERSION
    }
    
    url = f"{SUPABASE_URL}/rest/v1/rpc/activate_or_verify_video_license_v3"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
        if not isinstance(res_data, dict):
            return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Phản hồi từ máy chủ không hợp lệ.")
            
        valid = res_data.get("valid", False)
        status = res_data.get("status", "LICENSE_DATA_INVALID")
        message = res_data.get("message", "Lỗi kiểm tra bản quyền.")
        expired_at = res_data.get("expired_at")
        
        return LicenseVerificationResult(valid=valid, status=status, message=message, expired_at=expired_at)
    except urllib.error.HTTPError as e:
        status_code = e.code
        security_logger.error(f"[SECURITY] Online verification failed with HTTPError: {status_code}")
        if status_code in [401, 403]:
            return LicenseVerificationResult(valid=False, status="AUTH_ERROR", message=f"Lỗi xác thực máy chủ bản quyền (HTTP {status_code}).")
        elif status_code in [400, 404]:
            return LicenseVerificationResult(valid=False, status="CLIENT_CONFIG_ERROR", message=f"Lỗi cấu hình client hoặc API không tồn tại (HTTP {status_code}).")
        elif status_code >= 500:
            return LicenseVerificationResult(valid=False, status="SERVER_ERROR", message=f"Lỗi hệ thống máy chủ bản quyền (HTTP {status_code}).")
        else:
            return LicenseVerificationResult(valid=False, status="SERVER_ERROR", message=f"Lỗi máy chủ bản quyền không xác định (HTTP {status_code}).")
            
    except urllib.error.URLError as e:
        security_logger.error(f"[SECURITY] Online verification failed with URLError: {e.reason}")
        return LicenseVerificationResult(valid=False, status="NETWORK_ERROR", message=f"Lỗi kết nối mạng, không thể kiểm tra bản quyền: {e.reason}")
        
    except Exception as e:
        security_logger.error(f"[SECURITY] Online verification failed with unexpected exception: {e}")
        return LicenseVerificationResult(valid=False, status="NETWORK_ERROR", message=f"Lỗi kết nối hệ thống: {e}")

def check_license_on_startup() -> Tuple[LicenseVerificationResult, str]:
    """
    Validates license at application startup:
    1. Attempts legacy XOR files migration if no DPAPI license exists.
    2. Checks DPAPI license.
    3. Performs online validation.
    4. Applies controlled 3-day offline grace period if network/server is unavailable.
    """
    try:
        current_hwid = get_hwid()
        security_logger.info(f"[SECURITY] hwid_version={HWID_VERSION} id={mask_hwid(current_hwid)}")
    except Exception as e:
        security_logger.error(f"[SECURITY] HWID generation failed: {e}")
        return LicenseVerificationResult(valid=False, status="DEVICE_ID_UNAVAILABLE", message="Không thể tạo mã định danh thiết bị."), ""

    local_license = _load_local_license_dict()
    
    # 1. Migrate legacy XOR files if no new DPAPI license exists
    if not local_license:
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        legacy_paths = [
            os.path.join(app_data, "VideoCutter", "license.json"),
            os.path.join(app_data, "VideoFactory", "license.json")
        ]
        
        legacy_found = False
        legacy_key = None
        legacy_file_used = None
        
        for lp in legacy_paths:
            if os.path.exists(lp):
                try:
                    with open(lp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    obfuscated_token = data.get("token")
                    if obfuscated_token:
                        legacy_found = True
                        legacy_file_used = lp
                        # Try to decrypt token with legacy candidates
                        candidates = list(dict.fromkeys(get_hwid_upgrade_candidates() + get_legacy_hwid_candidates()))
                        decoded_chars = base64.b64decode(obfuscated_token.encode('utf-8')).decode('utf-8')
                        
                        for cand in candidates:
                            original_chars = []
                            for i, char in enumerate(decoded_chars):
                                char_c = ord(char)
                                cand_c = ord(cand[i % len(cand)])
                                original_chars.append(chr(char_c ^ cand_c))
                            candidate_key = "".join(original_chars).strip()
                            
                            # Check ascii printability and structure
                            if len(candidate_key) >= 10 and all(32 <= ord(c) < 127 for c in candidate_key):
                                # Verify online
                                res = verify_license_online(candidate_key, current_hwid, candidates=candidates)
                                if res.valid:
                                    legacy_key = candidate_key
                                    # Successful migration!
                                    save_local_license(
                                        key=legacy_key,
                                        status=res.status,
                                        last_verified_at=datetime.now(timezone.utc).isoformat(),
                                        cached_expires_at=getattr(res, "expired_at", None)
                                    )
                                    security_logger.info(f"[SECURITY] legacy_migration=True status={res.status}")
                                    break
                    if legacy_key:
                        break
                except Exception as e:
                    security_logger.warning(f"[SECURITY] Legacy migration attempt failed for {lp}: {e}")
                    
        if legacy_found:
            if legacy_key:
                # Rename all legacy files to .bak to avoid re-migration
                for lp in legacy_paths:
                    if lp != get_license_file_path() and os.path.exists(lp):
                        try:
                            os.rename(lp, lp + ".bak")
                        except Exception:
                            pass
                security_logger.info("[SECURITY] license_status=VALID")
                security_logger.info("[SECURITY] startup_authorization=True")
                return LicenseVerificationResult(valid=True, status="VALID", message="Di trú bản quyền cũ thành công!"), legacy_key
            else:
                security_logger.warning("[SECURITY] Legacy license exists but verification failed.")

    # Reload local license in case migration just succeeded
    local_license = _load_local_license_dict()

    if not local_license:
        security_logger.warning("[SECURITY] license_status=NOT_FOUND")
        security_logger.info("[SECURITY] startup_authorization=False")
        return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Không tìm thấy thông tin bản quyền local."), ""

    local_key = local_license.get("license_key", "").strip()
    local_hwid = local_license.get("hwid", "")
    
    # A v2 local record is allowed to reach the server once so the authenticated
    # v3 RPC can migrate it. Offline use is not allowed until migration succeeds.
    local_hwid_matches_current = (local_hwid == current_hwid)
    if not local_hwid_matches_current:
        security_logger.info("[SECURITY] local_hwid_upgrade_pending=True")
    # 3. Check if local license was ever successfully validated online
    last_status = local_license.get("last_server_status")
    if last_status not in ["VALID", "ACTIVATED", "MIGRATED", "SUCCESS", "ACTIVE"]:
        security_logger.warning(f"[SECURITY] local_license_never_validated status={last_status}")
        security_logger.info("[SECURITY] startup_authorization=False")
        return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Bản quyền chưa từng được xác thực thành công."), ""

    # 4. Perform Online check
    online_res = verify_license_online(local_key, current_hwid, candidates=list(dict.fromkeys(get_hwid_upgrade_candidates() + get_legacy_hwid_candidates())))
    if online_res.valid:
        save_local_license(
            key=local_key,
            status=online_res.status,
            last_verified_at=datetime.now(timezone.utc).isoformat(),
            cached_expires_at=getattr(online_res, "expired_at", None)
        )
        security_logger.info(f"[SECURITY] license_status={online_res.status}")
        security_logger.info("[SECURITY] startup_authorization=True")
        return online_res, local_key

    # 5. Online check failed, verify offline grace parameters
    # Offline grace is only for NETWORK_ERROR or SERVER_ERROR (HTTP 5xx)
    if local_hwid_matches_current and online_res.status in ["NETWORK_ERROR", "SERVER_ERROR"]:
        last_verified_str = local_license.get("last_verified_at")
        last_seen_str = local_license.get("last_seen_at", last_verified_str)
        cached_expires_str = local_license.get("cached_expires_at")
        try:
            last_verified_dt = datetime.fromisoformat(last_verified_str.replace("Z", "+00:00"))
            last_seen_dt = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            elapsed = now_dt - last_verified_dt
            clock_not_rolled_back = now_dt >= last_verified_dt and now_dt >= last_seen_dt
            within_grace = timedelta(0) <= elapsed <= timedelta(days=3)
            not_expired = True
            if cached_expires_str:
                cached_expires_dt = datetime.fromisoformat(cached_expires_str.replace("Z", "+00:00"))
                not_expired = now_dt < cached_expires_dt
            if clock_not_rolled_back and within_grace and not_expired:
                save_local_license(local_key, local_license.get("last_server_status", "VALID"), last_verified_str, cached_expires_str, now_dt.isoformat())
                security_logger.info(f"[SECURITY] offline_grace_authorized=True (elapsed={elapsed.days} days)")
                return LicenseVerificationResult(valid=True, status="VALID", message="Mất kết nối mạng. Đang chạy trong thời gian ân hạn ngoại tuyến (3 ngày)."), local_key
            security_logger.warning("[SECURITY] offline_grace_denied=True")
        except Exception as e:
            security_logger.error(f"[SECURITY] Error parsing offline dates: {e}")
    # Keep evidence for transient network/configuration/device errors. Removing it
    # would force needless reactivation and appears to users as HWID drift.
    if online_res.status in ["LICENSE_NOT_FOUND", "LICENSE_DISABLED", "LICENSE_EXPIRED"]:
        try:
            path = get_license_file_path()
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
    security_logger.warning(f"[SECURITY] license_status={online_res.status}")
    security_logger.info("[SECURITY] startup_authorization=False")
    return online_res, ""
