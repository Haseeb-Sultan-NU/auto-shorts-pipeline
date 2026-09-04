"""
app.py — Shorts Forge AI: Entry Point & Mode Router

Thin orchestration layer that:
  1. Configures the Streamlit page
  2. Renders the shared sidebar (subtitle styling + live canvas)
  3. Routes to the active mode tab (Legacy or Multi-Clip)
"""

import streamlit as st
from ui.sidebar import render_sidebar
from ui.mode_legacy import render_legacy_mode
from ui.mode_multiclip import render_multiclip_mode


# ── Page config (must be first Streamlit call) ────────────────────────
st.set_page_config(
    page_title="Shorts Forge AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Global CSS overrides for a polished dark-mode feel ────────────────
st.markdown(
    """
    <style>
        /* Tighten default Streamlit top padding */
        .block-container { padding-top: 2rem; }

        /* Title gradient */
        .sf-title {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #6366f1, #a855f7, #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 2px;
        }
        .sf-subtitle {
            color: #777;
            font-size: 14px;
            margin-bottom: 20px;
        }

        /* Softer tab styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 10px 24px;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Header ────────────────────────────────────────────────────────────
st.markdown('<div class="sf-title">Shorts Forge AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sf-subtitle">Automated generation engine for 9:16 vertical video</div>',
    unsafe_allow_html=True,
)


# ── Sidebar (shared across all modes) ─────────────────────────────────
sidebar_config = render_sidebar()


# ── Mode tabs ─────────────────────────────────────────────────────────
tab_legacy, tab_multiclip = st.tabs([
    "🎞️ Legacy Asset Stitcher",
    "🎬 Multi-Clip Processor",
])

with tab_legacy:
    render_legacy_mode(sidebar_config)

with tab_multiclip:
    render_multiclip_mode(sidebar_config)