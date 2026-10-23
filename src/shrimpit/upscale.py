"""Resize photos, illustrations, and pixel art without Qt."""

from dataclasses import dataclass
from math import ceil, isfinite

from PIL import Image, ImageFilter

from shrimpit.errors import ConversionError


@dataclass(frozen=True)
class UpscaleSettings:
    mode: str = "photo"
    illustration_filter: str = "bicubic"
    sharpen: bool = True
    radius: float = 0.8
    amount: int = 40
    threshold: int = 3

    def validate(self):
        if self.mode not in ("photo", "illustration", "pixel_art"):
            raise ConversionError("Choisissez Photographie, Illustration ou Pixel Art.")
        if self.illustration_filter not in ("bicubic", "lanczos"):
            raise ConversionError("Choisissez Bicubic ou Lanczos pour l’illustration.")
        if type(self.sharpen) is not bool:
            raise ConversionError("L’activation de la netteté doit être un booléen.")
        if type(self.radius) not in (int, float) or not isfinite(self.radius) or not 0.5 <= self.radius <= 2:
            raise ConversionError("Le rayon de netteté doit être compris entre 0,5 et 2 pixels.")
        if type(self.amount) is not int or not 0 <= self.amount <= 100:
            raise ConversionError("L’intensité de netteté doit être comprise entre 0 et 100 %.")
        if type(self.threshold) is not int or not 0 <= self.threshold <= 10:
            raise ConversionError("Le seuil de netteté doit être compris entre 0 et 10.")


def resize_image(image: Image.Image, size: tuple[int, int], settings: UpscaleSettings) -> Image.Image:
    """Resize normalized RGB/RGBA pixels and protect alpha during sharpening."""
    settings.validate()
    if settings.mode == "pixel_art":
        return image.resize(size, Image.Resampling.NEAREST)
    resampling = Image.Resampling.LANCZOS
    if settings.mode == "illustration" and settings.illustration_filter == "bicubic":
        resampling = Image.Resampling.BICUBIC
    # Pillow resizes RGBA through premultiplied alpha to avoid hidden-color fringes.
    resized = image.resize(size, resampling)
    if settings.mode != "photo" or not settings.sharpen or settings.amount == 0:
        return resized
    rgb = resized.convert("RGB")
    sharpened = rgb.filter(ImageFilter.UnsharpMask(settings.radius, settings.amount, settings.threshold))
    if resized.mode == "RGBA":
        alpha = resized.getchannel("A")
        # Keep sharpening away from transparent edges and leave alpha unchanged.
        opaque = alpha.point(lambda value: 255 if value == 255 else 0)
        opaque = opaque.filter(ImageFilter.MinFilter(2 * ceil(settings.radius * 3) + 1))
        sharpened = Image.composite(sharpened, rgb, opaque)
        sharpened.putalpha(alpha)
    return sharpened
