"""Bundled ExoQuant palette engine: availability, refinement, transparency, determinism and fallbacks."""

import os
import random
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from PIL import Image, ImageDraw
from test_png_compression import export, glowing_sticker, sticker

from shrimpit import refined_palette
from shrimpit.png_compression import MAX_BLOCK_ERROR, choose_png, measure, refined_palette_candidate, save_png

requires_engine = pytest.mark.skipif(
    not refined_palette.available(), reason="native palette engine not built (scripts/build_png_engine.py)"
)


def textured_with_rare_outline(size=480):
    """Many close colors, plus one-pixel green lines that the sampling grid of the first pass misses."""
    generator = random.Random(5)
    image = Image.new("RGB", (size, size))
    image.putdata(
        [
            (
                100 + generator.randint(-20, 20),
                80 + generator.randint(-20, 20),
                60 + generator.randint(-20, 20),
            )
            for _ in range(size * size)
        ]
    )
    draw = ImageDraw.Draw(image)
    for top in (40, 200, 360):
        # Column 7 falls between two sampled columns of a 480 -> 192 nearest-neighbour grid.
        draw.line((7, top, 7, top + 80), fill=(0, 255, 0))
    return image


def decoded(candidate):
    with Image.open(BytesIO(save_png(candidate))) as image:
        image.load()
        return image


def test_engine_is_built_when_required():
    # check.ps1 and the CI set this variable so that a missing DLL fails instead of skipping tests.
    if os.environ.get("SHRIMPIT_REQUIRE_PNG_ENGINE") != "1":
        pytest.skip("SHRIMPIT_REQUIRE_PNG_ENGINE is not set")
    assert refined_palette.available(), f"missing {refined_palette.NATIVE_LIBRARY}"


def quantize(image):
    return refined_palette.builder(image).build()


@requires_engine
def test_refinement_recovers_a_rare_thin_outline():
    image = textured_with_rare_outline()
    palette_builder = refined_palette.builder(image)
    first = palette_builder.build()
    single = measure(image, decoded(first))
    assert palette_builder.refine(first)
    refined = measure(image, decoded(palette_builder.build()))
    # The first pass loses the green lines; feeding the badly mapped pixels back restores them.
    assert single.worst_block > MAX_BLOCK_ERROR
    assert refined.worst_block <= MAX_BLOCK_ERROR
    assert refined.psnr_db > single.psnr_db
    assert refined_palette_candidate(image) is not None


@requires_engine
def test_banding_stops_refinement_early(monkeypatch):
    image = Image.new("RGB", (256, 256))
    image.putdata([(x, y, 255 - (x + y) // 2) for y in range(256) for x in range(256)])
    builds = []
    original = refined_palette.PaletteBuilder.build
    monkeypatch.setattr(
        refined_palette.PaletteBuilder, "build", lambda self: builds.append(1) or original(self)
    )
    # Refining cannot remove the bands of a smooth gradient: one pass, then the faithful PNG.
    assert refined_palette_candidate(image) is None
    assert len(builds) == 1


@requires_engine
def test_transparent_glow_gets_the_refined_palette(tmp_path):
    image = glowing_sticker()
    result, output = export(tmp_path, image)
    assert result.png_encoding == "palette_refined"
    assert result.output_bytes < result.input_bytes
    assert measure(image, output).acceptable
    hidden = image.getchannel("A").point(lambda value: 255 if value == 0 else 0)
    # Every originally invisible pixel is still fully transparent in the reopened file.
    assert output.convert("RGBA").getchannel("A").histogram(mask=hidden)[0] == hidden.histogram()[255]


@requires_engine
def test_reserved_entry_is_fully_transparent():
    candidate = quantize(glowing_sticker())
    palette = candidate.getpalette("RGBA")
    index = refined_palette.TRANSPARENT_INDEX
    assert palette[index * 4 + 3] == 0
    assert candidate.getpixel((0, 0)) == index


@requires_engine
@pytest.mark.parametrize(
    "image",
    [
        Image.new("RGBA", (1, 1), (10, 200, 30, 128)),
        Image.new("RGBA", (3, 2), (0, 0, 0, 0)),
        Image.new("RGB", (5, 1), (255, 255, 255)),
        sticker(24),
    ],
    ids=["one-pixel", "fully-transparent", "single-color", "small"],
)
def test_tiny_and_uniform_images(image):
    candidate = quantize(image)
    assert candidate.size == image.size
    assert measure(image, decoded(candidate)).transparent_kept


@requires_engine
def test_quantization_is_deterministic_across_threads():
    images = [glowing_sticker(), textured_with_rare_outline(240), sticker()]

    def two_passes(image):
        palette_builder = refined_palette.builder(image)
        palette_builder.refine(palette_builder.build())
        return palette_builder.build().tobytes()

    serial = [two_passes(image) for image in images]
    # The C code has no global state: concurrent calls must give the same pixels as serial ones.
    with ThreadPoolExecutor(max_workers=6) as pool:
        parallel = list(pool.map(two_passes, images * 4))
    assert parallel == serial * 4


def test_missing_engine_keeps_the_other_encodings(monkeypatch, tmp_path):
    monkeypatch.setattr(refined_palette, "NATIVE_LIBRARY", tmp_path / "missing.dll")
    refined_palette._library.cache_clear()
    try:
        assert not refined_palette.available()
        assert refined_palette.builder(glowing_sticker()) is None
        choice = choose_png(glowing_sticker())
        assert choice.encoding == "palette_alpha"
    finally:
        monkeypatch.undo()
        refined_palette._library.cache_clear()


def test_damaged_engine_file_is_treated_as_missing(monkeypatch, tmp_path):
    damaged = tmp_path / "exoquant.dll"
    damaged.write_bytes(b"not a library")
    monkeypatch.setattr(refined_palette, "NATIVE_LIBRARY", damaged)
    refined_palette._library.cache_clear()
    try:
        assert refined_palette.builder(sticker()) is None
    finally:
        monkeypatch.undo()
        refined_palette._library.cache_clear()


@requires_engine
def test_rejected_refined_palette_keeps_the_faithful_png(tmp_path):
    # Smooth gradients band with 256 colors: the refined candidate is built but must be refused.
    image = Image.new("RGB", (256, 256))
    image.putdata([(x, y, 255 - (x + y) // 2) for y in range(256) for x in range(256)])
    assert refined_palette.builder(image) is not None
    result, output = export(tmp_path, image)
    assert result.png_encoding == "lossless"
    assert output.convert("RGB").tobytes() == image.tobytes()
