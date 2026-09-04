"""
ui/sidebar.py — Sidebar Controls & Live Canvas Integration

Consolidates all sidebar widgets (font selection, subtitle styling,
vertical positioning, and the live 9:16 preview canvas) into a single
render function that returns a config dict consumed by downstream modules.
"""

import streamlit as st
from ui.canvas import render_canvas, get_zone_info
from utils.font_manager import scan_fonts, get_font_by_name
from engine.transcriber import MODEL_SIZES, DEFAULT_MODEL, detect_device
from engine.video_builder import TRANSITION_NAMES


# ---------------------------------------------------------------------------
# Defaults — single source of truth for initial session state values
# ---------------------------------------------------------------------------
DEFAULTS = {
    "font_color":           "#FFEB04",
    "stroke_color":         "#000000",
    "font_size":            180,
    "subtitle_vertical_pct": 72,
    "selected_font_name":   None,  # Will be set to first available font
    "whisper_model_size":   DEFAULT_MODEL,
    "transition_type":      "Hard Cut",
    "apply_motion_filter":  False,
    "enable_fade_in":       False,
    "fade_in_duration":     0.5,
    "enable_fade_out":      False,
    "fade_out_duration":    0.5,
}


def _init_state() -> None:
    """Populate session state with defaults if keys are missing."""
    for key, val in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_sidebar() -> dict:
    """
    Render all sidebar controls and return a config dict.

    Returns
    -------
    dict
        Keys: font_color, stroke_color, font_size, subtitle_vertical_pct,
              selected_font_name, font_path, font_css_family
    """

    _init_state()

    # ── Discover fonts (cached per session to avoid re-scanning) ──────
    fonts, is_fallback = scan_fonts()
    font_names = [f.display_name for f in fonts]

    # Resolve initial selection index
    current_name = st.session_state.get("selected_font_name")
    if current_name in font_names:
        default_idx = font_names.index(current_name)
    else:
        default_idx = 0
        st.session_state["selected_font_name"] = font_names[0]

    with st.sidebar:

        # ── App branding ──────────────────────────────────────────────
        st.markdown(
            "<div style='text-align:center;padding:4px 0 12px 0;'>"
            "<span style='font-size:26px;'>🎬</span><br>"
            "<span style='font-size:14px;font-weight:700;"
            "letter-spacing:1px;color:#ccc;'>SHORTS FORGE AI</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Font Selection ────────────────────────────────────────────
        st.subheader("🔤 Font Selection")

        if is_fallback:
            st.info(
                "No local fonts found. Drop **.ttf** or **.otf** files into "
                "the `fonts/` folder and restart.",
                icon="📂",
            )

        selected_font_name = st.selectbox(
            "Font Family",
            options=font_names,
            index=default_idx,
            key="selected_font_name",
            help="Fonts are loaded from the `fonts/` directory.",
        )

        # Look up full font entry
        font_entry = get_font_by_name(selected_font_name, fonts)

        # Show font file path as a subtle caption for local fonts
        if font_entry and font_entry.file_path:
            st.caption(f"📄 `{font_entry.file_path.split('/')[-1]}`")

        st.divider()

        # ── Subtitle Styling ──────────────────────────────────────────
        st.subheader("🎨 Subtitle Styling")

        font_color = st.color_picker(
            "Text Color",
            key="font_color",
        )
        stroke_color = st.color_picker(
            "Stroke Color",
            key="stroke_color",
        )
        font_size = st.slider(
            "Font Size",
            min_value=30,
            max_value=280,
            key="font_size",
            help="Controls the rendered subtitle text size in pixels.",
        )

        st.divider()

        # ── Vertical Positioning ──────────────────────────────────────
        st.subheader("📐 Subtitle Position")

        vertical_pct = st.slider(
            "Vertical Position (%)",
            min_value=0,
            max_value=100,
            key="subtitle_vertical_pct",
            help="0% = top of frame, 100% = bottom of frame.",
        )

        # Zone warning chips
        zone_label, zone_color, zone_emoji = get_zone_info(vertical_pct)

        if vertical_pct <= 25:
            st.warning(
                f"{zone_emoji} **{zone_label}** — May overlap Shorts UI / Search icons",
                icon="⚠️",
            )
        elif vertical_pct >= 86:
            st.error(
                f"{zone_emoji} **{zone_label}** — Overlaps video title & channel name",
                icon="🚨",
            )
        elif 26 <= vertical_pct <= 60:
            st.info(
                f"{zone_emoji} **{zone_label}** — High engagement / pop-in focus area",
                icon="🎯",
            )
        else:
            st.success(
                f"{zone_emoji} **{zone_label}** — Standard recommended position",
                icon="✅",
            )

        # ── Live canvas preview ───────────────────────────────────────
        render_canvas(
            vertical_pct=vertical_pct,
            font_css_family=font_entry.css_family if font_entry else "'Impact', sans-serif",
            font_path=font_entry.file_path if font_entry else "",
            font_color=font_color,
            stroke_color=stroke_color,
            font_size=font_size,
        )

        st.divider()

        # ── Transitions ───────────────────────────────────────────────
        st.subheader("🔀 Transitions")

        transition_type = st.selectbox(
            "Clip Transition",
            options=TRANSITION_NAMES,
            key="transition_type",
            help="Effect applied between consecutive clips.",
        )

        st.divider()

        # ── Motion Filter ─────────────────────────────────────────────
        st.subheader("🎥 Motion Filter")

        apply_motion = st.checkbox(
            "Apply Handheld Camera Motion",
            key="apply_motion_filter",
            help="Adds slow zoom (1.0x→1.05x) and subtle tremble to all clips.",
        )
        if apply_motion:
            st.caption("Slow Zoom + Sine-wave Tremble")

        st.divider()

        # ── Global Fades ──────────────────────────────────────────────
        st.subheader("🌅 Global Fades")

        enable_fade_in = st.checkbox(
            "Fade In from Black",
            key="enable_fade_in",
            help="Apply a fade-in from black at the start of the final video.",
        )
        if enable_fade_in:
            fade_in_dur = st.slider(
                "Fade In Duration (s)",
                min_value=0.2,
                max_value=3.0,
                step=0.1,
                key="fade_in_duration",
            )
        else:
            fade_in_dur = 0.0

        enable_fade_out = st.checkbox(
            "Fade Out to Black",
            key="enable_fade_out",
            help="Apply a fade-out to black at the end of the final video.",
        )
        if enable_fade_out:
            fade_out_dur = st.slider(
                "Fade Out Duration (s)",
                min_value=0.2,
                max_value=3.0,
                step=0.1,
                key="fade_out_duration",
            )
        else:
            fade_out_dur = 0.0

        st.divider()

        # ── Whisper Transcription Settings ─────────────────────────────
        st.subheader("🎙️ Whisper Engine")

        device, compute_type = detect_device()
        device_label = "⚡ CUDA GPU" if device == "cuda" else "🖥️ CPU"

        st.markdown(
            f"<div style='background:#1a1a2e;border:1px solid #333;border-radius:8px;"
            f"padding:8px 12px;margin-bottom:8px;'>"
            f"<span style='font-size:12px;color:#aaa;'>"
            f"{device_label} &nbsp;·&nbsp; {compute_type}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        whisper_model = st.selectbox(
            "Model Size",
            options=MODEL_SIZES,
            key="whisper_model_size",
            help=(
                "Larger models are more accurate but slower. "
                "'base' is recommended for fast local turnaround."
            ),
        )

        # Model size hints
        size_hints = {
            "tiny":     "~75MB · Fastest · Lower accuracy",
            "base":     "~140MB · Fast · Good accuracy ⭐",
            "small":    "~460MB · Moderate · High accuracy",
            "medium":   "~1.5GB · Slow · Very high accuracy",
            "large-v2": "~3GB · Slowest · Best accuracy",
        }
        st.caption(size_hints.get(whisper_model, ""))

    # ── Return config dict ────────────────────────────────────────────
    return {
        "font_color":           font_color,
        "stroke_color":         stroke_color,
        "font_size":            font_size,
        "subtitle_vertical_pct": vertical_pct,
        "selected_font_name":   selected_font_name,
        "font_path":            font_entry.file_path if font_entry else "",
        "font_css_family":      font_entry.css_family if font_entry else "'Impact', sans-serif",
        "whisper_model_size":   whisper_model,
        "transition_type":      transition_type,
        "apply_motion_filter":  apply_motion,
        "fade_in_duration":     fade_in_dur,
        "fade_out_duration":    fade_out_dur,
    }
