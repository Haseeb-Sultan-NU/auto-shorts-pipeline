"""
ui/mode_tts.py — Standalone Text-to-Speech Studio

Supports two engines:
  • Edge-TTS  (free, neural, zero API key)
  • ElevenLabs (premium, requires ELEVENLABS_API_KEY)

Produces downloadable MP3 audio + optional SRT subtitles.
"""

import asyncio
import io
import os
import sys
import tempfile
from typing import Optional

import edge_tts
import streamlit as st
from mutagen.mp3 import MP3

# ── Suppress Windows WinError 10054 during async websocket teardown ───
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

_TICKS_PER_SECOND = 10_000_000

# Hand-curated persona hints for the most popular Edge voices.
# Falls back to a generic label for unlisted voices.
_VOICE_PERSONAS: dict[str, str] = {
    "en-US-ChristopherNeural": "Conversational / Documentary",
    "en-US-GuyNeural":         "News / Narrative",
    "en-US-JennyNeural":       "Friendly / Expressive",
    "en-US-AriaNeural":        "Warm / Versatile",
    "en-US-DavisNeural":       "Calm / Professional",
    "en-US-JaneNeural":        "Informative / Bright",
    "en-US-JasonNeural":       "Authoritative / Steady",
    "en-US-NancyNeural":       "Soft / Gentle",
    "en-US-TonyNeural":        "Casual / Friendly",
    "en-US-SaraNeural":        "Youthful / Cheerful",
    "en-US-AndrewNeural":      "Mature / Measured",
    "en-US-BrianNeural":       "Clear / Direct",
    "en-US-EmmaNeural":        "Natural / Engaging",
    "en-GB-RyanNeural":        "British / Authoritative",
    "en-GB-SoniaNeural":       "British / Warm",
    "en-GB-LibbyNeural":       "British / Youthful",
    "en-AU-WilliamNeural":     "Australian / Relaxed",
    "en-AU-NatashaNeural":     "Australian / Warm",
    "en-CA-LiamNeural":        "Canadian / Neutral",
    "en-CA-ClaraNeural":       "Canadian / Clear",
}

# Default ElevenLabs voices (no API call needed for the list)
_ELEVENLABS_DEFAULT_VOICES = [
    ("Adam",    "pNInz6obpgDQGcFmaJgB"),
    ("Antoni",  "ErXwobaYiN019PkySvjV"),
    ("Rachel",  "21m00Tcm4TlvDq8ikWAM"),
    ("Domi",    "AZnzlk1XvdvUeBnXmlld"),
    ("Bella",   "EXAVITQu4vr4xnSDxMaL"),
    ("Elli",    "MF3mGyEYCl7XYWbV9V6O"),
    ("Josh",    "TxGEqnHWrfWFTfGW9XjX"),
    ("Sam",     "yoZ06aMxZJJ28mfd3POQ"),
]


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC BRIDGE
# ═══════════════════════════════════════════════════════════════════════════

def _run_async(coro):
    """Execute an async coroutine from Streamlit's synchronous thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
# EDGE-TTS: VOICE DISCOVERY (cached)
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner="Fetching available voices...")
def _fetch_edge_voices() -> list[dict]:
    """Fetch and cache all available Edge-TTS voices (runs once per session)."""
    async def _inner():
        return await edge_tts.list_voices()
    return _run_async(_inner())


def _format_voice_label(v: dict) -> str:
    """Build a rich display label: ShortName — Gender | Locale | Persona."""
    short = v["ShortName"]
    gender = v.get("Gender", "Unknown")
    locale = v.get("Locale", "")
    persona = _VOICE_PERSONAS.get(short, "Neural Voice")
    return f"{short} — {gender} ({locale}, {persona})"


# ═══════════════════════════════════════════════════════════════════════════
# EDGE-TTS: SYNTHESIS WITH WORD BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════

async def _synthesize_edge(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    output_path: str,
) -> list[dict]:
    """Synthesize via Edge-TTS, capturing word-boundary timestamps.

    Returns list of {"word": str, "start": float, "end": float}.
    """
    communicate = edge_tts.Communicate(
        text, voice, rate=rate, pitch=pitch, volume=volume,
        boundary="WordBoundary",
    )
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


# ═══════════════════════════════════════════════════════════════════════════
# ELEVENLABS: SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════

def _synthesize_elevenlabs(
    text: str,
    voice_id: str,
    api_key: str,
    stability: float,
    similarity: float,
    style: float,
    speaker_boost: bool,
    output_path: str,
) -> None:
    """Synthesize via ElevenLabs REST API (v1) and write MP3 to output_path."""
    import requests

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": speaker_boost,
        },
    }

    resp = requests.post(url, json=payload, headers=headers, stream=True)
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=4096):
            f.write(chunk)


# ═══════════════════════════════════════════════════════════════════════════
# SRT BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _srt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(word_timestamps: list[dict], max_words: int = 3) -> str:
    """Chunk word boundaries into short SRT caption groups."""
    if not word_timestamps:
        return ""

    lines: list[str] = []
    idx = 1
    i = 0
    while i < len(word_timestamps):
        group = word_timestamps[i : i + max_words]
        start = _srt_timestamp(group[0]["start"])
        end = _srt_timestamp(group[-1]["end"])
        text = " ".join(w["word"] for w in group)
        lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
        idx += 1
        i += max_words

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# STREAMLIT UI — ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def render_tts_mode(sidebar_config: dict) -> None:
    """Render the standalone Text-to-Speech studio tab."""

    st.markdown(
        "<p style='color:#999;font-size:13px;margin-top:-8px;'>"
        "Generate high-quality neural speech from text — free with Edge-TTS "
        "or premium via ElevenLabs."
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Detect ElevenLabs key availability ────────────────────────────
    el_key_env = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    el_available = bool(el_key_env)

    # ══════════════════════════════════════════════════════════════════
    # ENGINE SELECTION
    # ══════════════════════════════════════════════════════════════════

    engine_options = ["🆓 Edge-TTS (Free Neural)"]
    if el_available:
        engine_options.append("💎 ElevenLabs (API)")

    engine = st.radio(
        "Engine",
        options=engine_options,
        horizontal=True,
        key="tts_engine_radio",
    )
    use_elevenlabs = "ElevenLabs" in engine

    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # VOICE + MODULATION CONTROLS
    # ══════════════════════════════════════════════════════════════════

    if not use_elevenlabs:
        # ── Edge-TTS voice discovery + filters ────────────────────────
        all_voices = _fetch_edge_voices()

        col_lang, col_gender = st.columns(2)

        # Language filter
        all_locales = sorted({v["Locale"] for v in all_voices if v["Locale"].startswith("en")})
        if not all_locales:
            all_locales = ["en-US"]

        with col_lang:
            selected_locale = st.selectbox(
                "🌐 Language / Locale",
                options=all_locales,
                index=all_locales.index("en-US") if "en-US" in all_locales else 0,
                key="tts_locale",
            )

        with col_gender:
            gender_filter = st.selectbox(
                "👤 Gender",
                options=["All", "Male", "Female"],
                key="tts_gender",
            )

        # Filter voices
        filtered = [
            v for v in all_voices
            if v["Locale"] == selected_locale
            and (gender_filter == "All" or v.get("Gender") == gender_filter)
        ]

        if not filtered:
            st.warning("No voices match your filters. Try broadening the selection.")
            return

        # Build labels
        voice_labels = [_format_voice_label(v) for v in filtered]
        voice_map = {_format_voice_label(v): v["ShortName"] for v in filtered}

        selected_label = st.selectbox(
            "🗣️ Voice",
            options=voice_labels,
            key="tts_voice_select",
        )
        selected_voice = voice_map[selected_label]

        # ── Modulation sliders ────────────────────────────────────────
        with st.expander("🎛️ Voice Modulation", expanded=False):
            mod_col1, mod_col2, mod_col3 = st.columns(3)

            with mod_col1:
                rate_val = st.slider(
                    "Speed / Rate",
                    min_value=-50, max_value=100, value=0, step=5,
                    format="%+d%%",
                    key="tts_rate",
                    help="Negative = slower, positive = faster.",
                )

            with mod_col2:
                pitch_val = st.slider(
                    "Pitch",
                    min_value=-50, max_value=50, value=0, step=5,
                    format="%+dHz",
                    key="tts_pitch",
                    help="Adjust vocal pitch up or down.",
                )

            with mod_col3:
                volume_val = st.slider(
                    "Volume",
                    min_value=-50, max_value=50, value=0, step=5,
                    format="%+d%%",
                    key="tts_volume",
                    help="Boost or attenuate output volume.",
                )

        # Format strings for edge-tts API
        rate_str = f"{rate_val:+d}%"
        pitch_str = f"{pitch_val:+d}Hz"
        volume_str = f"{volume_val:+d}%"

    else:
        # ── ElevenLabs controls ───────────────────────────────────────
        el_voice_labels = [name for name, _ in _ELEVENLABS_DEFAULT_VOICES]
        el_voice_map = {name: vid for name, vid in _ELEVENLABS_DEFAULT_VOICES}

        selected_el_name = st.selectbox(
            "🗣️ ElevenLabs Voice",
            options=el_voice_labels,
            key="tts_el_voice",
        )
        selected_el_id = el_voice_map[selected_el_name]

        with st.expander("🎛️ ElevenLabs Voice Settings", expanded=False):
            el_col1, el_col2 = st.columns(2)

            with el_col1:
                el_stability = st.slider(
                    "Stability",
                    0.0, 1.0, 0.5, 0.05,
                    key="tts_el_stability",
                    help="Higher = more consistent, lower = more expressive.",
                )
                el_style = st.slider(
                    "Style Exaggeration",
                    0.0, 1.0, 0.0, 0.05,
                    key="tts_el_style",
                    help="Amplify the original voice style.",
                )

            with el_col2:
                el_similarity = st.slider(
                    "Similarity / Clarity",
                    0.0, 1.0, 0.75, 0.05,
                    key="tts_el_similarity",
                    help="Higher = closer to original voice.",
                )
                el_boost = st.toggle(
                    "Speaker Boost",
                    value=True,
                    key="tts_el_boost",
                    help="Enhance speaker clarity.",
                )

    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # TEXT INPUT
    # ══════════════════════════════════════════════════════════════════

    script_text = st.text_area(
        "📝 Voiceover Script",
        height=200,
        placeholder="Type or paste your voiceover script here...",
        key="tts_script_input",
    )

    # Metrics
    if script_text:
        word_count = len(script_text.split())
        char_count = len(script_text)
        mc1, mc2 = st.columns(2)
        mc1.caption(f"**{word_count:,}** words")
        mc2.caption(f"**{char_count:,}** characters")

    # Filename
    output_filename = st.text_input(
        "💾 Output Filename",
        value="voiceover_export.mp3",
        key="tts_output_filename",
    )
    if not output_filename.endswith(".mp3"):
        output_filename += ".mp3"

    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # GENERATE BUTTON
    # ══════════════════════════════════════════════════════════════════

    can_generate = bool(script_text and script_text.strip())

    if st.button(
        "⚡ Generate Speech (MP3)",
        use_container_width=True,
        disabled=not can_generate,
    ):
        if not script_text or not script_text.strip():
            st.error("Please enter some text before generating audio.")
            return

        p_bar = st.progress(0, text="Preparing synthesis...")

        try:
            tmp_dir = tempfile.mkdtemp(prefix="sf_tts_")
            tmp_audio = os.path.join(tmp_dir, output_filename)
            word_ts: list[dict] = []

            if not use_elevenlabs:
                # ── Edge-TTS synthesis ────────────────────────────────
                p_bar.progress(20, text=f"🎙️ Synthesizing with {selected_voice}...")
                word_ts = _run_async(
                    _synthesize_edge(
                        text=script_text.strip(),
                        voice=selected_voice,
                        rate=rate_str,
                        pitch=pitch_str,
                        volume=volume_str,
                        output_path=tmp_audio,
                    )
                )
            else:
                # ── ElevenLabs synthesis ──────────────────────────────
                p_bar.progress(20, text=f"🎙️ Synthesizing with ElevenLabs ({selected_el_name})...")
                _synthesize_elevenlabs(
                    text=script_text.strip(),
                    voice_id=selected_el_id,
                    api_key=el_key_env,
                    stability=el_stability,
                    similarity=el_similarity,
                    style=el_style,
                    speaker_boost=el_boost,
                    output_path=tmp_audio,
                )

            p_bar.progress(80, text="📊 Measuring audio...")

            # ── Read audio bytes & measure duration ───────────────────
            audio_info = MP3(tmp_audio)
            duration = audio_info.info.length

            with open(tmp_audio, "rb") as f:
                audio_bytes = f.read()

            p_bar.progress(100, text="✅ Generation complete!")

            # ── Results ───────────────────────────────────────────────
            st.success(f"Audio generated — **{duration:.1f}s** duration, **{len(audio_bytes) / 1024:.0f} KB**")

            st.audio(audio_bytes, format="audio/mp3")

            dl_col1, dl_col2 = st.columns(2)

            with dl_col1:
                st.download_button(
                    label=f"⬇️ Download {output_filename}",
                    data=audio_bytes,
                    file_name=output_filename,
                    mime="audio/mpeg",
                    use_container_width=True,
                )

            # ── SRT subtitles (Edge-TTS only — has word boundaries) ───
            with dl_col2:
                if word_ts:
                    srt_content = _build_srt(word_ts, max_words=3)
                    srt_filename = output_filename.rsplit(".", 1)[0] + ".srt"
                    st.download_button(
                        label=f"📝 Download {srt_filename}",
                        data=srt_content.encode("utf-8"),
                        file_name=srt_filename,
                        mime="text/srt",
                        use_container_width=True,
                    )
                else:
                    st.caption("SRT subtitles are only available with Edge-TTS.")

        except Exception as e:
            p_bar.progress(100, text="❌ Synthesis failed")
            st.error(f"Error during synthesis: {e}")
