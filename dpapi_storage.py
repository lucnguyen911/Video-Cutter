# dpapi_storage.py
# Provides secure Windows DPAPI storage capabilities and atomic file operations.

import os
import json
import ctypes
from ctypes import wintypes
from typing import Optional

# Load Crypt32.dll
crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

# Define DATA_BLOB
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]

CRYPTPROTECT_UI_FORBIDDEN = 0x01

def protect_data(data: bytes, entropy: bytes = None) -> bytes:
    """Encrypts bytes data using Windows DPAPI CryptProtectData."""
    if not isinstance(data, bytes):
        raise TypeError("Data must be bytes")
        
    data_in = DATA_BLOB()
    data_in.cbData = len(data)
    data_in.pbData = ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte))
    
    entropy_in = None
    if entropy:
        entropy_in = DATA_BLOB()
        entropy_in.cbData = len(entropy)
        entropy_in.pbData = ctypes.cast(ctypes.create_string_buffer(entropy), ctypes.POINTER(ctypes.c_byte))
        
    data_out = DATA_BLOB()
    
    success = crypt32.CryptProtectData(
        ctypes.byref(data_in),
        None,  # description
        ctypes.byref(entropy_in) if entropy_in else None,
        None,  # reserved
        None,  # prompt struct
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out)
    )
    
    if not success:
        raise OSError(f"CryptProtectData failed with error: {kernel32.GetLastError()}")
        
    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        kernel32.LocalFree(data_out.pbData)

def unprotect_data(data: bytes, entropy: bytes = None) -> bytes:
    """Decrypts bytes data using Windows DPAPI CryptUnprotectData."""
    if not isinstance(data, bytes):
        raise TypeError("Data must be bytes")
        
    data_in = DATA_BLOB()
    data_in.cbData = len(data)
    data_in.pbData = ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte))
    
    entropy_in = None
    if entropy:
        entropy_in = DATA_BLOB()
        entropy_in.cbData = len(entropy)
        entropy_in.pbData = ctypes.cast(ctypes.create_string_buffer(entropy), ctypes.POINTER(ctypes.c_byte))
        
    data_out = DATA_BLOB()
    
    success = crypt32.CryptUnprotectData(
        ctypes.byref(data_in),
        None,  # description
        ctypes.byref(entropy_in) if entropy_in else None,
        None,  # reserved
        None,  # prompt struct
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out)
    )
    
    if not success:
        raise OSError(f"CryptUnprotectData failed with error: {kernel32.GetLastError()}")
        
    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        kernel32.LocalFree(data_out.pbData)

def save_secure_file(path: str, data: bytes) -> None:
    """Saves bytes atomically by writing to a temporary file and replacing the target."""
    path = os.path.normpath(path)
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise e

def load_secure_file(path: str) -> Optional[bytes]:
    """Loads and returns file content if the file exists, otherwise returns None."""
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()

def save_secure_json(path: str, data: dict, entropy_str: str = None) -> None:
    """Serializes a dictionary, encrypts it via DPAPI, and saves it atomically."""
    raw_str = json.dumps(data, indent=4, ensure_ascii=False)
    raw_bytes = raw_str.encode("utf-8")
    entropy_bytes = entropy_str.encode("utf-8") if entropy_str else None
    encrypted_bytes = protect_data(raw_bytes, entropy_bytes)
    save_secure_file(path, encrypted_bytes)

def load_secure_json(path: str, entropy_str: str = None) -> Optional[dict]:
    """Loads, decrypts via DPAPI, and deserializes a JSON file. Returns None if invalid or missing."""
    encrypted_bytes = load_secure_file(path)
    if not encrypted_bytes:
        return None
    try:
        entropy_bytes = entropy_str.encode("utf-8") if entropy_str else None
        decrypted_bytes = unprotect_data(encrypted_bytes, entropy_bytes)
        raw_str = decrypted_bytes.decode("utf-8")
        return json.loads(raw_str)
    except Exception:
        return None
