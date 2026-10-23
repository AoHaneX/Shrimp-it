"""Measure the current compression engine without modifying input images."""

import argparse
import csv
import hashlib
import json
import math
import platform
from pathlib import Path
from time import perf_counter

import PIL
from PIL import Image, ImageChops, ImageOps, ImageStat

from shrimpit import engine

FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def composite(image, color):
    background = Image.new("RGBA", image.size, color)
    return Image.alpha_composite(background, image).convert("RGB")


def psnr(reference, actual):
    difference = ImageChops.difference(reference, actual)
    mse = sum(ImageStat.Stat(difference).sum2) / (reference.width * reference.height * 3)
    return "exact" if mse == 0 else round(10 * math.log10(255**2 / mse), 3)


def main():
    parser = argparse.ArgumentParser(description="Vérifie et mesure la compression locale de Shrimp'It.")
    parser.add_argument("--output", type=Path, required=True, help="Nouveau dossier de résultats")
    parser.add_argument("--inputs", type=Path, nargs="+", help="Images à mesurer ; sinon les assets PNG")
    args = parser.parse_args()
    sources = args.inputs or sorted((Path(engine.__file__).parent / "assets").rglob("*.png"))
    if not sources:
        parser.error("Aucune image à vérifier.")
    if args.output.exists():
        parser.error("Le dossier de résultats existe déjà. Choisissez un nouveau nom.")
    args.output.mkdir(parents=True)
    converted = args.output / "converted"
    converted.mkdir()
    rows, inputs, errors = [], [], []
    for index, source in enumerate(sources, start=1):
        source = source.resolve()
        before = digest(source)
        inputs.append({"index": index, "name": source.name, "sha256": before})
        with Image.open(source) as opened:
            reference = ImageOps.exif_transpose(opened).convert("RGBA")
        for fmt, extension in FORMATS.items():
            qualities = (80,) if fmt == "PNG" else (1, 40, 60, 80, 95)
            for quality in qualities:
                target = converted / f"{index:02d}-{source.stem}-{fmt.lower()}-q{quality}.{extension}"
                started = perf_counter()
                result = engine.convert_image(source, target, fmt, quality)
                elapsed = perf_counter() - started
                with Image.open(target) as output:
                    output.load()
                    actual_format = output.format
                    actual = output.convert("RGBA")
                dimensions_ok = actual.size == reference.size == result.input_size == result.output_size
                alpha_ok = fmt == "JPEG" or (
                    actual.getchannel("A").tobytes() == reference.getchannel("A").tobytes()
                )
                pixels_exact = actual.tobytes() == reference.tobytes()
                valid = dimensions_ok and alpha_ok and actual_format == fmt and (fmt != "PNG" or pixels_exact)
                if not valid:
                    errors.append(target.name)
                row = {
                    "source": source.name,
                    "output": target.name,
                    "format": fmt,
                    "quality": quality,
                    "input_bytes": result.input_bytes,
                    "output_bytes": result.output_bytes,
                    "savings_percent": round(result.savings_percent, 3),
                    "width": actual.width,
                    "height": actual.height,
                    "dimensions_ok": dimensions_ok,
                    "alpha_ok": alpha_ok,
                    "rgba_exact": pixels_exact,
                    "psnr_white_db": psnr(composite(reference, "white"), composite(actual, "white")),
                    "psnr_navy_db": "n/a"
                    if fmt == "JPEG"
                    else psnr(composite(reference, "#041d34"), composite(actual, "#041d34")),
                    "seconds": round(elapsed, 4),
                    "valid": valid,
                }
                rows.append(row)
        if digest(source) != before:
            errors.append(f"Source changed: {source.name}")
        print(f"{index}/{len(sources)} : {source.name}", flush=True)
    with (args.output / "measurements.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "python": platform.python_version(),
        "pillow": PIL.__version__,
        "engine_sha256": digest(Path(engine.__file__)),
        "inputs": inputs,
        "conversions": len(rows),
        "errors": errors,
        "note": "PSNR compares decoded pixels on white/navy, not color-managed display or human perception.",
        "totals_at_quality_80": {},
    }
    for fmt in FORMATS:
        selected = [row for row in rows if row["format"] == fmt and row["quality"] == 80]
        input_bytes = sum(row["input_bytes"] for row in selected)
        output_bytes = sum(row["output_bytes"] for row in selected)
        summary["totals_at_quality_80"][fmt] = {
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
            "savings_percent": round((1 - output_bytes / input_bytes) * 100, 3),
        }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary["totals_at_quality_80"], indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
