"""Portable output filename validation, including Windows device names."""

from shrimpit.errors import ConversionError

RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


def validate_filename(name: str) -> None:
    if not name or name in {".", ".."} or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name):
        raise ConversionError(
            "Le nom de sortie doit être un nom de fichier sans chemin ni caractère interdit."
        )
    if name.endswith((" ", ".")):
        raise ConversionError("Le nom ne doit pas se terminer par un espace ou un point.")
    if name.split(".", 1)[0].rstrip(" ").upper() in RESERVED:
        raise ConversionError("Ce nom est réservé par Windows. Choisissez un autre nom.")
    if len(name.encode("utf-16-le")) // 2 > 255:
        raise ConversionError("Le nom du fichier est trop long (255 caractères maximum).")
