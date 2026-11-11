# PyInstaller recipe for the Windows build: one folder, no console window.
# Run it through scripts/build_windows.ps1, which also tests and archives the result.

import re
from pathlib import Path

from PIL import Image
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent
SOURCE = ROOT / "src" / "shrimpit"
VERSION = re.search(r'__version__ = "([^"]+)"', (SOURCE / "__init__.py").read_text(encoding="utf-8"))[1]
NUMBERS = tuple(int(part) for part in VERSION.split(".")) + (0,)

# Build the executable icon from the mascot instead of storing a binary copy.
ICON = Path(workpath) / "shrimpit.ico"
ICON.parent.mkdir(parents=True, exist_ok=True)
with Image.open(SOURCE / "assets" / "branding" / "shrimpy.png") as mascot:
    mascot.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040C04B0",
                    [
                        StringStruct("CompanyName", "BlueShrimp"),
                        StringStruct("FileDescription", "Shrimp'It"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "ShrimpIt"),
                        StringStruct("LegalCopyright", "Code MIT · illustrations et sons : tous droits réservés"),
                        StringStruct("OriginalFilename", "ShrimpIt.exe"),
                        StringStruct("ProductName", "Shrimp'It"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)

# The ExoQuant palette engine (MIT) is compiled by scripts/build_png_engine.py before this recipe runs.
PNG_ENGINE = SOURCE / "native" / "exoquant.dll"
if not PNG_ENGINE.is_file():
    raise SystemExit(f"Missing {PNG_ENGINE}: run scripts/build_png_engine.py first.")

analysis = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    # The C sources stay out of the build; the DLL is listed as a binary so its imports are checked.
    binaries=[(str(PNG_ENGINE), "shrimpit/native")],
    datas=collect_data_files("shrimpit", excludes=["**/__pycache__/**", "native/**"]),
    excludes=["tkinter"],
    noarchive=False,
)
# Shrimp'It is a widgets application: it needs neither the software OpenGL renderer nor
# Qt Quick, which PySide6's hooks bundle by default.
UNUSED_BINARIES = {"opengl32sw.dll", "Qt6Quick.dll", "Qt6Qml.dll", "Qt6QmlModels.dll", "Qt6QmlMeta.dll"}
analysis.binaries = [entry for entry in analysis.binaries if Path(entry[0]).name not in UNUSED_BINARIES]
# The interface is in French only: keep Qt's French translations.
analysis.datas = [
    entry
    for entry in analysis.datas
    if not (Path(entry[0]).parent.name == "translations" and not entry[0].endswith("_fr.qm"))
]

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ShrimpIt",
    console=False,
    icon=str(ICON),
    version=VERSION_INFO,
    upx=False,
)
COLLECT(exe, analysis.binaries, analysis.datas, name="ShrimpIt", upx=False)
