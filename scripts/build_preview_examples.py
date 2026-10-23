"""Build the bundled comparison examples using the application's image engine."""

import argparse
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

from shrimpit.engine import convert_image, upscale_image
from shrimpit.processing import image_info


def main():
    parser = argparse.ArgumentParser(description="Rebuild Shrimp'It preview examples from one source image.")
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    image_info(args.source)
    target = Path(__file__).resolve().parents[1] / "src/shrimpit/assets/examples"
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="shrimpit-examples-") as temporary:
        folder = Path(temporary)
        with Image.open(args.source) as source:
            original = ImageOps.exif_transpose(source).convert("RGB")
        original.thumbnail((768, 512), Image.Resampling.LANCZOS)
        original.save(folder / "compression-before.png", optimize=True)
        convert_image(folder / "compression-before.png", folder / "compression-after.jpg", "JPEG", 80)
        small = original.copy()
        small.thumbnail((384, 256), Image.Resampling.LANCZOS)
        small.save(folder / "enlargement-before.png", optimize=True)
        upscale_image(folder / "enlargement-before.png", folder / "enlargement-after.png", 2, "PNG", 95)
        for path in folder.iterdir():
            shutil.copy2(path, target / path.name)
    print(f"Examples saved to {target}")


if __name__ == "__main__":
    main()
