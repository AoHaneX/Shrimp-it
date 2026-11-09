"""Pick the lightest PNG encoding that stays visually faithful, without a Qt dependency.

Compression to PNG tries, in order:

1. ``palette``: an indexed PNG of at most 256 colors. Images that already have 256 colors or fewer are
   mapped exactly; others are quantized with Pillow's fast octree, alpha included.
2. ``palette_alpha``: when the palette is rejected and the image has semi-transparent pixels, colors are
   reduced to 256 while the original opacity is copied exactly.
3. ``lossless``: the faithful optimized encoding, kept whenever no lighter variant passes ``Fidelity``.

When the source is a PNG, its own encoding is also considered: ``original`` keeps only the chunks that
carry the pixels (``IHDR``, ``PLTE``, ``tRNS``, ``IDAT``, ``IEND``), so metadata is still removed. It is
used only when it decodes to exactly the normalized pixels and is lighter than Pillow's faithful encoding:
an already optimized PNG is then not re-encoded into a heavier file. The palette variants must beat it.

Every candidate is decoded again and compared with the original composited on white and on black.
The thresholds were calibrated on a transparent mascot, icons, gradients and photographs (see the README):
they accept palettes whose differences are invisible at 200 % zoom and reject banding and lost details.
"""

import logging
import math
import struct
import sys
import zlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageChops

PALETTE_COLORS = 256
BACKGROUNDS = ("white", "black")
# Global fidelity, computed on the worse of both backgrounds.
MIN_PSNR_DB = 34.0
# Local fidelity: mean error of the worst 4 × 4 block, so a lost thin outline is not averaged away.
BLOCK_SIZE = 4
MAX_BLOCK_ERROR = 24
# Banding: share of pixels where the original changes by at most 1 level and the result jumps by 3 or more.
SMOOTH_STEP = 1
VISIBLE_STEP = 3
MAX_FALSE_CONTOURS = 0.01
# Semi-transparent pixels (0 < alpha < 255): mean and 99th percentile of their error.
MAX_EDGE_MEAN = 8.0
MAX_EDGE_P99 = 32
# Rows compared at once by measure(): a multiple of BLOCK_SIZE, so no block straddles two bands.
BAND_ROWS = 256

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Chunks that carry the pixels; every other one (text, EXIF, ICC, gamma, time, animation) is dropped.
PIXEL_CHUNKS = (b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND")

ENCODING_LABELS = {
    "lossless": "PNG fidèle",
    "original": "PNG fidèle, encodage d’origine sans métadonnées",
    "palette": "PNG à palette (256 couleurs max.)",
    "palette_alpha": "PNG à couleurs réduites, opacité d’origine",
}


@dataclass(frozen=True)
class Fidelity:
    """Differences between an original and a decoded candidate; errors are 0-255 channel levels."""

    psnr_db: float
    worst_block: int
    false_contours: float
    edge_mean: float
    edge_p99: int
    transparent_kept: bool

    @property
    def acceptable(self) -> bool:
        return (
            self.transparent_kept
            and self.psnr_db >= MIN_PSNR_DB
            and self.worst_block <= MAX_BLOCK_ERROR
            and self.false_contours <= MAX_FALSE_CONTOURS
            and self.edge_mean <= MAX_EDGE_MEAN
            and self.edge_p99 <= MAX_EDGE_P99
        )


@dataclass(frozen=True)
class PngChoice:
    data: bytes
    encoding: str
    lossless_bytes: int


def save_png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def choose_png(image: Image.Image, source: bytes | None = None) -> PngChoice:
    """Return the lightest acceptable encoding of a normalized RGB or RGBA image.

    ``source`` holds the bytes of the original file when it is a PNG; its encoding is reused, without
    metadata, when it gives exactly the same pixels in fewer bytes (see ``original_encoding``).

    Only the faithful encoding may fail for lack of memory: the other candidates are optional, so a
    ``MemoryError`` while building or measuring them keeps the best faithful PNG already found.
    """
    lossless = save_png(image)
    best = PngChoice(lossless, "lossless", len(lossless))
    try:
        original = original_encoding(image, source) if source is not None else None
        if original is not None and len(original) < len(lossless):
            best = PngChoice(original, "original", len(lossless))
        for encoding, build in (("palette", palette_candidate), ("palette_alpha", exact_alpha_candidate)):
            candidate = build(image)
            if candidate is None:
                continue
            data = save_png(candidate)
            # Free the candidate's pixels before decoding and measuring its encoded copy.
            del candidate
            if len(data) >= len(best.data):
                continue
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()
                if decoded.size == image.size and measure(image, decoded).acceptable:
                    return PngChoice(data, encoding, len(lossless))
    except MemoryError:
        logging.getLogger(__name__).warning(
            "Not enough memory to evaluate PNG palettes for %s × %s pixels: faithful PNG kept", *image.size
        )
    return best


def strip_png(data: bytes) -> bytes | None:
    """Keep only the pixel chunks of a PNG of at most 8 bits per channel.

    Return ``None`` for anything else: another format, a damaged or truncated chunk, a 16-bit image
    (normalized to 8 bits, so its pixels would differ) or an unknown critical chunk.
    """
    if not data.startswith(PNG_SIGNATURE):
        return None
    kept = [PNG_SIGNATURE]
    position = len(PNG_SIGNATURE)
    while position + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, position)
        end = position + 12 + length
        if end > len(data):
            return None
        (crc,) = struct.unpack_from(">I", data, end - 4)
        if zlib.crc32(data[position + 4 : end - 4]) != crc:
            return None
        if kind == b"IHDR" and (length != 13 or data[position + 16] > 8):
            return None
        if kind in PIXEL_CHUNKS:
            kept.append(data[position:end])
        elif not kind[0] & 0x20:
            # An uppercase first letter marks a critical chunk that decoders must understand.
            return None
        if kind == b"IEND":
            return b"".join(kept)
        position = end
    return None


def original_encoding(image: Image.Image, source: bytes) -> bytes | None:
    """Return the source PNG without metadata when it decodes to exactly ``image``, else ``None``."""
    stripped = strip_png(source)
    if stripped is None:
        return None
    with Image.open(BytesIO(stripped)) as decoded:
        if decoded.format != "PNG" or decoded.size != image.size:
            return None
        decoded.load()
        has_alpha = "A" in decoded.getbands() or "transparency" in decoded.info
        if has_alpha != (image.mode == "RGBA"):
            return None
        width, height = image.size
        # Compare in bands, like measure(), so no full-size converted copy is made.
        for top in range(0, height, BAND_ROWS):
            box = (0, top, width, min(top + BAND_ROWS, height))
            if decoded.crop(box).convert(image.mode).tobytes() != image.crop(box).tobytes():
                return None
    return stripped


def palette_candidate(image: Image.Image) -> Image.Image:
    exact = exact_palette(image)
    if exact is not None:
        return exact
    if image.mode == "RGBA":
        # Hidden colors under alpha 0 are invisible: dropping them frees palette entries.
        cleared = clear_hidden_colors(image)
        return exact_palette(cleared) or cleared.quantize(PALETTE_COLORS, Image.Quantize.FASTOCTREE)
    return image.quantize(PALETTE_COLORS, Image.Quantize.FASTOCTREE)


def exact_alpha_candidate(image: Image.Image) -> Image.Image | None:
    """Reduce colors only; alpha is copied unchanged, so anti-aliased edges keep their opacity."""
    if image.mode != "RGBA" or semi_transparent_mask(image.getchannel("A")).getbbox() is None:
        return None
    alpha = image.getchannel("A")
    reduced = clear_hidden_colors(image).convert("RGB")
    reduced = reduced.quantize(PALETTE_COLORS, Image.Quantize.FASTOCTREE).convert("RGB")
    reduced.putalpha(alpha)
    reduced = clear_hidden_colors(reduced)
    # Few color and opacity pairs still fit an exact palette; otherwise fewer colors help deflate.
    return exact_palette(reduced) or reduced


def exact_palette(image: Image.Image) -> Image.Image | None:
    """Map an image of at most 256 RGBA values to a palette without any loss."""
    colors = image.getcolors(PALETTE_COLORS)
    if colors is None:
        return None
    rgba = image.convert("RGBA")
    entries = [value if len(value) == 4 else (*value, 255) for _, value in colors]
    lookup = {int.from_bytes(bytes(value), sys.byteorder): index for index, value in enumerate(entries)}
    # One native 32-bit integer per pixel: the dictionary lookup runs in C through map().
    pixels = memoryview(rgba.tobytes()).cast("I")
    palette = Image.frombytes("P", rgba.size, bytes(map(lookup.__getitem__, pixels)))
    palette.putpalette([channel for value in entries for channel in value[:3]])
    alphas = bytes(value[3] for value in entries)
    if min(alphas) < 255:
        palette.info["transparency"] = alphas
    return palette


def clear_hidden_colors(image: Image.Image) -> Image.Image:
    cleared = Image.new("RGBA", image.size, (0, 0, 0, 0))
    cleared.paste(image, mask=image.getchannel("A").point(lambda value: 255 if value else 0))
    return cleared


def semi_transparent_mask(alpha: Image.Image) -> Image.Image:
    return alpha.point(lambda value: 255 if 0 < value < 255 else 0)


def measure(original: Image.Image, candidate: Image.Image) -> Fidelity:
    """Compare both images composited on white and black; keep the worse value of each criterion.

    The images are compared in bands of ``BAND_ROWS`` rows, so memory stays small on large images;
    every criterion is accumulated exactly, with the same result as a whole-image comparison.
    """
    width, height = original.size
    has_alpha = original.mode == "RGBA"
    backgrounds = BACKGROUNDS if has_alpha else BACKGROUNDS[:1]
    squared = dict.fromkeys(backgrounds, 0)
    blocks = dict.fromkeys(backgrounds, 0)
    contours = dict.fromkeys(backgrounds, 0)
    edges = {color: [0] * 256 for color in backgrounds}
    transparent_kept = True
    for top in range(0, height, BAND_ROWS):
        rows = min(BAND_ROWS, height - top)
        # One extra row gives the band's last row its lower neighbor for the banding check.
        box = (0, top, width, min(top + rows + 1, height))
        own = (0, 0, width, rows)
        reference_band = original.crop(box).convert("RGBA")
        result_band = candidate.crop(box).convert("RGBA")
        edge_mask = None
        if has_alpha:
            alpha = reference_band.getchannel("A")
            hidden = alpha.point(lambda value: 255 if value == 0 else 0)
            if ImageChops.multiply(hidden, result_band.getchannel("A")).getbbox() is not None:
                transparent_kept = False
            edge_mask = semi_transparent_mask(alpha).crop(own)
        for color in backgrounds:
            reference = _composite(reference_band, color)
            result = _composite(result_band, color)
            difference = ImageChops.difference(reference.crop(own), result.crop(own))
            squared[color] += _squared_error(difference)
            worst = _max_channel(difference)
            blocks[color] = max(blocks[color], worst.reduce(BLOCK_SIZE).getextrema()[1])
            contours[color] += _false_contours(reference, result)
            if edge_mask is not None:
                edges[color] = [a + b for a, b in zip(edges[color], worst.histogram(mask=edge_mask))]
    step_pixels = (width - 1) * (height - 1)
    return Fidelity(
        psnr_db=min(_psnr(squared[color], width * height * 3) for color in backgrounds),
        worst_block=max(blocks.values()),
        false_contours=max(contours.values()) / step_pixels if step_pixels else 0.0,
        edge_mean=max(_mean(edges[color]) for color in backgrounds),
        edge_p99=max(_percentile(edges[color], 0.99) for color in backgrounds),
        transparent_kept=transparent_kept,
    )


def _composite(rgba: Image.Image, color: str) -> Image.Image:
    return Image.alpha_composite(Image.new("RGBA", rgba.size, color), rgba).convert("RGB")


def _max_channel(difference: Image.Image) -> Image.Image:
    red, green, blue = difference.split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue)


def _squared_error(difference: Image.Image) -> int:
    return sum(count * (index % 256) ** 2 for index, count in enumerate(difference.histogram()))


def _psnr(squared: int, samples: int) -> float:
    mse = squared / samples
    return math.inf if mse == 0 else 10 * math.log10(255**2 / mse)


def _steps(image: Image.Image) -> Image.Image:
    """Largest change towards the right or bottom neighbor, on the strongest channel."""
    width, height = image.size
    base = image.crop((0, 0, width - 1, height - 1))
    right = ImageChops.difference(image.crop((1, 0, width, height - 1)), base)
    below = ImageChops.difference(image.crop((0, 1, width - 1, height)), base)
    return ImageChops.lighter(_max_channel(right), _max_channel(below))


def _false_contours(reference: Image.Image, result: Image.Image) -> int:
    """Count pixels that jump visibly where the reference is smooth (last row and column excluded)."""
    if reference.width < 2 or reference.height < 2:
        return 0
    smooth = _steps(reference).point(lambda value: 255 if value <= SMOOTH_STEP else 0)
    jumps = _steps(result).point(lambda value: 255 if value >= VISIBLE_STEP else 0)
    return ImageChops.multiply(smooth, jumps).histogram()[255]


def _mean(histogram: list[int]) -> float:
    total = sum(histogram)
    return sum(index * count for index, count in enumerate(histogram)) / total if total else 0.0


def _percentile(histogram: list[int], share: float) -> int:
    total, seen = sum(histogram), 0
    for index, count in enumerate(histogram):
        seen += count
        if seen >= total * share:
            return index
    return 0
