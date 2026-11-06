"""Automatic PNG compression: reopen real exports and check what the user actually gets."""

import random
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from shrimpit.engine import ConversionError, convert_image, upscale_image
from shrimpit.gui.workers import ExportJob, PreviewJob
from shrimpit.png_compression import (
    MAX_BLOCK_ERROR,
    MAX_EDGE_MEAN,
    MAX_EDGE_P99,
    MIN_PSNR_DB,
    choose_png,
    measure,
    palette_candidate,
    save_png,
)
from shrimpit.processing import Options
from shrimpit.upscale import UpscaleSettings


def sticker(size=192, noise=3):
    """Flat shapes, an outline, anti-aliased edges and slight noise, on a transparent background."""
    big = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    scale = size * 4 / 768
    draw.ellipse([v * scale for v in (40, 40, 720, 720)], fill=(255, 140, 40, 255))
    draw.ellipse([v * scale for v in (40, 40, 720, 720)], outline=(20, 30, 90, 255), width=int(24 * scale))
    draw.rectangle([v * scale for v in (240, 260, 520, 420)], fill=(40, 170, 220, 255))
    draw.ellipse([v * scale for v in (300, 480, 460, 640)], fill=(250, 240, 230, 255))
    image = big.resize((size, size), Image.Resampling.LANCZOS)
    generator = random.Random(7)
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            red, green, blue, alpha = pixels[x, y]
            if alpha:
                shift = generator.randint(-noise, noise)
                pixels[x, y] = (
                    min(255, max(0, red + shift)),
                    min(255, max(0, green + shift)),
                    min(255, max(0, blue - shift)),
                    alpha,
                )
    return image


def glowing_sticker():
    """A wide soft shadow: hundreds of opacity levels that a 256-entry RGBA palette cannot keep."""
    shadow = Image.new("L", (192, 192), 0)
    ImageDraw.Draw(shadow).ellipse((20, 20, 172, 172), fill=255)
    image = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
    image.putalpha(shadow.filter(ImageFilter.GaussianBlur(18)))
    image.alpha_composite(sticker(112), (40, 40))
    return image


def color_gradient(alpha=False):
    image = Image.new("RGB", (256, 256))
    image.putdata([(x, y, 255 - (x + y) // 2) for y in range(256) for x in range(256)])
    if alpha:
        image.putalpha(Image.linear_gradient("L").resize((256, 256)))
    return image


def export(tmp_path, image, name="source.png"):
    source = tmp_path / name
    image.save(source)
    target = tmp_path / f"{Path(name).stem}-min.png"
    result = convert_image(source, target, "PNG")
    with Image.open(target) as output:
        output.load()
        assert output.format == "PNG"
        assert output.size == image.size == result.input_size == result.output_size
        decoded = output.convert("RGBA")
    return result, decoded


def lossless_size(image):
    return len(save_png(image))


def test_illustration_gets_lighter_palette(tmp_path):
    image = sticker()
    assert image.getcolors(256) is None
    result, output = export(tmp_path, image)
    assert result.png_encoding == "palette"
    assert result.output_bytes < 0.5 * lossless_size(image)
    assert result.output_bytes < result.input_bytes
    fidelity = measure(image, output)
    assert fidelity.acceptable
    assert fidelity.psnr_db >= MIN_PSNR_DB


def test_fully_transparent_pixels_stay_fully_transparent(tmp_path):
    image = sticker()
    result, output = export(tmp_path, image)
    assert result.png_encoding == "palette"
    hidden = image.getchannel("A").point(lambda value: 255 if value == 0 else 0)
    assert hidden.getbbox() is not None
    # Every original background pixel is still alpha 0 in the reopened file.
    assert output.getchannel("A").histogram(mask=hidden)[0] == hidden.histogram()[255]


def test_semi_transparent_edges_stay_close(tmp_path):
    image = sticker()
    _, output = export(tmp_path, image)
    edges = image.getchannel("A").point(lambda value: 255 if 0 < value < 255 else 0)
    assert edges.histogram()[255] > 300
    alpha_error = ImageChops.difference(image.getchannel("A"), output.getchannel("A"))
    histogram = alpha_error.histogram(mask=edges)
    mean = sum(index * count for index, count in enumerate(histogram)) / sum(histogram)
    assert mean <= MAX_EDGE_MEAN
    fidelity = measure(image, output)
    assert fidelity.edge_mean <= MAX_EDGE_MEAN
    assert fidelity.edge_p99 <= MAX_EDGE_P99


def test_degraded_edges_fall_back_to_exact_opacity(tmp_path):
    image = glowing_sticker()
    # The plain palette shifts the soft shadow and lights up pixels that must stay invisible.
    with Image.open(_saved(tmp_path, palette_candidate(image))) as palette:
        assert not measure(image, palette).acceptable
    result, output = export(tmp_path, image)
    assert result.png_encoding == "palette_alpha"
    assert result.output_bytes < lossless_size(image)
    assert output.getchannel("A").tobytes() == image.getchannel("A").tobytes()
    assert measure(image, output).acceptable


def _saved(tmp_path, image):
    path = tmp_path / "candidate.png"
    path.write_bytes(save_png(image))
    return path


@pytest.mark.parametrize("alpha", [False, True])
def test_banding_keeps_faithful_encoding(tmp_path, alpha):
    image = color_gradient(alpha)
    result, output = export(tmp_path, image)
    assert result.png_encoding == "lossless"
    assert output.tobytes() == image.convert("RGBA").tobytes()


def test_lost_thin_outline_is_rejected_despite_high_global_psnr():
    original = Image.new("RGB", (512, 512), "white")
    ImageDraw.Draw(original).line((100, 100, 115, 100), fill=(30, 30, 30))
    damaged = Image.new("RGB", (512, 512), "white")
    fidelity = measure(original, damaged)
    assert fidelity.psnr_db > 40
    assert fidelity.worst_block > MAX_BLOCK_ERROR
    assert not fidelity.acceptable


def test_few_colors_use_an_exact_palette(tmp_path):
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 70, 60), fill=(200, 30, 60, 255))
    draw.rectangle((40, 30, 110, 75), fill=(20, 90, 200, 128))
    result, output = export(tmp_path, image)
    assert result.png_encoding == "palette"
    assert output.tobytes() == image.tobytes()


def test_already_optimized_png_is_handled(tmp_path):
    first, decoded = export(tmp_path, sticker(), "source.png")
    again = tmp_path / "again.png"
    second = convert_image(first.destination, again, "PNG")
    with Image.open(again) as output:
        # An existing palette is mapped exactly: no generation loss and no heavier file.
        assert output.convert("RGBA").tobytes() == decoded.tobytes()
    assert second.png_encoding == "palette"
    assert second.output_bytes <= first.output_bytes
    assert second.savings_percent >= 0


def test_already_optimized_faithful_png_stays_faithful(tmp_path):
    image = color_gradient()
    source = tmp_path / "optimized.png"
    source.write_bytes(save_png(image))
    result = convert_image(source, tmp_path / "result.png", "PNG")
    assert result.png_encoding == "lossless"
    assert result.output_bytes == result.input_bytes
    with Image.open(result.destination) as output:
        assert output.tobytes() == image.tobytes()


def raise_memory_error(*args, **kwargs):
    raise MemoryError


@pytest.mark.parametrize("step", ["palette_candidate", "exact_alpha_candidate", "measure"])
def test_memory_error_while_evaluating_variants_keeps_faithful_png(tmp_path, monkeypatch, caplog, step):
    image = glowing_sticker() if step == "exact_alpha_candidate" else sticker()
    if step == "exact_alpha_candidate":
        # Reach the second variant: the plain palette is rejected for this image.
        assert choose_png(image).encoding == "palette_alpha"
    monkeypatch.setattr(f"shrimpit.png_compression.{step}", raise_memory_error)
    result, output = export(tmp_path, image)
    assert result.png_encoding == "lossless"
    assert result.output_bytes == lossless_size(image)
    assert output.tobytes() == image.tobytes()
    assert "faithful PNG kept" in caplog.text


def test_memory_error_while_encoding_faithful_png_is_reported(tmp_path, monkeypatch):
    source = tmp_path / "sticker.png"
    sticker().save(source)
    target = tmp_path / "sticker-min.png"
    monkeypatch.setattr("shrimpit.png_compression.save_png", raise_memory_error)
    with pytest.raises(ConversionError, match="Mémoire insuffisante"):
        convert_image(source, target, "PNG")
    assert not target.exists()


@pytest.mark.parametrize(
    "image", [sticker(), glowing_sticker(), color_gradient(alpha=True)], ids=["sticker", "glow", "gradient"]
)
def test_measure_by_bands_matches_a_whole_image_comparison(monkeypatch, image):
    from shrimpit import png_compression

    candidate = palette_candidate(image)
    monkeypatch.setattr(png_compression, "BAND_ROWS", 100_000)
    whole = measure(image, candidate)
    # Bands of 4 rows: blocks, banding steps across band edges and edge histograms must add up exactly.
    monkeypatch.setattr(png_compression, "BAND_ROWS", 4)
    assert measure(image, candidate) == whole


def test_choice_is_deterministic():
    image = sticker()
    assert choose_png(image) == choose_png(image)


def test_pixel_art_enlargement_keeps_every_color(tmp_path):
    generator = random.Random(3)
    image = Image.new("RGBA", (32, 32))
    image.putdata(
        [
            (generator.randrange(256), generator.randrange(256), generator.randrange(256), 255)
            for _ in range(1024)
        ]
    )
    image.paste((0, 0, 0, 0), (0, 0, 8, 8))
    source = tmp_path / "sprite.png"
    image.save(source)
    target = tmp_path / "sprite-x2.png"
    result = upscale_image(source, target, 2, settings=UpscaleSettings(mode="pixel_art"))
    assert result.png_encoding is None
    with Image.open(target) as output:
        assert output.mode == "RGBA"
        assert output.size == (64, 64)
        assert sorted(output.getcolors(4096), key=lambda item: item[1]) == sorted(
            ((count * 4, color) for count, color in image.getcolors(4096)), key=lambda item: item[1]
        )
        assert output.tobytes() == image.resize((64, 64), Image.Resampling.NEAREST).tobytes()


def test_preview_and_export_make_the_same_choice(tmp_path):
    source = tmp_path / "sticker.png"
    sticker().save(source)
    options = Options(output_format="PNG")
    payloads = []
    preview = PreviewJob(source, options, 1)
    preview.ready.connect(lambda revision, payload: payloads.append(payload))
    preview.render()
    assert payloads
    preview_result = payloads[0][2]

    destination = tmp_path / "exported.png"
    job = ExportJob([(source, destination)], options)
    job.run()
    assert job.errors == []
    assert preview_result.png_encoding == "palette"
    assert preview_result.output_bytes == destination.stat().st_size
    assert lossless_size(sticker()) > destination.stat().st_size


def test_history_records_png_encoding(tmp_path):
    from shrimpit.gui.pages.history import parameter_text
    from shrimpit.history import HistoryStore, timestamp

    source = tmp_path / "sticker.png"
    sticker().save(source)
    result = convert_image(source, tmp_path / "sticker-min.png", "PNG")
    store = HistoryStore(tmp_path / "history.json")
    store.record("batch", timestamp(), source, result, Options(output_format="PNG"))
    entry = store.batches()[0]["images"][0]
    assert entry["parameters"]["png_encoding"] == "palette"
    assert "Encodage : PNG à palette" in parameter_text(entry)


def test_compression_page_shows_the_chosen_png_encoding(wait_for, window, tmp_path):
    page = window.compression
    page.output.format.setCurrentText("PNG")
    assert "Palette de 256 couleurs" in page.output.note.text()
    assert "Palette de 256 couleurs" not in window.enlargement.output.note.text()
    source = tmp_path / "sticker.png"
    sticker().save(source)
    page.add_files([source])
    wait_for(lambda: page.preview_payload is not None and page.preview_job is None)
    assert "Encodage retenu : PNG à palette" in page.preview_status.text()
