"""Errors that can be displayed to the user."""

import errno

from PIL import Image, UnidentifiedImageError


class ConversionError(Exception):
    """An invalid image operation or an export failure."""


def describe_error(error: BaseException) -> str:
    """Explain Pillow and system failures in French; technical details stay in the logs."""
    if isinstance(error, UnidentifiedImageError):
        return "Fichier non reconnu comme image JPEG, PNG ou WebP, ou fichier endommagé."
    if isinstance(error, (Image.DecompressionBombError, Image.DecompressionBombWarning)):
        return "Image trop grande pour être ouverte en sécurité."
    if isinstance(error, FileNotFoundError):
        return "Fichier ou dossier introuvable."
    if isinstance(error, IsADirectoryError):
        return "Un dossier a été fourni à la place d’une image."
    if isinstance(error, PermissionError):
        return "Accès refusé : vérifiez les droits du fichier ou du dossier."
    if isinstance(error, OSError) and error.errno == errno.ENOSPC:
        return "Espace disque insuffisant."
    if isinstance(error, OSError) and "truncated" in str(error):
        return "Image incomplète ou endommagée."
    if isinstance(error, OSError):
        return "Lecture ou écriture impossible : fichier endommagé ou inaccessible."
    return "Image endommagée ou non prise en charge."
