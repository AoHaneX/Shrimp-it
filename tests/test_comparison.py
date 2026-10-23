"""Check preview geometry, interaction, sample lifecycle, and pixel isolation."""

from io import BytesIO

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from shrimpit.examples import example_preview
from shrimpit.gui.comparison import ComparisonPreview
from shrimpit.gui.pages.processing import ProcessingPage


def pixmap(color, width=120, height=80):
    result = QPixmap(width, height)
    result.fill(QColor(color))
    return result


def comparison():
    preview = ComparisonPreview()
    preview.resize(620, 450)
    preview.display(pixmap("red"), pixmap("blue", 240, 160), (120, 80), (240, 160), "original", "result")
    preview.show()
    QApplication.processEvents()
    return preview


@pytest.mark.parametrize("size", [(120, 80), (80, 120), (600, 60)])
def test_same_frame_for_different_resolutions(size):
    preview = comparison()
    try:
        double = tuple(value * 2 for value in size)
        preview.display(pixmap("red", *size), pixmap("blue", *double), size, double, "", "")
        for width, height in [(420, 320), (920, 680)]:
            preview.resize(width, height)
            QApplication.processEvents()
            canvas = preview.canvas
            before = canvas.image_rect(canvas.before_size)
            after = canvas.image_rect(canvas.after_size)
            assert before == after
            assert before.width() / before.height() == pytest.approx(size[0] / size[1])
            assert not preview.ratio_note.isVisible()
    finally:
        preview.close()


def test_changed_aspect_ratio_is_centered_without_stretching():
    preview = comparison()
    try:
        preview.display(pixmap("red"), pixmap("blue"), (120, 80), (160, 160), "", "")
        before = preview.canvas.image_rect(preview.canvas.before_size)
        after = preview.canvas.image_rect(preview.canvas.after_size)
        assert before.center() == after.center()
        assert after.width() == pytest.approx(after.height())
        assert preview.ratio_note.isVisible()
    finally:
        preview.close()


def test_slider_reveals_pixels_and_preserves_pixmaps():
    preview = comparison()
    try:
        canvas = preview.canvas
        before = canvas.before.toImage()
        after = canvas.after.toImage()
        frame = canvas.image_rect(canvas.before_size)
        x1, x2 = int(frame.left() + frame.width() * 0.25), int(frame.left() + frame.width() * 0.75)
        y = int(frame.top() + frame.height() * 0.2)
        image = canvas.grab().toImage()
        assert image.pixelColor(x1, y) == QColor("red")
        assert image.pixelColor(x2, y) == QColor("blue")
        preview.slider.setValue(0)
        assert canvas.grab().toImage().pixelColor(x1, y) == QColor("blue")
        preview.slider.setValue(100)
        assert canvas.grab().toImage().pixelColor(x2, y) == QColor("red")
        assert canvas.before.toImage() == before
        assert canvas.after.toImage() == after
    finally:
        preview.close()


def test_drag_keyboard_and_slider_stay_synchronized():
    preview = comparison()
    try:
        canvas = preview.canvas
        frame = canvas.image_rect(canvas.before_size)
        point = QPoint(int(frame.left() + frame.width() * 0.25), int(frame.center().y()))
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=point)
        end = QPointF(frame.left() + frame.width() * 0.75, frame.center().y())
        event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            end,
            end,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(canvas, event)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end.toPoint())
        assert preview.slider.value() == 75
        QTest.keyClick(canvas, Qt.Key.Key_Left)
        assert preview.slider.value() == 74
        QTest.keyClick(canvas, Qt.Key.Key_Home)
        assert preview.slider.value() == 0
        QTest.keyClick(canvas, Qt.Key.Key_End)
        assert preview.slider.value() == 100
        canvas.move_divider(-100)
        assert preview.slider.value() == 0
    finally:
        preview.close()


@pytest.mark.parametrize("enlarge", [False, True])
def test_samples_replace_restore_and_never_become_exports(tmp_path, enlarge):
    page = ProcessingPage(enlarge=enlarge)
    try:
        sample_key = page.before.canvas.pixmap.toImage()
        assert not page.comparison.canvas.before.isNull()
        assert not page.comparison.canvas.after.isNull()
        assert "Exemple" in page.preview_status.text()
        assert page.sources == [] and page.preview_payload is None
        assert not page.export.isEnabled()
        path = tmp_path / "user.png"
        Image.new("RGB", (60, 40), "red").save(path)
        original = path.read_bytes()
        page.add_files([path])
        page.stop_timers()
        revision = page.revision
        assert page.comparison.canvas.before.isNull()
        assert page.comparison.canvas.after.isNull()
        page.preview_original(revision, original)
        assert page.comparison.canvas.before.toImage() != sample_key
        assert not page.comparison.slider.isEnabled()
        page.preview_failed(revision, "Example failure")
        assert page.comparison.canvas.after.isNull()
        page.remove_selected()
        assert page.before.canvas.pixmap.toImage() == sample_key
        assert page.comparison.slider.isEnabled()
        page.preview_original(revision, original)
        assert page.before.canvas.pixmap.toImage() == sample_key
        page.preview_toggle.click()
        assert page.preview_stack.currentIndex() == 1
        page.preview_toggle.click()
        assert page.preview_stack.currentIndex() == 0
        assert path.read_bytes() == original
        assert not page.export.isEnabled()
    finally:
        page.stop_timers()
        page.close()


def test_sample_files_match_real_dimensions_and_formats():
    for enlarge in (False, True):
        before, after, original, result = example_preview(enlarge)
        for thumbnail in (before, after):
            with Image.open(BytesIO(thumbnail)) as image:
                assert image.width <= 640 and image.height <= 420
        assert (
            result.size == tuple(value * 2 for value in original.size)
            if enlarge
            else result.size == original.size
        )
        assert result.format == ("PNG" if enlarge else "JPEG")


def test_missing_samples_do_not_prevent_import(tmp_path, monkeypatch):
    def fail(*args):
        raise FileNotFoundError("Missing example")

    monkeypatch.setattr("shrimpit.gui.pages.processing.example_preview", fail)
    page = ProcessingPage()
    try:
        assert "Exemple indisponible" in page.preview_status.text()
        source = tmp_path / "source.png"
        Image.new("RGB", (12, 12), "blue").save(source)
        page.add_files([source])
        page.stop_timers()
        assert page.export.isEnabled()
    finally:
        page.stop_timers()
        page.close()


def test_empty_loading_canvas_renders_without_dimensions():
    preview = comparison()
    try:
        preview.display(QPixmap(), QPixmap(), (0, 0), (0, 0), "—", "—")
        assert not preview.canvas.grab().isNull()
        assert not preview.slider.isEnabled()
    finally:
        preview.close()
