"""Decode small history previews outside the UI thread."""

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader


class ThumbnailSignals(QObject):
    ready = Signal(object, QImage, str)


class ThumbnailTask(QRunnable):
    def __init__(self, token, path, signals):
        super().__init__()
        self.token, self.path, self.signals = token, path, signals

    def run(self):
        image = QImage()
        status = "Image introuvable"
        try:
            if Path(self.path).is_file():
                reader = QImageReader(self.path)
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid():
                    reader.setScaledSize(size.scaled(QSize(240, 160), Qt.AspectRatioMode.KeepAspectRatio))
                    image = reader.read()
                status = "Aperçu indisponible" if image.isNull() else ""
        except (OSError, ValueError):
            status = "Aperçu indisponible"
        self.signals.ready.emit(self.token, image, status)


class ThumbnailLoader(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.signals = ThumbnailSignals(self)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)

    def request(self, token, path):
        self.pool.start(ThumbnailTask(token, path, self.signals))

    def stop(self):
        self.pool.clear()
        self.pool.waitForDone()
