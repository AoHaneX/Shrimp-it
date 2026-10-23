"""Keep automated tests silent and hide desktop notifications."""

import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QSystemTrayIcon


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
