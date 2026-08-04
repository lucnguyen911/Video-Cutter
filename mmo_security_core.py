# mmo_security_core.py
# Generalized MMO Security SDK for local licensing, HWID identification, and Supabase integration.

import os
import sys
import json
import base64
import logging
import winreg
import hashlib
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Tuple, Optional, List

@dataclass
class LicenseVerificationResult:
    valid: bool
    status: str
    message: str
    expired_at: Optional[str] = None

@dataclass
class DeviceIdentity:
    hwid: str
    version: int
    source: str

def get_windows_machine_guid() -> str:
    """Reads MachineGuid directly from Windows Cryptography registry key."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(guid).strip().lower().replace("{", "").replace("}", "")
    except Exception:
        return ""

def get_motherboard_uuid_powershell() -> str:
    """Gets Motherboard UUID via PowerShell."""
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        uuid_str = result.stdout.strip()
        if uuid_str and "to be filled" not in uuid_str.lower() and "ffffffff" not in uuid_str.lower():
            return uuid_str.lower()
    except Exception:
        pass
    return ""

def build_hwid_v2(machine_guid: str, motherboard_uuid: str, salt_key: str) -> str:
    """Constructs stable HWID fingerprint using SHA256 of salt, machine_guid, and motherboard_uuid."""
    raw = f"{salt_key}|{machine_guid}|{motherboard_uuid}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def get_profile_path(app_id: str) -> str:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(app_data, app_id, "device_profile.dat")

def get_hwid(app_id: str, salt_key: str) -> str:
    """Retrieves device HWID using DPAPI cache fallback."""
    path = get_profile_path(app_id)
    entropy = f"{app_id}-DeviceProfile-v2"
    
    # Try importing protection module
    from dpapi_storage import load_secure_json, save_secure_json
    
    # 1. Attempt to load cached profile
    if os.path.exists(path):
        try:
            profile = load_secure_json(path, entropy)
            if profile and profile.get("schema_version") == 2 and profile.get("hwid_version") == 2:
                hwid = profile.get("hwid")
                if hwid:
                    return hwid
        except Exception:
            pass
            
    # 2. Generate dynamically
    machine_guid = get_windows_machine_guid()
    motherboard_uuid = get_motherboard_uuid_powershell()
    if not machine_guid and not motherboard_uuid:
        raise RuntimeError("DEVICE_ID_UNAVAILABLE: Cannot query MachineGuid and Motherboard UUID.")
        
    hwid = build_hwid_v2(machine_guid, motherboard_uuid, salt_key)
    
    try:
        profile_data = {
            "schema_version": 2,
            "hwid_version": 2,
            "hwid": hwid,
            "source": "windows_machine_guid_powershell_uuid",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        save_secure_json(path, profile_data, entropy)
    except Exception:
        pass
        
    return hwid

def get_legacy_hwid_candidates() -> List[str]:
    """Generates legacy candidate HWID hashes from motherboard UUID and disk serials for migration."""
    mb_uuid = ""
    disk_serials = []
    
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        mb_uuid = res.stdout.strip().lower()
    except Exception:
        pass
        
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-PhysicalDisk | Select-Object -ExpandProperty SerialNumber"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in res.stdout.splitlines():
            s = line.strip()
            if s:
                disk_serials.append(s)
    except Exception:
        pass
        
    candidates = []
    if mb_uuid:
        candidates.append(hashlib.sha256(mb_uuid.encode('utf-8')).hexdigest())
    for ds in disk_serials:
        candidates.append(hashlib.sha256(ds.encode('utf-8')).hexdigest())
        if mb_uuid:
            candidates.append(hashlib.sha256(f"{mb_uuid}|{ds}".encode('utf-8')).hexdigest())
            
    return candidates

class MMOSecuritySDK:
    def __init__(
        self,
        app_id: str,
        app_version: str,
        salt_key: str,
        supabase_url: str,
        supabase_key: str,
        target_endpoint: str
    ):
        self.app_id = app_id
        self.app_version = app_version
        self.salt_key = salt_key
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.target_endpoint = target_endpoint.strip("/")
        
        # Setup security logger
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        log_dir = os.path.join(app_data, self.app_id, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        self.logger = logging.getLogger(f"security_{self.app_id}")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.FileHandler(os.path.join(log_dir, "security.log"), encoding="utf-8")
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
    def get_license_file_path(self) -> str:
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(app_data, self.app_id, "license.json")
        
    def save_local_license(self, key: str, status: str = "VALID", last_verified_at: Optional[str] = None, cached_expires_at: Optional[str] = None) -> None:
        from dpapi_storage import save_secure_json
        path = self.get_license_file_path()
        hwid = get_hwid(self.app_id, self.salt_key)
        if not last_verified_at:
            last_verified_at = datetime.utcnow().isoformat() + "Z"
        data = {
            "schema_version": 2,
            "license_key": key,
            "hwid": hwid,
            "hwid_version": 2,
            "last_verified_at": last_verified_at,
            "cached_expires_at": cached_expires_at,
            "last_server_status": status
        }
        entropy = f"{self.app_id}-License-v2"
        save_secure_json(path, data, entropy)
        
    def load_local_license(self) -> str:
        from dpapi_storage import load_secure_json
        path = self.get_license_file_path()
        entropy = f"{self.app_id}-License-v2"
        data = load_secure_json(path, entropy)
        if data and isinstance(data, dict):
            return data.get("license_key", "").strip()
        return ""
        
    def _load_local_license_dict(self) -> Optional[dict]:
        from dpapi_storage import load_secure_json
        path = self.get_license_file_path()
        entropy = f"{self.app_id}-License-v2"
        return load_secure_json(path, entropy)
        
    def verify_license_online(self, key: str, hwid: str, candidates: Optional[List[str]] = None) -> LicenseVerificationResult:
        key = key.strip()
        if not key:
            return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Vui lòng nhập Key kích hoạt.")
            
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "p_license_key": key,
            "p_hwid_v2": hwid,
            "p_hwid_version": 2,
            "p_legacy_candidates": candidates or [],
            "p_app_version": self.app_version
        }
        
        url = f"{self.supabase_url}/rest/v1/{self.target_endpoint}"
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
            self.logger.error(f"[SECURITY] Online verification failed with HTTPError: {status_code}")
            if status_code in [401, 403]:
                return LicenseVerificationResult(valid=False, status="AUTH_ERROR", message=f"Lỗi xác thực máy chủ bản quyền (HTTP {status_code}).")
            elif status_code in [400, 404]:
                return LicenseVerificationResult(valid=False, status="CLIENT_CONFIG_ERROR", message=f"Lỗi cấu hình client hoặc API không tồn tại (HTTP {status_code}).")
            elif status_code >= 500:
                return LicenseVerificationResult(valid=False, status="SERVER_ERROR", message=f"Lỗi hệ thống máy chủ bản quyền (HTTP {status_code}).")
            else:
                return LicenseVerificationResult(valid=False, status="SERVER_ERROR", message=f"Lỗi máy chủ bản quyền không xác định (HTTP {status_code}).")
                
        except urllib.error.URLError as e:
            self.logger.error(f"[SECURITY] Online verification failed with URLError: {e.reason}")
            return LicenseVerificationResult(valid=False, status="NETWORK_ERROR", message=f"Lỗi kết nối mạng: {e.reason}")
            
        except Exception as e:
            self.logger.error(f"[SECURITY] Online verification failed: {e}")
            return LicenseVerificationResult(valid=False, status="NETWORK_ERROR", message=f"Lỗi kết nối hệ thống: {e}")

    def check_license_on_startup(self, legacy_paths: Optional[List[str]] = None) -> Tuple[LicenseVerificationResult, str]:
        """Runs startup validation flow with legacy di-trú and offline grace period checks."""
        try:
            current_hwid = get_hwid(self.app_id, self.salt_key)
            self.logger.info(f"[SECURITY] hwid_version=2 id={current_hwid[:6]}...{current_hwid[-5:]}")
        except Exception as e:
            self.logger.error(f"[SECURITY] HWID generation failed: {e}")
            return LicenseVerificationResult(valid=False, status="DEVICE_ID_UNAVAILABLE", message="Không thể tạo mã định danh thiết bị."), ""

        local_license = self._load_local_license_dict()
        
        # 1. Migrate legacy XOR files if no new DPAPI license exists
        if not local_license and legacy_paths:
            legacy_found = False
            legacy_key = None
            
            for lp in legacy_paths:
                if os.path.exists(lp):
                    try:
                        with open(lp, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        obfuscated_token = data.get("token")
                        if obfuscated_token:
                            legacy_found = True
                            candidates = get_legacy_hwid_candidates()
                            decoded_chars = base64.b64decode(obfuscated_token.encode('utf-8')).decode('utf-8')
                            
                            for cand in candidates:
                                original_chars = []
                                for i, char in enumerate(decoded_chars):
                                    original_chars.append(chr(ord(char) ^ ord(cand[i % len(cand)])))
                                candidate_key = "".join(original_chars).strip()
                                
                                if len(candidate_key) >= 10 and all(32 <= ord(c) < 127 for c in candidate_key):
                                    res = self.verify_license_online(candidate_key, current_hwid, candidates=candidates)
                                    if res.valid:
                                        legacy_key = candidate_key
                                        self.save_local_license(
                                            key=legacy_key,
                                            status=res.status,
                                            last_verified_at=datetime.utcnow().isoformat() + "Z",
                                            cached_expires_at=res.expired_at
                                        )
                                        self.logger.info(f"[SECURITY] legacy_migration=True status={res.status}")
                                        break
                        if legacy_key:
                            break
                    except Exception as e:
                        self.logger.warning(f"[SECURITY] Legacy migration failed for {lp}: {e}")
                        
            if legacy_found:
                if legacy_key:
                    for lp in legacy_paths:
                        if lp != self.get_license_file_path() and os.path.exists(lp):
                            try:
                                os.rename(lp, lp + ".bak")
                            except Exception:
                                pass
                    self.logger.info("[SECURITY] license_status=VALID")
                    self.logger.info("[SECURITY] startup_authorization=True")
                    return LicenseVerificationResult(valid=True, status="VALID", message="Di trú bản quyền cũ thành công!"), legacy_key

        # Reload local license
        local_license = self._load_local_license_dict()
        if not local_license:
            self.logger.warning("[SECURITY] license_status=NOT_FOUND")
            return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Không tìm thấy thông tin bản quyền local."), ""

        local_key = local_license.get("license_key", "").strip()
        local_hwid = local_license.get("hwid", "")
        
        # 2. Check local HWID mismatch
        if local_hwid != current_hwid:
            self.logger.warning(f"[SECURITY] local_hwid_mismatch")
            return LicenseVerificationResult(valid=False, status="DEVICE_MISMATCH", message="Mã máy hiện tại không khớp với thiết bị đăng ký."), ""

        # 3. Whitelist check
        last_status = local_license.get("last_server_status")
        if last_status not in ["VALID", "ACTIVATED", "MIGRATED", "SUCCESS", "ACTIVE"]:
            self.logger.warning(f"[SECURITY] local_license_never_validated status={last_status}")
            return LicenseVerificationResult(valid=False, status="LICENSE_DATA_INVALID", message="Bản quyền chưa từng được xác thực thành công."), ""

        # 4. Perform Online check
        online_res = self.verify_license_online(local_key, current_hwid)
        if online_res.valid:
            self.save_local_license(
                key=local_key,
                status=online_res.status,
                last_verified_at=datetime.utcnow().isoformat() + "Z",
                cached_expires_at=online_res.expired_at
            )
            self.logger.info(f"[SECURITY] license_status={online_res.status}")
            return online_res, local_key

        # 5. Online check failed -> 3-day offline grace check
        if online_res.status in ["NETWORK_ERROR", "SERVER_ERROR"]:
            last_verified_str = local_license.get("last_verified_at")
            cached_expires_str = local_license.get("cached_expires_at")
            
            try:
                last_verified_dt = datetime.fromisoformat(last_verified_str.replace("Z", "+00:00"))
                now_dt = datetime.now(last_verified_dt.tzinfo)
                elapsed = now_dt - last_verified_dt
                within_grace = (elapsed <= timedelta(days=3))
                
                not_expired = True
                if cached_expires_str:
                    cached_expires_dt = datetime.fromisoformat(cached_expires_str.replace("Z", "+00:00"))
                    not_expired = (now_dt < cached_expires_dt)
                    
                if within_grace and not_expired:
                    self.logger.info(f"[SECURITY] offline_grace_authorized=True (elapsed={elapsed.days} days)")
                    return LicenseVerificationResult(valid=True, status="VALID", message="Mất kết nối mạng. Đang chạy trong thời gian ân hạn ngoại tuyến (3 ngày)."), local_key
            except Exception as e:
                self.logger.error(f"[SECURITY] Error parsing offline dates: {e}")

        # Hard license failure. Delete local license file.
        try:
            path = self.get_license_file_path()
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass

        self.logger.warning(f"[SECURITY] license_status={online_res.status}")
        return online_res, ""
