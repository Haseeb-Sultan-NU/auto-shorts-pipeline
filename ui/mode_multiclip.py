"""
ui/mode_multiclip.py — Multi-Clip Video Processor Mode

Upload, organize, and render multiple baked .mp4 clips from AI video
generators.  Full pipeline: audio extraction → Whisper transcription →
subtitle chunking → clip assembly with transitions, motion filter,
fades, and subtitle overlay → final render with progress.
"""

import os
import tempfile
import streamlit as st


# ---------------------------------------------------------------------------
# Output directory for rendered videos
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.abspath("outputs")


def _init_state() -> None:
    """Initialize session state keys for multi-clip mode."""
    defaults = {
        "multiclip_files": [],
        "multiclip_order": [],
        "multiclip_use_native_audio": True,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _swap_clips(i: int, j: int) -> None:
    """Swap two clips in the ordering list."""
    order = st.session_state["multiclip_order"]
    if 0 <= i < len(order) and 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
        st.session_state["multiclip_order"] = order


def render_multiclip_mode(sidebar_config: dict) -> None:
    """
    Render the Multi-Clip Video Processor UI.

    Parameters
    ----------
    sidebar_config : dict
        Config dict returned by sidebar.render_sidebar().
    """

    _init_state()

    st.markdown(
        "<p style='color:#999;font-size:13px;margin-top:-8px;'>"
        "Upload & organize multiple baked .mp4 clips from AI video generators"
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Upload section ────────────────────────────────────────────────
    st.subheader("1. Upload Video Clips")

    uploaded_files = st.file_uploader(
        "Drop your .mp4 clips here",
        type=["mp4"],
        accept_multiple_files=True,
        key="multiclip_uploader",
        help="Upload multiple .mp4 clips. They will be stitched in the order shown below.",
    )

    # Sync uploaded files into session state and rebuild order list
    if uploaded_files:
        st.session_state["multiclip_files"] = uploaded_files

        # Only reset order when clip count changes
        if len(st.session_state["multiclip_order"]) != len(uploaded_files):
            st.session_state["multiclip_order"] = list(range(len(uploaded_files)))

    clips = st.session_state["multiclip_files"]
    order = st.session_state["multiclip_order"]

    # ── Clip ordering & metadata ──────────────────────────────────────
    if clips:
        st.subheader("2. Clip Order & Metadata")
        st.caption("Use the arrows to reorder clips. The final video follows this sequence.")

        for display_idx, clip_idx in enumerate(order):
            if clip_idx >= len(clips):
                continue

            clip = clips[clip_idx]
            size_kb = len(clip.getvalue()) / 1024
            size_label = (
                f"{size_kb:.0f} KB" if size_kb < 1024
                else f"{size_kb / 1024:.1f} MB"
            )

            cols = st.columns([0.5, 3, 1.5, 0.8, 0.8])

            with cols[0]:
                st.markdown(
                    f"<div style='text-align:center;font-size:20px;font-weight:700;"
                    f"color:#666;padding-top:8px;'>{display_idx + 1}</div>",
                    unsafe_allow_html=True,
                )

            with cols[1]:
                st.markdown(
                    f"<div style='padding-top:6px;'>"
                    f"<span style='font-weight:600;'>{clip.name}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with cols[2]:
                st.markdown(
                    f"<div style='padding-top:8px;color:#888;font-size:12px;'>"
                    f"📦 {size_label}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with cols[3]:
                if display_idx > 0:
                    st.button(
                        "⬆️",
                        key=f"mc_up_{display_idx}",
                        on_click=_swap_clips,
                        args=(display_idx, display_idx - 1),
                        use_container_width=True,
                    )

            with cols[4]:
                if display_idx < len(order) - 1:
                    st.button(
                        "⬇️",
                        key=f"mc_down_{display_idx}",
                        on_click=_swap_clips,
                        args=(display_idx, display_idx + 1),
                        use_container_width=True,
                    )

        st.divider()

        # ── Audio source toggle ───────────────────────────────────────
        st.subheader("3. Audio Source")

        use_native = st.toggle(
            "Use native clip audio",
            key="multiclip_use_native_audio",
            help="Keep the original audio baked into each clip. "
                 "Disable to mute clips (subtitles will still be generated).",
        )

        st.divider()

        # ── Render section ────────────────────────────────────────────
        st.subheader("4. Render")

        # Summary bar
        transition = sidebar_config.get("transition_type", "Hard Cut")
        motion = "✅" if sidebar_config.get("apply_motion_filter") else "—"
        fade_in = sidebar_config.get("fade_in_duration", 0)
        fade_out = sidebar_config.get("fade_out_duration", 0)

        st.markdown(
            f"<div style='background:#1e1e2e;border:1px solid #333;border-radius:8px;"
            f"padding:12px 16px;margin-bottom:12px;'>"
            f"<span style='color:#aaa;font-size:13px;'>"
            f"📹 <b>{len(clips)}</b> clip{'s' if len(clips) != 1 else ''} · "
            f"🔊 {'Native audio' if use_native else 'Muted'} · "
            f"📐 Subtitles at <b>{sidebar_config['subtitle_vertical_pct']}%</b> · "
            f"🔀 {transition} · "
            f"🎥 Motion: {motion}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        if fade_in > 0 or fade_out > 0:
            fade_parts = []
            if fade_in > 0:
                fade_parts.append(f"Fade In: {fade_in:.1f}s")
            if fade_out > 0:
                fade_parts.append(f"Fade Out: {fade_out:.1f}s")
            st.caption(f"🌅 {' · '.join(fade_parts)}")

        # ── Process button ─────────────────────────────────────────────
        if st.button(
            "🚀 Process Clips",
            use_container_width=True,
            key="multiclip_process",
        ):
            _run_pipeline(clips, order, sidebar_config, use_native)

    else:
        # ── Empty state ───────────────────────────────────────────────
        st.markdown(
            "<div style='text-align:center;padding:60px 20px;'>"
            "<span style='font-size:48px;'>📹</span><br><br>"
            "<span style='color:#777;font-size:15px;'>"
            "Upload .mp4 clips above to get started"
            "</span>"
            "</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
# RENDER PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def _run_pipeline(clips, order, config, use_native):
    """Execute the full multi-clip render pipeline with progress UI."""

    # Lazy imports to avoid loading heavy deps until render time
    from engine.audio_extractor import extract_audio, cleanup_temp_audio
    from engine.transcriber import extract_word_timestamps, chunk_words_for_shorts
    from engine.video_builder import assemble_multiclip

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    progress_bar = st.progress(0.0)
    status_box = st.status("🚀 Initializing render pipeline…", expanded=True)

    def update_progress(pct, msg):
        progress_bar.progress(min(pct, 1.0))
        status_box.write(msg)

    try:
        # ── Step 1: Save clips to disk in order ───────────────────────
        update_progress(0.02, "💾 Saving uploaded clips to disk…")
        temp_dir = tempfile.mkdtemp(prefix="sf_render_")
        clip_paths = []

        for i, clip_idx in enumerate(order):
            if clip_idx >= len(clips):
                continue
            clip = clips[clip_idx]
            clip.seek(0)
            path = os.path.join(temp_dir, f"{i:03d}_{clip.name}")
            with open(path, "wb") as f:
                f.write(clip.read())
            clip_paths.append(path)
            update_progress(
                0.02 + 0.08 * ((i + 1) / len(order)),
                f"💾 Saved clip {i+1}/{len(order)}: {clip.name}"
            )

        if not clip_paths:
            st.error("No clips could be saved.")
            return

        # ── Step 2: Extract audio & transcribe ────────────────────────
        update_progress(0.12, "🎵 Extracting audio for transcription…")

        # Concatenate audio from all clips into one WAV for transcription
        # For simplicity, we extract audio from the first clip that has speech.
        # A more advanced approach would concatenate all audio tracks.
        all_audio_paths = []
        for i, path in enumerate(clip_paths):
            update_progress(
                0.12 + 0.08 * (i / len(clip_paths)),
                f"🎵 Extracting audio from clip {i+1}…"
            )
            try:
                wav_path = extract_audio(path)
                all_audio_paths.append(wav_path)
            except Exception as e:
                status_box.write(f"⚠️ Clip {i+1} audio extraction failed: {e}")

        # Transcribe each clip's audio and offset timestamps
        update_progress(0.22, "🎙️ Running Whisper transcription…")
        model_size = config.get("whisper_model_size", "base")
        all_word_data = []
        cumulative_offset = 0.0

        for i, wav_path in enumerate(all_audio_paths):
            update_progress(
                0.22 + 0.18 * (i / max(len(all_audio_paths), 1)),
                f"🎙️ Transcribing clip {i+1}/{len(all_audio_paths)}…"
            )
            try:
                words = extract_word_timestamps(wav_path, model_size=model_size)

                # Get clip duration for offset calculation
                from moviepy.editor import VideoFileClip as VFC
                with VFC(clip_paths[i]) as vc:
                    clip_duration = vc.duration or 0

                # Offset word timestamps by cumulative duration
                for w in words:
                    w["start"] += cumulative_offset
                    w["end"] += cumulative_offset
                all_word_data.extend(words)

                cumulative_offset += clip_duration

            except Exception as e:
                status_box.write(f"⚠️ Transcription failed for clip {i+1}: {e}")

        # Chunk words into subtitle cards
        update_progress(0.42, "📝 Chunking words into subtitle cards…")
        subtitle_chunks = chunk_words_for_shorts(all_word_data)
        status_box.write(
            f"✅ Generated **{len(subtitle_chunks)}** subtitle cards "
            f"from **{len(all_word_data)}** words"
        )

        # ── Step 3: Assemble final video ──────────────────────────────
        output_filename = "shorts_forge_output.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        # Merge sidebar config with audio toggle
        render_config = {**config, "multiclip_use_native_audio": use_native}

        update_progress(0.45, "🎞️ Assembling final video…")
        assemble_multiclip(
            clip_paths=clip_paths,
            output_path=output_path,
            subtitle_chunks=subtitle_chunks,
            config=render_config,
            progress_callback=lambda pct, msg: update_progress(
                0.45 + pct * 0.50,  # Map 0-1 to 0.45-0.95
                msg,
            ),
        )

        # ── Step 4: Cleanup temp audio ────────────────────────────────
        for wav in all_audio_paths:
            cleanup_temp_audio(wav)

        # ── Step 5: Show result ───────────────────────────────────────
        update_progress(1.0, "✅ Render complete!")
        status_box.update(label="✅ Render Complete!", state="complete")

        st.divider()
        st.subheader("🎬 Output")

        # Video preview
        with open(output_path, "rb") as f:
            video_bytes = f.read()

        st.video(video_bytes)

        # Download button
        st.download_button(
            label="⬇️ Download Final Video",
            data=video_bytes,
            file_name=output_filename,
            mime="video/mp4",
            use_container_width=True,
        )

        # File info
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        st.caption(f"📦 {size_mb:.1f} MB · Saved to `{output_path}`")

    except Exception as e:
        progress_bar.progress(1.0)
        status_box.update(label="❌ Render Failed", state="error")
        st.error(f"**Pipeline error:** {e}")
        import traceback
        st.code(traceback.format_exc(), language="text")
