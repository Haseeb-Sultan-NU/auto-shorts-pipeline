"""
utils/font_manager.py — Local Font Directory Scanner

Scans the project's `fonts/` directory for .ttf and .otf files, provides
a clean display-name mapping, and handles fallback to system fonts when
the directory is empty.
"""

import os
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Font directory — relative to project root
# ---------------------------------------------------------------------------
FONT_DIR = Path(os.path.abspath("fonts"))

# System fallbacks when no local fonts are available
SYSTEM_FALLBACKS: list[dict[str, str]] = [
    {"display_name": "Impact",      "css_family": "'Impact', sans-serif",       "file_path": ""},
    {"display_name": "Arial Black", "css_family": "'Arial Black', sans-serif",  "file_path": ""},
]

SUPPORTED_EXTENSIONS = {".ttf", ".otf"}


class FontEntry(NamedTuple):
    """Represents a single discovered font."""
    display_name: str   # e.g. "FeastOfFleshBb-AVm"
    file_path: str      # Absolute path (forward slashes for cross-compat)
    css_family: str     # CSS font-family value for @font-face usage


def scan_fonts() -> tuple[list[FontEntry], bool]:
    """
    Scan the local fonts directory and return available fonts.

    Returns
    -------
    fonts : list[FontEntry]
        List of discovered font entries (local fonts first, then fallbacks
        if no local fonts exist).
    is_fallback : bool
        True if we're using system fallbacks because no local fonts were found.
    """

    # Ensure the directory exists
    FONT_DIR.mkdir(parents=True, exist_ok=True)

    local_fonts: list[FontEntry] = []

    for f in sorted(FONT_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            stem = f.stem  # filename without extension
            # Use forward slashes so paths work in CSS url() and ImageMagick
            abs_path = str(f.resolve()).replace("\\", "/")
            css_family = f"'sf-{stem}', sans-serif"
            local_fonts.append(FontEntry(
                display_name=stem,
                file_path=abs_path,
                css_family=css_family,
            ))

    if local_fonts:
        return local_fonts, False

    # Fallback to system fonts
    fallback_entries = [
        FontEntry(
            display_name=fb["display_name"],
            file_path="",
            css_family=fb["css_family"],
        )
        for fb in SYSTEM_FALLBACKS
    ]
    return fallback_entries, True


def get_font_by_name(display_name: str, fonts: list[FontEntry]) -> FontEntry | None:
    """Look up a FontEntry by its display name."""
    for font in fonts:
        if font.display_name == display_name:
            return font
    return fonts[0] if fonts else None
