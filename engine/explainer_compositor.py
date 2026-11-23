"""
engine/explainer_compositor.py — Clean Video Render Engine (Pass 1)

Assembles static scene images and mastered voiceover audio into a
clean 9:16 vertical CFR MP4 using the FFmpeg concat demuxer.

Subtitles are burned in a separate pass by
``engine.explainer_subtitles.burn_subtitles_to_video``.

Pipeline:
  1. Concat demuxer → sequential image decoding (memory-safe).
  2. scale=1080:1920 → setsar=1 → fps=30 → setpts=PTS-STARTPTS.
  3. Voiceover audio → muxed as AAC.

Output: 1080×1920 @ 30 fps, libx264 (yuv420p), AAC 192 kbps.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.explainer_audio import ExplainerManifest


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

TARGET_WIDTH: int = 1080
TARGET_HEIGHT: int = 1920
TARGET_FPS: int = 30



# ═══════════════════════════════════════════════════════════════════════════
# RENDER ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def render_2_5D_short(
    manifest: "ExplainerManifest",
    images_dir: str,
    fx_dir: str,
    audio_path: str,
    output_mp4: str,
) -> str:
    """Composite scene images and audio into a clean CFR MP4 (no subtitles).

    Subtitles are burned in a separate pass by
    ``engine.explainer_subtitles.burn_subtitles_to_video``.

    Pipeline:
      1. Concat demuxer → sequential image decoding (memory-safe).
      2. ``scale=1080:1920,setsar=1,fps=30,setpts=PTS-STARTPTS``
      3. Voiceover audio → muxed as AAC.

    Parameters
    ----------
    manifest : ExplainerManifest
        Fully aligned manifest (``start_time``, ``duration`` populated).
    images_dir : str
        Directory containing ``{scene_id:03d}_scene.png`` files.
    fx_dir : str
        Directory containing transparent ``.webm`` FX clips.
    audio_path : str
        Path to the mastered voiceover MP3.
    output_mp4 : str
        Destination path for the rendered MP4.

    Returns
    -------
    str
        Absolute path to the rendered output file.

    Raises
    ------
    ValueError
        If the manifest contains no renderable scenes.
    FileNotFoundError
        If a required scene image or the audio file is missing.
    RuntimeError
        If FFmpeg returns a non-zero exit code.
    """

    # ── Filter renderable scenes ──────────────────────────────────────
    scenes = [
        s for s in manifest.scenes
        if s.start_time is not None
        and s.duration is not None
        and s.duration > 0
    ]
    if not scenes:
        raise ValueError("No renderable scenes (missing timing data).")

    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    out_dir = os.path.dirname(os.path.abspath(output_mp4)) or "."
    os.makedirs(out_dir, exist_ok=True)

    # ── Validate scene images exist ───────────────────────────────────
    for scene in scenes:
        img_path = os.path.join(images_dir, f"{scene.scene_id:03d}_scene.png")
        if not os.path.isfile(img_path):
            raise FileNotFoundError(f"Scene image not found: {img_path}")

    # ── Write concat demuxer file ─────────────────────────────────────
    CONCAT_NAME = "concat.txt"
    concat_path = os.path.join(out_dir, CONCAT_NAME)

    with open(concat_path, "w", encoding="utf-8") as cf:
        for scene in scenes:
            img_path = os.path.join(images_dir, f"{scene.scene_id:03d}_scene.png")
            safe_path = os.path.abspath(img_path).replace("\\", "/")
            cf.write(f"file '{safe_path}'\n")
            cf.write(f"duration {scene.duration:.3f}\n")
        # Repeat last file to prevent a 1-frame flash at the end
        last_path = os.path.abspath(
            os.path.join(images_dir, f"{scenes[-1].scene_id:03d}_scene.png")
        ).replace("\\", "/")
        cf.write(f"file '{last_path}'\n")

    print(f"  Wrote concat file: {concat_path} ({len(scenes)} scenes)")

    # ── Build FFmpeg command ──────────────────────────────────────────
    cmd: list[str] = ["ffmpeg", "-y"]

    # Input 0: video via concat demuxer
    cmd.extend([
        "-f", "concat",
        "-safe", "0",
        "-i", concat_path,
    ])

    # Input 1: audio
    cmd.extend(["-i", audio_path])

    # ── Filter: scale + CFR + PTS reset (no subtitles) ────────────────
    filter_complex = (
        f"[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT},setsar=1,"
        f"fps={TARGET_FPS},setpts=PTS-STARTPTS[vout]"
    )

    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", "[vout]", "-map", "1:a"])
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-r", str(TARGET_FPS),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_mp4,
    ])

    # ── Execute FFmpeg ────────────────────────────────────────────────
    n = len(scenes)
    print(f"  Running FFmpeg Pass 1 — clean video ({n} scene(s)) ...")
    print(f"  Filter: {filter_complex}")
    print(f"\n⚙️ FFmpeg Command:\n{' '.join(cmd)}\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            cwd=out_dir,
        )

        stderr_log = result.stderr.decode("utf-8", errors="replace")
        print(f"\n📋 FFmpeg Log (Pass 1):\n{stderr_log}\n")

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg exited with code {result.returncode}:\n"
                f"{stderr_log[-3000:]}"
            )
    finally:
        # Clean up concat file
        if os.path.isfile(concat_path):
            try:
                os.remove(concat_path)
            except OSError:
                pass

    abs_output = os.path.abspath(output_mp4)
    size_mb = os.path.getsize(abs_output) / (1024 * 1024)
    print(f"  Pass 1 complete: {abs_output} ({size_mb:.1f} MB)")

    return abs_output


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from engine.explainer_audio import ExplainerManifest, Scene
    from PIL import Image as PILImage

    TEST_DIR = os.path.join("temp_workspace", "compositor_test")
    IMAGES_DIR = os.path.join(TEST_DIR, "images")
    FX_DIR = os.path.join(TEST_DIR, "fx")

    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(FX_DIR, exist_ok=True)

    # ── Create dummy scene images (solid colour) ──────────────────────
    SCENE_COLOURS = [
        (20, 30, 80),   # dark blue
        (80, 20, 40),   # dark red
        (20, 70, 40),   # dark green
    ]
    for i, colour in enumerate(SCENE_COLOURS, start=1):
        img = PILImage.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), colour)
        img.save(os.path.join(IMAGES_DIR, f"{i:03d}_scene.png"))
    print(f"  Created {len(SCENE_COLOURS)} dummy scene images.")

    # ── Create 10 s of silent audio ───────────────────────────────────
    audio_path = os.path.join(TEST_DIR, "silence.mp3")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", "10", "-c:a", "libmp3lame", "-q:a", "9",
            audio_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    print(f"  Created silent audio: {audio_path}")

    # ── Create dummy SRT ──────────────────────────────────────────────
    srt_path = os.path.join(TEST_DIR, "test.srt")
    with open(srt_path, "w", encoding="utf-8") as fp:
        fp.write(
            "1\n00:00:00,000 --> 00:00:03,000\nScene One\n\n"
            "2\n00:00:03,500 --> 00:00:06,500\nScene Two\n\n"
            "3\n00:00:07,000 --> 00:00:09,500\nScene Three\n\n"
        )
    print(f"  Created dummy SRT: {srt_path}")

    # ── Build test manifest ───────────────────────────────────────────
    test_manifest = ExplainerManifest(
        title="Compositor_Test",
        full_narration="Scene one. Scene two. Scene three.",
        scenes=[
            Scene(
                scene_id=1,
                narration_segment="Scene one.",
                visual_prompt="test",
                start_time=0.0,
                end_time=3.5,
                duration=3.5,
            ),
            Scene(
                scene_id=2,
                narration_segment="Scene two.",
                visual_prompt="test",
                overlay_fx="accent.webm",  # won't exist → skipped gracefully
                start_time=3.5,
                end_time=6.5,
                duration=3.0,
            ),
            Scene(
                scene_id=3,
                narration_segment="Scene three.",
                visual_prompt="test",
                start_time=6.5,
                end_time=9.5,
                duration=3.0,
            ),
        ],
    )

    output_mp4 = os.path.join(TEST_DIR, "compositor_output.mp4")

    print("=" * 60)
    print("SHORTS FORGE AI — Compositor Engine Test")
    print("=" * 60)
    print(f"  Images:  {os.path.abspath(IMAGES_DIR)}")
    print(f"  FX dir:  {os.path.abspath(FX_DIR)}")
    print(f"  Audio:   {os.path.abspath(audio_path)}")
    print(f"  SRT:     {os.path.abspath(srt_path)}")
    print(f"  Output:  {os.path.abspath(output_mp4)}")
    print()

    result_path = render_2_5D_short(
        manifest=test_manifest,
        images_dir=IMAGES_DIR,
        fx_dir=FX_DIR,
        audio_path=audio_path,
        srt_path=srt_path,
        output_mp4=output_mp4,
    )

    print(f"\n  Final output: {result_path}")
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
