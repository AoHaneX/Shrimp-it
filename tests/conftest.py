"""Shared fixtures: silent notifications, isolated history and Qt helpers."""

import os
import time
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from shrimpit.engine import ConversionResult
from shrimpit.gui.main_window import MainWindow
from shrimpit.history import HistoryStore, timestamp
from shrimpit.processing import Options


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr("shrimpit.history.default_history_path", lambda: tmp_path / "history.json")


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    app = QApplication.instance() or QApplication([])
    yield app
    # Destroy closed test windows before Qt and Python tear down their runtimes.
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(autouse=True)
def quiet_notifications(monkeypatch):
    calls = {"sound": Mock(), "message": Mock()}
    player = Mock()
    player.play = calls["sound"]
    player.setSource.side_effect = lambda url: setattr(player.source, "return_value", url)
    monkeypatch.setattr("shrimpit.gui.notifications.QMediaPlayer", Mock(return_value=player))
    monkeypatch.setattr("shrimpit.gui.notifications.QAudioOutput", Mock())
    monkeypatch.setattr(QSystemTrayIcon, "showMessage", calls["message"])
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    return calls


@pytest.fixture
def wait_for(qt_application):
    """Process Qt events until a condition holds, then assert it."""

    def wait(condition, timeout=10):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            qt_application.processEvents()
            time.sleep(0.01)
        qt_application.processEvents()
        assert condition()

    return wait


def stop_workers(window, timeout=15000):
    """Let running jobs end so that closing the window cannot interrupt a Qt thread."""
    for page in (window.compression, window.enlargement):
        page.shutting_down = True
        page.stop_timers()
        for job in (page.job, page.preview_job):
            if job:
                job.requestInterruption()
                assert job.wait(timeout)


@pytest.fixture
def window(qt_application, tmp_path):
    """Main window with preferences and history stored in the test folder."""
    widget = MainWindow(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        HistoryStore(tmp_path / "history.json"),
    )
    widget.show()
    qt_application.processEvents()
    yield widget
    stop_workers(widget)
    qt_application.processEvents()
    widget.close()
    qt_application.processEvents()


@pytest.fixture
def record(tmp_path):
    """Return a helper that saves two small images and records them in a history store."""

    def save(store, batch="batch", name="photo", created_at=None):
        source = tmp_path / f"{name}.png"
        output = tmp_path / f"{name}-min.png"
        Image.new("RGBA", (12, 8), (80, 120, 220, 90)).save(source)
        Image.new("RGBA", (12, 8), (80, 120, 220, 90)).save(output)
        result = ConversionResult(output, source.stat().st_size, output.stat().st_size, (12, 8), (12, 8))
        store.record(batch, created_at or timestamp(), source, result, Options(output_format="PNG"))
        return source, output

    return save
