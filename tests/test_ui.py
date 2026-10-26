"""Exercise navigation, previews, imports, and exports with real Qt workers."""

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from shrimpit.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, condition):
    deadline = time.monotonic() + 15
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert condition()


@pytest.fixture
def window(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = MainWindow(settings)
    widget.show()
    app.processEvents()
    yield widget
    for page in (widget.compression, widget.enlargement):
        page.stop_timers()
        if page.job:
            page.job.wait(15000)
        if page.preview_job:
            page.preview_job.wait(15000)
    app.processEvents()
    for page in (widget.compression, widget.enlargement):
        page.stop_timers()
    widget.close()
    app.processEvents()


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "été.photo.png"
    Image.new("RGBA", (40, 20), (30, 150, 220, 128)).save(path)
    return path


def test_navigation_and_animated_sidebar(app, window):
    assert window.stack.currentIndex() == 0
    window.sidebar.buttons[1].click()
    assert window.stack.currentIndex() == 1
    window.sidebar.menu.click()
    wait_for(app, lambda: window.sidebar.width() == 68)
    assert window.sidebar.buttons[1].toolTip() == "Compression"
    window.sidebar.buttons[2].click()
    assert window.stack.currentIndex() == 2
    window.sidebar.menu.click()
    wait_for(app, lambda: window.sidebar.width() == 320)
    assert window.sidebar.brand.isVisible()


def test_actual_drag_and_drop(app, window, source):
    window.navigate(1)
    page = window.compression
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    enter = QDragEnterEvent(
        QPoint(12, 12),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(page.drop_zone, enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(12, 12),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(page.drop_zone, drop)
    assert drop.isAccepted()
    assert page.sources == [source]


def test_compression_preview_and_save(app, window, source, tmp_path, monkeypatch):
    page = window.compression
    destination = tmp_path / "été.photo-min.jpg"
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(source)], ""))

    def save_dialog(parent, title, suggestion, *args, **kwargs):
        assert Path(suggestion) == destination
        return str(destination), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", save_dialog)
    page.choose_files()
    wait_for(app, lambda: page.preview_payload is not None and page.preview_job is None)
    assert not page.before.canvas.pixmap.isNull()
    assert not page.after.canvas.pixmap.isNull()
    assert not destination.exists()
    page.export.click()
    assert not page.drop_zone.isEnabled()
    wait_for(app, lambda: page.job is None)
    assert destination.exists()
    assert "1 image(s) enregistrée(s)" in page.status.text()
    assert page.export.isEnabled()


def test_batch_export_and_collision(app, window, source, tmp_path, monkeypatch):
    page = window.compression
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    second = other_dir / source.name
    second.write_bytes(source.read_bytes())
    folder = tmp_path / "export"
    folder.mkdir()
    existing = folder / "été.photo-min.jpg"
    existing.write_bytes(b"preserve")
    page.add_files([source, second])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    page.start_export()
    wait_for(app, lambda: page.job is None)
    assert existing.read_bytes() == b"preserve"
    assert (folder / "été.photo-min-2.jpg").exists()
    assert (folder / "été.photo-min-3.jpg").exists()
    assert "2 image(s) enregistrée(s)" in page.status.text()


def test_custom_dimensions_and_ratio(app, window, source, tmp_path, monkeypatch):
    page = window.enlargement
    page.add_files([source])
    page.output.factor.setCurrentIndex(3)
    page.output.width_input.setValue(120)
    assert page.output.height_input.value() == 60
    destination = tmp_path / "custom.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destination), ""))
    page.start_export()
    wait_for(app, lambda: page.job is None)
    with Image.open(destination) as image:
        assert image.size == (120, 60)
    assert "120x60" in page.output.filename.text()


def test_corrupt_import_and_duplicate_filter(window, source, tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"invalid")
    window.navigate(1)
    window.compression.add_files([broken])
    assert not window.compression.sources
    assert not window.compression.export.isEnabled()
    assert window.compression.import_errors.isVisible()
    assert "broken.png" in window.compression.import_errors.text()
    window.compression.add_files([source])
    assert not window.compression.import_errors.isVisible()
    window.enlargement.add_files([source, source])
    assert window.enlargement.sources == [source]


def test_preview_uses_latest_settings(app, window, source):
    page = window.enlargement
    page.add_files([source])
    page.start_preview()
    page.output.factor.setCurrentIndex(2)
    wait_for(app, lambda: page.preview_payload is not None and page.preview_job is None)
    assert page.preview_payload[2].output_size == (160, 80)


def test_export_error_restores_controls(app, window, source, tmp_path, monkeypatch):
    page = window.compression
    vanished = tmp_path / "vanished.jpg"
    vanished.write_bytes(source.read_bytes())
    page.add_files([vanished])
    vanished.unlink()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "out.jpg"), ""))
    page.start_export()
    wait_for(app, lambda: page.job is None)
    assert "1 erreur(s)" in page.status.text()
    assert "Fichier ou dossier introuvable" in page.status.text()
    assert page.export.isEnabled()
    assert page.drop_zone.isEnabled()


@pytest.mark.parametrize("chosen", ["source", "wrong_extension"])
def test_single_export_refused_before_start(window, source, tmp_path, monkeypatch, chosen):
    page = window.compression
    page.add_files([source])
    page.output.format.setCurrentText("PNG")
    target = source if chosen == "source" else tmp_path / "result.jpg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    before = source.read_bytes()
    page.start_export()
    assert page.job is None
    assert window.stack.currentIndex() != 4
    assert page.status.text().startswith("Échec")
    assert source.read_bytes() == before
    assert not (tmp_path / "result.jpg").exists()


@pytest.mark.parametrize("size", [(1360, 960), (760, 560)])
def test_export_bar_stays_visible_without_scrolling(app, window, source, size):
    window.navigate(2)
    window.resize(*size)
    window.enlargement.add_files([source])
    app.processEvents()
    button = window.enlargement.export
    bottom = button.mapTo(window, button.rect().bottomLeft()).y()
    assert button.isVisible()
    assert bottom <= window.height()


def test_batch_list_shows_several_rows(window):
    assert window.compression.files.maximumHeight() >= 5 * 28


def test_cancelled_file_dialog_writes_nothing(window, source, monkeypatch):
    page = window.compression
    page.add_files([source])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    page.start_export()
    assert page.job is None
    assert window.stack.currentIndex() != 4
    assert "1 image(s) prête(s)" in page.status.text()


def test_settings_persist(window):
    window.preferences.quality.setValue(72)
    window.preferences.scale.setCurrentIndex(2)
    window.preferences.animation.setChecked(False)
    window.settings.sync()
    assert int(window.settings.value("quality")) == 72
    assert int(window.settings.value("scale")) == 4
    assert window.sidebar.animation.duration() == 0
