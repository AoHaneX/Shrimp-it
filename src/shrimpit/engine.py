"""Image processing without a Qt dependency."""

import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageMath, ImageOps, UnidentifiedImageError

from shrimpit.errors import ConversionError, describe_error
from shrimpit.filenames import validate_filename
from shrimpit.limits import check_export_memory, check_output_size
from shrimpit.upscale import UpscaleSettings, resize_image

EXTENSIONS = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}, "WEBP": {".webp"}}
MAX_PIXELS = 25_000_000
HIGH_DEPTH_GRAYSCALE = {"I", "I;16", "I;16L", "I;16B", "I;16N"}


def to_8_bit(image: Image.Image) -> Image.Image:
    """Scale 16-bit grayscale to 8 bits; a plain conversion would clip it to white."""
    if image.mode not in HIGH_DEPTH_GRAYSCALE:
        return image
    values = image.convert("I")
    gray = values.point(lambda value: value / 256).convert("L")
    gray.info.pop("transparency", None)
    transparent = image.info.get("transparency")
    if isinstance(transparent, int):
        # PNG stores one transparent 16-bit gray level instead of an alpha channel.
        alpha = ImageMath.lambda_eval(lambda args: (args["values"] != transparent) * 255, values=values)
        gray.putalpha(alpha.convert("L"))
    return gray


@dataclass(frozen=True)
class ConversionResult:
    destination: Path
    input_bytes: int
    output_bytes: int
    input_size: tuple[int, int]
    output_size: tuple[int, int]

    @property
    def savings_percent(self) -> float:
        return (1 - self.output_bytes / self.input_bytes) * 100


def convert_image(
    source: str | Path,
    destination: str | Path,
    output_format: str = "JPEG",
    quality: int = 80,
) -> ConversionResult:
    """Compress or convert a static image without resizing it."""
    return _process_image(source, destination, output_format, quality, scale=1)


def upscale_image(
    source: str | Path,
    destination: str | Path,
    scale: int = 2,
    output_format: str = "PNG",
    quality: int = 95,
    size: tuple[int, int] | None = None,
    *,
    settings: UpscaleSettings = UpscaleSettings(),
) -> ConversionResult:
    """Enlarge an image with the selected mode and optional photo sharpening."""
    if not isinstance(settings, UpscaleSettings):
        raise ConversionError("Réglages d’agrandissement invalides.")
    settings.validate()
    if type(scale) is not int or scale not in (2, 3, 4):
        raise ConversionError("Choisissez un agrandissement ×2, ×3 ou ×4.")
    if size is not None and (
        not isinstance(size, tuple)
        or len(size) != 2
        or any(type(value) is not int or value <= 0 for value in size)
    ):
        raise ConversionError("Les dimensions doivent être deux entiers positifs.")
    if settings.mode == "pixel_art" and (size is not None or str(output_format).upper() != "PNG"):
        raise ConversionError("Le mode Pixel Art utilise PNG et les facteurs entiers ×2, ×3 ou ×4.")
    return _process_image(source, destination, output_format, quality, scale, size, settings)


def _process_image(
    source: str | Path,
    destination: str | Path,
    output_format: str,
    quality: int,
    scale: int,
    size: tuple[int, int] | None = None,
    upscale_settings: UpscaleSettings | None = None,
) -> ConversionResult:
    """Share validation, image preparation, and safe output creation."""
    source, destination = Path(source), Path(destination)
    validate_filename(destination.name)
    if not isinstance(output_format, str):
        raise ConversionError("Choisissez JPEG, PNG ou WebP.")
    output_format = output_format.upper()
    if output_format not in EXTENSIONS:
        raise ConversionError("Choisissez JPEG, PNG ou WebP.")
    if type(quality) is not int or not 1 <= quality <= 95:
        raise ConversionError("La qualité doit être un entier entre 1 et 95.")
    if destination.suffix.lower() not in EXTENSIONS[output_format]:
        raise ConversionError("L'extension de sortie ne correspond pas au format choisi.")
    if source.resolve() == destination.resolve() or destination.exists():
        raise ConversionError("Ce fichier existe déjà. Choisissez un nouveau nom.")

    created = False
    try:
        input_bytes = source.stat().st_size
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as original:
                if original.format not in EXTENSIONS:
                    raise ConversionError("Formats d'entrée acceptés : JPEG, PNG et WebP.")
                if getattr(original, "n_frames", 1) != 1:
                    raise ConversionError("Les images animées ne sont pas prises en charge.")
                if original.width * original.height > MAX_PIXELS:
                    raise ConversionError("Les images d'entrée sont limitées à 25 mégapixels.")
                width, height = original.size
                if original.getexif().get(274) in (5, 6, 7, 8):
                    width, height = height, width
                target_size = size or (width * scale, height * scale)
                if size is not None and (size[0] < width or size[1] < height or size == (width, height)):
                    raise ConversionError("Les dimensions personnalisées doivent agrandir l'image.")
                if upscale_settings is not None:
                    check_output_size(target_size, output_format)
                    check_export_memory((width, height), target_size, upscale_settings)
                oriented = to_8_bit(ImageOps.exif_transpose(original))
                input_size = oriented.size
                has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                pixels = oriented.convert("RGBA" if has_alpha else "RGB")
                if output_format == "JPEG" and has_alpha and upscale_settings is None:
                    background = Image.new("RGB", pixels.size, "white")
                    background.paste(pixels, mask=pixels.getchannel("A"))
                    pixels = background
                # Create a new image to remove EXIF, GPS, text, and ICC metadata.
                clean = Image.frombytes(pixels.mode, pixels.size, pixels.tobytes())

        if target_size != clean.size:
            clean = resize_image(clean, target_size, upscale_settings or UpscaleSettings(sharpen=False))
        if upscale_settings is not None and output_format == "JPEG" and clean.mode == "RGBA":
            background = Image.new("RGB", clean.size, "white")
            background.paste(clean, mask=clean.getchannel("A"))
            clean = background

        options = {"optimize": True} if output_format == "PNG" else {"quality": quality}
        if output_format == "JPEG":
            options.update(optimize=True, progressive=True)
        elif output_format == "WEBP":
            options.update(method=4)

        # Exclusive mode also protects files created after the initial check.
        with destination.open("xb") as stream:
            created = True
            clean.save(stream, format=output_format, **options)
        return ConversionResult(destination, input_bytes, destination.stat().st_size, input_size, clean.size)
    except (
        ConversionError,
        OSError,
        ValueError,
        MemoryError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError as cleanup_error:
                raise ConversionError(
                    f"Échec de l’écriture ; un fichier incomplet reste à supprimer : {destination}"
                ) from cleanup_error
        if isinstance(exc, ConversionError):
            raise
        if isinstance(exc, MemoryError):
            raise ConversionError(
                "Mémoire insuffisante. Choisissez une image ou une taille plus petite."
            ) from exc
        raise ConversionError(f"Impossible de convertir l'image : {describe_error(exc)}") from exc
