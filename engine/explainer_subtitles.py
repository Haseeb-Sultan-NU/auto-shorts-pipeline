"""
engine/explainer_subtitles.py — Subtitle Burn-In Pass (Decoupled)

Takes a clean, pre-rendered CFR MP4 and burns SRT subtitles onto it
in a separate FFmpeg invocation.  This decouples subtitle rendering
from the image-concat compositor, eliminating VFR-related subtitle
drops and Windows colon-in-path parsing errors.

Usage::

    burn_subtitles_to_video(
        input_mp4="clean.mp4",
        srt_path="subtitles.srt",
        output_mp4="final.mp4",
        config=sidebar_config,
    )
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_FONT = "Burbank Big Regular Bold"
_DEFAULT_FONT_SIZE = 90
_DEFAULT_MARGIN_V = 150
_DEFAULT_PRIMARY = "&H0004EBFF"
_DEFAULT_OUTLINE = "&H00000000"
_DEFAULT_BACK = "&H80000000"


# ═══════════════════════════════════════════════════════════════════════════
# STYLE BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _hex_to_ass_color(hex_color: str) -> str:
    """Convert CSS hex (#RRGGBB) to ASS colour (&H00BBGGRR)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "&H00FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def _build_force_style(config: Optional[dict] = None) -> str:
    """Build an ASS ``force_style`` string from a sidebar config dict.

    Keys (all optional):
        selected_font_name    – str
        font_size             – int (sidebar scale 30–280, mapped /3)
        font_color            – CSS hex (#RRGGBB)
        stroke_color          – CSS hex (#RRGGBB)
        subtitle_vertical_pct – int 0–100
    """
    if not config:
        return (
            f"FontName={_DEFAULT_FONT},"
            f"FontSize={_DEFAULT_FONT_SIZE},"
            f"PrimaryColour={_DEFAULT_PRIMARY},"
            f"OutlineColour={_DEFAULT_OUTLINE},"
            f"BackColour={_DEFAULT_BACK},"
            f"Outline=3,Shadow=1,Bold=1,"
            f"Alignment=2,MarginV={_DEFAULT_MARGIN_V}"
        )

    font_name = config.get("selected_font_name") or _DEFAULT_FONT
    raw_size = config.get("font_size", 180)
    font_size = max(48, min(120, int(raw_size / 3)))
    primary = _hex_to_ass_color(config.get("font_color", "#FFEB04"))
    outline = _hex_to_ass_color(config.get("stroke_color", "#000000"))
    vert_pct = config.get("subtitle_vertical_pct", 72)
    margin_v = max(60, min(300, int(1920 * (1.0 - vert_pct / 100.0) - 100)))

    style = (
        f"FontName={font_name},"
        f"FontSize={font_size},"
        f"PrimaryColour={primary},"
        f"OutlineColour={outline},"
        f"BackColour={_DEFAULT_BACK},"
        f"Outline=3,Shadow=1,Bold=1,"
        f"Alignment=2,MarginV={margin_v}"
    )
    print(f"  Subtitle style: {style}")
    return style


# ═══════════════════════════════════════════════════════════════════════════
# SUBTITLE BURN-IN
# ═══════════════════════════════════════════════════════════════════════════

def burn_subtitles_to_video(
    input_mp4: str,
    srt_path: str,
    output_mp4: str,
    config: Optional[dict] = None,
) -> str:
    """Burn SRT subtitles onto a pre-rendered video in a separate pass.

    The function copies both the input video and the SRT file into the
    output directory under simple basenames, then runs FFmpeg with
    ``cwd=output_dir``.  All filter paths are strictly relative,
    completely bypassing Windows drive-letter colon parsing bugs.

    Parameters
    ----------
    input_mp4 : str
        Path to the clean (subtitle-free) video.
    srt_path : str
        Path to the ``.srt`` subtitle file.
    output_mp4 : str
        Destination path for the final subtitled MP4.
    config : dict, optional
        Sidebar subtitle styling config.

    Returns
    -------
    str
        Absolute path to the rendered output file.

    Raises
    ------
    FileNotFoundError
        If input video or SRT file is missing.
    ValueError
        If the SRT file is empty.
    RuntimeError
        If FFmpeg returns a non-zero exit code.
    """
    if not os.path.isfile(input_mp4):
        raise FileNotFoundError(f"Input video not found: {input_mp4}")
    if not os.path.isfile(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")
    if os.path.getsize(srt_path) == 0:
        raise ValueError("SRT file is 0 bytes — nothing to burn.")

    # ── Set up working directory ──────────────────────────────────────
    out_dir = os.path.dirname(os.path.abspath(output_mp4)) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Copy files into the working directory under simple names
    LOCAL_VID = "_sub_input.mp4"
    LOCAL_SRT = "_sub_captions.srt"
    LOCAL_OUT = os.path.basename(output_mp4)

    local_vid_path = os.path.join(out_dir, LOCAL_VID)
    local_srt_path = os.path.join(out_dir, LOCAL_SRT)

    shutil.copy2(input_mp4, local_vid_path)
    shutil.copy2(srt_path, local_srt_path)

    # ── Validate SRT ──────────────────────────────────────────────────
    with open(local_srt_path, "r", encoding="utf-8", errors="replace") as f:
        preview = [next(f, "").rstrip() for _ in range(3)]
    srt_size = os.path.getsize(local_srt_path)
    print(f"  SRT check: {srt_size} bytes, preview: {preview}")

    # ── Build FFmpeg command (all paths relative) ─────────────────────
    style = _build_force_style(config)
    vf = f"subtitles='{LOCAL_SRT}':force_style='{style}'"

    cmd: list[str] = [
        "ffmpeg", "-y",
        "-i", LOCAL_VID,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        LOCAL_OUT,
    ]

    print(f"  🔤 Burning subtitles ...")
    print(f"  vf: {vf}")
    print(f"\n⚙️ FFmpeg Command:\n{' '.join(cmd)}\n")

    # ── Execute FFmpeg from the output directory ──────────────────────
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            cwd=out_dir,
        )

        stderr_log = result.stderr.decode("utf-8", errors="replace")
        print(f"\n📋 FFmpeg Subtitle Log:\n{stderr_log}\n")

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg subtitle pass exited with code {result.returncode}:\n"
                f"{stderr_log[-3000:]}"
            )
    finally:
        # Clean up temporary copies
        for tmp in (local_vid_path, local_srt_path):
            if os.path.isfile(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    abs_output = os.path.abspath(output_mp4)
    size_mb = os.path.getsize(abs_output) / (1024 * 1024)
    print(f"  Subtitle pass complete: {abs_output} ({size_mb:.1f} MB)")

    return abs_output
