"""Check history navigation, asynchronous previews, and deletion controls."""

import time
from copy import deepcopy

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from test_history import record

from shrimpit.gui.main_window import MainWindow
from shrimpit.gui.pages.history import HistoryDetails, HistoryPage
from shrimpit.history import HistoryStore


def drain(loader):
    loader.pool.waitForDone()
    for _ in range(10):
        QApplication.processEvents()


def test_history_navigation_and_missing_previews(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    source, output = record(store, tmp_path)
    source.unlink()
    page = HistoryPage(store)
    try:
        item = page.tree.topLevelItem(0)
        item.setExpanded(True)
        drain(page.loader)
        child = item.child(0)
        assert "Image introuvable" in child.text(0)
        assert not child.icon(1).isNull()
        batch_id, entry_id = child.data(0, Qt.ItemDataRole.UserRole)
        batch, entry = page.batches_by_id[batch_id], page.entries_by_id[entry_id]
        dialog = HistoryDetails(page, batch, entry)
        drain(page.loader)
        assert not dialog.open_buttons["source"].isEnabled()
        assert dialog.open_buttons["destination"].isEnabled()
        assert dialog.previews["source"].text() == "Image introuvable"
        output.unlink()
        dialog.open_location("destination")
        assert not dialog.open_buttons["destination"].isEnabled()
        dialog.delete_button.click()
        assert store.batches() == []
        assert page.status.text() == "Aucun traitement dans l’historique"
        dialog.deleteLater()
    finally:
        page.shutdown()
        page.close()


def test_confirmation_and_immediate_batch_deletion(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    source, output = record(store, tmp_path)
    page = HistoryPage(store)
    try:
        batch = store.batches()[0]
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        page.delete_batch(batch)
        page.clear_history()
        assert page.tree.topLevelItemCount() == 1
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        page.delete_batch(batch)
        assert page.tree.topLevelItemCount() == 0
        record(store, tmp_path)
        page.reload()
        page.clear_button.click()
        assert page.tree.topLevelItemCount() == 0
        assert source.is_file() and output.is_file()
    finally:
        page.shutdown()
        page.close()


def test_navigation_and_export_integration(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    store = HistoryStore(tmp_path / "history.json")
    source, _ = record(store, tmp_path)
    store.clear()
    window = MainWindow(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat), store)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "final.jpg"), ""))
    try:
        page = window.compression
        page.add_files([source])
        page.start_export()
        deadline = time.monotonic() + 10
        while page.job and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        assert page.job is None
        assert len(store.batches()) == 1
        window.sidebar.buttons[3].click()
        assert window.stack.currentWidget().widget() is window.history
        assert window.sidebar.buttons[3].isChecked()
        assert window.history.tree.topLevelItemCount() == 1
        window.sidebar.buttons[4].click()
        assert window.stack.currentWidget().widget() is window.preferences
        assert window.sidebar.buttons[4].isChecked()
    finally:
        for page in (window.compression, window.enlargement):
            page.stop_timers()
            if page.job:
                page.job.wait()
            if page.preview_job:
                page.preview_job.wait()
        QApplication.processEvents()
        window.close()


def test_progressive_rows_ignore_pending_callbacks_after_deletion(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    record(store, tmp_path)
    batches = store.batches()
    entry = batches[0]["images"][0]
    batches[0]["images"] = [dict(deepcopy(entry), id=str(i)) for i in range(45)]
    monkeypatch.setattr(store, "batches", lambda: batches)
    page = HistoryPage(store)
    try:
        item = page.tree.topLevelItem(0)
        item.setExpanded(True)
        assert item.childCount() == 20
        deadline = time.monotonic() + 2
        while item.childCount() < 45 and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        assert item.childCount() == 45
        page.reload()
        batches.clear()
        page.reload()
        drain(page.loader)
        assert page.tree.topLevelItemCount() == 0
    finally:
        page.shutdown()
        page.close()
