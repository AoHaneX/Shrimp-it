from pathlib import Path

import pytest
from PIL import Image

from shrimpit.engine import ConversionError, convert_image
from shrimpit.processing import thumbnail


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (80, 40), "coral").save(path)
    return path


@pytest.mark.parametrize("fmt,extension", [("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")])
def test_formats_and_original_unchanged(source, tmp_path, fmt, extension):
    before = source.read_bytes()
    destination = tmp_path / ("result" + extension)
    result = convert_image(source, destination, fmt)
    with Image.open(destination) as image:
        image.load()
        assert image.format == fmt
        assert image.size == (80, 40)
    assert source.read_bytes() == before
    assert result.input_bytes == len(before)
    assert result.output_bytes == destination.stat().st_size
    assert result.savings_percent == pytest.approx((1 - result.output_bytes / len(before)) * 100)


def test_jpeg_flattens_alpha_on_white(tmp_path):
    source = tmp_path / "transparent.png"
    Image.new("RGBA", (20, 20), (255, 0, 0, 0)).save(source)
    destination = tmp_path / "white.jpg"
    convert_image(source, destination)
    with Image.open(destination) as image:
        assert image.mode == "RGB"
        assert min(image.getpixel((10, 10))) >= 250


@pytest.mark.parametrize("fmt,extension", [("PNG", ".png"), ("WEBP", ".webp")])
def test_alpha_preserved(tmp_path, fmt, extension):
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (20, 20), (255, 0, 0, 42)).save(source)
    destination = tmp_path / ("result" + extension)
    convert_image(source, destination, fmt)
    with Image.open(destination) as image:
        assert image.convert("RGBA").getpixel((10, 10))[3] == 42


def test_palette_transparency(tmp_path):
    source = tmp_path / "palette.png"
    image = Image.new("P", (10, 10), 0)
    image.save(source, transparency=0)
    destination = tmp_path / "result.png"
    convert_image(source, destination, "PNG")
    with Image.open(destination) as result:
        assert result.convert("RGBA").getpixel((0, 0))[3] == 0


def test_png_pixels_unchanged(source, tmp_path):
    destination = tmp_path / "copy.png"
    convert_image(source, destination, "PNG")
    with Image.open(source) as original, Image.open(destination) as result:
        assert original.tobytes() == result.tobytes()


def test_orientation_and_metadata(tmp_path):
    source = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Private author"
    Image.new("RGB", (40, 20), "red").save(source, exif=exif)
    destination = tmp_path / "result.png"
    convert_image(source, destination, "PNG")
    with Image.open(destination) as result:
        assert result.size == (20, 40)
        assert not result.getexif()


def test_never_overwrites(source, tmp_path):
    destination = tmp_path / "existing.jpg"
    destination.write_bytes(b"keep me")
    with pytest.raises(ConversionError):
        convert_image(source, destination)
    assert destination.read_bytes() == b"keep me"
    before = source.read_bytes()
    with pytest.raises(ConversionError):
        convert_image(source, source, "PNG")
    assert source.read_bytes() == before


@pytest.mark.parametrize("quality", [0, 96, 80.5, True])
def test_invalid_quality(source, tmp_path, quality):
    with pytest.raises(ConversionError):
        convert_image(source, tmp_path / "out.jpg", quality=quality)


@pytest.mark.parametrize("kind", ["missing", "corrupt", "unsupported", "animated"])
def test_bad_inputs_leave_no_output(tmp_path, kind):
    source = tmp_path / "input"
    if kind == "corrupt":
        source.write_bytes(b"not an image")
    elif kind == "unsupported":
        Image.new("RGB", (2, 2)).save(source, format="BMP")
    elif kind == "animated":
        Image.new("RGB", (2, 2), "red").save(
            source,
            format="PNG",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
            duration=100,
        )
    destination = tmp_path / "out.jpg"
    with pytest.raises(ConversionError):
        convert_image(source, destination)
    assert not destination.exists()


@pytest.mark.parametrize("fmt,name", [("GIF", "out.gif"), ("JPEG", "out.png")])
def test_invalid_format_or_extension(source, tmp_path, fmt, name):
    with pytest.raises(ConversionError):
        convert_image(source, tmp_path / name, fmt)


def test_pixel_limit(source, tmp_path, monkeypatch):
    monkeypatch.setattr("shrimpit.engine.MAX_PIXELS", 10)
    with pytest.raises(ConversionError, match="25 mégapixels"):
        convert_image(source, tmp_path / "out.jpg")


def test_failed_save_removes_partial_file(source, tmp_path, monkeypatch):
    def broken_save(self, stream, **kwargs):
        stream.write(b"partial")
        raise OSError("Simulated disk failure")

    monkeypatch.setattr(Image.Image, "save", broken_save)
    destination = tmp_path / "out.jpg"
    with pytest.raises(ConversionError):
        convert_image(source, destination)
    assert not destination.exists()


def test_destination_race_is_protected(source, tmp_path, monkeypatch):
    destination = tmp_path / "out.jpg"
    real_open = Path.open

    def competing_open(path, mode="r", *args, **kwargs):
        if path == destination and mode == "xb":
            with real_open(path, "wb") as stream:
                stream.write(b"other process")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", competing_open)
    with pytest.raises(ConversionError):
        convert_image(source, destination)
    assert destination.read_bytes() == b"other process"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("text", "non reconnu"),
        ("missing", "introuvable"),
        ("folder", "Un dossier"),
        ("truncated", "endommagée"),
    ],
)
def test_import_errors_are_explained_in_french(source, tmp_path, kind, expected):
    path = tmp_path / "input.png"
    if kind == "text":
        path.write_text("not an image")
    elif kind == "folder":
        path.mkdir()
    elif kind == "truncated":
        image = Image.effect_noise((64, 64), 40).convert("RGB")
        image.save(path)
        path.write_bytes(path.read_bytes()[:200])
    with pytest.raises(ConversionError, match=expected):
        thumbnail(path)
