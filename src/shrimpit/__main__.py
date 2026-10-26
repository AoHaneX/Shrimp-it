"""Start Shrimpit with python -m shrimpit."""

import ctypes
import logging
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from shrimpit.diagnostics import configure_logging
from shrimpit.gui.main_window import MainWindow
from shrimpit.resources import SHRIMPY_ICON


def install_french_translation(app):
    """Translate Qt's standard buttons (Yes, No, Cancel) to match the French interface."""
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(QLocale.Language.French), "qtbase", "_", folder):
        app.installTranslator(translator)
        return translator
    return None


def set_taskbar_identity():
    """Group Shrimpit's windows under its own taskbar icon; failing only affects grouping."""
    try:
        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        result = set_app_id("BlueShrimp.Shrimpit")
    except (AttributeError, OSError):
        result = -1
    if result < 0:
        logging.getLogger("shrimpit").warning("Windows taskbar identity unavailable: %s", result)


def main() -> int:
    arguments = sys.argv[1:]
    if arguments[:1] == ["--self-test"]:
        # Packaging check: no log, no settings, no history in the user's folders.
        from shrimpit.selftest import run_self_test

        app = QApplication(sys.argv[:1])
        install_french_translation(app)
        app.setStyle("Fusion")
        return run_self_test(app, arguments[1] if len(arguments) > 1 else None)

    folder = configure_logging()
    if sys.platform == "win32":
        set_taskbar_identity()

    app = QApplication(sys.argv)
    install_french_translation(app)

    def report_error(error_type, error, traceback):
        logging.getLogger("shrimpit").error(
            "Unexpected application error", exc_info=(error_type, error, traceback)
        )
        details = f"\nDiagnostic : {folder / 'shrimpit.log'}" if folder else ""
        QMessageBox.critical(None, "Erreur Shrimp'It", "Une erreur inattendue est survenue." + details)

    sys.excepthook = report_error
    app.setStyle("Fusion")
    app.setApplicationName("Shrimp'It")
    # Resolve the bundled image independently of the working directory.
    app.setWindowIcon(QIcon(str(SHRIMPY_ICON)))
    try:
        window = MainWindow()
    except Exception:
        report_error(*sys.exc_info())
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
