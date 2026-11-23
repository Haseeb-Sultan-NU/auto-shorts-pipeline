"""
engine/explainer_audio.py — Script & Audio Timing Engine (Step 1)

Core responsibilities:
  1. Strict Pydantic schema for 2D Explainer JSON manifests.
  2. TTS voiceover synthesis via edge-tts with word-level boundary capture.
  3. Scene ↔ timestamp alignment for downstream visual scene cuts.
  4. SRT subtitle export with short-form caption chunking.

Dependencies: edge-tts, pydantic ≥ 2.0
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Optional

import edge_tts
from pydantic import BaseModel, Field

# ── Suppress Windows WinError 10054 during async websocket teardown ───
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class Scene(BaseModel):
    scene_id: int
    narration_segment: str
    
    # We replaced visual_prompt (str) with these two dictionaries
    image_prompt_data: dict 
    video_prompt_data: dict
    
    overlay_fx: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration: Optional[float] = None


class ExplainerManifest(BaseModel):
    """Root manifest defining a complete 2D explainer video.

    ``full_narration`` is the concatenated text sent to TTS in a single
    call.  Each scene's ``narration_segment`` must be a contiguous
    ordered substring of ``full_narration``.
    """

    title: str
    voice_name: str = Field(
        default="en-US-ChristopherNeural",
        description="Microsoft Edge TTS voice identifier.",
    )
    full_narration: str
    scenes: list[Scene]


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

# edge-tts reports WordBoundary offsets in 100-nanosecond ticks.
_TICKS_PER_SECOND: int = 10_000_000

# Strip all non-word, non-whitespace characters (unicode-safe).
_STRIP_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation for fuzzy word matching."""
    return _STRIP_RE.sub("", text).lower().strip()


def _tokenize(text: str) -> list[str]:
    """Split *text* into a list of normalized, non-empty tokens."""
    return [tok for tok in _normalize(text).split() if tok]


def _srt_timestamp(seconds: float) -> str:
    """Format *seconds* as an SRT timestamp ``HH:MM:SS,mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ═══════════════════════════════════════════════════════════════════════════
# TTS SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════

async def synthesize_voiceover(
    text: str,
    voice: str,
    output_audio_path: str,
) -> list[dict]:
    """Synthesize speech via Microsoft Edge TTS and capture word boundaries.

    Streams audio chunks to *output_audio_path* (MP3) and collects
    ``WordBoundary`` events emitted by the TTS engine.

    Parameters
    ----------
    text : str
        Full narration text to synthesize.
    voice : str
        Edge TTS voice identifier (e.g. ``'en-US-ChristopherNeural'``).
    output_audio_path : str
        Destination file path for the generated MP3.

    Returns
    -------
    list[dict]
        Word-level timestamps sorted chronologically::

            [{"word": str, "start": float, "end": float}, ...]

        Times are in **seconds**, rounded to 3 decimal places.

    Raises
    ------
    edge_tts.exceptions.NoAudioReceived
        If the TTS engine returns no audio data.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)

    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    word_timestamps: list[dict] = []

    with open(output_audio_path, "wb") as fp:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fp.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                offset_s = chunk["offset"] / _TICKS_PER_SECOND
                duration_s = chunk["duration"] / _TICKS_PER_SECOND
                word_timestamps.append({
                    "word": chunk["text"],
                    "start": round(offset_s, 3),
                    "end": round(offset_s + duration_s, 3),
                })

    return word_timestamps


# ═══════════════════════════════════════════════════════════════════════════
# SCENE ↔ TIMESTAMP ALIGNMENT
# ═══════════════════════════════════════════════════════════════════════════

def align_scenes_with_timestamps(
    manifest: ExplainerManifest,
    word_timestamps: list[dict],
) -> ExplainerManifest:
    """Map each scene's narration segment to concrete start/end times.
    
    Uses aggressive text normalization and mathematical fallbacks to prevent crashes
    if the LLM hallucinated words or if punctuation mismatches occur.
    """
    if not word_timestamps or not manifest.scenes:
        return manifest

    total_audio_duration = word_timestamps[-1]["end"]
    
    # Normalize TTS words to ignore punctuation mismatches
    tts_words = []
    for wt in word_timestamps:
        norm = _tokenize(wt["word"])
        tts_words.append(norm[0] if norm else "")
        
    last_end_idx = 0
    last_end_time = 0.0

    for i, scene in enumerate(manifest.scenes):
        # Force zero-gaps by starting exactly where the last scene ended
        scene.start_time = round(last_end_time, 3)
        
        # If it's the last scene, it simply runs until the audio ends
        if i == len(manifest.scenes) - 1:
            scene.end_time = round(total_audio_duration, 3)
        else:
            # Find where the NEXT scene starts
            next_scene_words = _tokenize(manifest.scenes[i+1].narration_segment)
            match_idx = -1
            
            # Sliding window to find the next scene's start word
            if next_scene_words:
                target_word = next_scene_words[0]
                for j in range(last_end_idx, len(tts_words)):
                    if tts_words[j] == target_word:
                        match_idx = j
                        break
            
            if match_idx != -1:
                # Perfect match found
                scene.end_time = round(word_timestamps[match_idx]["start"], 3)
                last_end_idx = match_idx
            else:
                # FALLBACK: If LLM hallucinated, estimate the duration proportionally 
                # so the pipeline never crashes.
                fallback_duration = total_audio_duration / len(manifest.scenes)
                scene.end_time = round(last_end_time + fallback_duration, 3)

        # Calculate final duration
        scene.duration = round(scene.end_time - scene.start_time, 3)
        last_end_time = scene.end_time

    return manifest


# ═══════════════════════════════════════════════════════════════════════════
# SRT EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def export_srt(
    word_timestamps: list[dict],
    output_srt_path: str,
    max_words_per_card: int = 3,
) -> None:
    """Chunk word timestamps into short subtitle cards and write ``.srt``.

    Chunking mirrors the Shorts-style rhythm from
    ``transcriber.chunk_words_for_shorts``:

    * 1–*max_words_per_card* words per on-screen card.
    * Silence gaps ≥ 0.35 s force a card break.
    * Minimum card duration clamped to 0.25 s to prevent flicker.

    Parameters
    ----------
    word_timestamps : list[dict]
        Chronological word boundaries from :func:`synthesize_voiceover`.
    output_srt_path : str
        Destination file path for the ``.srt`` output.
    max_words_per_card : int
        Maximum words per subtitle card (default ``3``).
    """
    GAP_THRESHOLD = 0.35  # seconds
    MIN_DURATION = 0.25   # seconds

    if not word_timestamps:
        return

    # ── Chunk words ───────────────────────────────────────────────────
    chunks: list[list[dict]] = []
    buf: list[dict] = []

    for word in word_timestamps:
        if buf:
            gap = word["start"] - buf[-1]["end"]
            if gap >= GAP_THRESHOLD or len(buf) >= max_words_per_card:
                chunks.append(buf)
                buf = []
        buf.append(word)

    if buf:
        chunks.append(buf)

    # ── Write SRT ─────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(os.path.abspath(output_srt_path)), exist_ok=True)

    with open(output_srt_path, "w", encoding="utf-8") as fp:
        for idx, chunk in enumerate(chunks, start=1):
            start = chunk[0]["start"]
            end = chunk[-1]["end"]

            # Enforce minimum duration to prevent flicker.
            if end - start < MIN_DURATION:
                end = start + MIN_DURATION

            text = " ".join(w["word"] for w in chunk)

            fp.write(f"{idx}\n")
            fp.write(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n")
            fp.write(f"{text}\n\n")


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    SAMPLE_MANIFEST = ExplainerManifest(
        title="How_Black_Holes_Work",
        full_narration=(
            "A black hole forms when a massive star collapses under its own gravity. "
            "The result is a region of space where gravity is so intense that nothing can escape. "
            "Not even light itself can break free from its pull."
        ),
        scenes=[
            Scene(
                scene_id=1,
                narration_segment=(
                    "A black hole forms when a massive star collapses under its own gravity."
                ),
                visual_prompt="Dramatic star collapse animation, deep space background",
            ),
            Scene(
                scene_id=2,
                narration_segment=(
                    "The result is a region of space where gravity is so intense that nothing can escape."
                ),
                visual_prompt="Warped spacetime grid pulled toward singularity",
                overlay_fx="slow_zoom",
            ),
            Scene(
                scene_id=3,
                narration_segment=(
                    "Not even light itself can break free from its pull."
                ),
                visual_prompt="Light beams bending and vanishing into event horizon",
                overlay_fx="zoom_in",
            ),
        ],
    )

    async def _run_test() -> None:
        output_dir = os.path.join("temp_workspace", "explainer_test")
        os.makedirs(output_dir, exist_ok=True)

        audio_path = os.path.join(output_dir, "voiceover.mp3")
        srt_path = os.path.join(output_dir, "subtitles.srt")
        manifest_path = os.path.join(output_dir, "aligned_manifest.json")

        print("=" * 60)
        print("SHORTS FORGE AI — Explainer Audio Engine Test")
        print("=" * 60)

        # ── 1. Synthesize ─────────────────────────────────────────────
        print("\n[1/3] Synthesizing voiceover via edge-tts …")
        word_ts = await synthesize_voiceover(
            text=SAMPLE_MANIFEST.full_narration,
            voice=SAMPLE_MANIFEST.voice_name,
            output_audio_path=audio_path,
        )
        print(f"      ✅ {len(word_ts)} word boundaries captured")
        print(f"      📄 Audio: {os.path.abspath(audio_path)}")
        for w in word_ts:
            print(f"         {w['start']:>7.3f}s → {w['end']:>7.3f}s  {w['word']}")

        # ── 2. Align ──────────────────────────────────────────────────
        print("\n[2/3] Aligning scenes to word timestamps …")
        aligned = align_scenes_with_timestamps(SAMPLE_MANIFEST, word_ts)
        for sc in aligned.scenes:
            st = f"{sc.start_time:>7.3f}" if sc.start_time is not None else "   None"
            et = f"{sc.end_time:>7.3f}" if sc.end_time is not None else "   None"
            du = f"{sc.duration:>5.3f}" if sc.duration is not None else " None"
            print(
                f"      Scene {sc.scene_id}: "
                f"{st}s -> {et}s "
                f"({du}s)  "
                f"\"{sc.narration_segment[:50]}...\""
            )

        # ── 3. Export SRT ─────────────────────────────────────────────
        print("\n[3/3] Exporting SRT subtitles …")
        export_srt(word_ts, srt_path, max_words_per_card=3)
        print(f"      ✅ SRT: {os.path.abspath(srt_path)}")

        # ── Dump aligned manifest ─────────────────────────────────────
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(aligned.model_dump(), f, indent=2)
        print(f"      📋 Manifest: {os.path.abspath(manifest_path)}")

        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)

    asyncio.run(_run_test())