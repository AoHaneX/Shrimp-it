"""Validate custom dimensions, output planning, and batch failures."""

from pathlib import Path
from threading import Event

import pytest
from PIL import Image

from shrimpit.engine import ConversionError, upscale_image
from shrimpit.gui.workers import ExportJob
from shrimpit.processing import Options, export_plan, readable_size, suggested_name


@pytest.mark.parametrize("size", [(0, 10), (10, -1), (True, 20), (2.5, 10), [20, 20], (20,)])
def test_invalid_custom_dimensions(tmp_path, size):
    with pytest.raises(ConversionError):
        upscale_image(tmp_path / "source.png", tmp_path / "out.png", size=size)


def test_custom_size_and_orientation(tmp_path):
    source = tmp_path / "source.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (40, 20)).save(source, exif=exif)
    result = upscale_image(source, tmp_path / "out.png", size=(60, 120))
    assert result.input_size == (20, 40)
    assert result.output_size == (60, 120)


@pytest.mark.parametrize("size", [(20, 20), (10, 40), (21000, 21000)])
def test_custom_size_rejects_shrinking_or_oversize(tmp_path, size):
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20)).save(source)
    with pytest.raises(ConversionError):
        upscale_image(source, tmp_path / "out.png", size=size)
    assert not (tmp_path / "out.png").exists()


def test_batch_continues_after_failure(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20), "blue").save(source)
    good = tmp_path / "good.jpg"
    job = ExportJob([(tmp_path / "missing.png", tmp_path / "bad.jpg"), (source, good)], Options())
    job.run()
    assert job.successes == 1
    assert len(job.errors) == 1
    assert job.completed == 2
    assert good.exists()


@pytest.mark.parametrize("name", ["../out.jpg", "out.png", "", "a/b.jpg"])
def test_batch_rejects_invalid_names(tmp_path, name):
    source = tmp_path / "image.png"
    with pytest.raises(ConversionError):
        export_plan([source], tmp_path, {source: name}, Options())


def test_names_keep_stem_and_selected_extension():
    source = Path("vacances.été.png")
    assert suggested_name(source, Options()) == "vacances.été-min.jpg"
    assert suggested_name(source, Options(True, "PNG", size=(100, 200))) == "vacances.été-100x200.png"


def test_batch_cancel_finishes_current_image(tmp_path, monkeypatch):
    started, release = Event(), Event()
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    from shrimpit.gui import workers

    original_process = workers.process

    def waiting_process(*args):
        started.set()
        assert release.wait(5)
        return original_process(*args)

    monkeypatch.setattr(workers, "process", waiting_process)
    first, second = tmp_path / "first.jpg", tmp_path / "second.jpg"
    job = ExportJob([(source, first), (source, second)], Options())
    job.start()
    try:
        assert started.wait(5)
        job.requestInterruption()
    finally:
        release.set()
        assert job.wait(5000)
    assert first.exists()
    assert not second.exists()
    assert job.completed == 1
    assert job.successes == 1


@pytest.mark.parametrize(
    "count,text", [(999, "1,0 Ko"), (999_949, "999,9 Ko"), (999_999, "1,00 Mo"), (2_500_000, "2,50 Mo")]
)
def test_readable_size_never_shows_a_thousand_kilobytes(count, text):
    assert readable_size(count) == text
