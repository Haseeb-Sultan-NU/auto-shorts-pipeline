import subprocess
import os

def master_voiceover(input_path: str, output_path: str):
    """
    Applies professional vocal mastering to an audio file using FFmpeg:
    1. highpass=f=80: Rolls off low-end rumble below 80Hz.
    2. treble=g=4:f=3000: Boosts upper-mid/high frequencies (3kHz+) by 4dB for clarity.
    3. acompressor: Lightly compresses the dynamic range to keep the volume punchy and consistent.
    """
    print(f"🎙️ Mastering audio: {input_path}")
    
    # The FFmpeg audio filter chain
    eq_filters = "highpass=f=80,treble=g=4:f=3000,acompressor=threshold=-15dB:ratio=3:attack=5:release=50:makeup=2"
    
    command = [
        "ffmpeg",
        "-y",               # Overwrite output file if it exists
        "-i", input_path,   # Input file
        "-af", eq_filters,  # Apply the audio filter chain
        output_path         # Output file
    ]
    
    try:
        # Run FFmpeg silently, only throwing an error if it fails
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"❌ Audio mastering failed: {e}")
        # Fallback to the original unmastered audio if FFmpeg fails
        return input_path