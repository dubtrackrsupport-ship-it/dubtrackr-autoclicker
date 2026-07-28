"""Build DubtrackrAutoClicker.exe with PyInstaller.

    pip install pyinstaller pillow
    python build.py

Produces dist/DubtrackrAutoClicker.exe (single file, windowed, branded icon).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    import customtkinter
    ctk_dir = os.path.dirname(customtkinter.__file__)
    sep = ";" if os.name == "nt" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "DubtrackrAutoClicker",
        "--icon", os.path.join(HERE, "dubtrackr.ico"),
        "--version-file", os.path.join(HERE, "version_info.txt"),
        "--add-data", f"{os.path.join(HERE, 'dubtrackr.ico')}{sep}.",
        "--add-data", f"{os.path.join(HERE, 'assets')}{sep}assets",
        "--add-data", f"{ctk_dir}{sep}customtkinter",
        "--collect-submodules", "customtkinter",
        # numpy is dragged in by Pillow but never used — ~28 MB of dead weight
        "--exclude-module", "numpy",
        os.path.join(HERE, "dubtrackr_autoclicker.py"),
    ]
    print(" ".join(cmd))
    subprocess.check_call(cmd)
    print("\nDone -> dist/DubtrackrAutoClicker.exe")


if __name__ == "__main__":
    main()
