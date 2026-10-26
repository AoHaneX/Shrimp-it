"""Verify shared export names, validation, and collision handling."""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QFileDialog

from shrimpit.errors import ConversionError
from shrimpit.gui.pages.processing import ProcessingPage
from shrimpit.processing import expand_name_template


@pytest.mark.parametrize(
    "template", ["../[original name].jpg", "[nom].jpg", "CON.jpg", "[original name].png", ""]
)
def test_invalid_template_is_rejected(template):
    with pytest.raises(ConversionError):
        expand_name_template(Path("photo.png"), template, "JPEG")


def test_template_keeps_dots_accents_and_literal_brackets_in_source():
    assert (
        expand_name_template(Path("été.[1].photo.png"), "web-[original name]-min.jpg", "JPEG")
        == "web-été.[1].photo-min.jpg"
    )


def test_default_model_is_visible_before_import_and_tracks_factor(qt_application):
    page = ProcessingPage(enlarge=True)
    try:
        assert page.output.filename.text() == "[original name]-x2.png"
        page.output.factor.setCurrentIndex(2)
        assert page.output.filename.text() == "[original name]-x4.png"
        page.output.format.setCurrentText("JPEG")
        assert page.output.filename.text() == "[original name]-x4.jpg"
        page.output.filename.setText("web-[original name]-final.jpg")
        page.output.store_name()
        page.output.factor.setCurrentIndex(0)
        assert page.output.filename.text() == "web-[original name]-final.jpg"
    finally:
        page.stop_timers()
        page.close()


def test_default_custom_dimensions_are_resolved_per_image(tmp_path, qt_application):
    page = ProcessingPage(enlarge=True)
    sources = [tmp_path / "wide.png", tmp_path / "square.png"]
    for source, size in zip(sources, [(20, 10), (10, 10)]):
        Image.new("RGB", size).save(source)
    try:
        page.add_files(sources)
        page.output.factor.setCurrentIndex(3)
        page.output.width_input.setValue(80)
        assert page.output_name(sources[0]) == "wide-80x40.png"
        assert page.output_name(sources[1]) == "square-80x80.png"
        page.clear_images()
        assert page.output.filename.text().startswith("[original name]")
    finally:
        page.stop_timers()
        page.close()


@pytest.mark.parametrize("enlarge", [False, True])
def test_shared_template_exports_all_files_and_survives_selection(
    tmp_path, monkeypatch, qt_application, enlarge
):
    page = ProcessingPage(enlarge=enlarge)
    sources = [tmp_path / "été.png", tmp_path / "mer.png"]
    for source in sources:
        Image.new("RGB", (12, 8), "blue").save(source)
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "web-été-final.png"
    existing.write_bytes(b"keep me")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(output))
    try:
        page.add_files(sources)
        page.output.format.setCurrentText("PNG")
        assert page.output.filename.text().startswith("[original name]")
        page.output.filename.setText("web-[original name]-final.png")
        page.output.store_name()
        page.files.setCurrentRow(0)
        assert page.output.filename.text() == "web-[original name]-final.png"
        assert "web-été-final.png" in page.output.name_example.text()
        page.output.format.setCurrentText("WebP")
        assert page.output.filename.text() == "web-[original name]-final.webp"
        page.output.format.setCurrentText("PNG")
        page.start_export()
        assert page.job is not None
        assert page.job.wait(10000)
        qt_application.processEvents()
        assert page.last_export["successes"] == 2
        assert not page.last_export["errors"]
        assert existing.read_bytes() == b"keep me"
        assert (output / "web-été-final-2.png").is_file()
        assert (output / "web-mer-final.png").is_file()
        assert all(source.is_file() for source in sources)
    finally:
        page.shutting_down = True
        page.stop_timers()
        for job in (page.job, page.preview_job):
            if job:
                job.requestInterruption()
                assert job.wait(10000)
        qt_application.processEvents()
        page.close()
