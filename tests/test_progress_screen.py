"""Check animated exports, result access, and bundled asset paths."""

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QApplication, QFileDialog

from shrimpit.gui.main_window import MainWindow
from shrimpit.gui.workers import ExportJob
from shrimpit.processing import Options, export_plan
from shrimpit.resources import BACKGROUND, PROCESSING_ANIMATIONS, SHRIMPY_ICON, SIDEBAR_MASCOT, TITLE_FONT


def test_packaged_assets():
    for path in (BACKGROUND, SIDEBAR_MASCOT, SHRIMPY_ICON, TITLE_FONT, *PROCESSING_ANIMATIONS.values()):
        assert path.is_file()
    app = QApplication.instance() or QApplication([])
    for path in PROCESSING_ANIMATIONS.values():
        movie = QMovie(str(path))
        assert movie.isValid()
        assert movie.frameCount() > 1
        movie.start()
        app.processEvents()
        assert not movie.currentPixmap().isNull()
        movie.stop()


def test_export_screen_and_open_results(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat))
    page = window.enlargement
    folder = tmp_path / "results"
    folder.mkdir()
    sources = []
    for index, size in enumerate([(20, 10), (10, 20)]):
        path = tmp_path / f"image{index}.png"
        Image.new("RGB", size, "blue").save(path)
        sources.append(path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    opened = []
    monkeypatch.setattr(
        "shrimpit.gui.pages.progress.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    try:
        window.show()
        page.add_files(sources)
        page.start_export()
        assert window.stack.currentIndex() == 4
        assert window.processing.running
        assert window.processing.movie.state() == QMovie.MovieState.Running
        deadline = time.monotonic() + 10
        while page.job and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert page.job is None
        assert not window.processing.running
        assert window.processing.movie.state() == QMovie.MovieState.NotRunning
        assert "2 image(s)" in window.processing.current_file.text()
        assert len(list(folder.glob("*.png"))) == 2
        window.processing.open_folder.click()
        assert [Path(path) for path in opened] == [folder]
        window.processing.back.click()
        assert window.stack.currentIndex() == 2
        assert window.sidebar.logo.pixmap() is not None
        scaled = window.sidebar._scaled
        original = window.sidebar.background
        assert abs(scaled.width() / scaled.height() - original.width() / original.height()) < 0.003
    finally:
        for p in (window.compression, window.enlargement):
            p.stop_timers()
            if p.job:
                p.job.wait(10000)
            if p.preview_job:
                p.preview_job.wait(10000)
        app.processEvents()
        for p in (window.compression, window.enlargement):
            p.stop_timers()
        window.close()


def test_mixed_ratio_batch_custom_dimensions(tmp_path):
    sources = []
    for index, size in enumerate([(40, 20), (20, 40)]):
        path = tmp_path / f"image{index}.png"
        Image.new("RGBA", size, (10, 100, 200, 128)).save(path)
        sources.append(path)
    options = Options(True, "PNG", size=(80, 40), keep_ratio=True)
    plan = export_plan(sources, tmp_path, {}, options)
    job = ExportJob(plan, options)
    job.run()
    assert job.successes == 2
    for (_, destination), size in zip(plan, [(80, 40), (80, 160)]):
        with Image.open(destination) as image:
            assert image.size == size
            assert image.getpixel((0, 0))[3] == 128
        assert f"{size[0]}x{size[1]}" in destination.name
