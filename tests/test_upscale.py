"""Check enlargement dimensions, transparency, and output protection."""

import pytest
from PIL import Image

from shrimpit.engine import ConversionError, upscale_image


@pytest.mark.parametrize("scale", [2, 3, 4])
def test_enlargement_preserves_ratio_and_alpha(tmp_path, scale):
    source = tmp_path / "source.png"
    destination = tmp_path / "large.png"
    Image.new("RGBA", (13, 7), (40, 100, 200, 128)).save(source)
    before = source.read_bytes()
    result = upscale_image(source, destination, scale)
    with Image.open(destination) as image:
        assert image.size == (13 * scale, 7 * scale)
        assert image.getpixel((scale, scale))[3] == 128
    assert result.input_size == (13, 7)
    assert result.output_size == (13 * scale, 7 * scale)
    assert source.read_bytes() == before


@pytest.mark.parametrize("scale", [0, 1, 5, 2.5, True])
def test_invalid_scale(tmp_path, scale):
    with pytest.raises(ConversionError, match="agrandissement"):
        upscale_image(tmp_path / "unused.png", tmp_path / "out.png", scale)


def test_output_limit_checked_before_resizing(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    monkeypatch.setattr("shrimpit.limits.MAX_OUTPUT_PIXELS", 200)
    destination = tmp_path / "out.png"
    with pytest.raises(ConversionError, match="dépasserait"):
        upscale_image(source, destination, 2)
    assert not destination.exists()


def test_enlargement_applies_orientation(tmp_path):
    source = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (30, 10), "blue").save(source, exif=exif)
    destination = tmp_path / "out.png"
    result = upscale_image(source, destination)
    assert result.input_size == (10, 30)
    with Image.open(destination) as image:
        assert image.size == (20, 60)
        assert not image.getexif()


def test_enlargement_never_overwrites(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    before = source.read_bytes()
    with pytest.raises(ConversionError):
        upscale_image(source, source)
    assert source.read_bytes() == before


@pytest.mark.parametrize("fmt,extension", [("JPEG", ".jpg"), ("WEBP", ".webp")])
def test_enlargement_other_formats(tmp_path, fmt, extension):
    source = tmp_path / "source.png"
    Image.new("RGBA", (10, 20), (255, 0, 0, 0)).save(source)
    destination = tmp_path / ("out" + extension)
    upscale_image(source, destination, 2, fmt)
    with Image.open(destination) as image:
        assert image.format == fmt
        assert image.size == (20, 40)
        if fmt == "JPEG":
            assert min(image.getpixel((5, 5))) >= 250
        else:
            assert image.getpixel((5, 5))[3] == 0


def test_fast_png_keeps_pixels_and_skips_optimization(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGBA", (24, 16), (40, 100, 200, 128))
    image.paste((250, 30, 10, 255), (0, 0, 12, 8))
    image.save(source)
    optimized = upscale_image(source, tmp_path / "optimized.png", 3)
    fast = upscale_image(source, tmp_path / "fast.png", 3, fast_png=True)
    with Image.open(optimized.destination) as first, Image.open(fast.destination) as second:
        assert first.tobytes() == second.tobytes()
    assert fast.output_bytes >= optimized.output_bytes
