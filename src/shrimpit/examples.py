"""Read bundled demonstration previews without adding user files or history."""

from functools import lru_cache

from shrimpit.processing import image_info, thumbnail
from shrimpit.resources import ASSETS


@lru_cache(maxsize=2)
def example_preview(enlarge):
    prefix = "enlargement" if enlarge else "compression"
    before = ASSETS / "examples" / f"{prefix}-before.png"
    after = ASSETS / "examples" / (f"{prefix}-after.png" if enlarge else f"{prefix}-after.jpg")
    return thumbnail(before), thumbnail(after), image_info(before), image_info(after)
