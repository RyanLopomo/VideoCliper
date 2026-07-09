import subprocess

def burn_subtitles(input_video, subtitle_file, output_video):
    command = ["ffmpeg", "-i", input_video, "-vf", f"subtitles={subtitle_file}",
                "-c:v", "livx264", "-c:a", "aac", output_video, "-y"]
    
    subprocess.run(command, check=True)