"""
ui/mode_legacy.py — Legacy Asset Stitcher Mode

Extracts the original app.py pipeline into a dedicated mode function.
Handles JSON blueprint ingestion, ElevenLabs audio upload, visual asset
uploads, and triggers the existing engine/ pipeline.
"""

import json
import os
import streamlit as st

# Workspace paths
WORKSPACE_DIR = os.path.abspath("temp_workspace")
INPUTS_DIR = os.path.join(WORKSPACE_DIR, "input_assets")
OUTPUTS_DIR = os.path.join(WORKSPACE_DIR, "outputs")


def _ensure_dirs() -> None:
    os.makedirs(INPUTS_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)


def _init_state() -> None:
    """Initialize session state keys for legacy mode."""
    defaults = {
        "legacy_json": "",
        "legacy_audio": None,
        "legacy_visuals": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_legacy_mode(sidebar_config: dict) -> None:
    """
    Render the Legacy Asset Stitcher UI and handle pipeline execution.

    Parameters
    ----------
    sidebar_config : dict
        Config dict returned by sidebar.render_sidebar().
    """

    _ensure_dirs()
    _init_state()

    st.markdown(
        "<p style='color:#999;font-size:13px;margin-top:-8px;'>"
        "Images + External Audio + ElevenLabs / TTS pipeline"
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Two-column input layout ───────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. Script Ingestion")
        json_str = st.text_area(
            "Paste JSON Blueprint Here",
            height=240,
            placeholder=(
                '{\n'
                '  "title": "WW2_Mincemeat",\n'
                '  "visual_assets": [\n'
                '    {"filename": "01_hook.mp4"},\n'
                '    {"filename": "02_warroom.jpeg"}\n'
                '  ]\n'
                '}'
            ),
            key="legacy_json_input",
        )

    with col2:
        st.subheader("2. Asset Uploads")
        audio_file = st.file_uploader(
            "Upload ElevenLabs Voiceover (MP3)",
            type=["mp3"],
            key="legacy_audio_upload",
        )
        visual_assets = st.file_uploader(
            "Upload Flow Visuals (PNG/MP4/JPEG)",
            type=["png", "mp4", "jpeg", "jpg"],
            accept_multiple_files=True,
            key="legacy_visuals_upload",
        )

    # ── Generate button ───────────────────────────────────────────────
    if st.button("🚀 Generate Short", use_container_width=True, key="legacy_generate"):

        if not json_str or not audio_file or not visual_assets:
            st.error(
                "Missing inputs. Please paste the JSON blueprint, "
                "upload the audio, and upload your visual assets."
            )
            return

        try:
            blueprint = json.loads(json_str)
        except json.JSONDecodeError:
            st.error("Invalid JSON format. Please check the blueprint syntax.")
            return

        # ── Lazy-import engine modules (heavy deps) ───────────────────
        from engine.transcriber import extract_word_timestamps, chunk_words_for_shorts
        from engine.video_builder import assemble_short
        from engine.audio_synth import master_voiceover

        status_box = st.status("Initializing Batch Pipeline…", expanded=True)

        # 1 — Save audio
        status_box.write("💾 Saving raw audio stream…")
        original_audio_path = os.path.join(INPUTS_DIR, audio_file.name)
        with open(original_audio_path, "wb") as f:
            f.write(audio_file.read())

        # 2 — Master audio
        status_box.write("🎛️ Mastering Audio: Cutting low rumble & boosting vocal clarity…")
        mastered_audio_path = os.path.join(INPUTS_DIR, f"mastered_{audio_file.name}")
        final_audio_path = master_voiceover(original_audio_path, mastered_audio_path)

        # 3 — Save visual assets
        status_box.write("📁 Processing visual assets…")
        asset_map = {}
        for asset in visual_assets:
            save_path = os.path.join(INPUTS_DIR, asset.name)
            with open(save_path, "wb") as f:
                f.write(asset.read())
            asset_map[asset.name] = save_path

        # 4 — Transcribe
        status_box.write("🎙️ Extracting word-level timestamps with Faster-Whisper…")
        word_data = extract_word_timestamps(final_audio_path, model_size="base")

        # 4b — Chunk words into punchy 1–3 word caption groups
        status_box.write("📝 Chunking words into Shorts-style captions…")
        caption_chunks = chunk_words_for_shorts(word_data)
        print(f"✅ Chunked into {len(caption_chunks)} caption groups")

        # 5 — Composite video
        status_box.write("🎞️ Slicing video, applying punch-ins, rendering dynamic captions…")
        output_filename = f"{blueprint.get('title', 'rendered_short')}.mp4"
        output_video_path = os.path.join(OUTPUTS_DIR, output_filename)

        assemble_short(
            json_blueprint=blueprint,
            audio_path=final_audio_path,
            asset_files_map=asset_map,
            word_timestamps=caption_chunks,
            output_path=output_video_path,
            font_color=sidebar_config["font_color"],
            stroke_color=sidebar_config["stroke_color"],
            font_size=sidebar_config["font_size"],
            vertical_pos=sidebar_config.get("subtitle_vertical_pct", 72),
            font_path=sidebar_config.get("font_path", ""),
        )

        status_box.update(
            label="✅ Short Rendered Successfully!",
            state="complete",
            expanded=False,
        )

        # ── Display result ────────────────────────────────────────────
        st.subheader("🎉 Final Rendered Short")
        st.video(output_video_path)

        with open(output_video_path, "rb") as file:
            st.download_button(
                label="⬇️ Download Final Short (1080p)",
                data=file,
                file_name=output_filename,
                mime="video/mp4",
                use_container_width=True,
                key="legacy_download",
            )
