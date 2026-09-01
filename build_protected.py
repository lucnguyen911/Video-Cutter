"""Release build that obfuscates the sensitive modules actually imported by Video Cutter.

Usage: .venv\\Scripts\\python.exe build_protected.py
"""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OBFUSCATED = ROOT / "build" / "obfuscated"
PROTECTED_MODULES = [
    "security.py", "device_identity.py", "dpapi_storage.py",
    "updater.py", "license_dialog.py", "version.py", "processing_policy.py",
]

MSVC_RUNTIME_PATTERNS = (
    "concrt140.dll",
    "msvcp140*.dll",
    "vcruntime140*.dll",
)


def synchronize_msvc_runtime(dist_dir: Path) -> list[str]:
    """Use one coherent MSVC runtime for Python and Qt on clean machines.

    PyInstaller can copy the runtime used to build Python into ``_internal``
    while the PyQt wheel ships a newer runtime beside Qt. Windows may load the
    older top-level DLL first and then fail QtWidgets with "procedure not
    found". Newer MSVC redistributables are backward compatible, so the Qt
    wheel's complete runtime set is copied to the top-level runtime directory.
    """
    internal_dir = dist_dir / "_internal"
    qt_bin_dir = internal_dir / "PyQt6" / "Qt6" / "bin"
    if not qt_bin_dir.is_dir():
        raise RuntimeError(f"Qt runtime directory not found: {qt_bin_dir}")

    sources = {}
    for pattern in MSVC_RUNTIME_PATTERNS:
        for source in qt_bin_dir.glob(pattern):
            sources[source.name.casefold()] = source
    if not sources:
        raise RuntimeError("No MSVC runtime DLLs were found beside Qt.")

    copied = []
    for source in sorted(sources.values(), key=lambda item: item.name.casefold()):
        target = internal_dir / source.name
        shutil.copy2(source, target)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
            raise RuntimeError(f"MSVC runtime copy verification failed: {source.name}")
        copied.append(source.name)
    return copied

def run(command):
    print("+", " ".join(map(str, command)))
    subprocess.run(command, cwd=ROOT, check=True)

def main():
    pyarmor = ROOT / ".venv" / "Scripts" / "pyarmor.exe"
    pyarmor_command = str(pyarmor) if pyarmor.exists() else "pyarmor"
    shutil.rmtree(OBFUSCATED, ignore_errors=True)
    run([pyarmor_command, "gen", "-O", str(OBFUSCATED), *PROTECTED_MODULES])
    shutil.copy2(ROOT / "main.py", OBFUSCATED / "main.py")

    # Run PyInstaller using Video_Cutter.spec (which includes collect_all PyQt6)
    run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "Video_Cutter.spec"
    ])

    # Copy FFmpeg and FFprobe binaries into dist directory for self-contained execution
    dist_dir = ROOT / "dist" / "Video_Cutter"
    synchronized = synchronize_msvc_runtime(dist_dir)
    print("+ Synchronized MSVC runtime:", ", ".join(synchronized))
    ffmpeg_sys = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"
    ffprobe_sys = shutil.which("ffprobe") or r"C:\ffmpeg\bin\ffprobe.exe"

    if Path(ffmpeg_sys).exists() and Path(ffprobe_sys).exists():
        print(f"+ Bundling ffmpeg from: {ffmpeg_sys}")
        shutil.copy2(ffmpeg_sys, dist_dir / "ffmpeg.exe")
        print(f"+ Bundling ffprobe from: {ffprobe_sys}")
        shutil.copy2(ffprobe_sys, dist_dir / "ffprobe.exe")
        print("Successfully bundled FFmpeg binaries with GPU acceleration support.")
    else:
        print("WARNING: ffmpeg or ffprobe not found!")

if __name__ == "__main__":
    main()
