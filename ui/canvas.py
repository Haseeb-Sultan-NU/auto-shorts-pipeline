"""
ui/canvas.py — Live 9:16 Interactive Subtitle Preview Canvas

Renders a self-contained HTML/CSS block via st.html() for flicker-free,
real-time visual feedback.  Now supports dynamic font injection via
CSS @font-face and live fill/stroke color preview.

st.html() injects directly into the DOM (no iframe like st.components.v1.html)
and does NOT sanitize HTML (unlike st.markdown with unsafe_allow_html).
"""

import base64
import os
import streamlit as st


# ---------------------------------------------------------------------------
# Zone definitions: (min_pct, max_pct, label, css_color, emoji)
# ---------------------------------------------------------------------------
ZONES = [
    (0,  25,  "Top / Header Zone",        "#ef4444", "⚠️"),
    (26, 60,  "Center / Mid-Screen",       "#3b82f6", "🎯"),
    (61, 85,  "Lower Third / Safe Zone",   "#22c55e", "✅"),
    (86, 100, "Bottom Danger Zone",        "#ef4444", "⛔"),
]


def get_zone_info(pct: int) -> tuple[str, str, str]:
    """Return (label, color, emoji) for the given percentage."""
    for lo, hi, label, color, emoji in ZONES:
        if lo <= pct <= hi:
            return label, color, emoji
    return "Unknown", "#888888", "❓"


def _build_font_face_css(font_path: str, css_family: str) -> str:
    """
    Generate a CSS @font-face rule that embeds a local font file as a
    base64 data URI.  This guarantees the preview renders the actual font
    regardless of the user's installed system fonts.

    Returns an empty string if font_path is empty (system fallback fonts).
    """
    if not font_path or not os.path.isfile(font_path):
        return ""

    ext = os.path.splitext(font_path)[1].lower()
    fmt_map = {".ttf": "truetype", ".otf": "opentype"}
    font_format = fmt_map.get(ext, "truetype")

    # Extract the raw family name from the css_family string
    # css_family looks like "'sf-FontName', sans-serif" → we need 'sf-FontName'
    face_name = css_family.split(",")[0].strip().strip("'\"")

    try:
        with open(font_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""

    return (
        f"@font-face {{\n"
        f"  font-family: '{face_name}';\n"
        f"  src: url('data:font/{ext.lstrip('.')};base64,{b64}') format('{font_format}');\n"
        f"  font-weight: normal;\n"
        f"  font-style: normal;\n"
        f"}}\n"
    )


def _stroke_shadow(color: str, px: float = 1.0) -> str:
    """Generate a CSS text-shadow that simulates a text stroke."""
    offsets = [
        (-px, -px), (px, -px), (-px, px), (px, px),
        (0, -px), (0, px), (-px, 0), (px, 0),
    ]
    parts = [f"{x:.1f}px {y:.1f}px 0 {color}" for x, y in offsets]
    return ", ".join(parts)


def render_canvas(
    vertical_pct: int,
    font_css_family: str = "'Impact', 'Arial Black', sans-serif",
    font_path: str = "",
    font_color: str = "#FFEB04",
    stroke_color: str = "#000000",
    font_size: int = 180,
) -> None:
    """
    Inject a 9:16 mobile-frame preview into the Streamlit DOM.

    Parameters
    ----------
    vertical_pct : int
        Vertical position as a percentage (0 = top, 100 = bottom).
    font_css_family : str
        CSS font-family value for the subtitle text.
    font_path : str
        Absolute path to the .ttf/.otf file (empty for system fonts).
    font_color : str
        Hex color for the subtitle text fill.
    stroke_color : str
        Hex color for the subtitle text stroke (simulated via text-shadow).
    font_size : int
        Full-resolution font size in 1080×1920 pixels (30–280).
    """

    zone_label, zone_color, zone_emoji = get_zone_info(vertical_pct)

    # Clamp subtitle position so it doesn't clip out of frame
    clamped_top = max(4, min(vertical_pct, 94))

    # Build font-face injection (empty string if system font)
    font_face_css = _build_font_face_css(font_path, font_css_family)

    # Proportional scaling: 200px mockup width / 1080px render width
    scale_ratio = 200 / 1080
    scaled_font_size = max(10, int(font_size * scale_ratio))
    scaled_stroke_px = max(0.5, round(font_size * scale_ratio * 0.08, 1))
    webkit_stroke_px = max(0.5, round(font_size * scale_ratio * 0.06, 1))

    # Build stroke simulation with scaled thickness
    stroke_shadow = _stroke_shadow(stroke_color, px=scaled_stroke_px)

    # Compute a subtle border color from the font_color
    border_color = font_color + "40"  # 25% opacity

    html = f"""
    <style>
        {font_face_css}

        .sf-canvas-wrap {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            margin: 8px 0 4px 0;
            user-select: none;
        }}

        .sf-phone {{
            position: relative;
            width: 200px;
            height: 355px;
            background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
            border-radius: 18px;
            border: 2.5px solid #333346;
            box-shadow:
                0 0 0 1px rgba(255,255,255,0.05),
                0 8px 32px rgba(0,0,0,0.5),
                inset 0 1px 0 rgba(255,255,255,0.05);
            overflow: hidden;
        }}

        .sf-dz-top {{
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 25%;
            background: linear-gradient(180deg, rgba(239,68,68,0.18) 0%, transparent 100%);
            border-bottom: 1px dashed rgba(239,68,68,0.45);
            pointer-events: none;
            z-index: 2;
        }}
        .sf-dz-top-label {{
            position: absolute;
            bottom: 4px; left: 8px;
            font-size: 7px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            color: rgba(239,68,68,0.6);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}

        .sf-dz-bot {{
            position: absolute;
            bottom: 0; left: 0; right: 0;
            height: 15%;
            background: linear-gradient(0deg, rgba(239,68,68,0.22) 0%, transparent 100%);
            border-top: 1px dashed rgba(239,68,68,0.45);
            pointer-events: none;
            z-index: 2;
        }}
        .sf-dz-bot-label {{
            position: absolute;
            top: 4px; right: 8px;
            font-size: 7px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            color: rgba(239,68,68,0.6);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}

        .sf-guide {{
            position: absolute;
            left: 0; right: 0;
            height: 0;
            border-top: 1px dashed rgba(255,255,255,0.12);
            pointer-events: none;
            z-index: 1;
        }}
        .sf-guide span {{
            position: absolute;
            right: 6px;
            top: 2px;
            font-size: 6.5px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            color: rgba(255,255,255,0.25);
            letter-spacing: 0.3px;
        }}
        .sf-g25 {{ top: 25%; }}
        .sf-g60 {{ top: 60%; }}
        .sf-g85 {{ top: 85%; }}

        .sf-sub {{
            position: absolute;
            top: {clamped_top}%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 10;
        }}
        .sf-sub-text {{
            background: rgba(0,0,0,0.75);
            color: {font_color};
            font-family: {font_css_family};
            font-size: {scaled_font_size}px;
            font-weight: 900;
            letter-spacing: 1.2px;
            text-transform: uppercase;
            padding: 5px 14px;
            border-radius: 4px;
            text-align: center;
            white-space: nowrap;
            -webkit-text-stroke: {webkit_stroke_px}px {stroke_color};
            paint-order: stroke fill;
            text-shadow: {stroke_shadow};
            border: 1px solid {border_color};
        }}

        .sf-pct {{
            position: absolute;
            top: {clamped_top}%;
            right: 8px;
            transform: translateY(-50%);
            font-size: 9px;
            font-family: 'Consolas', 'Courier New', monospace;
            color: rgba(255,255,255,0.5);
            background: rgba(0,0,0,0.5);
            padding: 1px 5px;
            border-radius: 3px;
            z-index: 11;
        }}

        .sf-badge {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 11.5px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-weight: 600;
            color: white;
            background: {zone_color}22;
            border: 1px solid {zone_color}55;
        }}
        .sf-badge-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: {zone_color};
            box-shadow: 0 0 6px {zone_color}88;
            display: inline-block;
        }}
    </style>

    <div class="sf-canvas-wrap">
        <div class="sf-phone">
            <div class="sf-dz-top">
                <span class="sf-dz-top-label">UI Overlap</span>
            </div>
            <div class="sf-dz-bot">
                <span class="sf-dz-bot-label">Title Overlap</span>
            </div>

            <div class="sf-guide sf-g25"><span>25%</span></div>
            <div class="sf-guide sf-g60"><span>60%</span></div>
            <div class="sf-guide sf-g85"><span>85%</span></div>

            <div class="sf-sub">
                <div class="sf-sub-text">SAMPLE SUBTITLE</div>
            </div>

            <div class="sf-pct">{vertical_pct}%</div>
        </div>

        <div class="sf-badge">
            <span class="sf-badge-dot"></span>
            {zone_emoji} {zone_label}
        </div>
    </div>
    """

    st.html(html)
