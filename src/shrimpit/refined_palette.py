"""Palette building with the bundled ExoQuant engine (MIT), without a Qt dependency.

``PaletteBuilder`` wraps one image:

- ``build()`` feeds ExoQuant a histogram made of a regular grid sample of at most ``SAMPLE_SIDE`` ×
  ``SAMPLE_SIDE`` pixels, plus any pixels fed back so far, splits it into at most 256 colors and maps
  every pixel of the image to its nearest entry, without dithering;
- ``refine(candidate)`` feeds back the pixels whose error exceeds ``REFINE_ERROR`` levels on a white
  or black background (at most ``REFINE_BUDGET`` per call). Colors that were rare in the sample, such
  as a thin outline or a small highlight, then weigh enough to receive their own palette entries.

``png_compression`` decides how many passes to run and whether a result is kept.

Pixels that are fully transparent in the source are mapped to a reserved palette entry whose opacity
is zero, so the background stays invisible whatever the quantizer does.

The native library is optional: when ``exoquant.dll`` is missing or cannot be loaded, ``builder``
returns ``None`` and the other PNG encodings remain available. The C code keeps no global state, so
several images can be processed at once from different threads.
"""

import ctypes
import itertools
import logging
import sys
from array import array
from functools import cache
from pathlib import Path

from PIL import Image, ImageChops

NATIVE_LIBRARY = Path(__file__).with_name("native") / "exoquant.dll"
# Side of the sampling grid (see the README for the measurements).
SAMPLE_SIDE = 192
# Error, in 0-255 levels on the worse background, above which a pixel is fed back, and the largest
# number of such pixels added by one refinement.
REFINE_ERROR = 16
REFINE_BUDGET = 32_768
PALETTE_SIZE = 256
# Index of the fully transparent entry kept for pixels whose opacity is zero.
TRANSPARENT_INDEX = PALETTE_SIZE - 1
# ExoQuant counts pixels with a C int.
MAX_PIXELS = 2**31 - 1
# Rows compared at once when looking for badly mapped pixels.
BAND_ROWS = 256


@cache
def _library() -> ctypes.CDLL | None:
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.CDLL(str(NATIVE_LIBRARY))
    except OSError:
        logging.getLogger(__name__).info("ExoQuant engine unavailable: %s", NATIVE_LIBRARY)
        return None
    pointer, integer, data = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
    signatures = {
        "exq_init": ([], pointer),
        "exq_failed": ([pointer], integer),
        "exq_feed": ([pointer, data, integer], None),
        "exq_quantize": ([pointer, integer], None),
        "exq_get_palette": ([pointer, pointer, integer], None),
        "exq_map_image": ([pointer, integer, data, pointer], None),
        "exq_map_image_ordered": ([pointer, integer, integer, data, pointer], None),
        "exq_free": ([pointer], None),
    }
    try:
        for name, (arguments, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
    except AttributeError:
        logging.getLogger(__name__).warning("ExoQuant engine is incomplete: %s", NATIVE_LIBRARY)
        return None
    return library


def available() -> bool:
    return _library() is not None


def builder(image: Image.Image, sample_side: int = SAMPLE_SIDE, dither: bool = False):
    """Return a ``PaletteBuilder`` for ``image``, or ``None`` when the native engine is unavailable.

    ``sample_side`` and ``dither`` (2 × 2 ordered pattern) exist for measurements; the application
    uses the defaults.
    """
    library = _library()
    if library is None or image.width * image.height > MAX_PIXELS or 0 in image.size:
        return None
    return PaletteBuilder(library, image, sample_side, dither)


class PaletteBuilder:
    def __init__(self, library: ctypes.CDLL, image: Image.Image, sample_side: int, dither: bool):
        self.library = library
        self.dither = dither
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        hidden = alpha.point(lambda value: 255 if value == 0 else 0)
        if hidden.getbbox() is None:
            self.hidden = None
        else:
            self.hidden = hidden
            # Colors under alpha 0 are invisible: give them all the same value before sampling.
            cleared = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
            cleared.paste(rgba, mask=alpha.point(lambda value: 255 if value else 0))
            rgba = cleared
        self.rgba = rgba
        sample = rgba.resize(
            (min(sample_side, rgba.width), min(sample_side, rgba.height)), Image.Resampling.NEAREST
        )
        self.feeds = [sample.tobytes()]

    def build(self) -> Image.Image:
        """Build a palette from the sample and the pixels fed back, and map the image to it.

        Raise ``MemoryError`` when the engine cannot allocate its histogram.
        """
        library, rgba = self.library, self.rgba
        limit = TRANSPARENT_INDEX if self.hidden is not None else PALETTE_SIZE
        # Ask for no more entries than distinct colors: ExoQuant cannot split a single color.
        count = min(
            limit, len(set(itertools.chain.from_iterable(memoryview(f).cast("I") for f in self.feeds)))
        )
        pixels = rgba.tobytes()
        indices = bytearray(rgba.width * rgba.height)
        palette = bytearray(PALETTE_SIZE * 4)
        output = (ctypes.c_char * len(indices)).from_buffer(indices)
        palette_buffer = (ctypes.c_char * len(palette)).from_buffer(palette)
        context = library.exq_init()
        if not context:
            raise MemoryError("Cannot allocate the ExoQuant context")
        try:
            for feed in self.feeds:
                library.exq_feed(context, feed, len(feed) // 4)
            library.exq_quantize(context, count)
            if library.exq_failed(context):
                raise MemoryError("Cannot allocate the ExoQuant histogram")
            library.exq_get_palette(context, palette_buffer, count)
            if self.dither:
                library.exq_map_image_ordered(context, rgba.width, rgba.height, pixels, output)
            else:
                library.exq_map_image(context, rgba.width * rgba.height, pixels, output)
        finally:
            library.exq_free(context)
        del output, palette_buffer, pixels
        # Entries past ``count`` stay at zero, so the reserved last entry is fully transparent.
        candidate = Image.frombytes("P", rgba.size, bytes(indices))
        candidate.putpalette(bytes(palette), rawmode="RGBA")
        if self.hidden is not None:
            candidate.paste(TRANSPARENT_INDEX, mask=self.hidden)
        return candidate

    def refine(self, candidate: Image.Image) -> bool:
        """Feed back the pixels of ``candidate`` whose error exceeds ``REFINE_ERROR``.

        Errors are the largest channel difference on a white and on a black background, as in
        ``png_compression.measure``. Return ``False`` when no pixel needs it.
        """
        rgba = self.rgba
        width, height = rgba.size
        found = array("I")
        for top in range(0, height, BAND_ROWS):
            box = (0, top, width, min(top + BAND_ROWS, height))
            source = rgba.crop(box)
            result = candidate.crop(box).convert("RGBA")
            error = None
            for color in ("white", "black"):
                background = Image.new("RGBA", source.size, color)
                difference = ImageChops.difference(
                    Image.alpha_composite(background, source).convert("RGB"),
                    Image.alpha_composite(background, result).convert("RGB"),
                )
                red, green, blue = difference.split()
                channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
                error = channel if error is None else ImageChops.lighter(error, channel)
            selected = error.point(lambda value: 1 if value > REFINE_ERROR else 0).tobytes()
            found.extend(itertools.compress(memoryview(source.tobytes()).cast("I"), selected))
        if not found:
            return False
        # A regular stride keeps the selection deterministic and spread over the whole image.
        step = -(-len(found) // REFINE_BUDGET)
        self.feeds.append(found[::step].tobytes())
        return True
