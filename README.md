# Shorts Forge AI

A local Streamlit app that turns scripts, images, voiceovers and AI-generated clips into finished 9:16 vertical videos (1080×1920) with word-by-word captions. Transcription runs locally with faster-whisper, and the video is assembled with FFmpeg and MoviePy.

The app has four modes, one per tab, plus a shared sidebar for caption styling.

## Modes

### 1. Legacy Asset Stitcher
Builds a short from a JSON blueprint, an uploaded voiceover (for example an ElevenLabs MP3) and a set of images or clips.

1. Paste a JSON blueprint that lists the visual assets in order.
2. Upload the voiceover MP3 and the visuals (PNG, JPG, MP4).
3. The voiceover is mastered with an FFmpeg filter chain (high-pass at 80 Hz, a treble lift and a compressor).
4. faster-whisper extracts word-level timestamps, which are chunked into short 1–3 word captions.
5. Images get a slow Ken Burns zoom, clips are cover-cropped to 9:16, and captions are rendered on top.

### 2. Multi-Clip Processor
Takes several finished `.mp4` clips (for example from AI video generators) and joins them into one video.

- Reorder clips with the arrow buttons.
- Use each clip's native audio, or use a separate voiceover.
- Transcribes the audio with faster-whisper and overlays word-by-word captions.
- Transitions: Hard Cut, Crossfade, Dip to Black, Slide Left, Whip Pan.
- Optional handheld camera motion (slow zoom plus a subtle tremble), and fade-in and fade-out.
- Shows a progress bar while rendering.

### 3. 2.5D Explainer
Script-driven explainer videos with exact timing between voice and images.

1. Paste a script, with one visual beat per line, and choose an Edge-TTS voice, rate and pitch.
2. The whole script is synthesised as one continuous MP3. Word boundaries from Edge-TTS are mapped back to each script line, which gives an exact start, end and duration for every scene.
3. A timestamped scene manifest is shown, with an audio preview. Upload one image per scene.
4. A first FFmpeg pass assembles the images and audio into a clean 1080×1920, 30 fps MP4. A second pass burns in the subtitles. Keeping the two passes separate avoids dropped subtitles on variable-frame-rate video and Windows path-parsing errors.

The manifest is validated with Pydantic (`ExplainerManifest`, `Scene`). `engine/prompt_templates.py` holds detailed JSON templates for writing video and image generation prompts for each scene.

### 4. Text to Speech
A standalone voiceover studio.

- Edge-TTS: free neural voices, no API key needed. It can also export SRT subtitles from word timings.
- ElevenLabs: optional, needs `ELEVENLABS_API_KEY`. SRT export is only available with Edge-TTS.
- Downloads the audio as MP3.

### Shared sidebar
- Caption font (scanned from the `fonts/` folder), font size, fill colour and stroke colour.
- Vertical caption position, with a live 9:16 phone-frame preview that marks safe and unsafe zones.
- Whisper model size: tiny, base, small, medium or large-v2. `base` is a good default. The CUDA GPU is used automatically when available, otherwise the CPU.

## Project structure

```
app.py                      Entry point and mode router
ui/
  sidebar.py                Caption styling, transitions, fades, Whisper model
  canvas.py                 Live 9:16 caption preview
  mode_legacy.py            Legacy Asset Stitcher tab
  mode_multiclip.py         Multi-Clip Processor tab
  mode_explainer.py         2.5D Explainer tab
  mode_tts.py               Text to Speech tab
engine/
  transcriber.py            faster-whisper transcription and caption chunking
  audio_extractor.py        FFmpeg audio extraction (16 kHz mono WAV)
  audio_synth.py            Voiceover mastering filter chain
  video_builder.py          Ken Burns zoom, cover-crop, transitions, motion, captions
  explainer_audio.py        Manifest schema, Edge-TTS timing, SRT export
  explainer_compositor.py   Image + audio to clean 9:16 MP4 (pass 1)
  explainer_subtitles.py    Subtitle burn-in (pass 2)
  prompt_templates.py       Video and image prompt JSON templates
utils/font_manager.py       Finds fonts in the fonts/ folder
fonts/                      Bundled caption fonts
```

## Requirements

- Python 3.9 or newer
- [FFmpeg](https://ffmpeg.org/) on your `PATH`
- [ImageMagick](https://imagemagick.org/), used by MoviePy for text rendering. `engine/video_builder.py` sets the binary path for Windows near the top of the file, so change it to match your install.
- An NVIDIA GPU is optional and speeds up transcription.

## Setup

```bash
git clone https://github.com/Haseeb-Sultan-NU/auto-shorts-pipeline.git
cd auto-shorts-pipeline
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Optional: create a `.env` file in the project root for ElevenLabs.

```
ELEVENLABS_API_KEY=your_key_here
```

## Run

```bash
streamlit run app.py
```

The app opens in your browser. Pick a mode tab, set your caption style in the sidebar, and follow the steps in that tab. Finished videos are written to `outputs/` and temporary files go to `temp_workspace/`. Both folders are ignored by Git.

## Built with

Streamlit, faster-whisper, edge-tts, MoviePy, FFmpeg, Pydantic, Pillow, mutagen.
