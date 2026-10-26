"""Bound large exports using pixel count and available physical memory."""

import ctypes
import sys

from shrimpit.errors import ConversionError
from shrimpit.upscale import UpscaleSettings

MAX_INPUT_PIXELS = 25_000_000
MAX_OUTPUT_PIXELS = 400_000_000
# Outputs up to the input ceiling are previewed automatically and need no memory check.
MAX_PREVIEW_PIXELS = MAX_INPUT_PIXELS


def available_memory_bytes() -> int | None:
    """Read available Windows RAM without an additional dependency."""
    if sys.platform != "win32":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
            (name, ctypes.c_uint64)
            for name in (
                "total",
                "available",
                "page_total",
                "page_available",
                "virtual_total",
                "virtual_available",
                "extended",
            )
        ]

    try:
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        query = ctypes.windll.kernel32.GlobalMemoryStatusEx
        query.argtypes = [ctypes.POINTER(MemoryStatus)]
        query.restype = ctypes.c_int
        if query(ctypes.byref(status)):
            return status.available
    except (AttributeError, OSError):
        pass
    return None


def check_output_size(size: tuple[int, int], output_format: str):
    width, height = size
    pixels = width * height
    if pixels > MAX_OUTPUT_PIXELS:
        raise ConversionError(
            f"Le résultat dépasserait {MAX_OUTPUT_PIXELS / 1_000_000:g} mégapixels : "
            f"{width} × {height} ({pixels / 1_000_000:.1f} MP). "
            "Choisissez un facteur plus petit ou des dimensions personnalisées."
        )
    if output_format == "WEBP" and max(size) > 16383:
        raise ConversionError(
            f"WebP accepte au maximum 16 383 pixels par côté ; résultat demandé : {width} × {height}. "
            "Choisissez PNG ou des dimensions plus petites."
        )


def check_export_memory(
    source_size: tuple[int, int], target_size: tuple[int, int], settings: UpscaleSettings
):
    """Reserve headroom for Pillow buffers; this estimate is not a guarantee."""
    target_pixels = target_size[0] * target_size[1]
    if target_pixels <= MAX_PREVIEW_PIXELS:
        return
    available = available_memory_bytes()
    if available is None:
        raise ConversionError(
            "Mémoire disponible impossible à vérifier pour ce grand export. "
            "Choisissez une sortie de 25 MP maximum."
        )
    bytes_per_pixel = 12 if settings.mode == "pixel_art" else 20
    if settings.mode == "photo" and settings.sharpen and settings.amount:
        bytes_per_pixel = 32
    estimated = target_pixels * bytes_per_pixel + source_size[0] * source_size[1] * 16 + 128 * 1024**2
    if estimated > available * 0.8:
        raise ConversionError(
            f"Sortie {target_size[0]} × {target_size[1]} ({target_pixels / 1_000_000:.1f} MP) : "
            f"environ {estimated / 1024**3:.1f} Gio de mémoire de travail estimés, "
            f"{available / 1024**3:.1f} Gio de RAM disponibles (20 % gardés libres). "
            "Fermez d’autres applications ou réduisez le facteur."
        )
