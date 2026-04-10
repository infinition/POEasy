"""
Build script for POEasy 2.0 — creates a standalone .exe using PyInstaller.
Run: python build.py
"""

import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(HERE, "POEasy.py")
ICON_FILE = os.path.join(HERE, "poeasy.ico")
ICON_CREATOR = os.path.join(HERE, "create_icon.py")
DIST_DIR = os.path.join(HERE, "dist")
BUILD_DIR = os.path.join(HERE, "build")


def run(cmd: list[str], desc: str):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=HERE)
    if result.returncode != 0:
        print(f"FAILED: {desc} (exit code {result.returncode})")
        sys.exit(result.returncode)


def main():
    python = sys.executable

    # 1. Ensure pyinstaller is installed
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("Installing PyInstaller...")
        run([python, "-m", "pip", "install", "pyinstaller"], "Install PyInstaller")

    # 2. Generate icon if not present
    if not os.path.isfile(ICON_FILE):
        print("Generating icon...")
        run([python, ICON_CREATOR], "Generate icon")

    # 3. Find conda Library/bin DLLs that PyInstaller misses
    conda_prefix = os.environ.get("CONDA_PREFIX", os.path.dirname(os.path.dirname(python)))
    dll_dir = os.path.join(conda_prefix, "Library", "bin")
    missing_dlls = ["ffi.dll", "zstd.dll", "liblzma.dll", "libmpdec-4.dll"]

    # 4. Build exe
    pyinstaller_args = [
        python, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "POEasy",
        "--icon", ICON_FILE,
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "keyboard",
        "--hidden-import", "PyQt6.sip",
        # Add the icon as data so it's available at runtime
        "--add-data", f"{ICON_FILE};.",
    ]

    # Include missing DLLs from conda environment
    for dll_name in missing_dlls:
        dll_path = os.path.join(dll_dir, dll_name)
        if os.path.isfile(dll_path):
            pyinstaller_args.extend(["--add-binary", f"{dll_path};."])
            print(f"  Including DLL: {dll_name}")
        else:
            print(f"  WARNING: DLL not found: {dll_path}")

    pyinstaller_args.append(MAIN_SCRIPT)

    run(pyinstaller_args, "Build POEasy.exe with PyInstaller")

    exe_path = os.path.join(DIST_DIR, "POEasy.exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n{'='*60}")
        print(f"  BUILD SUCCESSFUL!")
        print(f"  Output: {exe_path}")
        print(f"  Size:   {size_mb:.1f} MB")
        print(f"{'='*60}")
    else:
        print("\nERROR: .exe not found after build.")
        sys.exit(1)


if __name__ == "__main__":
    main()
