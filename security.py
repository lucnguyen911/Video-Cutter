"""
security.py — License verification and management for Video Cutter.
===================================================================
Uses HWID v2, DPAPI storage, and Supabase RPC for secure licensing.

Key changes from v1:
  - HWID v2 (MachineGuid-based, stable)
  - DPAPI-protected local license (replaces XOR+base64)
  - Supabase RPC transaction (replaces GET+PATCH)
  - Structured error classification
  - Offline grace period (3 days)
  - Legacy license migration support
"""

import base64
import hashlib
import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Tuple

from version import APP_ID, APP_VERSION, APPDATA_FOLDER, LEGACY_APPDATA_FOLDER
from device_identity import (
    get_hwid, get_device_identity, get_legacy_hwid_candidates,
    DeviceIdentityError, HWID_VERSION,
)
from dpapi_storage import save_license_data, load_license_data, get_license_file_path
from app_logging import mask_hwid, mask_key

logger = logging.getLogger("security")

# ═══════════════════════════════════════════════════════════════════════════════
#  SUPABASE CREDENTIALS
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://owskwezrldwlerywsfex.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im93c2t3ZXpybGR3bGVyeXdzZmV4Iiwicm9s"
    "ZSI6ImFub24iLCJpYXQiOjE3ODIzMTAxMDMsImV4cCI6MjA5Nzg4NjEwM30."
    "DPmF5hoQl-FhuNhAladxHUmIYctWjb7J1c5YpkHHTLQ"
)

OFFLINE_GRACE_DAYS = 3

# ═══════════════════════════════════════════════════════════════════════════════
#  LICENSE STATUS ENUM & RESULT DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════


class LicenseStatus(str, Enum):
    VALID = "VALID"
    ACTIVATED = "ACTIVATED"
    MIGRATED = "MIGRATED"
    LICENSE_NOT_FOUND = "LICENSE_NOT_FOUND"
    LICENSE_DISABLED = "LICENSE_DISABLED"
    LICENSE_EXPIRED = "LICENSE_EXPIRED"
    DEVICE_MISMATCH = "DEVICE_MISMATCH"
    LEGACY_DEVICE_MISMATCH = "LEGACY_DEVICE_MISMATCH"
    DEVICE_ID_UNAVAILABLE = "DEVICE_ID_UNAVAILABLE"
    NETWORK_ERROR = "NETWORK_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    CLIENT_CONFIG_ERROR = "CLIENT_CONFIG_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    LICENSE_DATA_INVALID = "LICENSE_DATA_INVALID"


# Statuses that allow offline grace
_GRACE_ELIGIBLE_STATUSES = {
    LicenseStatus.NETWORK_ERROR,
    LicenseStatus.SERVER_ERROR,
}

# Statuses that mean the server positively confirmed validity
_POSITIVE_STATUSES = {
    LicenseStatus.VALID,
    LicenseStatus.ACTIVATED,
    LicenseStatus.MIGRATED,
}

# User-friendly messages
_STATUS_MESSAGES = {
    LicenseStatus.VALID: "Bản quyền hợp lệ.",
    LicenseStatus.ACTIVATED: "Kích hoạt bản quyền thành công trên máy này!",
    LicenseStatus.MIGRATED: "Bản quyền đã được chuyển đổi sang thiết bị mới thành công!",
    LicenseStatus.LICENSE_NOT_FOUND: "Key bản quyền không tồn tại.",
    LicenseStatus.LICENSE_DISABLED: "Key bản quyền đã bị vô hiệu hóa.",
    LicenseStatus.LICENSE_EXPIRED: "Mã kích hoạt của bạn đã hết hạn!",
    LicenseStatus.DEVICE_MISMATCH: "Key đã được sử dụng ở máy khác!",
    LicenseStatus.LEGACY_DEVICE_MISMATCH: "Key đã được sử dụng ở máy khác (legacy)!",
    LicenseStatus.DEVICE_ID_UNAVAILABLE: "Không thể xác định mã máy. Vui lòng chạy với quyền phù hợp.",
    LicenseStatus.NETWORK_ERROR: "Lỗi kết nối mạng. Vui lòng kiểm tra kết nối internet.",
    LicenseStatus.SERVER_ERROR: "Máy chủ tạm thời lỗi. Vui lòng thử lại sau.",
    LicenseStatus.CLIENT_CONFIG_ERROR: "Lỗi cấu hình ứng dụng. Vui lòng cập nhật phiên bản mới nhất.",
    LicenseStatus.AUTH_ERROR: "Lỗi xác thực với máy chủ. Vui lòng cập nhật ứng dụng.",
    LicenseStatus.LICENSE_DATA_INVALID: "Dữ liệu bản quyền từ máy chủ không hợp lệ.",
}


@dataclass
class LicenseVerificationResult:
    valid: bool
    status: LicenseStatus
    message: str
    expires_at: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
#  HTTP ERROR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_http_error(e: Exception) -> Tuple[LicenseStatus, int]:
    """
    Classify an HTTP/network exception into a LicenseStatus.
    
    Returns:
        (status, http_status_code_or_0)
    """
    if isinstance(e, urllib.error.HTTPError):
        code = e.code
        if code in (401, 403):
            return LicenseStatus.AUTH_ERROR, code
        elif code in (400, 404):
            return LicenseStatus.CLIENT_CONFIG_ERROR, code
        elif code >= 500:
            return LicenseStatus.SERVER_ERROR, code
        else:
            return LicenseStatus.SERVER_ERROR, code
    elif isinstance(e, urllib.error.URLError):
        # URLError without HTTP status = network issue
        return LicenseStatus.NETWORK_ERROR, 0
    elif isinstance(e, (TimeoutError, OSError)):
        return LicenseStatus.NETWORK_ERROR, 0
    else:
        return LicenseStatus.NETWORK_ERROR, 0


# ═══════════════════════════════════════════════════════════════════════════════
#  SUPABASE RPC CALL
# ═══════════════════════════════════════════════════════════════════════════════

def _call_license_rpc(
    license_key: str,
    hwid_v2: str,
    legacy_candidates: list,
) -> LicenseVerificationResult:
    """
    Call the Supabase RPC `activate_or_verify_video_license_v2`.
    
    This is a single atomic transaction on the server side.
    The client does NOT directly GET+PATCH the table.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "p_license_key": license_key.strip(),
        "p_hwid_v2": hwid_v2,
        "p_hwid_version": HWID_VERSION,
        "p_legacy_candidates": legacy_candidates,
        "p_app_version": APP_VERSION,
    }
    
    url = f"{SUPABASE_URL}/rest/v1/rpc/activate_or_verify_video_license_v2"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        status_str = result.get("status", "")
        message = result.get("message", "")
        expires_at = result.get("expires_at")
        
        try:
            status = LicenseStatus(status_str)
        except ValueError:
            logger.error(f"[SECURITY] unknown RPC status: {status_str}")
            return LicenseVerificationResult(
                valid=False,
                status=LicenseStatus.SERVER_ERROR,
                message=f"Phản hồi máy chủ không hợp lệ: {status_str}",
            )
        
        is_valid = status in _POSITIVE_STATUSES
        display_message = message or _STATUS_MESSAGES.get(status, str(status))
        
        return LicenseVerificationResult(
            valid=is_valid,
            status=status,
            message=display_message,
            expires_at=expires_at,
        )
    
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        error_status, http_code = _classify_http_error(e)
        logger.error(f"[SECURITY] RPC error: {type(e).__name__} http={http_code}")
        return LicenseVerificationResult(
            valid=False,
            status=error_status,
            message=_STATUS_MESSAGES.get(error_status, str(e)),
        )
    except json.JSONDecodeError:
        logger.error("[SECURITY] RPC returned invalid JSON")
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.SERVER_ERROR,
            message="Máy chủ trả về dữ liệu không hợp lệ.",
        )
    except Exception as e:
        logger.error(f"[SECURITY] unexpected RPC error: {type(e).__name__}")
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.NETWORK_ERROR,
            message=f"Lỗi kết nối: {type(e).__name__}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  FALLBACK: DIRECT REST API (if RPC not yet deployed)
# ═══════════════════════════════════════════════════════════════════════════════

def _verify_license_rest_fallback(
    key: str, hwid: str
) -> LicenseVerificationResult:
    """
    Fallback verification using direct REST API (GET then conditional PATCH).
    Used when the RPC function is not yet deployed on Supabase.
    
    This preserves backward compatibility but should be replaced by RPC.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    
    encoded_key = urllib.parse.quote(key.strip())
    url = f"{SUPABASE_URL}/rest/v1/video_licenses?license_key=eq.{encoded_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        if not data:
            return LicenseVerificationResult(
                valid=False,
                status=LicenseStatus.LICENSE_NOT_FOUND,
                message=_STATUS_MESSAGES[LicenseStatus.LICENSE_NOT_FOUND],
            )
        
        license_info = data[0]
        
        # Check active
        if not license_info.get("is_active", True):
            return LicenseVerificationResult(
                valid=False,
                status=LicenseStatus.LICENSE_DISABLED,
                message=_STATUS_MESSAGES[LicenseStatus.LICENSE_DISABLED],
            )
        
        # Check expiry
        expired_at_val = license_info.get("expired_at")
        expires_at_str = None
        if expired_at_val is not None and str(expired_at_val).strip():
            try:
                expired_at_str_raw = str(expired_at_val)
                normalized = expired_at_str_raw.replace("Z", "+00:00")
                expired_dt = datetime.fromisoformat(normalized)
                if expired_dt.tzinfo is not None:
                    now_dt = datetime.now(expired_dt.tzinfo)
                else:
                    now_dt = datetime.now()
                if expired_dt < now_dt:
                    return LicenseVerificationResult(
                        valid=False,
                        status=LicenseStatus.LICENSE_EXPIRED,
                        message=_STATUS_MESSAGES[LicenseStatus.LICENSE_EXPIRED],
                    )
                expires_at_str = expired_at_str_raw
            except Exception as e:
                logger.error(f"[SECURITY] expired_at parse error: {e}")
                return LicenseVerificationResult(
                    valid=False,
                    status=LicenseStatus.LICENSE_DATA_INVALID,
                    message="Dữ liệu hạn sử dụng từ máy chủ không hợp lệ.",
                )
        
        # Check HWID binding
        db_hwid = license_info.get("hwid_v2") or license_info.get("hwid")
        if not db_hwid:
            # No HWID bound — try to bind
            success = _bind_hwid_rest(key, hwid)
            if success:
                return LicenseVerificationResult(
                    valid=True,
                    status=LicenseStatus.ACTIVATED,
                    message=_STATUS_MESSAGES[LicenseStatus.ACTIVATED],
                    expires_at=expires_at_str,
                )
            else:
                return LicenseVerificationResult(
                    valid=False,
                    status=LicenseStatus.SERVER_ERROR,
                    message="Không thể liên kết mã máy HWID vào máy chủ.",
                )
        elif db_hwid == hwid:
            return LicenseVerificationResult(
                valid=True,
                status=LicenseStatus.VALID,
                message=_STATUS_MESSAGES[LicenseStatus.VALID],
                expires_at=expires_at_str,
            )
        else:
            return LicenseVerificationResult(
                valid=False,
                status=LicenseStatus.DEVICE_MISMATCH,
                message=_STATUS_MESSAGES[LicenseStatus.DEVICE_MISMATCH],
            )
    
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        error_status, http_code = _classify_http_error(e)
        logger.error(f"[SECURITY] REST fallback error: {type(e).__name__} http={http_code}")
        return LicenseVerificationResult(
            valid=False,
            status=error_status,
            message=_STATUS_MESSAGES.get(error_status, str(e)),
        )
    except Exception as e:
        logger.error(f"[SECURITY] unexpected REST error: {type(e).__name__}")
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.NETWORK_ERROR,
            message=f"Lỗi kết nối: {type(e).__name__}",
        )


def _bind_hwid_rest(key: str, hwid: str) -> bool:
    """Bind HWID via REST PATCH (fallback only)."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    encoded_key = urllib.parse.quote(key.strip())
    url = f"{SUPABASE_URL}/rest/v1/video_licenses?license_key=eq.{encoded_key}"
    payload = {
        "hwid": hwid,
        "hwid_v2": hwid,
        "hwid_version": HWID_VERSION,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.getcode() in (200, 201, 204)
    except Exception as e:
        logger.error(f"[SECURITY] bind HWID REST error: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN VERIFICATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def verify_license_online(key: str, hwid: str) -> LicenseVerificationResult:
    """
    Verify a license key against Supabase.
    
    Tries RPC first, falls back to REST API if RPC function doesn't exist.
    
    Args:
        key: License key string.
        hwid: HWID v2 hex string.
        
    Returns:
        LicenseVerificationResult with structured status.
    """
    key = key.strip()
    if not key:
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.LICENSE_NOT_FOUND,
            message="Vui lòng nhập Key kích hoạt.",
        )
    
    # Get legacy candidates for migration
    try:
        legacy_candidates = get_legacy_hwid_candidates()
    except Exception:
        legacy_candidates = []
    
    # Try RPC first
    result = _call_license_rpc(key, hwid, legacy_candidates)
    
    # If RPC function doesn't exist (404), fall back to REST
    if result.status == LicenseStatus.CLIENT_CONFIG_ERROR:
        logger.info("[SECURITY] RPC not available, falling back to REST API")
        result = _verify_license_rest_fallback(key, hwid)
    
    logger.info(f"[SECURITY] license status={result.status.value}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  LOCAL LICENSE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def save_local_license(
    key: str,
    result: Optional[LicenseVerificationResult] = None,
) -> None:
    """
    Save license locally using DPAPI.
    
    Args:
        key: License key.
        result: Verification result (for expires_at).
    """
    try:
        hwid = get_hwid()
    except DeviceIdentityError:
        logger.error("[SECURITY] cannot save local license: HWID unavailable")
        return
    
    now_iso = datetime.now(timezone.utc).isoformat()
    
    bundle = {
        "schema_version": 2,
        "license_key": key,
        "hwid": hwid,
        "hwid_version": HWID_VERSION,
        "last_verified_at": now_iso,
        "cached_expires_at": result.expires_at if result else None,
        "last_server_status": result.status.value if result else "UNKNOWN",
    }
    
    save_license_data(bundle)


def load_local_license() -> Optional[dict]:
    """
    Load local license data.
    
    Tries DPAPI v2 first, then legacy migration.
    
    Returns:
        License bundle dict, or None if not found.
    """
    # Try DPAPI v2 first
    data = load_license_data()
    if data:
        return data
    
    # Try legacy migration
    return _migrate_legacy_license()


# ═══════════════════════════════════════════════════════════════════════════════
#  LEGACY LICENSE MIGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def _try_xor_decode(token_b64: str, hwid: str) -> Optional[str]:
    """
    Try to decode a legacy XOR-encoded license token.
    
    The old algorithm:
        key_char XOR hwid_char → base64
    """
    try:
        decoded_chars = base64.b64decode(token_b64.encode("utf-8")).decode("utf-8")
        original_chars = []
        for i, char in enumerate(decoded_chars):
            char_c = ord(char)
            hwid_c = ord(hwid[i % len(hwid)])
            original_chars.append(chr(char_c ^ hwid_c))
        key = "".join(original_chars)
        
        # Basic validation: should be printable ASCII and reasonable length
        if len(key) < 5 or len(key) > 100:
            return None
        if not all(32 <= ord(c) <= 126 for c in key):
            return None
        return key
    except Exception:
        return None


def _read_legacy_json(path: str) -> Optional[str]:
    """Read legacy license.json and return the token field."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("token")
    except Exception:
        return None


def _migrate_legacy_license() -> Optional[dict]:
    """
    Try to migrate a legacy license from VideoFactory or VideoCutter.
    
    Searches for license.json in both AppData folders, tries all
    legacy HWID candidates to decode the XOR token.
    
    Returns:
        Migrated license bundle dict, or None if migration failed.
    """
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    
    # Paths to check (new location first, then legacy)
    legacy_paths = [
        os.path.join(app_data, APPDATA_FOLDER, "license.json"),
        os.path.join(app_data, LEGACY_APPDATA_FOLDER, "license.json"),
    ]
    
    for path in legacy_paths:
        token = _read_legacy_json(path)
        if not token:
            continue
        
        logger.info(f"[SECURITY] found legacy license at {os.path.basename(os.path.dirname(path))}")
        
        # Try all legacy HWID candidates
        try:
            candidates = get_legacy_hwid_candidates()
        except Exception:
            candidates = []
        
        for candidate in candidates:
            decoded_key = _try_xor_decode(token, candidate)
            if decoded_key:
                logger.info("[SECURITY] legacy license decoded successfully")
                
                # Return as a v2-compatible bundle (needs online verification)
                return {
                    "schema_version": 2,
                    "license_key": decoded_key,
                    "hwid": "",  # Will be updated after online verification
                    "hwid_version": 1,  # Legacy
                    "last_verified_at": None,
                    "cached_expires_at": None,
                    "last_server_status": "PENDING_MIGRATION",
                    "_migrated_from": path,
                }
        
        logger.warning("[SECURITY] legacy license found but could not decode with any candidate")
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  APPDATA MIGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def migrate_appdata() -> None:
    """
    Migrate data from legacy VideoFactory AppData to VideoCutter.
    
    1. Check if VideoCutter folder exists.
    2. If not, check VideoFactory.
    3. Copy non-conflicting files.
    4. Don't delete old data.
    """
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    new_dir = os.path.join(app_data, APPDATA_FOLDER)
    old_dir = os.path.join(app_data, LEGACY_APPDATA_FOLDER)
    
    # New dir already has data → no migration needed
    if os.path.exists(new_dir) and os.listdir(new_dir):
        return
    
    # Old dir doesn't exist → nothing to migrate
    if not os.path.exists(old_dir):
        os.makedirs(new_dir, exist_ok=True)
        return
    
    # Migrate
    os.makedirs(new_dir, exist_ok=True)
    
    import shutil
    for item in os.listdir(old_dir):
        src = os.path.join(old_dir, item)
        dst = os.path.join(new_dir, item)
        if not os.path.exists(dst):
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                logger.info(f"[SECURITY] migrated {item} from legacy AppData")
            except Exception as e:
                logger.warning(f"[SECURITY] failed to migrate {item}: {type(e).__name__}")
    
    logger.info("[SECURITY] AppData migration completed")


# ═══════════════════════════════════════════════════════════════════════════════
#  STARTUP LICENSE CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def check_license_on_startup() -> LicenseVerificationResult:
    """
    Check license on application startup.
    
    Flow:
    1. Migrate AppData if needed.
    2. Get device identity.
    3. Load local license.
    4. If valid local license exists, verify online.
    5. On network/server error, apply offline grace.
    6. Return structured result.
    
    Returns:
        LicenseVerificationResult — check result.valid explicitly.
    """
    # Step 1: Migrate AppData
    try:
        migrate_appdata()
    except Exception as e:
        logger.warning(f"[SECURITY] AppData migration error: {type(e).__name__}")
    
    # Step 2: Get device identity
    try:
        identity = get_device_identity()
        hwid = identity.hwid
    except DeviceIdentityError as e:
        logger.error(f"[SECURITY] device identity unavailable: {e}")
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.DEVICE_ID_UNAVAILABLE,
            message=_STATUS_MESSAGES[LicenseStatus.DEVICE_ID_UNAVAILABLE],
        )
    
    # Step 3: Load local license
    local_license = load_local_license()
    if not local_license:
        logger.info("[SECURITY] no local license found")
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.LICENSE_NOT_FOUND,
            message="",
        )
    
    key = local_license.get("license_key")
    if not key:
        logger.warning("[SECURITY] local license has no key")
        return LicenseVerificationResult(
            valid=False,
            status=LicenseStatus.LICENSE_NOT_FOUND,
            message="",
        )
    
    # Step 4: Verify online
    result = verify_license_online(key, hwid)
    
    # Step 5: Handle result
    if result.valid is True:
        # Server confirmed valid — save updated local license
        save_local_license(key, result)
        return result
    
    # Step 6: Offline grace check
    if result.status in _GRACE_ELIGIBLE_STATUSES:
        grace_result = _check_offline_grace(local_license, hwid)
        if grace_result is not None:
            return grace_result
    
    # Not eligible for grace or grace expired
    return result


def _check_offline_grace(
    local_license: dict, current_hwid: str
) -> Optional[LicenseVerificationResult]:
    """
    Check if offline grace period allows the app to run.
    
    Conditions for grace:
    1. Local license has schema_version 2.
    2. Local HWID matches current HWID.
    3. License was previously verified online (last_server_status is VALID/ACTIVATED/MIGRATED).
    4. last_verified_at is within OFFLINE_GRACE_DAYS.
    5. cached_expires_at hasn't passed.
    
    Returns:
        LicenseVerificationResult if grace is granted, None otherwise.
    """
    if local_license.get("schema_version") != 2:
        return None
    
    local_hwid = local_license.get("hwid", "")
    if local_hwid != current_hwid:
        logger.warning("[SECURITY] offline grace denied: HWID mismatch")
        return None
    
    last_status = local_license.get("last_server_status", "")
    if last_status not in ("VALID", "ACTIVATED", "MIGRATED"):
        logger.warning("[SECURITY] offline grace denied: never verified online")
        return None
    
    last_verified = local_license.get("last_verified_at")
    if not last_verified:
        return None
    
    try:
        verified_dt = datetime.fromisoformat(last_verified)
        if verified_dt.tzinfo is None:
            verified_dt = verified_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        grace_deadline = verified_dt + timedelta(days=OFFLINE_GRACE_DAYS)
        
        if now > grace_deadline:
            logger.warning("[SECURITY] offline grace expired")
            return None
    except Exception:
        return None
    
    # Check cached expiry
    cached_expires = local_license.get("cached_expires_at")
    if cached_expires:
        try:
            normalized = str(cached_expires).replace("Z", "+00:00")
            expires_dt = datetime.fromisoformat(normalized)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_dt:
                logger.warning("[SECURITY] offline grace denied: license expired")
                return None
        except Exception:
            pass  # If we can't parse, allow grace (better than blocking)
    
    logger.info("[SECURITY] offline grace granted")
    return LicenseVerificationResult(
        valid=True,
        status=LicenseStatus.VALID,
        message="Bản quyền hợp lệ (chế độ ngoại tuyến).",
    )
