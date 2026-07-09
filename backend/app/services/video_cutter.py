import subprocess
from pathlib import Path

def generate_clip(input_video: str, output_video: str, start: float, end: float):
    
    duration = end - start

    command = [
        "ffmpeg",
        "-i", input_video,
        "-ss", str(start),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        output_video,
        "-y",
    ]

    subprocess.run(command, check=True)