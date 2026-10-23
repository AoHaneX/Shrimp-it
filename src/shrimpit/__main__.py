"""Start Shrimpit with python -m shrimpit."""

import ctypes
import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from shrimpit.diagnostics import configure_logging
from shrimpit.gui.main_window import MainWindow
from shrimpit.resources import SHRIMPY_ICON


def main() -> int:
    folder = configure_logging()
    if sys.platform == "win32":
        # Give Shrimpit its own Windows taskbar identity.
        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        result = set_app_id("BlueShrimp.Shrimpit")
        if result < 0:
            raise OSError(f"Windows application identity failed: {result}")

    app = QApplication(sys.argv)

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
