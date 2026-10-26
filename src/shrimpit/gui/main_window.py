"""Application shell and page navigation."""

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QScrollArea, QStackedWidget

from shrimpit.gui.navigation import Page, Sidebar
from shrimpit.gui.notifications import CompletionNotifier
from shrimpit.gui.pages import HomePage, ProcessingPage, SettingsPage
from shrimpit.gui.pages.history import HistoryPage
from shrimpit.gui.pages.progress import ProgressPage
from shrimpit.gui.theme import stylesheet, title_font
from shrimpit.gui.widgets import OceanBackground
from shrimpit.history import HistoryStore
from shrimpit.preferences import boolean_setting


class MainWindow(QMainWindow):
    def __init__(self, settings=None, history_store=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("BlueShrimp", "Shrimpit")
        self.setWindowTitle("Shrimp'It — Compression et agrandissement")
        self.resize(1360, 960)
        self.setMinimumSize(760, 560)
        self.setStyleSheet(stylesheet(title_font()))
        root = OceanBackground()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.home = HomePage()
        self.compression = ProcessingPage(settings=self.settings)
        self.enlargement = ProcessingPage(enlarge=True, settings=self.settings)
        self.preferences = SettingsPage(self.settings)
        self.processing = ProgressPage()
        self.history_store = history_store if history_store is not None else HistoryStore()
        self.history = HistoryPage(self.history_store)
        self.processing_source = None
        self.close_pending = False
        self.notifier = CompletionNotifier(self, settings=self.settings)
        self.notifier.activated.connect(self.show_results)
        pages = {
            Page.HOME: self.home,
            Page.COMPRESSION: self.compression,
            Page.ENLARGEMENT: self.enlargement,
            Page.SETTINGS: self.preferences,
            Page.PROGRESS: self.processing,
            Page.HISTORY: self.history,
        }
        for _, page in sorted(pages.items()):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            scroll.viewport().setAutoFillBackground(False)
            self.stack.addWidget(scroll)
        self.sidebar.selected.connect(self.navigate)
        self.home.navigate.connect(self.navigate)
        self.preferences.animation_changed.connect(self.set_animation)
        self.set_animation(boolean_setting(self.settings, "animation"))
        for page in (self.compression, self.enlargement):
            page.busy_changed.connect(lambda busy, source=page: self.set_busy(source, busy))
        self.processing.cancel_requested.connect(self.cancel_processing)
        self.processing.return_requested.connect(self.return_to_images)

    def navigate(self, index):
        if self.compression.job or self.enlargement.job:
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_page(index)
        if index == Page.HISTORY:
            self.history.reload()

    def set_animation(self, enabled):
        self.sidebar.animation.setDuration(190 if enabled else 0)

    def set_busy(self, source, busy):
        for button in self.sidebar.buttons:
            button.setEnabled(not busy)
        if busy:
            source.job.history_store = self.history_store
            self.processing_source = source
            self.sidebar.set_page(self.tool_page(source))
            self.processing.begin(source.job, source.enlarge, "smooth" if source.enlarge else "pixel")
            self.stack.setCurrentIndex(Page.PROGRESS)
        else:
            self.processing.finish(source.last_export)
            if source.last_export.get("history_errors"):
                self.processing.details.setText(
                    self.processing.details.text()
                    + "\nHistorique incomplet :\n"
                    + "\n".join(source.last_export["history_errors"])
                )
            if not self.close_pending:
                self.notifier.finished(source.last_export, source.enlarge)

    def show_results(self):
        if self.processing_source:
            self.stack.setCurrentIndex(Page.PROGRESS)
            self.sidebar.set_page(self.tool_page(self.processing_source))
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def cancel_processing(self):
        if self.processing_source:
            self.processing_source.cancel_export()

    def return_to_images(self):
        self.navigate(self.tool_page(self.processing_source))

    @staticmethod
    def tool_page(source):
        return Page.ENLARGEMENT if source.enlarge else Page.COMPRESSION

    def closeEvent(self, event):
        pages = (self.compression, self.enlargement)
        if not self.close_pending and any(page.job for page in pages):
            choice = QMessageBox.question(
                self,
                "Quitter Shrimp'It ?",
                "Un export est en cours. Terminer l’image actuelle, annuler la suite et quitter ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.close_pending = True
        for page in pages:
            page.shutting_down = True
            page.stop_timers()
        if any(page.running() for page in pages):
            self.centralWidget().setEnabled(False)
            for page in pages:
                for worker in (page.job, page.preview_job):
                    if worker is not None:
                        worker.requestInterruption()
                        worker.finished.connect(self.retry_close)
                        if worker.isFinished():
                            self.retry_close()
            self.setWindowTitle("Shrimp'It — Fermeture après l’image en cours…")
            event.ignore()
        else:
            self.history.shutdown()
            self.settings.sync()
            self.notifier.close()
            event.accept()

    def retry_close(self):
        if self.close_pending:
            QTimer.singleShot(0, self.close)
