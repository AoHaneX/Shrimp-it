"""Regression checks for failures found during the desktop audit."""

import logging
import time
from threading import Event

import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox

from shrimpit.diagnostics import configure_logging
from shrimpit.engine import ConversionError, convert_image
from shrimpit.filenames import validate_filename
from shrimpit.gui.main_window import MainWindow
from shrimpit.processing import Options, export_plan


def wait_for(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert condition()


@pytest.fixture
def window(tmp_path, qt_application):
    value = MainWindow(QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat))
    value.show()
    yield value
    for page in (value.compression, value.enlargement):
        page.shutting_down = True
        page.stop_timers()
        for job in (page.job, page.preview_job):
            if job:
                job.requestInterruption()
                assert job.wait(10000)
    qt_application.processEvents()
    value.close()
    qt_application.processEvents()


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "photo.png"
    Image.new("RGBA", (20, 10), (10, 100, 200, 90)).save(path)
    return path


@pytest.mark.parametrize(
    "name",
    [
        "CON.jpg",
        "nul.png",
        "COM1.webp",
        "LPT².png",
        "PRN.backup.png",
        "foo.jpg ",
        "foo.jpg.",
        "a\x01.png",
        "x" * 252 + ".png",
    ],
)
def test_windows_names_rejected_before_writing(tmp_path, source, name):
    with pytest.raises(ConversionError):
        validate_filename(name)
    with pytest.raises(ConversionError):
        export_plan([source], tmp_path, {source: name}, Options(output_format="PNG"))


def test_export_does_not_reopen_source_just_to_use_explicit_name(tmp_path):
    missing = tmp_path / "missing.png"
    options = Options(True, "PNG", size=(100, 100), keep_ratio=True)
    assert export_plan([missing], tmp_path, {missing: "chosen.png"}, options)[0][1].name == "chosen.png"


def test_memory_failure_removes_partial_output(tmp_path, source, monkeypatch):
    def fail(self, stream, **kwargs):
        stream.write(b"partial")
        raise MemoryError()

    monkeypatch.setattr(Image.Image, "save", fail)
    destination = tmp_path / "out.png"
    with pytest.raises(ConversionError, match="Mémoire insuffisante"):
        convert_image(source, destination, "PNG")
    assert not destination.exists()
    assert source.exists()


def test_corrupt_preferences_do_not_prevent_startup(tmp_path, qt_application):
    settings = QSettings(str(tmp_path / "broken.ini"), QSettings.Format.IniFormat)
    for key in ("quality", "scale", "animation", "sound", "notifications"):
        settings.setValue(key, "invalid")
    window = MainWindow(settings)
    try:
        assert window.compression.output.quality.value() == 80
        assert window.enlargement.output.factor.currentData() == 2
        assert window.preferences.sound.isChecked()
        assert window.notifier.player is None
    finally:
        window.close()


def test_custom_name_survives_format_and_factor_changes(window, source):
    page = window.enlargement
    page.add_files([source])
    page.output.filename.setText("portfolio.png")
    page.output.store_name()
    page.output.factor.setCurrentIndex(2)
    assert page.output.filename.text() == "portfolio.png"
    page.output.format.setCurrentText("WebP")
    assert page.output.filename.text() == "portfolio.webp"
    page.output.filename.setText(".")
    page.output.store_name()
    page.output.factor.setCurrentIndex(0)
    assert page.output.filename.text() == "."


def test_deleted_source_does_not_break_custom_dimension_controls(window, source):
    page = window.enlargement
    page.add_files([source])
    source.unlink()
    page.output.factor.setCurrentIndex(3)
    page.output.width_input.setValue(80)
    assert "80x40" in page.output.filename.text()


def test_clear_list_discards_pending_preview(window, source, qt_application):
    page = window.compression
    page.add_files([source])
    page.start_preview()
    page.clear.click()
    wait_for(qt_application, lambda: page.preview_job is None)
    assert page.source is None
    assert page.preview_payload is None
    assert not page.export.isEnabled()
    assert source.exists()


def test_sound_and_notifications_can_be_disabled_live(window, quiet_notifications):
    service = window.notifier
    window.preferences.sound.setChecked(False)
    window.preferences.notifications.setChecked(False)
    service.finished(dict(total=1, completed=1, successes=1, errors=[]))
    quiet_notifications["sound"].assert_not_called()
    quiet_notifications["message"].assert_not_called()
    assert service.player is None
    window.preferences.sound.setChecked(True)
    service.finished(dict(total=1, completed=1, successes=1, errors=[]))
    quiet_notifications["sound"].assert_called_once()


@pytest.mark.parametrize("export", [False, True])
def test_close_waits_for_worker_and_then_closes(
    window, source, tmp_path, monkeypatch, qt_application, export
):
    from shrimpit.gui import workers

    started, release = Event(), Event()
    original = workers.process if export else workers.thumbnail

    def slow(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(workers, "process" if export else "thumbnail", slow)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "out.jpg"), ""))
    page = window.compression
    page.add_files([source])
    page.stop_timers()
    if export:
        page.start_export()
    else:
        page.start_preview()
    try:
        assert started.wait(5)
        window.close()
        assert window.close_pending
        assert window.isVisible()
    finally:
        release.set()
    wait_for(qt_application, lambda: not window.isVisible())
    assert not page.running()
    assert not page.preview_timer.isActive()
    if export:
        assert (tmp_path / "out.jpg").is_file()


def test_logs_are_local_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    logger = logging.getLogger("shrimpit")
    old_handlers = logger.handlers[:]
    logger.handlers.clear()
    try:
        folder = configure_logging()
        logger.error("Simulated export failure")
        assert "Simulated export failure" in (folder / "shrimpit.log").read_text(encoding="utf-8")
        assert logger.handlers[0].maxBytes == 1_000_000
        assert logger.handlers[0].backupCount == 2
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers[:] = old_handlers
