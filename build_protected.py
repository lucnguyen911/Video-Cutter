"""Release build that obfuscates the sensitive modules actually imported by Video Cutter.

Usage: .venv\\Scripts\\python.exe build_protected.py
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OBFUSCATED = ROOT / "build" / "obfuscated"
PROTECTED_MODULES = [
    "security.py", "device_identity.py", "dpapi_storage.py",
    "updater.py", "license_dialog.py", "version.py", "processing_policy.py",
]

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
