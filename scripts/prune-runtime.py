"""Remove build artifacts and ELF debug symbols before copying runtime files.

Run only inside the Docker builder. Preserve package metadata, Python/JS
runtime modules, Chromium resources, ICU data, and browser graphics libraries.
"""
from pathlib import Path
import shutil
import subprocess
import sys


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def strip_elf(root: Path) -> None:
    saved = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                if handle.read(4) != b"\x7fELF":
                    continue
            before = path.stat().st_size
            subprocess.run(["strip", "--strip-unneeded", str(path)], check=True)
            saved += before - path.stat().st_size
    print(f"Stripped {root}: removed {saved:,} bytes of symbols/debug data.", flush=True)


def prune_python() -> None:
    local = Path("/usr/local")
    venv = Path("/opt/venv")
    # The venv is installed with the builder's pip; pip itself is not needed
    # at runtime. Remove it from the separately copied Python installation.
    for path in (
        local / "include",
        local / "share/man",
        local / "lib/python3.13/site-packages",
        local / "lib/python3.13/ensurepip",
        local / "lib/python3.13/idlelib",
        local / "lib/python3.13/tkinter",
        local / "lib/python3.13/turtledemo",
        local / "lib/python3.13/pydoc_data",
    ):
        remove(path)
    for path in (local / "bin").glob("pip*"):
        remove(path)
    for root in (local, venv):
        for path in list(root.rglob("__pycache__")):
            remove(path)
        for pattern in ("*.pyc", "*.pyo", "*.a", "*.h", "*.d.ts", "*.map"):
            for path in root.rglob(pattern):
                remove(path)
        strip_elf(root)


if __name__ == "__main__":
    if sys.platform != "linux":
        raise SystemExit("This helper operates on Linux Docker builder paths only.")
    if sys.argv[1:] == ["python"]:
        prune_python()
    elif sys.argv[1:] == ["browser"]:
        strip_elf(Path("/ms-playwright"))
    else:
        raise SystemExit("Usage: prune-runtime.py python|browser (Docker builder only)")
