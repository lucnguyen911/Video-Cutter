# build_sdk.py
# Automation script to compile the MMO Security SDK using PyArmor.

import os
import shutil
import subprocess
import sys

def build_sdk():
    print("Starting MMO Security SDK compilation...")
    
    # Locate pyarmor in the virtual environment
    venv_pyarmor = os.path.join(".venv", "Scripts", "pyarmor.exe")
    if not os.path.exists(venv_pyarmor):
        venv_pyarmor = "pyarmor"  # Fallback to system PATH

    dist_dir = "dist_sdk"
    if os.path.exists(dist_dir):
        print(f"Cleaning existing {dist_dir} directory...")
        try:
            shutil.rmtree(dist_dir)
        except Exception as e:
            print(f"Warning: Could not remove old {dist_dir}: {e}")

    # Compile the SDK core
    cmd = [
        venv_pyarmor,
        "gen",
        "-O", dist_dir,
        "mmo_security_core.py"
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    print(result.stdout)
    if result.returncode != 0:
        print("Error: PyArmor compilation failed!")
        print(result.stderr)
        sys.exit(result.returncode)
        
    print("MMO Security SDK obfuscation completed successfully!")
    print(f"Distribution files generated in: {os.path.abspath(dist_dir)}")

if __name__ == "__main__":
    build_sdk()
