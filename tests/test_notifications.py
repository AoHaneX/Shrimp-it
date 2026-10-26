"""Check batch completion, cancellation, and notification fallback."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon

from shrimpit.gui.main_window import MainWindow
from shrimpit.gui.notifications import CompletionNotifier
from shrimpit.resources import FINISH_SOUND


@pytest.fixture
def notifier(monkeypatch, qt_application):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", lambda: True)
    service = CompletionNotifier()
    yield service
    service.close()


@pytest.mark.parametrize(
    "enlarge,completed,successes,errors,title,plays",
    [
        (False, 2, 2, [], "Compression terminée", 1),
        (True, 2, 2, [], "Agrandissement terminé", 1),
        (False, 2, 1, ["broken.png"], "Compression terminée avec erreurs", 1),
        (True, 2, 0, ["a.png", "b.png"], "Agrandissement terminé avec erreurs", 1),
        (False, 1, 1, [], "Compression interrompue", 0),
    ],
)
def test_completion_summary(
    notifier, quiet_notifications, enlarge, completed, successes, errors, title, plays
):
    notifier.finished(dict(total=2, completed=completed, successes=successes, errors=errors), enlarge)
    assert quiet_notifications["sound"].call_count == plays
    quiet_notifications["message"].assert_called_once()
    args = quiet_notifications["message"].call_args.args
    assert args[0] == f"Shrimp'It — {title}"
    assert f"{successes} / 2" in args[1]
    if plays:
        assert Path(notifier.player.source().toLocalFile()) == FINISH_SOUND


def test_tray_icon_appears_only_for_notifications(notifier, monkeypatch):
    shown = []
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: shown.append(self))
    service = CompletionNotifier()
    try:
        assert not shown
        service.finished(dict(total=1, completed=1, successes=1, errors=[]))
        assert shown == [service.tray]
        assert service.hide_timer.isActive()
    finally:
        service.close()
    assert not service.hide_timer.isActive()


def test_missing_sound_keeps_notification(notifier, quiet_notifications, monkeypatch, tmp_path):
    monkeypatch.setattr("shrimpit.gui.notifications.FINISH_SOUND", tmp_path / "missing.ogg")
    notifier.finished(dict(total=1, completed=1, successes=1, errors=[]))
    quiet_notifications["sound"].assert_not_called()
    quiet_notifications["message"].assert_called_once()


def test_missing_tray_keeps_sound(notifier, quiet_notifications, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    notifier.finished(dict(total=1, completed=1, successes=1, errors=[]))
    quiet_notifications["sound"].assert_called_once()
    quiet_notifications["message"].assert_not_called()


@pytest.mark.parametrize("enlarge", [False, True])
def test_real_batch_notifies_once(wait_for, enlarge, tmp_path, monkeypatch, quiet_notifications):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", lambda: True)
    window = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    page = window.enlargement if enlarge else window.compression
    results = tmp_path / "results"
    results.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(results))
    sources = [tmp_path / "first.png", tmp_path / "second.png"]
    for source in sources:
        Image.new("RGB", (12, 12), "blue").save(source)
    try:
        page.add_files(sources)
        page.start_export()
        wait_for(lambda: page.job is None)
        assert page.last_export["successes"] == 2
        quiet_notifications["sound"].assert_called_once()
        quiet_notifications["message"].assert_called_once()
        window.navigate(0)
        window.notifier.tray.messageClicked.emit()
        assert window.stack.currentIndex() == 4
        assert window.isVisible()
    finally:
        for tool in (window.compression, window.enlargement):
            tool.stop_timers()
            if tool.job:
                tool.job.wait(10000)
            if tool.preview_job:
                tool.preview_job.wait(10000)
        app.processEvents()
        window.close()
