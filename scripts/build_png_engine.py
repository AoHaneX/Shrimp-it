"""Build the bundled ExoQuant palette engine (MIT) into src/shrimpit/native/exoquant.dll.

The compiler comes from the pinned ``ziglang`` wheel of the ``build`` extra, so no Visual Studio or
MinGW installation is needed. Only the DLL is copied next to the sources; the import library and the
debug symbols stay in a temporary folder. Usage: ``python scripts/build_png_engine.py``.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "src" / "shrimpit" / "native"
TARGET = NATIVE / "exoquant.dll"


def build(destination: Path = TARGET) -> Path:
    with tempfile.TemporaryDirectory(prefix="shrimpit-exoquant-") as temporary:
        output = Path(temporary) / "exoquant.dll"
        command = [
            sys.executable,
            "-m",
            "ziglang",
            "cc",
            "-shared",
            "-O2",
            "-std=c99",
            "-Wall",
            "-Werror",
            "-target",
            "x86_64-windows-gnu",
            # Strict IEEE floating point keeps palettes identical from one build to the next.
            "-ffp-contract=off",
            "-fno-sanitize=all",
            "-s",
            "-Wl,--export-all-symbols",
            "-o",
            str(output),
            str(NATIVE / "exoquant.c"),
        ]
        subprocess.run(command, check=True, cwd=temporary)
        shutil.copyfile(output, destination)
    return destination


if __name__ == "__main__":
    print(build())
