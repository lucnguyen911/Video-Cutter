"""Release build that obfuscates the sensitive modules actually imported by Video Cutter.

Usage: .venv\\Scripts\\python.exe build_protected.py
Run this from a clean release workspace. Keep code-signing credentials outside
this repository and sign the produced EXE and installer in CI/release tooling.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OBFUSCATED = ROOT / "build" / "obfuscated"
PROTECTED_MODULES = [
    "security.py", "device_identity.py", "dpapi_storage.py",
    "updater.py", "license_dialog.py", "version.py",
]
PROTECTED_MODULE_NAMES = [Path(module).stem for module in PROTECTED_MODULES]
HIDDEN_IMPORTS = [
    # PyArmor hides imports from PyInstaller's static analysis. Keep every
    # protected module and non-trivial dependency it imports at runtime.
    *PROTECTED_MODULE_NAMES,
    "packaging", "packaging.version",
    "urllib.request", "urllib.error", "urllib.parse",
    "http.cookiejar", "html.parser",
    "winreg", "ctypes", "ctypes.wintypes",
]

def run(command):
    print("+", " ".join(map(str, command)))
    subprocess.run(command, cwd=ROOT, check=True)

def main():
    pyarmor = ROOT / ".venv" / "Scripts" / "pyarmor.exe"
    pyarmor_command = str(pyarmor) if pyarmor.exists() else "pyarmor"
    shutil.rmtree(OBFUSCATED, ignore_errors=True)
    run([pyarmor_command, "gen", "-O", str(OBFUSCATED), *PROTECTED_MODULES])
    # The PyArmor trial cannot protect a large entry script. Copying main.py into
    # the protected staging directory makes it import the obfuscated modules.
    shutil.copy2(ROOT / "main.py", OBFUSCATED / "main.py")
    run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", "Video_Cutter",
        "--icon", "icon_scissors.ico", "--add-data", "assets;assets",
        "--add-data", "icon_scissors.ico;.",
        *[item for module in HIDDEN_IMPORTS for item in ("--hidden-import", module)],
        "--paths", str(OBFUSCATED), str(OBFUSCATED / "main.py"),
    ])

if __name__ == "__main__":
    main()