"""Image metadata, previews, and export planning without Qt."""

import warnings
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from shrimpit.engine import EXTENSIONS, MAX_PIXELS, ConversionError, convert_image, upscale_image
from shrimpit.errors import describe_error
from shrimpit.filenames import validate_filename
from shrimpit.upscale import UpscaleSettings


@dataclass(frozen=True)
class Options:
    enlarge: bool = False
    output_format: str = "JPEG"
    quality: int = 80
    scale: int = 2
    size: tuple[int, int] | None = None
    keep_ratio: bool = False
    upscale: UpscaleSettings = UpscaleSettings()


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    size: tuple[int, int]
    byte_count: int
    format: str


READ_ERRORS = (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning)


def image_info(path: Path) -> ImageInfo:
    """Read the header and validate limits before decoding pixels."""
    if path.is_dir():
        # Windows reports folders as permission errors when Pillow opens them.
        raise ConversionError(describe_error(IsADirectoryError()))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ConversionError("Format non pris en charge : JPEG, PNG ou WebP attendu.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ConversionError("Les images animées ne sont pas prises en charge.")
                if image.width * image.height > MAX_PIXELS:
                    raise ConversionError("Cette image dépasse 25 mégapixels.")
                size = image.size
                if image.getexif().get(274) in (5, 6, 7, 8):
                    size = size[::-1]
                return ImageInfo(path, size, path.stat().st_size, image.format)
    except READ_ERRORS as exc:
        raise ConversionError(describe_error(exc)) from exc


def thumbnail(path: Path, pixel_art: bool = False) -> bytes:
    """Return a bounded PNG thumbnail for display in the GUI."""
    image_info(path)
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((640, 420), Image.Resampling.NEAREST if pixel_art else Image.Resampling.LANCZOS)
            stream = BytesIO()
            image.convert("RGBA").save(stream, format="PNG")
            return stream.getvalue()
    except READ_ERRORS as exc:
        raise ConversionError(describe_error(exc)) from exc


def options_for_source(source: Path, options: Options, source_size=None) -> Options:
    """Apply a custom width to each image without changing its proportions."""
    if options.enlarge and options.size and options.keep_ratio:
        width, height = source_size or image_info(source).size
        target_width = options.size[0]
        target_height = max(1, round(target_width * height / width))
        return replace(options, size=(target_width, target_height), keep_ratio=False)
    return options


def process(source: Path, destination: Path, options: Options):
    options = options_for_source(source, options)
    if options.enlarge:
        return upscale_image(
            source,
            destination,
            options.scale,
            options.output_format,
            options.quality,
            options.size,
            settings=options.upscale,
        )
    return convert_image(source, destination, options.output_format, options.quality)


def suggested_name(source: Path, options: Options, source_size=None) -> str:
    options = options_for_source(source, options, source_size)
    extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[options.output_format]
    suffix = "-min"
    if options.enlarge:
        suffix = f"-{options.size[0]}x{options.size[1]}" if options.size else f"-x{options.scale}"
    return source.stem + suffix + extension


def export_plan(sources: list[Path], folder: Path, names: dict[Path, str], options: Options):
    """Avoid collisions within a batch and with files already on disk."""
    reserved = set()
    plan = []
    for source in sources:
        name = names[source] if source in names else suggested_name(source, options)
        validate_filename(name)
        if Path(name).suffix.lower() not in EXTENSIONS[options.output_format]:
            raise ConversionError("L’extension du nom de sortie doit correspondre au format choisi.")
        destination = folder / name
        index = 2
        while destination.exists() or str(destination).casefold() in reserved:
            destination = folder / f"{Path(name).stem}-{index}{Path(name).suffix}"
            index += 1
        reserved.add(str(destination).casefold())
        plan.append((source, destination))
    return plan


def expand_name_template(source: Path, template: str, output_format: str) -> str:
    """Expand the original stem without interpreting paths or executable expressions."""
    if "[" in template.replace("[original name]", "") or "]" in template.replace("[original name]", ""):
        raise ConversionError("Utilisez [original name] pour reprendre le nom de chaque image.")
    name = template.replace("[original name]", source.stem)
    validate_filename(name)
    if Path(name).suffix.lower() not in EXTENSIONS[output_format]:
        raise ConversionError("L’extension du modèle doit correspondre au format de sortie.")
    return name


def readable_size(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.2f} Mo".replace(".", ",")
    return f"{count / 1_000:.1f} Ko".replace(".", ",")
