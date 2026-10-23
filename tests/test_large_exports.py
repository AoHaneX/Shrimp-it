"""Validate large-export guards without allocating huge images in unit tests."""

import pytest
from PIL import Image

from shrimpit.engine import ConversionError, upscale_image
from shrimpit.gui.workers import PreviewJob
from shrimpit.limits import check_export_memory, check_output_size
from shrimpit.processing import Options
from shrimpit.upscale import UpscaleSettings


@pytest.mark.parametrize("size", [(12000, 16000), (20000, 20000)])
def test_large_png_dimensions_are_allowed(size):
    check_output_size(size, "PNG")


def test_output_cap_reports_requested_dimensions():
    with pytest.raises(ConversionError, match="20001 × 20000"):
        check_output_size((20001, 20000), "PNG")


def test_webp_side_limit_is_separate_from_pixel_count():
    check_output_size((16383, 16383), "WEBP")
    with pytest.raises(ConversionError, match="16 383"):
        check_output_size((16384, 1000), "WEBP")


@pytest.mark.parametrize("mode", ["photo", "illustration", "pixel_art"])
def test_large_exports_require_memory_headroom(monkeypatch, mode):
    monkeypatch.setattr("shrimpit.limits.available_memory_bytes", lambda: 1024**3)
    with pytest.raises(ConversionError, match="RAM disponibles"):
        check_export_memory((4000, 3000), (16000, 12000), UpscaleSettings(mode=mode))
    monkeypatch.setattr("shrimpit.limits.available_memory_bytes", lambda: 24 * 1024**3)
    check_export_memory((4000, 3000), (16000, 12000), UpscaleSettings(mode=mode))


def test_unknown_memory_keeps_small_exports_available(monkeypatch):
    monkeypatch.setattr("shrimpit.limits.available_memory_bytes", lambda: None)
    check_export_memory((10, 10), (100, 100), UpscaleSettings())
    with pytest.raises(ConversionError, match="impossible à vérifier"):
        check_export_memory((4000, 3000), (16000, 12000), UpscaleSettings())


def test_large_size_reaches_resizer_with_enough_memory(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    monkeypatch.setattr("shrimpit.limits.available_memory_bytes", lambda: 32 * 1024**3)
    calls = []

    def stop_before_allocation(image, size, settings):
        calls.append(size)
        raise MemoryError("Stop the simulated large allocation")

    monkeypatch.setattr("shrimpit.engine.resize_image", stop_before_allocation)
    with pytest.raises(ConversionError, match="Mémoire insuffisante"):
        upscale_image(source, tmp_path / "out.png", size=(16000, 12000))
    assert calls == [(16000, 12000)]
    assert not (tmp_path / "out.png").exists()


def test_memory_rejection_happens_before_decode(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    monkeypatch.setattr("shrimpit.limits.available_memory_bytes", lambda: 0)

    def unexpected_decode(*args, **kwargs):
        pytest.fail("Large export must be rejected before decoding")

    monkeypatch.setattr("shrimpit.engine.ImageOps.exif_transpose", unexpected_decode)
    with pytest.raises(ConversionError, match="RAM disponibles"):
        upscale_image(source, tmp_path / "out.png", size=(6000, 6000))
    assert not (tmp_path / "out.png").exists()


def test_large_preview_keeps_original_without_processing_full_output(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)

    def unexpected_export(*args, **kwargs):
        pytest.fail("Large preview must not compute the full export")

    monkeypatch.setattr("shrimpit.gui.workers.process", unexpected_export)
    job = PreviewJob(source, Options(enlarge=True, output_format="PNG", size=(16000, 12000)), 7)
    originals, messages = [], []
    job.original_ready.connect(lambda revision, data: originals.append((revision, data)))
    job.failed.connect(lambda revision, message: messages.append(message))
    job.run()
    assert originals[0][0] == 7
    assert "192.0 MP" in messages[0]
    assert "Agrandir et enregistrer" in messages[0]
    assert "ERROR" not in messages[0]
