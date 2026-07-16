import subprocess
import hashlib
import sys
import os
import json
import base64
import urllib.request
from datetime import datetime
from typing import Tuple, Optional

SUPABASE_URL = "https://owskwezrldwlerywsfex.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im93c2t3ZXpybGR3bGVyeXdzZmV4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIzMTAxMDMsImV4cCI6MjA5Nzg4NjEwM30.DPmF5hoQl-FhuNhAladxHUmIYctWjb7J1c5YpkHHTLQ"

def get_hwid() -> str:
    parts = []
    try:
        out = subprocess.check_output("wmic csproduct get uuid", shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in out.splitlines():
            line = line.strip()
            if line and "uuid" not in line.lower() and "node" not in line.lower():
                parts.append(line)
                break
    except Exception: pass
        
    try:
        out = subprocess.check_output("wmic diskdrive get serialnumber", shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in out.splitlines():
            line = line.strip()
            if line and "serialnumber" not in line.lower():
                parts.append(line)
                break
    except Exception: pass
        
    if not parts:
        try:
            import uuid
            parts.append(str(uuid.getnode()))
        except Exception:
            parts.append("VIDEO_FACTORY_DEFAULT_FALLBACK_HWID")
            
    raw_hwid = "|".join(parts)
    return hashlib.sha256(raw_hwid.encode('utf-8')).hexdigest()

def verify_license_online(key: str, hwid: str) -> Tuple[bool, str]:
    key = key.strip()
    if not key: return False, "Vui lòng nhập Key kích hoạt."
        
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    import urllib.parse
    encoded_key = urllib.parse.quote(key.strip())
    url = f"{SUPABASE_URL}/rest/v1/video_licenses?license_key=eq.{encoded_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        if not data: return False, "Key bản quyền không tồn tại."
        license_info = data[0]
        
        if not license_info.get("is_active", True):
            return False, "Key bản quyền đã bị vô hiệu hóa."
            
        expired_at_val = license_info.get("expired_at")
        if expired_at_val is not None and str(expired_at_val).strip() != "":
            try:
                expired_at_str = str(expired_at_val)
                normalized = expired_at_str.replace("Z", "+00:00")
                expired_dt = datetime.fromisoformat(normalized)
                if expired_dt.tzinfo is not None:
                    now_dt = datetime.now(expired_dt.tzinfo)
                else:
                    now_dt = datetime.now()
                if expired_dt < now_dt:
                    return False, "Mã kích hoạt của bạn đã hết hạn!"
            except Exception as e:
                print(f"Error parsing expiration date: {e}")
                
        db_hwid = license_info.get("hwid")
        if not db_hwid:
            success = bind_hwid_online(key, hwid)
            if success: return True, "Kích hoạt bản quyền thành công trên máy này!"
            else: return False, "Không thể liên kết mã máy HWID vào máy chủ."
        else:
            if db_hwid != hwid:
                return False, "Key đã được sử dụng ở máy khác!"
                
        return True, "Bản quyền hợp lệ."
    except Exception as e:
        return False, f"Lỗi kết nối kiểm tra bản quyền: {e}"

def bind_hwid_online(key: str, hwid: str) -> bool:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    import urllib.parse
    encoded_key = urllib.parse.quote(key.strip())
    url = f"{SUPABASE_URL}/rest/v1/video_licenses?license_key=eq.{encoded_key}"
    payload = {"hwid": hwid}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.getcode() in [200, 201, 204]
    except Exception as e:
        return False

def get_license_file_path() -> str:
    app_data = os.environ.get("APPDATA")
    if not app_data: app_data = os.path.expanduser("~")
    folder = os.path.join(app_data, "VideoFactory")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "license.json")

def save_local_license(key: str) -> None:
    path = get_license_file_path()
    hwid = get_hwid()
    encoded_chars = []
    for i, char in enumerate(key):
        key_c = ord(char)
        hwid_c = ord(hwid[i % len(hwid)])
        encoded_chars.append(chr(key_c ^ hwid_c))
    obfuscated_token = base64.b64encode("".join(encoded_chars).encode('utf-8')).decode('utf-8')
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"token": obfuscated_token}, f, indent=4)

def load_local_license() -> Optional[str]:
    path = get_license_file_path()
    if not os.path.exists(path): return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        obfuscated_token = data.get("token")
        if not obfuscated_token: return None
        decoded_chars = base64.b64decode(obfuscated_token.encode('utf-8')).decode('utf-8')
        hwid = get_hwid()
        original_chars = []
        for i, char in enumerate(decoded_chars):
            char_c = ord(char)
            hwid_c = ord(hwid[i % len(hwid)])
            original_chars.append(chr(char_c ^ hwid_c))
        return "".join(original_chars)
    except Exception:
        return None

def check_license_on_startup() -> Tuple[bool, str]:
    key = load_local_license()
    if not key: return False, ""
    hwid = get_hwid()
    is_valid, _ = verify_license_online(key, hwid)
    if is_valid: return True, key
    return False, ""
