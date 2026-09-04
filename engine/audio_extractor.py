"""
engine/audio_extractor.py — Fast Local Audio Extraction

Extracts clean 16kHz mono WAV audio from .mp4 video files using ffmpeg
subprocess calls.  Handles both file paths and in-memory BytesIO buffers.
Uses tempfile for clean lifecycle management of intermediate files.
"""

import os
import subprocess
import tempfile
from io import BytesIO
from typing import Union


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000   # Whisper expects 16kHz
CHANNELS = 1          # Mono


def extract_audio(
    source: Union[str, BytesIO],
    output_path: str | None = None,
    source_name: str = "clip.mp4",
) -> str:
    """
    Extract audio from a video file or BytesIO buffer to a 16kHz mono WAV.

    Parameters
    ----------
    source : str | BytesIO
        Absolute path to an .mp4 file, or an in-memory BytesIO buffer
        containing the video data.
    output_path : str | None
        If provided, write the WAV to this path.  Otherwise a temp file
        is created (caller is responsible for cleanup).
    source_name : str
        Filename hint used when source is a BytesIO (for the temp file ext).

    Returns
    -------
    str
        Absolute path to the extracted WAV file.

    Raises
    ------
    RuntimeError
        If ffmpeg is not found or the extraction fails.
    """

    # ── Resolve source to a file path ─────────────────────────────────
    temp_video = None

    if isinstance(source, BytesIO):
        ext = os.path.splitext(source_name)[1] or ".mp4"
        temp_video = tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, prefix="sf_vid_"
        )
        temp_video.write(source.getvalue())
        temp_video.close()
        input_path = temp_video.name
    else:
        input_path = source

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Video source not found: {input_path}")

    # ── Resolve output path ───────────────────────────────────────────
    if output_path is None:
        output_fd = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, prefix="sf_audio_"
        )
        output_fd.close()
        output_path = output_fd.name

    # ── Run ffmpeg ────────────────────────────────────────────────────
    cmd = [
        "ffmpeg",
        "-y",                           # Overwrite
        "-i", input_path,               # Input video
        "-vn",                          # Drop video stream
        "-acodec", "pcm_s16le",         # 16-bit PCM
        "-ar", str(SAMPLE_RATE),        # 16kHz
        "-ac", str(CHANNELS),           # Mono
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found.  Please install ffmpeg and ensure it is on your PATH."
        )
    except subprocess.CalledProcessError as e:
        stderr_text = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        raise RuntimeError(
            f"ffmpeg audio extraction failed (exit code {e.returncode}):\n{stderr_text}"
        )
    finally:
        # Clean up temp video file if we created one
        if temp_video and os.path.exists(temp_video.name):
            try:
                os.unlink(temp_video.name)
            except OSError:
                pass

    return output_path


def cleanup_temp_audio(path: str) -> None:
    """
    Safely remove a temporary audio file.

    Call this after transcription is complete to free disk space.
    Safe to call with any path — only deletes files in the system
    temp directory that match our naming prefix.
    """
    if not path:
        return

    temp_dir = tempfile.gettempdir()
    abs_path = os.path.abspath(path)

    # Safety: only delete files in temp dir with our prefix
    if abs_path.startswith(temp_dir) and os.path.basename(abs_path).startswith("sf_"):
        try:
            os.unlink(abs_path)
        except OSError:
            pass
