"""
ui/mode_explainer.py — Explainer Pipeline v3 (Single-Pass Timestamp Engine)

Workflow:
  Step 1 → Paste script + voice/rate/pitch settings → synthesize a single
           continuous MP3 via edge-tts → map word boundaries back to each
           script line to derive exact start/end/duration per visual beat.
  Step 2 → Timestamped manifest display + audio preview + bulk image upload.
  Step 3 → Assemble final video via the existing FFmpeg compositor engine.
"""

import asyncio
import os
import re
import sys
import tempfile
import streamlit as st

import edge_tts
from mutagen.mp3 import MP3

# ── Suppress Windows WinError 10054 during async websocket teardown ───
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from engine.explainer_audio import (
    ExplainerManifest,
    Scene,
    export_srt,
)
from engine.explainer_compositor import render_2_5D_short
from engine.explainer_subtitles import burn_subtitles_to_video


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

_TICKS_PER_SECOND = 10_000_000
_STRIP_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Curated voices for the dropdown
_VOICE_OPTIONS = [
    ("en-US-ChristopherNeural", "Christopher — Male, Conversational"),
    ("en-US-GuyNeural",         "Guy — Male, News / Narrative"),
    ("en-US-SteffanNeural",     "Steffan — Male, Clear / Warm"),
    ("en-US-DavisNeural",       "Davis — Male, Calm / Professional"),
    ("en-US-BrianNeural",       "Brian — Male, Clear / Direct"),
    ("en-US-AndrewNeural",      "Andrew — Male, Mature / Measured"),
    ("en-US-JennyNeural",       "Jenny — Female, Friendly"),
    ("en-US-AriaNeural",        "Aria — Female, Warm / Versatile"),
    ("en-US-SaraNeural",        "Sara — Female, Youthful"),
    ("en-GB-RyanNeural",        "Ryan — Male, British"),
    ("en-GB-SoniaNeural",       "Sonia — Female, British"),
    ("en-AU-WilliamNeural",     "William — Male, Australian"),
]


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC BRIDGE
# ═══════════════════════════════════════════════════════════════════════════

def _run_async(coro):
    """Execute an async coroutine from Streamlit's synchronous context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
# EDGE-TTS: SINGLE-PASS SYNTHESIS WITH WORD BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════

async def _synthesize_full(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: str,
) -> list[dict]:
    """Synthesize the entire script as one continuous MP3 and capture
    word-level boundary timestamps.

    Returns [{"word": str, "start": float, "end": float}, ...].
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    word_timestamps: list[dict] = []

    with open(output_path, "wb") as fp:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fp.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                offset_s = chunk["offset"] / _TICKS_PER_SECOND
                dur_s = chunk["duration"] / _TICKS_PER_SECOND
                word_timestamps.append({
                    "word": chunk["text"],
                    "start": round(offset_s, 3),
                    "end": round(offset_s + dur_s, 3),
                })

    return word_timestamps


async def _preview_voice(
    voice: str,
    rate: str,
    pitch: str,
) -> str:
    """Synthesize a short sample clip for instant voice preview.

    Returns the path to the generated MP3 file.
    """
    sample_text = (
        "Hello, this is a preview of my voice. "
        "Let's make a great video."
    )
    preview_path = os.path.join(tempfile.gettempdir(), "preview.mp3")
    communicate = edge_tts.Communicate(
        sample_text, voice, rate=rate, pitch=pitch,
    )
    await communicate.save(preview_path)
    return preview_path


# ═══════════════════════════════════════════════════════════════════════════
# TIMESTAMP ALIGNMENT: MAP WORD BOUNDARIES → SCRIPT LINES
# ═══════════════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    return _STRIP_RE.sub("", text).lower().strip()


def _tokenize(text: str) -> list[str]:
    return [t for t in _normalize(text).split() if t]


def _align_lines_to_word_boundaries(
    lines: list[str],
    word_ts: list[dict],
) -> list[dict]:
    """Map each script line to its precise start/end/duration using word
    boundaries from the continuous TTS pass.

    Strategy: tokenize each line, walk through the word-boundary stream,
    match tokens sequentially.  Each line's start = first matched word's
    start; end = last matched word's end.  The final line always extends
    to the audio's true end to avoid gaps.
    """
    if not word_ts:
        # Fallback: equal distribution
        return [
            {"id": i + 1, "text": ln, "start": 0.0, "end": 0.0, "duration": 0.0}
            for i, ln in enumerate(lines)
        ]

    total_duration = word_ts[-1]["end"]

    # Normalise the TTS word stream for matching
    tts_norm = [_normalize(w["word"]) for w in word_ts]

    results: list[dict] = []
    cursor = 0  # current position in the word_ts stream

    for idx, line_text in enumerate(lines):
        tokens = _tokenize(line_text)
        if not tokens:
            # Empty / whitespace-only line — zero-length beat
            prev_end = results[-1]["end"] if results else 0.0
            results.append({
                "id": idx + 1,
                "text": line_text,
                "start": prev_end,
                "end": prev_end,
                "duration": 0.0,
            })
            continue

        # Find the first token of this line in the TTS stream
        first_token = tokens[0]
        match_start = -1
        for j in range(cursor, len(tts_norm)):
            if tts_norm[j] == first_token:
                match_start = j
                break

        if match_start == -1:
            # Fallback: couldn't find first token — use cursor position
            match_start = cursor

        # Walk forward to consume all tokens for this line
        match_end = match_start
        tok_idx = 0
        for j in range(match_start, len(tts_norm)):
            if tok_idx >= len(tokens):
                break
            if tts_norm[j] == tokens[tok_idx]:
                match_end = j
                tok_idx += 1

        line_start = word_ts[match_start]["start"]
        line_end = word_ts[match_end]["end"]

        # Last line extends to total audio duration to prevent trailing gap
        if idx == len(lines) - 1:
            line_end = total_duration

        results.append({
            "id": idx + 1,
            "text": line_text,
            "start": round(line_start, 3),
            "end": round(line_end, 3),
            "duration": round(line_end - line_start, 3),
        })

        cursor = match_end + 1

    # Ensure zero-gap continuity: each scene starts where the previous ended
    for i in range(1, len(results)):
        results[i]["start"] = results[i - 1]["end"]
        results[i]["duration"] = round(results[i]["end"] - results[i]["start"], 3)

    return results


# ═══════════════════════════════════════════════════════════════════════════
# FORMAT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_ts(seconds: float) -> str:
    """Format seconds as MM:SS.d (e.g. 01:03.2)."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:04.1f}"


def _natural_sort_key(file_obj) -> list:
    """Sort key that handles embedded integers so Scene-2 < Scene-10."""
    parts = re.split(r'(\d+)', file_obj.name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


# ═══════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════

def _init_state() -> None:
    defaults = {
        "explainer_stage":       "script_input",
        "timed_scenes":          [],       # list[dict] — id, text, start, end, duration
        "word_timestamps":       [],       # raw word boundaries from TTS
        "work_dir":              "",
        "master_audio_path":     "",
        "explainer_manifest":    None,
        "explainer_voice":       _VOICE_OPTIONS[0][0],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def reset_pipeline() -> None:
    st.session_state["explainer_stage"] = "script_input"
    st.session_state["timed_scenes"] = []
    st.session_state["word_timestamps"] = []
    st.session_state["work_dir"] = ""
    st.session_state["master_audio_path"] = ""
    st.session_state["explainer_manifest"] = None
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Script Input, Voice Config & Synthesis
# ═══════════════════════════════════════════════════════════════════════════

def render_step1_script_input() -> None:
    """Script ingestion + voice/rate/pitch controls + single-pass TTS."""

    st.markdown(
        "<p style='color:#999;font-size:13px;margin-top:-8px;'>"
        "Paste your voiceover script below — each line becomes one visual beat / image."
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Script input ──────────────────────────────────────────────────
    script_text = st.text_area(
        "📜 Master Voiceover Script (Each line = One Image Beat)",
        height=250,
        placeholder=(
            "Line 1: Hook — did you know the sun is actually white?\n"
            "Line 2: The atmosphere scatters blue light, tricking your brain.\n"
            "Line 3: But in space, astronauts see a blazing white disc.\n"
            "..."
        ),
        key="explainer_script_input",
    )

    lines = [
        line.strip()
        for line in script_text.split("\n")
        if line.strip()
    ] if script_text else []

    if lines:
        st.caption(f"Detected **{len(lines)}** visual beat(s).")

    st.divider()

    # ── Voice & modulation ────────────────────────────────────────────
    voice_labels = [label for _, label in _VOICE_OPTIONS]
    voice_map = {label: vid for vid, label in _VOICE_OPTIONS}

    col_voice, col_preview = st.columns([3, 1])

    with col_voice:
        selected_label = st.selectbox(
            "🗣️ Voice",
            options=voice_labels,
            key="explainer_voice_label",
        )
        selected_voice = voice_map[selected_label]

    with col_preview:
        st.markdown("<div style='height:27px'></div>", unsafe_allow_html=True)
        preview_clicked = st.button(
            "🔊 Preview Voice",
            use_container_width=True,
            key="explainer_preview_btn",
        )

    col_rate, col_pitch = st.columns(2)

    with col_rate:
        rate_val = st.slider(
            "Speed",
            min_value=-20, max_value=50, value=0, step=5,
            format="%+d%%",
            key="explainer_rate",
        )

    with col_pitch:
        pitch_val = st.slider(
            "Pitch",
            min_value=-20, max_value=20, value=0, step=5,
            format="%+dHz",
            key="explainer_pitch",
        )

    rate_str = f"{rate_val:+d}%"
    pitch_str = f"{pitch_val:+d}Hz"

    # ── Voice preview playback ────────────────────────────────────────
    if preview_clicked:
        with st.spinner("Generating preview..."):
            try:
                preview_path = _run_async(
                    _preview_voice(
                        voice=selected_voice,
                        rate=rate_str,
                        pitch=pitch_str,
                    )
                )
                st.audio(preview_path, format="audio/mp3", autoplay=True)
            except Exception as e:
                st.error(f"Preview failed: {e}")

    st.divider()

    # ── Generate button ───────────────────────────────────────────────
    ready = len(lines) >= 1

    if st.button(
        "⚡ Synthesize Audio & Calculate Timestamps",
        use_container_width=True,
        disabled=not ready,
    ):
        if not lines:
            st.error("Please paste at least one line of script text.")
            return

        p_bar = st.progress(0, text="Preparing workspace...")

        try:
            # Reuse existing workspace if available (preserves uploaded images)
            work_dir = st.session_state.get("work_dir") or ""
            if not work_dir or not os.path.isdir(work_dir):
                work_dir = tempfile.mkdtemp(prefix="sf_explainer_")
            os.makedirs(os.path.join(work_dir, "images"), exist_ok=True)
            os.makedirs(os.path.join(work_dir, "fx"), exist_ok=True)

            audio_path = os.path.join(work_dir, "master_voiceover.mp3")

            # ── Single-pass synthesis ─────────────────────────────────
            p_bar.progress(15, text=f"🎙️ Synthesizing full audio with {selected_voice}...")

            full_script = "\n".join(lines)

            word_ts = _run_async(
                _synthesize_full(
                    text=full_script,
                    voice=selected_voice,
                    rate=rate_str,
                    pitch=pitch_str,
                    output_path=audio_path,
                )
            )

            # ── Align script lines to word boundaries ─────────────────
            p_bar.progress(70, text="⏱️ Mapping timestamps to script lines...")

            timed_scenes = _align_lines_to_word_boundaries(lines, word_ts)

            p_bar.progress(100, text="✅ Audio synthesised & timestamps calculated!")

            # ── Persist and advance ───────────────────────────────────
            st.session_state["timed_scenes"] = timed_scenes
            st.session_state["word_timestamps"] = word_ts
            st.session_state["work_dir"] = work_dir
            st.session_state["master_audio_path"] = audio_path
            st.session_state["explainer_voice"] = selected_voice
            st.session_state["explainer_stage"] = "manifest"
            st.rerun()

        except Exception as e:
            p_bar.progress(100, text="❌ Synthesis failed")
            st.error(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — Manifest Display + Audio Preview + Bulk Image Upload
# ═══════════════════════════════════════════════════════════════════════════

def render_step2_manifest() -> None:
    """Show the timestamped manifest, audio player, and image uploader."""
    timed_scenes: list[dict] = st.session_state["timed_scenes"]
    audio_path: str = st.session_state["master_audio_path"]
    n_scenes = len(timed_scenes)

    # ── Summary metrics ───────────────────────────────────────────────
    total_dur = sum(s["duration"] for s in timed_scenes)
    avg_dur = total_dur / n_scenes if n_scenes else 0

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("🎬 Total Beats / Images Needed", n_scenes)
    mc2.metric("⏱️ Total Duration", f"{total_dur:.1f}s")
    mc3.metric("📐 Average Cut Pacing", f"{avg_dur:.1f}s")

    st.divider()

    # ── Timestamped manifest (copy-ready) ─────────────────────────────
    st.subheader("📋 Timestamped Scene Manifest")
    st.caption(
        "Copy this block to use for art direction — each line shows the "
        "exact timing window for its visual."
    )

    manifest_lines = []
    for s in timed_scenes:
        start_fmt = _fmt_ts(s["start"])
        end_fmt = _fmt_ts(s["end"])
        manifest_lines.append(
            f"Scene {s['id']:02d} [{start_fmt} - {end_fmt}] "
            f"({s['duration']:.1f}s): \"{s['text']}\""
        )
    manifest_block = "\n".join(manifest_lines)

    st.code(manifest_block, language="text")

    st.divider()

    # ── Audio preview & download ──────────────────────────────────────
    st.subheader("🎧 Master Voiceover Preview")

    if os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        st.audio(audio_bytes, format="audio/mp3")

        st.download_button(
            label="⬇️ Download master_voiceover.mp3",
            data=audio_bytes,
            file_name="master_voiceover.mp3",
            mime="audio/mpeg",
            use_container_width=True,
        )
    else:
        st.warning("Audio file not found. Try regenerating.")

    st.divider()

    # ── Bulk image upload ─────────────────────────────────────────────
    st.subheader("🖼️ Upload Scene Images")
    st.write(
        f"Upload exactly **{n_scenes}** images — one per visual beat. "
        f"Name them with numbers (e.g. `Scene-1.png` … `Scene-{n_scenes}.png`); "
        f"they will be **naturally sorted** so `Scene-2` comes before `Scene-10`."
    )

    uploaded_files = st.file_uploader(
        "🖼️ Upload Scene Images (Sorted 01.png, 02.png...)",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg"],
        key="explainer_bulk_images",
    )

    n_uploaded = len(uploaded_files) if uploaded_files else 0
    match_ok = n_uploaded == n_scenes

    # Validation status
    if n_uploaded == 0:
        st.caption("No images uploaded yet.")
    elif match_ok:
        st.success(f"✅ Uploaded {n_uploaded} / {n_scenes} images — ready!")
    else:
        st.warning(
            f"⚠️ Uploaded **{n_uploaded}** / **{n_scenes}** images required. "
            f"Please upload exactly {n_scenes} image(s)."
        )

    # ── Preview & per-scene override ──────────────────────────────────
    if uploaded_files:
        sorted_files = sorted(uploaded_files, key=_natural_sort_key)

        # Build a lookup: scene_id → bulk file
        bulk_map: dict[int, object] = {}
        for i, f in enumerate(sorted_files):
            if i < n_scenes:
                bulk_map[timed_scenes[i]["id"]] = f

        with st.expander("✏️ Preview & Edit Scene Mapping", expanded=True):
            for i, s in enumerate(timed_scenes):
                bulk_file = bulk_map.get(s["id"])
                bulk_name = bulk_file.name if bulk_file else "—"

                col_info, col_override = st.columns([3, 2])

                with col_info:
                    st.markdown(
                        f"**Scene {s['id']:02d}** · "
                        f"`{_fmt_ts(s['start'])}–{_fmt_ts(s['end'])}` "
                        f"({s['duration']:.1f}s)"
                    )
                    st.caption(s["text"])
                    # Show which file is currently assigned
                    override_file = st.session_state.get(f"override_{s['id']}")
                    if override_file:
                        st.markdown(f"📎 Using override: `{override_file.name}`")
                    elif bulk_file:
                        st.markdown(f"📎 Bulk: `{bulk_name}`")

                with col_override:
                    st.file_uploader(
                        "Replace image (optional)",
                        accept_multiple_files=False,
                        type=["png", "jpg", "jpeg"],
                        key=f"override_{s['id']}",
                        label_visibility="collapsed",
                    )

                if i < n_scenes - 1:
                    st.divider()

            # Show extras (if user uploaded more than needed)
            for i in range(n_scenes, len(sorted_files)):
                st.markdown(f"**⚠️ Extra** ← `{sorted_files[i].name}`")

    st.divider()

    # ── Action buttons ────────────────────────────────────────────────
    col_assemble, col_back, col_reset = st.columns(3)

    with col_assemble:
        if st.button(
            "🚀 Assemble Video",
            use_container_width=True,
            disabled=not match_ok,
        ):
            st.session_state["explainer_stage"] = "assembling"
            st.rerun()

    with col_back:
        if st.button(
            "⬅️ Back to Script",
            type="secondary",
            use_container_width=True,
        ):
            st.session_state["explainer_stage"] = "script_input"
            st.rerun()

    with col_reset:
        if st.button(
            "Cancel & Start Over",
            type="secondary",
            use_container_width=True,
        ):
            reset_pipeline()


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Assembly & FFmpeg Handoff
# ═══════════════════════════════════════════════════════════════════════════

def render_step3_assemble(sidebar_config: dict) -> None:
    """Write images to disk, build manifest, invoke the two-pass render."""
    timed_scenes: list[dict] = st.session_state["timed_scenes"]
    word_ts: list[dict] = st.session_state["word_timestamps"]
    work_dir: str = st.session_state["work_dir"]
    audio_path: str = st.session_state["master_audio_path"]
    voice: str = st.session_state["explainer_voice"]

    images_dir = os.path.join(work_dir, "images")
    fx_dir = os.path.join(work_dir, "fx")
    srt_path = os.path.join(work_dir, "subtitles.srt")
    clean_video_path = os.path.join(work_dir, "clean_explainer.mp4")
    final_video_path = os.path.join(work_dir, "final_explainer.mp4")

    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(fx_dir, exist_ok=True)

    # ── Retrieve uploaded files ───────────────────────────────────────
    uploaded_files = st.session_state.get("explainer_bulk_images")
    if not uploaded_files or len(uploaded_files) != len(timed_scenes):
        st.error("❌ Image upload mismatch. Going back.")
        st.session_state["explainer_stage"] = "manifest"
        st.rerun()
        return

    sorted_files = sorted(uploaded_files, key=_natural_sort_key)

    # ── Pass 1: Clean video (images + audio, no subtitles) ────────────
    with st.spinner("🎬 Pass 1 — Assembling clean video..."):
        # 1. Write images to disk (per-scene overrides take priority)
        for i, scene in enumerate(timed_scenes):
            override = st.session_state.get(f"override_{scene['id']}")
            img_file = override if override else sorted_files[i]
            img_path = os.path.join(images_dir, f"{scene['id']:03d}_scene.png")
            with open(img_path, "wb") as f:
                f.write(img_file.getvalue())

        # 2. Build the ExplainerManifest for the compositor
        full_narration = " ".join(s["text"] for s in timed_scenes)

        manifest_scenes = []
        for s in timed_scenes:
            manifest_scenes.append(
                Scene(
                    scene_id=s["id"],
                    narration_segment=s["text"],
                    image_prompt_data={},
                    video_prompt_data={},
                    overlay_fx=None,
                    start_time=s["start"],
                    end_time=s["end"],
                    duration=s["duration"],
                )
            )

        manifest = ExplainerManifest(
            title="explainer_video",
            voice_name=voice,
            full_narration=full_narration,
            scenes=manifest_scenes,
        )

        # 3. Export SRT subtitles (used in Pass 2)
        export_srt(word_ts, srt_path, max_words_per_card=3)

        # 4. Render clean video via FFmpeg (no subtitles)
        try:
            render_2_5D_short(
                manifest=manifest,
                images_dir=images_dir,
                fx_dir=fx_dir,
                audio_path=audio_path,
                output_mp4=clean_video_path,
            )
        except (RuntimeError, ValueError) as e:
            st.error(f"❌ Pass 1 Failed:\n```\n{e}\n```")
            return

    # ── Pass 2: Burn subtitles onto the clean video ───────────────────
    with st.spinner("🔤 Pass 2 — Burning subtitles..."):
        try:
            burn_subtitles_to_video(
                input_mp4=clean_video_path,
                srt_path=srt_path,
                output_mp4=final_video_path,
                config=sidebar_config,
            )
        except (RuntimeError, ValueError) as e:
            st.error(f"❌ Pass 2 (Subtitles) Failed:\n```\n{e}\n```")
            return

    st.success("✅ Render complete!")
    st.session_state["explainer_manifest"] = manifest.model_dump()
    st.session_state["explainer_stage"] = "complete"
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — Complete / Download
# ═══════════════════════════════════════════════════════════════════════════

def render_step4_complete() -> None:
    """Display the rendered video with download button."""
    work_dir = st.session_state["work_dir"]
    output_path = os.path.join(work_dir, "final_explainer.mp4")

    if not os.path.exists(output_path):
        st.error("❌ Output video not found. Something went wrong during render.")
        if st.button("Start Over"):
            reset_pipeline()
        return

    st.success("✅ Video Rendered Successfully!")

    with open(output_path, "rb") as f:
        video_bytes = f.read()

    st.video(video_bytes)

    st.download_button(
        label="⬇️ Download Video",
        data=video_bytes,
        file_name="explainer_video.mp4",
        mime="video/mp4",
        use_container_width=True,
    )

    st.divider()
    if st.button("🔄 Start New Video", use_container_width=True):
        reset_pipeline()


# ═══════════════════════════════════════════════════════════════════════════
# STREAMLIT UI — ENTRY POINT / ROUTER
# ═══════════════════════════════════════════════════════════════════════════

def render_explainer_mode(sidebar_config: dict) -> None:
    """Render the Explainer Pipeline mode tab (state machine router)."""
    _init_state()

    stage = st.session_state["explainer_stage"]

    if stage == "script_input":
        render_step1_script_input()
    elif stage == "manifest":
        render_step2_manifest()
    elif stage == "assembling":
        render_step3_assemble(sidebar_config)
    elif stage == "complete":
        render_step4_complete()
    else:
        st.error(f"Unknown pipeline stage: {stage}")
        if st.button("Reset Pipeline"):
            reset_pipeline()