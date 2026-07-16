"""
dpapi_storage.py — Windows DPAPI wrapper using ctypes.
======================================================
Provides CryptProtectData / CryptUnprotectData for securing
device profiles and license data locally.

Uses ctypes directly — no heavy external dependencies.
"""

import ctypes
import ctypes.wintypes
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("security")

# ═══════════════════════════════════════════════════════════════════════════════
#  DPAPI CONSTANTS & STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

DEVICE_PROFILE_ENTROPY = b"VideoCutter-DeviceProfile-v2"
LICENSE_ENTROPY = b"VideoCutter-License-v2"

# CRYPTPROTECT flags
CRYPTPROTECT_UI_FORBIDDEN = 0x01
CRYPTPROTECT_LOCAL_MACHINE = 0x04


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32

_CryptProtectData = _crypt32.CryptProtectData
_CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),  # pDataIn
    ctypes.c_wchar_p,           # szDataDescr
    ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
    ctypes.c_void_p,            # pvReserved
    ctypes.c_void_p,            # pPromptStruct
    ctypes.wintypes.DWORD,      # dwFlags
    ctypes.POINTER(DATA_BLOB),  # pDataOut
]
_CryptProtectData.restype = ctypes.wintypes.BOOL

_CryptUnprotectData = _crypt32.CryptUnprotectData
_CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),  # pDataIn
    ctypes.POINTER(ctypes.c_wchar_p),  # ppszDataDescr
    ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
    ctypes.c_void_p,            # pvReserved
    ctypes.c_void_p,            # pPromptStruct
    ctypes.wintypes.DWORD,      # dwFlags
    ctypes.POINTER(DATA_BLOB),  # pDataOut
]
_CryptUnprotectData.restype = ctypes.wintypes.BOOL

_LocalFree = _kernel32.LocalFree
_LocalFree.argtypes = [ctypes.c_void_p]
_LocalFree.restype = ctypes.c_void_p


# ═══════════════════════════════════════════════════════════════════════════════
#  DPAPI CORE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_blob(data: bytes) -> DATA_BLOB:
    """Create a DATA_BLOB from bytes."""
    blob = DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                              ctypes.POINTER(ctypes.c_char))
    return blob


def dpapi_encrypt(plaintext: bytes, entropy: bytes = b"") -> bytes:
    """
    Encrypt data using Windows DPAPI (CryptProtectData).
    
    Args:
        plaintext: Data to encrypt.
        entropy: Optional entropy for additional protection.
        
    Returns:
        Encrypted bytes.
        
    Raises:
        OSError: If encryption fails.
    """
    data_in = _make_blob(plaintext)
    data_out = DATA_BLOB()
    
    entropy_blob = None
    p_entropy = None
    if entropy:
        entropy_blob = _make_blob(entropy)
        p_entropy = ctypes.byref(entropy_blob)
    
    success = _CryptProtectData(
        ctypes.byref(data_in),
        "VideoCutter",      # description
        p_entropy,          # entropy
        None,               # reserved
        None,               # prompt
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    
    if not success:
        error_code = ctypes.get_last_error()
        raise OSError(f"CryptProtectData failed (error {error_code})")
    
    try:
        result = ctypes.string_at(data_out.pbData, data_out.cbData)
        return bytes(result)
    finally:
        if data_out.pbData:
            _LocalFree(data_out.pbData)


def dpapi_decrypt(ciphertext: bytes, entropy: bytes = b"") -> bytes:
    """
    Decrypt data using Windows DPAPI (CryptUnprotectData).
    
    Args:
        ciphertext: Data to decrypt.
        entropy: Must match the entropy used during encryption.
        
    Returns:
        Decrypted bytes.
        
    Raises:
        OSError: If decryption fails (wrong user, corrupt data, wrong entropy).
    """
    data_in = _make_blob(ciphertext)
    data_out = DATA_BLOB()
    
    entropy_blob = None
    p_entropy = None
    if entropy:
        entropy_blob = _make_blob(entropy)
        p_entropy = ctypes.byref(entropy_blob)
    
    descr = ctypes.c_wchar_p()
    
    success = _CryptUnprotectData(
        ctypes.byref(data_in),
        ctypes.byref(descr),
        p_entropy,
        None,               # reserved
        None,               # prompt
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    
    if not success:
        error_code = ctypes.get_last_error()
        raise OSError(f"CryptUnprotectData failed (error {error_code})")
    
    try:
        result = ctypes.string_at(data_out.pbData, data_out.cbData)
        return bytes(result)
    finally:
        if data_out.pbData:
            _LocalFree(data_out.pbData)


# ═══════════════════════════════════════════════════════════════════════════════
#  HIGH-LEVEL STORAGE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_appdata_dir() -> str:
    """Get the canonical AppData directory, creating if needed."""
    from version import APPDATA_FOLDER
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    folder = os.path.join(app_data, APPDATA_FOLDER)
    os.makedirs(folder, exist_ok=True)
    return folder


def save_encrypted_file(filepath: str, data: dict, entropy: bytes) -> None:
    """
    Save a dict as DPAPI-encrypted file, atomically.
    
    1. Serialize to JSON.
    2. Encrypt with DPAPI + entropy.
    3. Write to .tmp file.
    4. Flush + fsync.
    5. os.replace to final path.
    """
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = dpapi_encrypt(json_bytes, entropy)
    
    tmp_path = filepath + ".tmp"
    dir_path = os.path.dirname(filepath)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    with open(tmp_path, "wb") as f:
        f.write(encrypted)
        f.flush()
        os.fsync(f.fileno())
    
    os.replace(tmp_path, filepath)


def load_encrypted_file(filepath: str, entropy: bytes) -> Optional[dict]:
    """
    Load and decrypt a DPAPI-encrypted file.
    
    Returns:
        Parsed dict, or None if file doesn't exist or is corrupt.
    """
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, "rb") as f:
            encrypted = f.read()
        
        if not encrypted:
            return None
        
        decrypted = dpapi_decrypt(encrypted, entropy)
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        logger.warning(f"[DPAPI] failed to load {os.path.basename(filepath)}: {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  LICENSE STORAGE
# ═══════════════════════════════════════════════════════════════════════════════

def get_license_file_path() -> str:
    """Get path to the DPAPI-protected license file."""
    return os.path.join(_get_appdata_dir(), "license.dat")


def save_license_data(license_bundle: dict) -> None:
    """
    Save license data protected by DPAPI.
    
    Expected bundle keys:
        schema_version, license_key, hwid, hwid_version,
        last_verified_at, cached_expires_at, last_server_status
    """
    path = get_license_file_path()
    save_encrypted_file(path, license_bundle, LICENSE_ENTROPY)
    logger.info("[DPAPI] license data saved")


def load_license_data() -> Optional[dict]:
    """
    Load license data from DPAPI-protected file.
    
    Returns:
        License bundle dict, or None if unavailable.
    """
    path = get_license_file_path()
    data = load_encrypted_file(path, LICENSE_ENTROPY)
    if data and data.get("schema_version") == 2:
        return data
    if data:
        logger.warning("[DPAPI] license data has unexpected schema version")
    return None
