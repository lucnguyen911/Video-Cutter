# device_identity.py
"""Stable Windows device identity with one-time migration support.

The motherboard UUID is deliberately the primary anchor. Unlike MachineGuid it
normally survives a Windows reinstall and feature upgrades. DPAPI protects the
cached profile; the cache is for availability, not the source of truth.
"""

import hashlib
import os
import re
import subprocess
import uuid
import winreg
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from dpapi_storage import load_secure_json, save_secure_json

HWID_VERSION = 3
HWID_NAMESPACE = "video-cutter|hwid-v3"
PROFILE_ENTROPY = "VideoCutter-DeviceProfile-v3"
_V2_PROFILE_ENTROPY = "VideoCutter-DeviceProfile-v2"
_INVALID_UUIDS = {
    "00000000-0000-0000-0000-000000000000",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
}

@dataclass(frozen=True)
class DeviceIdentity:
    hwid: str
    version: int
    source: str

def get_profile_path() -> str:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(app_data, "VideoCutter", "device_profile.dat")

def get_windows_machine_guid() -> str:
    """Return the Windows installation identifier, only as a fallback."""
    for access in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | access) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                value = str(value).strip().lower().strip("{}")
                if value:
                    return value
        except OSError:
            continue
    return ""

def _normalise_motherboard_uuid(value: str) -> str:
    value = (value or "").strip().lower().strip("{}")
    if not value or value in _INVALID_UUIDS:
        return ""
    if "to be filled" in value or "default string" in value:
        return ""
    pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    return value if re.fullmatch(pattern, value) else ""

def get_motherboard_uuid_powershell() -> str:
    """Read SMBIOS product UUID via CIM; returns empty for unusable OEM values."""
    command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        return _normalise_motherboard_uuid(result.stdout)
    except (OSError, subprocess.SubprocessError):
        return ""

def build_hwid_v3(anchor: str, source: str) -> str:
    """Hash a single stable anchor. Do not combine it with volatile values."""
    if source not in {"motherboard_uuid", "machine_guid"} or not anchor:
        raise ValueError("A valid device identity anchor is required")
    material = f"{HWID_NAMESPACE}|{source}|{anchor.strip().lower()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

def build_hwid_v2(machine_guid: str, motherboard_uuid: str) -> str:
    """Compatibility helper for migrating already activated v2 installations."""
    raw = f"video_cutter_salt|{machine_guid}|{motherboard_uuid}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _load_v3_profile() -> Optional[DeviceIdentity]:
    profile = load_secure_json(get_profile_path(), PROFILE_ENTROPY)
    if not isinstance(profile, dict):
        return None
    if profile.get("schema_version") != 3 or profile.get("hwid_version") != HWID_VERSION:
        return None
    hwid, source = profile.get("hwid"), profile.get("source")
    if isinstance(hwid, str) and len(hwid) == 64 and source in {"motherboard_uuid", "machine_guid"}:
        return DeviceIdentity(hwid=hwid, version=HWID_VERSION, source=source)
    return None

def get_device_identity() -> DeviceIdentity:
    """Return a stable v3 identity, recreating its protected cache when needed."""
    cached = _load_v3_profile()
    if cached:
        return cached
    motherboard_uuid = get_motherboard_uuid_powershell()
    if motherboard_uuid:
        source, anchor = "motherboard_uuid", motherboard_uuid
    else:
        machine_guid = get_windows_machine_guid()
        if not machine_guid:
            raise RuntimeError("DEVICE_ID_UNAVAILABLE: no stable Windows anchor available")
        source, anchor = "machine_guid", machine_guid
    identity = DeviceIdentity(build_hwid_v3(anchor, source), HWID_VERSION, source)
    profile = {"schema_version": 3, "hwid_version": HWID_VERSION, "hwid": identity.hwid, "source": identity.source, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        save_secure_json(get_profile_path(), profile, PROFILE_ENTROPY)
    except OSError:
        pass
    return identity

def get_hwid() -> str:
    return get_device_identity().hwid

def get_hwid_upgrade_candidates() -> List[str]:
    """Return v2 values that this same device may already have registered."""
    candidates: List[str] = []
    old_profile = load_secure_json(get_profile_path(), _V2_PROFILE_ENTROPY)
    if isinstance(old_profile, dict) and old_profile.get("hwid_version") == 2:
        old_hwid = old_profile.get("hwid")
        if isinstance(old_hwid, str) and len(old_hwid) == 64:
            candidates.append(old_hwid)
    machine_guid = get_windows_machine_guid()
    motherboard_uuid = get_motherboard_uuid_powershell()
    if machine_guid or motherboard_uuid:
        candidates.append(build_hwid_v2(machine_guid, motherboard_uuid))
    return list(dict.fromkeys(candidates))

def get_legacy_hwid_candidates() -> List[str]:
    """Generate pre-v2 values only for the one-time server-side migration."""
    motherboard_uuid = ""
    disk_serials: List[str] = []
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        motherboard_uuid = _normalise_motherboard_uuid(result.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    def sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-CimInstance Win32_DiskDrive | Select-Object -ExpandProperty SerialNumber"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        disk_serials = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    candidates: List[str] = []
    if motherboard_uuid:
        candidates.extend(sha256(f"{motherboard_uuid}|{serial}") for serial in disk_serials)
        candidates.append(sha256(motherboard_uuid))
    candidates.extend(sha256(serial) for serial in disk_serials)
    if motherboard_uuid or disk_serials:
        first_disk = disk_serials[0] if disk_serials else ""
        candidates.append(sha256("|".join(part for part in (motherboard_uuid, first_disk) if part)))
    else:
        candidates.append(sha256(str(uuid.getnode())))
    return list(dict.fromkeys(candidates))