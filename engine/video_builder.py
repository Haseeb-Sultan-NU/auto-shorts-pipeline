import PIL.Image
# Fix for MoviePy 1.0.3 compatibility with newer Pillow versions
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = getattr(PIL.Image.Resampling, 'LANCZOS', PIL.Image.LANCZOS)

import os

# --- IMPORTANT: UPDATE THIS PATH TO YOUR EXACT IMAGEMAGICK MAGICK.EXE FILE ---
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
# -----------------------------------------------------------------------------

import math
import numpy as np
from PIL import Image as PILImage
from typing import List, Dict, Any, Optional, Callable

from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips,
    ColorClip,
    vfx
)

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS (preserved from original)
# ═══════════════════════════════════════════════════════════════════════════

def _cover_crop_frame(frame_array, target_w, target_h):
    """
    Takes a raw numpy frame, scales it to fully COVER target_w x target_h
    (no black bars, no squishing), then center-crops to the exact target size.
    Returns a numpy array of shape (target_h, target_w, 3).
    """
    img = PILImage.fromarray(frame_array)
    src_w, src_h = img.size

    # Compute scale factor to COVER the target canvas.
    scale = max(target_w / src_w, target_h / src_h)

    new_w = int(math.ceil(src_w * scale))
    new_h = int(math.ceil(src_h * scale))
    img = img.resize((new_w, new_h), PILImage.LANCZOS)

    # Center-crop to exact target dimensions
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    return np.array(img)


def create_zooming_image(image_path: str, duration: float, zoom_ratio: float = 0.04):
    """
    Creates a smooth Ken Burns slow-zoom effect on a static image.
    The image scales up by zoom_ratio (4% by default) over its duration.
    """
    src_img = PILImage.open(image_path).convert("RGB")
    src_w, src_h = src_img.size
    base_scale = max(TARGET_WIDTH / src_w, TARGET_HEIGHT / src_h)

    def make_frame(t):
        zoom = 1.0 + (zoom_ratio * (t / max(duration, 0.01)))
        effective_scale = base_scale * zoom

        new_w = int(math.ceil(src_w * effective_scale))
        new_h = int(math.ceil(src_h * effective_scale))

        zoomed = src_img.resize((new_w, new_h), PILImage.LANCZOS)

        left = (new_w - TARGET_WIDTH) // 2
        top = (new_h - TARGET_HEIGHT) // 2
        cropped = zoomed.crop((left, top, left + TARGET_WIDTH, top + TARGET_HEIGHT))

        return np.array(cropped)

    clip = ImageClip(make_frame(0)).set_duration(duration)
    clip = clip.fl(lambda gf, t: make_frame(t))
    clip = clip.set_duration(duration)
    return clip


def process_video_asset(video_path: str, duration: float):
    """
    Loads, mutes, trims, and cover-crops a video clip to 9:16 (1080x1920).
    """
    clip = VideoFileClip(video_path).without_audio()
    if clip.duration > duration:
        clip = clip.subclip(0, duration)
    else:
        clip = clip.set_duration(duration)

    clip = clip.fl_image(lambda frame: _cover_crop_frame(frame, TARGET_WIDTH, TARGET_HEIGHT))
    return clip


def apply_punch_in(clip, punch_duration=0.4, max_scale=1.12):
    """
    Simulates a dynamic camera 'punch in' by scaling the frame up 
    and smoothly settling back to normal size over the defined duration.
    """
    def effect(get_frame, t):
        frame = get_frame(t)
        if t >= punch_duration:
            return frame
            
        # Calculate dropping scale: starts at max_scale, ends at 1.0
        current_scale = 1.0 + (max_scale - 1.0) * (1.0 - (t / punch_duration))
        
        img = PILImage.fromarray(frame)
        w, h = img.size
        new_w, new_h = int(w * current_scale), int(h * current_scale)
        img = img.resize((new_w, new_h), PILImage.LANCZOS)
        
        # Center crop back to original clip dimensions
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        img = img.crop((left, top, left + w, top + h))
        return np.array(img)
        
    return clip.fl(effect)


# ═══════════════════════════════════════════════════════════════════════════
# CINEMATIC MOTION FILTER (Slow Zoom + Handheld Tremble)
# ═══════════════════════════════════════════════════════════════════════════

def apply_handheld_motion(clip, zoom_end: float = 1.05, tremble_px: float = 2.0):
    """
    Apply a cinematic handheld camera feel to a clip:
      - Slow linear zoom from 1.0x to zoom_end over the clip duration
      - Subtle X/Y tremble using smoothed sine waves (no randomness to
        avoid flicker on re-renders)

    The clip must already be at TARGET_WIDTH x TARGET_HEIGHT.
    """
    dur = clip.duration or 1.0

    # Pre-compute tremble frequencies (smooth sine, not random)
    freq_x = 3.7   # Hz — slow horizontal breathing
    freq_y = 2.9   # Hz — slightly different vertical rhythm

    def effect(get_frame, t):
        frame = get_frame(t)

        # Zoom: linear 1.0 → zoom_end
        zoom = 1.0 + (zoom_end - 1.0) * (t / max(dur, 0.01))

        # Tremble: smooth sine-based offset
        dx = tremble_px * math.sin(2 * math.pi * freq_x * t)
        dy = tremble_px * math.sin(2 * math.pi * freq_y * t + 0.7)

        img = PILImage.fromarray(frame)
        w, h = img.size

        new_w = int(math.ceil(w * zoom))
        new_h = int(math.ceil(h * zoom))
        img = img.resize((new_w, new_h), PILImage.LANCZOS)

        # Center crop with tremble offset
        cx = (new_w - w) // 2 + int(dx)
        cy = (new_h - h) // 2 + int(dy)

        # Clamp to stay within bounds
        cx = max(0, min(cx, new_w - w))
        cy = max(0, min(cy, new_h - h))

        img = img.crop((cx, cy, cx + w, cy + h))
        return np.array(img)

    return clip.fl(effect)


# ═══════════════════════════════════════════════════════════════════════════
# TRANSITION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

TRANSITION_NAMES = [
    "Hard Cut",
    "Crossfade",
    "Dip to Black",
    "Slide Left",
    "Whip Pan",
]

# Default overlap duration for blending transitions (seconds)
DEFAULT_TRANSITION_DURATION = 0.4


def join_clips_with_transition(
    clips: list,
    transition: str = "Hard Cut",
    t_dur: float = DEFAULT_TRANSITION_DURATION,
) -> "VideoFileClip":
    """
    Join a list of video clips using the selected transition.

    All transitions that involve blending shorten the total duration by
    t_dur * (n-1) to maintain audio sync.

    Parameters
    ----------
    clips : list
        List of MoviePy video clips (must all be same size).
    transition : str
        One of TRANSITION_NAMES.
    t_dur : float
        Duration of each transition in seconds.

    Returns
    -------
    VideoFileClip
        The concatenated clip with transitions applied.
    """
    if not clips:
        raise ValueError("No clips to join.")
    if len(clips) == 1:
        return clips[0]

    if transition == "Hard Cut":
        return concatenate_videoclips(clips, method="compose")

    elif transition == "Crossfade":
        return _crossfade(clips, t_dur)

    elif transition == "Dip to Black":
        return _dip_to_black(clips, t_dur)

    elif transition == "Slide Left":
        return _slide_left(clips, t_dur)

    elif transition == "Whip Pan":
        return _whip_pan(clips, t_dur)

    else:
        # Unknown transition — fall back to hard cut
        return concatenate_videoclips(clips, method="compose")


def _crossfade(clips, t_dur):
    """Overlap clips with opacity crossfade."""
    result = clips[0]
    for i in range(1, len(clips)):
        next_clip = clips[i]
        # CompositeVideoClip approach: overlay next clip with fadein
        # starting at (current_end - t_dur)
        overlap_start = max(0, result.duration - t_dur)
        next_clip = (
            next_clip
            .set_start(overlap_start)
            .crossfadein(t_dur)
        )
        result = CompositeVideoClip(
            [result, next_clip],
            size=(TARGET_WIDTH, TARGET_HEIGHT),
        )
        result = result.set_duration(overlap_start + clips[i].duration)
    return result


def _dip_to_black(clips, t_dur):
    """Fade out → black → fade in between clips."""
    half = t_dur / 2
    parts = []
    for i, clip in enumerate(clips):
        c = clip
        if i > 0:
            c = c.fx(vfx.fadein, half)
        if i < len(clips) - 1:
            c = c.fx(vfx.fadeout, half)
        parts.append(c)

    # Insert a short black gap between each pair
    black = ColorClip(
        size=(TARGET_WIDTH, TARGET_HEIGHT),
        color=(0, 0, 0),
    ).set_duration(0.08)

    assembled = []
    for i, part in enumerate(parts):
        assembled.append(part)
        if i < len(parts) - 1:
            assembled.append(black)

    return concatenate_videoclips(assembled, method="compose")


def _slide_left(clips, t_dur):
    """Slide the next clip in from the right over the current clip."""
    result = clips[0]
    for i in range(1, len(clips)):
        next_clip = clips[i]
        overlap_start = max(0, result.duration - t_dur)

        def make_position(t, _dur=t_dur):
            progress = min(1.0, t / max(_dur, 0.01))
            # Ease-out cubic
            progress = 1.0 - (1.0 - progress) ** 3
            x = int(TARGET_WIDTH * (1.0 - progress))
            return (x, 0)

        next_clip = (
            next_clip
            .set_start(overlap_start)
            .set_position(make_position)
        )
        result = CompositeVideoClip(
            [result, next_clip],
            size=(TARGET_WIDTH, TARGET_HEIGHT),
        )
        result = result.set_duration(overlap_start + clips[i].duration)
    return result


def _whip_pan(clips, t_dur):
    """
    Simulate a whip pan: apply motion blur via horizontal shift to the
    outgoing clip's last frames, then hard-cut to the next clip.
    Uses a flash frame to simulate the blur peak.
    """
    flash = ColorClip(
        size=(TARGET_WIDTH, TARGET_HEIGHT),
        color=(255, 255, 255),
    ).set_duration(0.06)

    parts = []
    for i, clip in enumerate(clips):
        parts.append(clip)
        if i < len(clips) - 1:
            parts.append(flash)
    return concatenate_videoclips(parts, method="compose")


# ═══════════════════════════════════════════════════════════════════════════
# SUBTITLE OVERLAY ENGINE (Phase 5 — configurable via sidebar)
# ═══════════════════════════════════════════════════════════════════════════

def generate_caption_clips(
    word_timestamps: List[Dict[str, Any]],
    font_color: str,
    stroke_color: str,
    font_size: int,
    vertical_pos,
    font_path: str = "",
):
    """
    Generates word-by-word dynamic subtitle TextClips.
    Uses a flat list to stack the stroke layer and fill layer sequentially.

    Parameters
    ----------
    word_timestamps : list[dict]
        Each dict has "word"/"text", "start", "end".
        Accepts both word-level dicts and chunked dicts.
    font_color : str
        Hex fill color (e.g. "#FFEB04").
    stroke_color : str
        Hex stroke color (e.g. "#000000").
    font_size : int
        Font size in pixels for 1080x1920 canvas.
    vertical_pos : int | str
        Either an int percentage (0-100) or legacy string ("center", "bottom", "top").
    font_path : str
        Absolute path to .ttf/.otf (forward slashes for ImageMagick).
    """
    caption_clips = []

    # Convert percentage to pixel y-position
    if isinstance(vertical_pos, (int, float)):
        y_pos = int(TARGET_HEIGHT * (vertical_pos / 100))
    elif vertical_pos == "top":
        y_pos = int(TARGET_HEIGHT * 0.15)
    elif vertical_pos == "center":
        y_pos = int(TARGET_HEIGHT * 0.5)
    else:
        y_pos = int(TARGET_HEIGHT * 0.75)

    actual_font_size = font_size
    thick_stroke = int(actual_font_size * 0.18)

    # Use provided font path or fallback to bundled font
    if font_path:
        font_selection = font_path
    else:
        font_selection = "D:/auto-shorts-pipeline/fonts/FeastOfFleshBb-AVm.ttf"

    for item in word_timestamps:
        # Accept both "word" key (word-level) and "text" key (chunked)
        text = item.get("text", item.get("word", "")).upper()
        start = item["start"]
        end = item["end"]
        duration = max(0.1, end - start)

        if not text.strip():
            continue

        try:
            # 1. Base Layer (Massive Stroke)
            outline_clip = (
                TextClip(
                    text,
                    fontsize=actual_font_size,
                    font=font_selection,
                    color=stroke_color,        
                    stroke_color=stroke_color, 
                    stroke_width=thick_stroke,
                    method="caption",
                    size=(int(TARGET_WIDTH * 0.9), None)
                )
                .set_start(start)
                .set_duration(duration)
                .set_position(("center", y_pos))
            )

            # 2. Top Layer (Pure Fill, No Stroke)
            fill_clip = (
                TextClip(
                    text,
                    fontsize=actual_font_size,
                    font=font_selection,
                    color=font_color, 
                    stroke_color=None,
                    stroke_width=0,
                    method="caption",
                    size=(int(TARGET_WIDTH * 0.9), None)
                )
                .set_start(start)
                .set_duration(duration)
                .set_position(("center", y_pos))
            )

            # Append sequentially: outline renders first, fill renders on top
            caption_clips.append(outline_clip)
            caption_clips.append(fill_clip)
            
        except Exception as e:
            print(f"⚠️ Warning: Failed to render text '{text}' with font '{font_selection}': {e}")

    return caption_clips


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-CLIP ASSEMBLY PIPELINE (Phase 5)
# ═══════════════════════════════════════════════════════════════════════════

def load_clip_with_audio(video_path: str, keep_audio: bool = True):
    """
    Load and cover-crop a video clip to 9:16, optionally keeping audio.
    """
    clip = VideoFileClip(video_path)
    if not keep_audio:
        clip = clip.without_audio()

    clip = clip.fl_image(
        lambda frame: _cover_crop_frame(frame, TARGET_WIDTH, TARGET_HEIGHT)
    )
    return clip


def assemble_multiclip(
    clip_paths: List[str],
    output_path: str,
    subtitle_chunks: List[Dict[str, Any]],
    config: dict,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Full multi-clip assembly pipeline.

    Parameters
    ----------
    clip_paths : list[str]
        Ordered list of .mp4 file paths.
    output_path : str
        Where to write the final rendered video.
    subtitle_chunks : list[dict]
        Chunked subtitle timing data from transcriber.chunk_words_for_shorts().
    config : dict
        Sidebar config dict containing all styling + effect settings.
    progress_callback : callable, optional
        Function(progress: float, message: str) for UI updates.
        progress is 0.0 to 1.0.

    Returns
    -------
    str
        Path to the rendered output file.
    """

    def _progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    keep_audio = config.get("multiclip_use_native_audio", True)
    transition = config.get("transition_type", "Hard Cut")
    apply_motion = config.get("apply_motion_filter", False)
    fade_in_dur = config.get("fade_in_duration", 0.0)
    fade_out_dur = config.get("fade_out_duration", 0.0)

    # ── 1. Load clips ─────────────────────────────────────────────────
    _progress(0.05, "📂 Loading video clips…")
    clips = []
    for i, path in enumerate(clip_paths):
        _progress(0.05 + 0.15 * (i / max(len(clip_paths), 1)),
                  f"📂 Loading clip {i+1}/{len(clip_paths)}…")
        clip = load_clip_with_audio(path, keep_audio=keep_audio)
        clips.append(clip)

    if not clips:
        raise ValueError("No valid clips could be loaded.")

    # ── 2. Apply motion filter ────────────────────────────────────────
    if apply_motion:
        _progress(0.25, "🎥 Applying handheld camera motion…")
        clips = [apply_handheld_motion(c) for c in clips]

    # ── 3. Concatenate with transitions ───────────────────────────────
    _progress(0.35, f"🔗 Joining clips ({transition})…")
    final_video = join_clips_with_transition(clips, transition=transition)

    # ── 4. Merge audio if keeping native ──────────────────────────────
    # When clips have native audio and were joined via concatenate,
    # audio is already embedded.  For composite transitions (crossfade,
    # slide), we rely on MoviePy's audio compositing.

    # ── 5. Generate subtitles ─────────────────────────────────────────
    _progress(0.50, "📝 Generating subtitle overlays…")
    subtitle_clips = generate_caption_clips(
        word_timestamps=subtitle_chunks,
        font_color=config.get("font_color", "#FFEB04"),
        stroke_color=config.get("stroke_color", "#000000"),
        font_size=config.get("font_size", 180),
        vertical_pos=config.get("subtitle_vertical_pct", 72),
        font_path=config.get("font_path", ""),
    )

    # ── 6. Composite subtitles over video ─────────────────────────────
    _progress(0.60, "🎞️ Compositing subtitles…")
    if subtitle_clips:
        composite = CompositeVideoClip(
            [final_video] + subtitle_clips,
            size=(TARGET_WIDTH, TARGET_HEIGHT),
        )
        # Preserve audio from the base video
        composite = composite.set_audio(final_video.audio)
        composite = composite.set_duration(final_video.duration)
    else:
        composite = final_video

    # ── 7. Apply global fades ─────────────────────────────────────────
    if fade_in_dur > 0:
        _progress(0.70, "🌅 Applying fade-in…")
        composite = composite.fx(vfx.fadein, fade_in_dur)
    if fade_out_dur > 0:
        _progress(0.72, "🌇 Applying fade-out…")
        composite = composite.fx(vfx.fadeout, fade_out_dur)

    # ── 8. Render ─────────────────────────────────────────────────────
    _progress(0.75, "🔧 Rendering final video (this may take a while)…")

    composite.write_videofile(
        output_path,
        fps=TARGET_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger=None,      # Suppress moviepy's tqdm to avoid log spam
    )

    _progress(0.95, "🧹 Cleaning up…")

    # Close all clips
    for c in clips:
        try:
            c.close()
        except Exception:
            pass
    try:
        final_video.close()
    except Exception:
        pass
    try:
        composite.close()
    except Exception:
        pass

    _progress(1.0, "✅ Render complete!")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════
# LEGACY ASSEMBLY (preserved for mode_legacy.py backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════

def assemble_short(
    json_blueprint: dict,
    audio_path: str,
    asset_files_map: Dict[str, str],
    word_timestamps: List[Dict[str, Any]],
    output_path: str,
    font_color: str = "#FFEB04",
    stroke_color: str = "#000000",
    font_size: int = 110,
    vertical_pos: str = "bottom",
    font_path: str = "",
):
    # 1. Load Audio
    voiceover = AudioFileClip(audio_path)
    total_audio_duration = voiceover.duration

    # 2. Sequence Visuals based on JSON
    visual_specs = json_blueprint.get("visual_assets", [])
    num_assets = max(len(visual_specs), len(asset_files_map))
    default_duration = total_audio_duration / max(num_assets, 1)

    visual_clips = []
    
    for idx, spec in enumerate(visual_specs):
        filename = spec.get("filename", "")
        filepath = asset_files_map.get(filename)
        
        if not filepath and idx < len(asset_files_map):
            filepath = list(asset_files_map.values())[idx]

        if not filepath or not os.path.exists(filepath):
            continue

        ext = os.path.splitext(filepath)[1].lower()
        clip_duration = spec.get("duration", default_duration)

        if ext in [".mp4", ".mov", ".webm"]:
            clip = process_video_asset(filepath, clip_duration)
        else:
            clip = create_zooming_image(filepath, clip_duration)

        visual_clips.append(clip)

    if not visual_clips:
        raise ValueError("No valid visual assets could be loaded.")

    # 3. Concatenate Visuals with Flash & Zoom Punch
    final_clips_with_transitions = []
    flash_duration = 0.15  # Increased slightly for better visibility

    for i, clip in enumerate(visual_clips):
        
        # Apply the camera punch-in to every incoming clip (except the first one)
        if i > 0:
            clip = apply_punch_in(clip, punch_duration=0.4, max_scale=1.12)
            
        final_clips_with_transitions.append(clip)
        
        # Add a white flash after every clip EXCEPT the very last one
        if i < len(visual_clips) - 1:
            flash = ColorClip(size=(TARGET_WIDTH, TARGET_HEIGHT), color=(255, 255, 255)).set_duration(flash_duration)
            final_clips_with_transitions.append(flash)

    # Concatenate everything together
    final_video = concatenate_videoclips(final_clips_with_transitions, method="compose")
    final_video = final_video.set_duration(total_audio_duration)
    final_video = final_video.set_audio(voiceover)

    # 4. Generate Subtitles
    subtitle_clips = generate_caption_clips(
        word_timestamps,
        font_color=font_color,
        stroke_color=stroke_color,
        font_size=font_size,
        vertical_pos=vertical_pos,
        font_path=font_path,
    )

    # 5. Composite Final Output (Flattened array)
    composite_elements = [final_video] + subtitle_clips
    final_composite = CompositeVideoClip(composite_elements, size=(TARGET_WIDTH, TARGET_HEIGHT))

    # 6. Render MP4
    final_composite.write_videofile(
        output_path,
        fps=TARGET_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4
    )

    voiceover.close()
    final_video.close()
    final_composite.close()
    
    return output_path