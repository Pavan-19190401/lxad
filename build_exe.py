"""
PyInstaller Build Automation Script for LXAD.

Generates a standalone single-file Windows executable:
    python build_exe.py
"""

import os
import subprocess
import sys


def build():
    print("========================================")
    print("Building LXAD Standalone Executable (.exe)")
    print("========================================")

    # Ensure bundled dataset is generated before freezing
    from lxad.benchmark.loghub_hdfs import generate_synthetic_hdfs
    generate_synthetic_hdfs()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "lxad.spec",
        "--clean",
        "--noconfirm"
    ]

    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        exe_path = os.path.abspath(os.path.join("dist", "LXAD.exe"))
        print("\n[SUCCESS] Build completed successfully!")
        print(f"Executable path: {exe_path}")
    else:
        print(f"\n[ERROR] Build failed with exit code: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
