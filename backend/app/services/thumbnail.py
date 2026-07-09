import subprocess

def generate_thumbnail(video_path: str, output_path: str):
    command =["ffmpeg", "-i", video_path, "-frames:v", "1", output_path, "-y"]
    subprocess.run(command, check=True)