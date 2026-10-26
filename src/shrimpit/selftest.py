"""Check an installed or packaged copy without touching the user's files or settings."""

import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QSettings, QThread, QUrl
from PySide6.QtGui import QMovie
from PySide6.QtMultimedia import QMediaPlayer

from shrimpit import __version__
from shrimpit.engine import convert_image, upscale_image
from shrimpit.resources import (
    ASSETS,
    BACKGROUND,
    FINISH_SOUND,
    PROCESSING_ANIMATIONS,
    SHRIMPY_ICON,
    SIDEBAR_MASCOT,
    TITLE_FONT,
)
from shrimpit.upscale import UpscaleSettings

ICONS = ("home", "image", "expand", "history", "settings")
EXAMPLES = (
    "compression-before.png",
    "compression-after.jpg",
    "enlargement-before.png",
    "enlargement-after.png",
)


def check_assets(folder):
    paths = [
        BACKGROUND,
        SIDEBAR_MASCOT,
        SHRIMPY_ICON,
        TITLE_FONT,
        FINISH_SOUND,
        *PROCESSING_ANIMATIONS.values(),
    ]
    paths += [ASSETS / "icons" / f"{name}.png" for name in ICONS]
    paths += [ASSETS / "examples" / name for name in EXAMPLES]
    paths.append(ASSETS / "licenses" / "chakra-petch-OFL.txt")
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(f"missing assets: {', '.join(missing)}")


def check_formats(folder):
    source = ASSETS / "examples" / "compression-before.png"
    for output_format, suffix in (("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")):
        result = convert_image(source, folder / f"converted{suffix}", output_format, 80)
        with Image.open(result.destination) as image:
            image.load()
            if image.format != output_format or image.size != result.input_size:
                raise AssertionError(f"{output_format} output is invalid")


def check_enlargement(folder):
    source = ASSETS / "examples" / "enlargement-before.png"
    for mode in ("photo", "illustration", "pixel_art"):
        result = upscale_image(source, folder / f"{mode}.png", 2, settings=UpscaleSettings(mode=mode))
        if result.output_size != tuple(value * 2 for value in result.input_size):
            raise AssertionError(f"{mode} enlargement has the wrong size")


def check_sound(folder):
    """Decode the completion sound without playing it: this loads Qt's FFmpeg backend."""
    player = QMediaPlayer()
    player.setSource(QUrl.fromLocalFile(str(FINISH_SOUND)))
    loaded = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)
    timer = QElapsedTimer()
    timer.start()
    while player.mediaStatus() not in loaded and player.error() == QMediaPlayer.Error.NoError:
        if timer.elapsed() > 5000:
            break
        QCoreApplication.processEvents()
        QThread.msleep(10)
    if player.mediaStatus() not in loaded:
        raise AssertionError(
            f"completion sound cannot be loaded: {player.errorString() or player.mediaStatus()}"
        )


def check_qt_resources(folder):
    from shrimpit.gui.theme import title_font

    if title_font() == "Consolas":
        raise AssertionError("title font could not be loaded")
    for path in PROCESSING_ANIMATIONS.values():
        if not QMovie(str(path)).isValid():
            raise AssertionError(f"animation {path.name} cannot be decoded")
    if QCoreApplication.translate("QPlatformTheme", "&Yes") == "&Yes":
        raise AssertionError("French Qt translation is not installed")


def check_window(folder):
    from shrimpit.gui.main_window import MainWindow
    from shrimpit.history import HistoryStore

    settings = QSettings(str(folder / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings, HistoryStore(folder / "history.json"))
    try:
        if window.stack.count() != 6:
            raise AssertionError("main window pages are incomplete")
    finally:
        for page in (window.compression, window.enlargement):
            page.shutting_down = True
            page.stop_timers()
        window.close()
        window.deleteLater()


CHECKS = (
    ("Ressources de l’application", check_assets),
    ("Compression JPEG, PNG et WebP", check_formats),
    ("Agrandissement Photographie, Illustration et Pixel Art", check_enlargement),
    ("Police, animations et traduction Qt", check_qt_resources),
    ("Son de fin de traitement", check_sound),
    ("Fenêtre principale", check_window),
)


def run_self_test(app, report_path=None) -> int:
    """Run every check in a temporary folder; return 0 when all of them pass."""
    lines = [f"Shrimp'It {__version__} : autotest"]
    failures = 0
    with TemporaryDirectory(prefix="shrimpit-selftest-") as temporary:
        for title, check in CHECKS:
            try:
                check(Path(temporary))
                app.processEvents()
            except Exception:
                failures += 1
                lines.append(f"ÉCHEC  {title}\n{traceback.format_exc()}")
            else:
                lines.append(f"OK     {title}")
    lines.append("Résultat : " + ("réussi" if not failures else f"{failures} échec(s)"))
    report = "\n".join(lines) + "\n"
    if report_path:
        Path(report_path).write_text(report, encoding="utf-8")
    else:
        try:
            print(report, end="")
        except (AttributeError, OSError):
            # A windowed executable has no console to print to.
            pass
    return 1 if failures else 0
