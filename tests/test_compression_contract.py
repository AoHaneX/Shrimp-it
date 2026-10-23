"""Protect compression behavior across formats, alpha modes, and quality settings."""

import pytest
from PIL import Image, ImageChops, ImageStat

from shrimpit.engine import ConversionError, convert_image

FORMATS = [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")]


def pattern():
    image = Image.new("RGB", (128, 64))
    image.putdata([(x * 2, y * 4, (x * 7 + y * 3) % 256) for y in range(64) for x in range(128)])
    return image


@pytest.mark.parametrize("source_format,source_ext", FORMATS)
@pytest.mark.parametrize("target_format,target_ext", FORMATS)
def test_conversion_matrix(tmp_path, source_format, source_ext, target_format, target_ext):
    source = tmp_path / f"source.{source_ext}"
    pattern().save(source, format=source_format)
    original_bytes = source.read_bytes()
    target = tmp_path / f"result.{target_ext}"
    result = convert_image(source, target, target_format)
    with Image.open(source) as original, Image.open(target) as output:
        output.load()
        assert output.format == target_format
        assert output.size == original.size == result.input_size == result.output_size
        if target_format == "PNG":
            assert output.convert("RGB").tobytes() == original.convert("RGB").tobytes()
    assert source.read_bytes() == original_bytes


@pytest.mark.parametrize("orientation", range(1, 9))
def test_all_exif_orientations(tmp_path, orientation):
    source = tmp_path / "oriented.png"
    original = pattern()
    exif = Image.Exif()
    exif[274] = orientation
    original.save(source, exif=exif)
    operations = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_270,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_90,
    }
    expected = original if orientation == 1 else original.transpose(operations[orientation])
    target = tmp_path / "result.png"
    result = convert_image(source, target, "PNG")
    with Image.open(target) as output:
        assert output.size == expected.size == result.output_size == result.input_size
        assert output.tobytes() == expected.tobytes()
        assert not output.getexif()


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P", "RGB"])
@pytest.mark.parametrize("fmt,extension", [("PNG", "png"), ("WEBP", "webp")])
def test_alpha_modes_and_partial_transparency(tmp_path, mode, fmt, extension):
    source = tmp_path / "alpha.png"
    alpha = Image.linear_gradient("L").resize((64, 256))
    options = {}
    if mode == "P":
        image = alpha.copy().convert("P")
        options["transparency"] = bytes(range(256))
    elif mode == "RGB":
        image = Image.new("RGB", (64, 256), "red")
        image.paste("blue", (0, 0, 32, 256))
        options["transparency"] = (255, 0, 0)
    else:
        image = Image.new(mode, (64, 256))
        image.putalpha(alpha)
    image.save(source, **options)
    target = tmp_path / f"result.{extension}"
    convert_image(source, target, fmt)
    with Image.open(source) as original, Image.open(target) as output:
        expected = original.convert("RGBA")
        actual = output.convert("RGBA")
        assert actual.getchannel("A").tobytes() == expected.getchannel("A").tobytes()
        if fmt == "PNG":
            assert actual.tobytes() == expected.tobytes()


def test_partial_alpha_is_composited_on_white_for_jpeg(tmp_path):
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (32, 32), (240, 20, 80, 128)).save(source)
    target = tmp_path / "result.jpg"
    convert_image(source, target, "JPEG", quality=95)
    with Image.open(target) as output:
        assert output.mode == "RGB"
        assert output.getpixel((16, 16)) == pytest.approx((247, 137, 167), abs=3)


def test_png_quality_does_not_change_pixels_or_encoding(tmp_path):
    source = tmp_path / "source.png"
    pattern().save(source, compress_level=0)
    outputs = []
    for quality in (1, 80, 95):
        target = tmp_path / f"q{quality}.png"
        result = convert_image(source, target, "PNG", quality)
        assert result.output_bytes < result.input_bytes
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1] == outputs[2]


@pytest.mark.parametrize("fmt,extension", [("JPEG", "jpg"), ("WEBP", "webp")])
def test_quality_improves_fidelity_on_diagnostic_pattern(tmp_path, fmt, extension):
    source = tmp_path / "source.png"
    original = pattern()
    original.save(source)
    measurements = []
    for quality in (1, 95):
        target = tmp_path / f"q{quality}.{extension}"
        convert_image(source, target, fmt, quality)
        with Image.open(target) as output:
            mse = sum(ImageStat.Stat(ImageChops.difference(original, output.convert("RGB"))).sum2)
        measurements.append((target.stat().st_size, mse))
    assert measurements[1][0] > measurements[0][0]
    assert measurements[1][1] < measurements[0][1]


def test_negative_savings_are_reported_honestly(tmp_path):
    source = tmp_path / "tiny.png"
    Image.new("RGB", (1, 1), "red").save(source)
    result = convert_image(source, tmp_path / "larger.jpg")
    assert result.output_bytes > result.input_bytes
    assert result.savings_percent < 0


@pytest.mark.parametrize("fmt,extension", FORMATS)
def test_truncated_input_has_no_partial_output(tmp_path, fmt, extension):
    source = tmp_path / f"truncated.{extension}"
    pattern().save(source, format=fmt)
    data = source.read_bytes()
    source.write_bytes(data[: len(data) // 2])
    target = tmp_path / "result.png"
    with pytest.raises(ConversionError):
        convert_image(source, target, "PNG")
    assert not target.exists()


def test_missing_destination_directory_is_reported(tmp_path):
    source = tmp_path / "source.png"
    pattern().save(source)
    target = tmp_path / "missing" / "result.png"
    with pytest.raises(ConversionError):
        convert_image(source, target, "PNG")
    assert not target.exists()
