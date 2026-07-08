import subprocess

def extract_audio(
        video_path: str, audio_path: str):
    command = ["ffmpeg", "-i", video_path, "-vn", "-acodec", "mpcm_s16le",
                "-ar", "16000", "-ac", "1", audio_path, "-y"]
    subprocess.run(command, check=True)