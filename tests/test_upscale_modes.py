"""Verify enlargement modes, alpha safety, and parameter validation."""

from dataclasses import replace

import pytest
from PIL import Image, ImageDraw, ImageFilter

from shrimpit.engine import ConversionError, upscale_image
from shrimpit.upscale import UpscaleSettings


@pytest.fixture
def source(tmp_path):
    image = Image.new("RGBA", (24, 16), (255, 0, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 3, 19, 12), fill=(0, 200, 0, 255))
    draw.rectangle((10, 5, 16, 10), fill=(0, 70, 0, 255))
    image.putpixel((3, 3), (0, 180, 0, 128))
    path = tmp_path / "source.png"
    image.save(path)
    return path


@pytest.mark.parametrize("scale", [2, 3, 4])
@pytest.mark.parametrize("mode", ["RGBA", "RGB", "P", "L"])
def test_pixel_art_repeats_exact_pixels(tmp_path, scale, mode):
    source = tmp_path / "pixels.png"
    image = Image.new("RGBA", (3, 2))
    image.putdata([(255, 0, 0, 0), (50, 90, 180, 128), (0, 255, 0, 255)] * 2)
    if mode == "P":
        image = image.quantize(colors=3)
    else:
        image = image.convert(mode)
    image.save(source)
    before = source.read_bytes()
    target = tmp_path / "out.png"
    upscale_image(source, target, scale, settings=UpscaleSettings(mode="pixel_art"))
    with Image.open(source) as original, Image.open(target) as output:
        original = original.convert("RGBA")
        output = output.convert("RGBA")
        assert output.size == (3 * scale, 2 * scale)
        for y in range(output.height):
            for x in range(output.width):
                assert output.getpixel((x, y)) == original.getpixel((x // scale, y // scale))
    assert source.read_bytes() == before


@pytest.mark.parametrize("format,extension", [("JPEG", "jpg"), ("WEBP", "webp")])
def test_pixel_art_refuses_lossy_exports(source, tmp_path, format, extension):
    target = tmp_path / f"out.{extension}"
    with pytest.raises(ConversionError, match="Pixel Art"):
        upscale_image(source, target, output_format=format, settings=UpscaleSettings(mode="pixel_art"))
    assert not target.exists()


def test_pixel_art_refuses_custom_dimensions(source, tmp_path):
    with pytest.raises(ConversionError, match="Pixel Art"):
        upscale_image(source, tmp_path / "out.png", size=(60, 40), settings=UpscaleSettings(mode="pixel_art"))


@pytest.mark.parametrize("mode", ["pixel_art", "illustration"])
def test_non_photo_modes_never_sharpen(source, tmp_path, monkeypatch, mode):
    def forbidden(*args, **kwargs):
        pytest.fail("Sharpening must only be used for photos")

    monkeypatch.setattr(ImageFilter, "UnsharpMask", forbidden)
    upscale_image(source, tmp_path / "out.png", settings=UpscaleSettings(mode=mode))


def test_photo_sharpening_changes_detail_but_preserves_alpha(source, tmp_path):
    plain, sharp = tmp_path / "plain.png", tmp_path / "sharp.png"
    upscale_image(source, plain, 4, settings=UpscaleSettings(sharpen=False))
    upscale_image(source, sharp, 4)
    with Image.open(plain) as original, Image.open(sharp) as enhanced:
        assert enhanced.getchannel("A").tobytes() == original.getchannel("A").tobytes()
        assert enhanced.tobytes() != original.tobytes()
        for y in range(original.height):
            for x in range(original.width):
                if original.getpixel((x, y))[3] < 255:
                    assert enhanced.getpixel((x, y)) == original.getpixel((x, y))


@pytest.mark.parametrize("filter", ["bicubic", "lanczos"])
def test_hidden_colors_do_not_bleed_into_transparent_edges(source, tmp_path, filter):
    target = tmp_path / "out.png"
    upscale_image(
        source, target, 4, settings=UpscaleSettings(mode="illustration", illustration_filter=filter)
    )
    with Image.open(target) as output:
        for y in range(output.height):
            for x in range(output.width):
                red, green, blue, alpha = output.getpixel((x, y))
                if alpha > 0:
                    assert red == blue == 0


@pytest.mark.parametrize("mode", ["photo", "illustration", "pixel_art"])
def test_uniform_opaque_colors_stay_uniform(tmp_path, mode):
    source = tmp_path / "flat.png"
    Image.new("RGB", (16, 16), (60, 120, 180)).save(source)
    target = tmp_path / "out.png"
    upscale_image(source, target, settings=UpscaleSettings(mode=mode))
    with Image.open(target) as output:
        assert output.getcolors() == [(32 * 32, (60, 120, 180))]


@pytest.mark.parametrize("mode", ["photo", "illustration"])
def test_custom_size_and_jpeg_transparency(source, tmp_path, mode):
    target = tmp_path / "out.jpg"
    upscale_image(source, target, output_format="JPEG", size=(72, 48), settings=UpscaleSettings(mode=mode))
    with Image.open(target) as output:
        assert output.size == (72, 48)
        assert min(output.getpixel((0, 0))) >= 250


@pytest.mark.parametrize("mode", ["photo", "illustration", "pixel_art"])
def test_modes_preserve_size_limit(source, tmp_path, mode, monkeypatch):
    monkeypatch.setattr("shrimpit.limits.MAX_OUTPUT_PIXELS", 1000)
    with pytest.raises(ConversionError, match="dépasserait"):
        upscale_image(source, tmp_path / "out.png", settings=UpscaleSettings(mode=mode))


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "unknown"},
        {"illustration_filter": "invalid"},
        {"sharpen": 1},
        {"radius": float("nan")},
        {"radius": True},
        {"radius": 0.4},
        {"radius": 2.1},
        {"amount": -1},
        {"amount": 101},
        {"amount": True},
        {"threshold": -1},
        {"threshold": 11},
    ],
)
def test_invalid_mode_settings_leave_no_output(source, tmp_path, changes):
    target = tmp_path / "out.png"
    with pytest.raises(ConversionError):
        upscale_image(source, target, settings=replace(UpscaleSettings(), **changes))
    assert not target.exists()
