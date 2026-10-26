"""Central paths for packaged assets and local user data."""

import os
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
BACKGROUND = ASSETS / "backgrounds/ocean.png"
SIDEBAR_MASCOT = ASSETS / "backgrounds/sidebar-shrimpy.png"
SHRIMPY_ICON = ASSETS / "branding/shrimpy.png"
TITLE_FONT = ASSETS / "fonts/chakra-petch-bold.ttf"
FINISH_SOUND = ASSETS / "sounds/finish.ogg"
PROCESSING_ANIMATIONS = {
    "pixel": ASSETS / "animations/processing-pixel.gif",
    "smooth": ASSETS / "animations/processing-smooth.gif",
}

SIDEBAR_EXPANDED_WIDTH = 320
SIDEBAR_COLLAPSED_WIDTH = 68


def data_directory() -> Path:
    """Folder holding the history and the logs, removable to reset the application."""
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "BlueShrimp" / "Shrimpit"
