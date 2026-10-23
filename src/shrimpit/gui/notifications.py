"""Play a completion sound and show a desktop notification."""

import logging

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QSystemTrayIcon

from shrimpit.preferences import boolean_setting
from shrimpit.resources import FINISH_SOUND, SHRIMPY_ICON


class CompletionNotifier(QObject):
    activated = Signal()

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.audio = None
        self.player = None
        self.tray = QSystemTrayIcon(QIcon(str(SHRIMPY_ICON)), self)
        self.tray.setToolTip("Shrimp'It")
        self.tray.messageClicked.connect(self.activated)
        self.tray.activated.connect(self.on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.activated.emit()

    def finished(self, summary, enlarge=False):
        total = summary["total"]
        if not total:
            return
        interrupted = summary["completed"] < total
        errors = len(summary["errors"])
        operation = "Agrandissement" if enlarge else "Compression"
        if interrupted:
            title = f"{operation} interrompu" if enlarge else "Compression interrompue"
        elif errors:
            title = f"{operation} terminé avec erreurs" if enlarge else "Compression terminée avec erreurs"
        else:
            title = f"{operation} terminé" if enlarge else "Compression terminée"
        message = f"{summary['successes']} / {total} image(s) enregistrée(s)."
        if errors:
            message += f" {errors} erreur(s)."
        if interrupted:
            message += f" {total - summary['completed']} image(s) non traitée(s)."
        message += " Cliquez pour revenir à Shrimp'It."
        if not interrupted and boolean_setting(self.settings, "sound") and FINISH_SOUND.is_file():
            if self.player is None:
                self.audio = QAudioOutput(self)
                self.audio.setVolume(0.7)
                self.player = QMediaPlayer(self)
                self.player.setAudioOutput(self.audio)
                self.player.setLoops(1)
                self.player.errorOccurred.connect(self.audio_failed)
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(FINISH_SOUND)))
            self.player.play()
        if (
            boolean_setting(self.settings, "notifications")
            and QSystemTrayIcon.isSystemTrayAvailable()
            and QSystemTrayIcon.supportsMessages()
        ):
            self.tray.show()
            icon = (
                QSystemTrayIcon.MessageIcon.Warning
                if errors or interrupted
                else QSystemTrayIcon.MessageIcon.Information
            )
            self.tray.showMessage(f"Shrimp'It — {title}", message, icon, 7000)

    def close(self):
        if self.player is not None:
            self.player.stop()
        self.tray.hide()

    def audio_failed(self, error, message):
        logging.getLogger(__name__).warning("Completion audio unavailable: %s", message)
