"""
device_identity.py — Stable HWID v2 based on Windows MachineGuid.
=================================================================
Replaces the old unstable HWID mechanism (WMIC + disk serial + MAC fallback).

HWID v2 algorithm:
    SHA256("video-cutter|hwid-v2|" + normalized_machine_guid)

The MachineGuid is read from:
    HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid

This value is stable across hardware changes (USB, disks, VPN, MAC changes).
"""

import hashlib
import logging
import os
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("security")

HWID_VERSION = 2
HWID_NAMESPACE = "video-cutter|hwid-v2"


class DeviceIdentityError(Exception):
    """Raised when device identity cannot be determined."""
    pass


@dataclass
class DeviceIdentity:
    hwid: str
    version: int
    source: str


def read_windows_machine_guid() -> str:
    """
    Read MachineGuid from Windows Registry.
    Uses winreg with KEY_READ | KEY_WOW64_64KEY for consistent access.
    
    Returns:
        The raw MachineGuid string from Registry.
        
    Raises:
        DeviceIdentityError: If the registry key cannot be read.
    """
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception as e:
        raise DeviceIdentityError(
            f"Cannot read MachineGuid from Registry: {type(e).__name__}"
        ) from e


def normalize_machine_guid(value: str) -> str:
    """
    Normalize a MachineGuid value for consistent hashing.
    
    - Convert to string
    - Strip whitespace
    - Lowercase
    - Remove braces {}
    - Validate non-empty
    
    Returns:
        Normalized MachineGuid string.
        
    Raises:
        DeviceIdentityError: If the value is empty after normalization.
    """
    normalized = str(value).strip().lower().replace("{", "").replace("}", "")
    if not normalized:
        raise DeviceIdentityError("MachineGuid is empty after normalization")
    return normalized


def build_hwid_v2(machine_guid: str) -> str:
    """
    Build HWID v2 from a normalized MachineGuid.
    
    Algorithm: SHA256("video-cutter|hwid-v2|" + machine_guid)
    
    Returns:
        Hex-encoded SHA256 hash.
    """
    raw = f"{HWID_NAMESPACE}|{machine_guid}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_device_profile_path() -> str:
    """Get path to device profile file."""
    from version import APPDATA_FOLDER
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    folder = os.path.join(app_data, APPDATA_FOLDER)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "device_profile.dat")


def _save_device_profile(identity: DeviceIdentity) -> None:
    """Save device profile to disk, protected by DPAPI."""
    try:
        from dpapi_storage import dpapi_encrypt, DEVICE_PROFILE_ENTROPY
        
        profile_data = json.dumps({
            "schema_version": 2,
            "hwid_version": identity.version,
            "hwid": identity.hwid,
            "source": identity.source,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        encrypted = dpapi_encrypt(
            profile_data.encode("utf-8"),
            DEVICE_PROFILE_ENTROPY,
        )
        
        path = _get_device_profile_path()
        tmp_path = path + ".tmp"
        
        with open(tmp_path, "wb") as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        
        os.replace(tmp_path, path)
        logger.info("[IDENTITY] device profile saved successfully")
    except Exception as e:
        logger.warning(f"[IDENTITY] failed to save device profile: {type(e).__name__}")


def _load_device_profile() -> Optional[DeviceIdentity]:
    """Load device profile from disk, decrypting with DPAPI."""
    try:
        from dpapi_storage import dpapi_decrypt, DEVICE_PROFILE_ENTROPY
        
        path = _get_device_profile_path()
        if not os.path.exists(path):
            return None
        
        with open(path, "rb") as f:
            encrypted = f.read()
        
        if not encrypted:
            return None
        
        decrypted = dpapi_decrypt(encrypted, DEVICE_PROFILE_ENTROPY)
        data = json.loads(decrypted.decode("utf-8"))
        
        if data.get("schema_version") != 2:
            logger.warning("[IDENTITY] device profile has unexpected schema version")
            return None
        
        hwid = data.get("hwid")
        version = data.get("hwid_version", 2)
        source = data.get("source", "cached_profile")
        
        if not hwid:
            return None
        
        return DeviceIdentity(hwid=hwid, version=version, source=f"{source}|cached")
    except Exception as e:
        logger.warning(f"[IDENTITY] failed to load device profile: {type(e).__name__}")
        return None


def get_device_identity() -> DeviceIdentity:
    """
    Get device identity using HWID v2.
    
    Strategy:
    1. Try reading MachineGuid from Registry → build HWID v2.
    2. Save/update device profile on success.
    3. If Registry fails, try loading cached device profile.
    4. If no profile exists and Registry fails, raise error.
    
    Returns:
        DeviceIdentity with hwid, version, and source.
        
    Raises:
        DeviceIdentityError: If identity cannot be determined.
    """
    # Try reading from Registry
    try:
        raw_guid = read_windows_machine_guid()
        normalized = normalize_machine_guid(raw_guid)
        hwid = build_hwid_v2(normalized)
        
        identity = DeviceIdentity(
            hwid=hwid,
            version=HWID_VERSION,
            source="windows_machine_guid",
        )
        
        # Log masked HWID (never log raw MachineGuid)
        masked = hwid[:8] + "..." + hwid[-5:]
        logger.info(f"[IDENTITY] version={HWID_VERSION} id={masked}")
        
        # Save/update device profile
        _save_device_profile(identity)
        
        return identity
    except DeviceIdentityError:
        # Registry failed — try cached profile
        logger.warning("[IDENTITY] registry read failed, trying cached profile")
        cached = _load_device_profile()
        if cached:
            masked = cached.hwid[:8] + "..." + cached.hwid[-5:]
            logger.info(f"[IDENTITY] using cached profile version={cached.version} id={masked}")
            return cached
        
        raise DeviceIdentityError(
            "Cannot determine device identity: "
            "MachineGuid not readable and no cached profile exists. "
            "Please run the application with appropriate permissions."
        )


def get_hwid() -> str:
    """
    Convenience function: get the HWID string.
    
    Returns:
        HWID v2 hex string.
        
    Raises:
        DeviceIdentityError: If identity cannot be determined.
    """
    return get_device_identity().hwid


# ═══════════════════════════════════════════════════════════════════════════════
#  LEGACY HWID CANDIDATES (for migration only)
# ═══════════════════════════════════════════════════════════════════════════════

def get_legacy_hwid_candidates() -> list:
    """
    Generate all possible HWID values that the old algorithm might have produced.
    Used ONLY for migrating legacy XOR-encoded license tokens.
    
    The old algorithm:
        parts = [motherboard_uuid, first_disk_serial]  (or subsets)
        fallback: uuid.getnode() or "VIDEO_FACTORY_DEFAULT_FALLBACK_HWID"
        SHA256("|".join(parts))
    
    Returns:
        List of possible legacy HWID hex strings.
    """
    candidates = []
    
    motherboard_uuid = None
    disk_serials = []
    
    # Try getting motherboard UUID (same as old code)
    try:
        out = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=10,
        )
        for line in out.splitlines():
            line = line.strip()
            if line and "uuid" not in line.lower() and "node" not in line.lower():
                motherboard_uuid = line
                break
    except Exception:
        pass
    
    # Try getting ALL disk serials (old code took first one, but order may vary)
    try:
        out = subprocess.check_output(
            "wmic diskdrive get serialnumber",
            shell=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=10,
        )
        for line in out.splitlines():
            line = line.strip()
            if line and "serialnumber" not in line.lower() and line:
                disk_serials.append(line)
    except Exception:
        pass
    
    # MAC address
    mac_str = None
    try:
        import uuid as uuid_mod
        mac_str = str(uuid_mod.getnode())
    except Exception:
        pass
    
    # Generate all candidate combinations the old algorithm might produce
    # Case 1: motherboard_uuid + first_disk_serial (primary old behavior)
    if motherboard_uuid and disk_serials:
        for serial in disk_serials:
            raw = f"{motherboard_uuid}|{serial}"
            candidates.append(hashlib.sha256(raw.encode("utf-8")).hexdigest())
    
    # Case 2: motherboard_uuid only (disk serial failed)
    if motherboard_uuid:
        candidates.append(
            hashlib.sha256(motherboard_uuid.encode("utf-8")).hexdigest()
        )
    
    # Case 3: disk_serial only (motherboard UUID failed)
    for serial in disk_serials:
        candidates.append(
            hashlib.sha256(serial.encode("utf-8")).hexdigest()
        )
    
    # Case 4: MAC address fallback
    if mac_str:
        candidates.append(
            hashlib.sha256(mac_str.encode("utf-8")).hexdigest()
        )
    
    # Case 5: Default fallback (shared — not ideal but must try)
    candidates.append(
        hashlib.sha256(
            "VIDEO_FACTORY_DEFAULT_FALLBACK_HWID".encode("utf-8")
        ).hexdigest()
    )
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    
    return unique
