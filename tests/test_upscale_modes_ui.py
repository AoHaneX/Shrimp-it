"""Exercise mode selection through real preview and export workers."""

import time
from io import BytesIO

import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog

from shrimpit.gui.main_window import MainWindow
from shrimpit.processing import thumbnail


def wait_until(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert condition()


@pytest.fixture
def window(qt_application, tmp_path):
    widget = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    yield widget
    for page in (widget.compression, widget.enlargement):
        page.shutting_down = True
        page.stop_timers()
        if page.preview_job:
            assert page.preview_job.wait(10000)
        if page.job:
            assert page.job.wait(10000)
    qt_application.processEvents()
    widget.close()


def test_pixel_mode_limits_controls_and_restores_format(window):
    page = window.enlargement
    page.output.format.setCurrentText("WebP")
    page.output.factor.setCurrentIndex(3)
    page.output.upscale_controls.mode.setCurrentIndex(2)
    assert page.output.format.currentText() == "PNG"
    assert not page.output.format.isEnabled()
    assert page.output.factor.currentData() == 2
    assert not page.output.factor.model().item(3).isEnabled()
    assert page.output.custom.isHidden()
    assert page.output.upscale_controls.sharpen.isHidden()
    assert page.before.canvas.pixel_art and page.after.canvas.pixel_art
    page.output.upscale_controls.mode.setCurrentIndex(1)
    assert page.output.format.currentText() == "WebP"
    assert page.output.format.isEnabled()
    assert page.output.factor.model().item(3).isEnabled()
    assert not page.output.upscale_controls.interpolation.isHidden()
    assert not page.after.canvas.pixel_art
    assert window.compression.output.upscale_controls.isHidden()
    assert window.compression.output.format.currentText() == "JPEG"


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_mode_used_by_preview_and_batch_export(window, qt_application, tmp_path, monkeypatch, mode):
    page = window.enlargement
    page.output.upscale_controls.mode.setCurrentIndex(mode)
    page.output.factor.setCurrentIndex(1)
    sources = []
    for i in range(2):
        path = tmp_path / f"source-{i}.png"
        image = Image.new("RGBA", (8, 6), (255, 0, 0, 0))
        image.putpixel((3, 2), (10, 100, 220, 255))
        image.save(path)
        sources.append(path)
    page.add_files(sources)
    wait_until(qt_application, lambda: page.preview_payload is not None and page.preview_job is None)
    preview = page.preview_payload[1]
    folder = tmp_path / "export"
    folder.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(folder))
    page.start_export()
    wait_until(qt_application, lambda: page.job is None)
    assert page.last_export["successes"] == 2
    assert not page.last_export["errors"]
    target = folder / "source-1-x3.png"
    assert preview == thumbnail(target, pixel_art=mode == 2)
    with Image.open(target) as output:
        assert output.size == (24, 18)
        if mode == 2:
            assert output.getpixel((9, 6)) == (10, 100, 220, 255)
            assert output.getpixel((8, 6)) == (255, 0, 0, 0)
    assert page.output.format.isEnabled() == (mode != 2)


def test_sharpness_controls_trigger_new_preview(window, qt_application, tmp_path):
    page = window.enlargement
    source = tmp_path / "source.png"
    image = Image.new("RGB", (16, 16), (60, 60, 60))
    image.paste((180, 180, 180), (8, 0, 16, 16))
    image.save(source)
    page.add_files([source])
    wait_until(qt_application, lambda: page.preview_payload is not None and page.preview_job is None)
    sharpened = page.preview_payload[1]
    page.output.upscale_controls.sharpen.setChecked(False)
    wait_until(qt_application, lambda: page.preview_payload is not None and page.preview_job is None)
    plain = page.preview_payload[1]
    with Image.open(BytesIO(sharpened)) as first, Image.open(BytesIO(plain)) as second:
        assert first.tobytes() != second.tobytes()
    assert page.output.upscale_controls.amount.isHidden()
