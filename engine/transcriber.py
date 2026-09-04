"""
engine/transcriber.py — Local Whisper Transcription Engine

Uses faster-whisper (CTranslate2) for high-speed local transcription with
word-level timestamps.  Features:

  - Model caching via @st.cache_resource (loads once, stays in memory)
  - Auto CUDA/CPU device detection with appropriate compute types
  - Word-level timestamp extraction
  - Shorts-style caption chunking (1–3 words per pop-up, punchy timing)
"""

import streamlit as st
from faster_whisper import WhisperModel


# ---------------------------------------------------------------------------
# Model sizes available in faster-whisper
# ---------------------------------------------------------------------------
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v2"]
DEFAULT_MODEL = "base"


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------
def detect_device() -> tuple[str, str]:
    """
    Auto-detect the best compute device for faster-whisper.

    Returns
    -------
    (device, compute_type) : tuple[str, str]
        ("cuda", "float16") if CUDA is available, else ("cpu", "int8").
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass

    return "cpu", "int8"


# ---------------------------------------------------------------------------
# Cached model loader
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading Whisper model…")
def _load_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    """
    Load a faster-whisper model.  Cached by Streamlit so the model stays
    in memory across app reruns — only re-loads when arguments change.
    """
    print(f"🎙️ Loading Whisper model: {model_size} ({device}/{compute_type})")
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def get_model(model_size: str = DEFAULT_MODEL) -> WhisperModel:
    """
    Get a cached Whisper model instance.

    Parameters
    ----------
    model_size : str
        One of: "tiny", "base", "small", "medium", "large-v2"
    """
    device, compute_type = detect_device()
    return _load_model(model_size, device, compute_type)


# ---------------------------------------------------------------------------
# Word-level timestamp extraction
# ---------------------------------------------------------------------------
def extract_word_timestamps(
    audio_path: str,
    model_size: str = DEFAULT_MODEL,
) -> list[dict]:
    """
    Transcribe an audio file and return word-level timestamps.

    Parameters
    ----------
    audio_path : str
        Path to an audio file (WAV, MP3, etc.).
    model_size : str
        Whisper model size to use.

    Returns
    -------
    list[dict]
        Each dict has keys: "word" (str), "start" (float), "end" (float).
    """
    model = get_model(model_size)

    print(f"🎙️ Transcribing: {audio_path}")
    segments, info = model.transcribe(audio_path, word_timestamps=True)

    word_data = []
    for segment in segments:
        if segment.words is None:
            continue
        for word in segment.words:
            word_data.append({
                "word": word.word.strip(),
                "start": round(word.start, 3),
                "end": round(word.end, 3),
            })

    print(f"✅ Transcription complete. Extracted {len(word_data)} words.")
    return word_data


# ---------------------------------------------------------------------------
# Shorts-style caption chunking
# ---------------------------------------------------------------------------
# Tuning constants
MAX_WORDS_PER_CHUNK = 3       # 1–3 words per on-screen pop-up
MAX_CHUNK_DURATION = 1.2       # Max seconds a single caption card stays on screen
MIN_CHUNK_DURATION = 0.25      # Minimum duration to avoid flicker
GAP_THRESHOLD = 0.35           # Silence gap (seconds) that forces a chunk break


def chunk_words_for_shorts(
    word_data: list[dict],
    max_words: int = MAX_WORDS_PER_CHUNK,
    max_duration: float = MAX_CHUNK_DURATION,
    gap_threshold: float = GAP_THRESHOLD,
) -> list[dict]:
    """
    Group word-level timestamps into punchy Shorts-style subtitle chunks.

    Each chunk contains 1–3 words and lasts 0.25–1.2 seconds.  Natural
    pauses (gaps > gap_threshold) force a chunk break for rhythmic delivery.

    Parameters
    ----------
    word_data : list[dict]
        Output from extract_word_timestamps().
    max_words : int
        Maximum words per subtitle card (default: 3).
    max_duration : float
        Maximum duration in seconds per card (default: 1.2).
    gap_threshold : float
        Silence gap that forces a new chunk (default: 0.35s).

    Returns
    -------
    list[dict]
        Each dict has keys: "text" (str), "start" (float), "end" (float),
        "words" (list[dict]) — the original word entries in this chunk.
    """
    if not word_data:
        return []

    chunks: list[dict] = []
    current_words: list[dict] = []

    def _flush():
        """Emit the current word buffer as a finished chunk."""
        if not current_words:
            return
        text = " ".join(w["word"] for w in current_words)
        start = current_words[0]["start"]
        end = current_words[-1]["end"]

        # Enforce minimum duration to avoid flicker
        if end - start < MIN_CHUNK_DURATION:
            end = start + MIN_CHUNK_DURATION

        chunks.append({
            "text": text,
            "start": round(start, 3),
            "end": round(end, 3),
            "words": list(current_words),
        })

    for i, word in enumerate(word_data):
        # ── Check break conditions before adding this word ────────────
        if current_words:
            prev = current_words[-1]

            # Gap break: silence between words exceeds threshold
            gap = word["start"] - prev["end"]
            if gap >= gap_threshold:
                _flush()
                current_words = []

            # Word count break
            elif len(current_words) >= max_words:
                _flush()
                current_words = []

            # Duration break
            elif word["end"] - current_words[0]["start"] > max_duration:
                _flush()
                current_words = []

        current_words.append(word)

    # Flush remaining words
    _flush()

    return chunks