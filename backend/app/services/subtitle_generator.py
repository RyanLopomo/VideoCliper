from pathlib import Path

def seconds_to_srt_time(seconds: float):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds - int((seconds - int(seconds)) * 1000)
    
    return(
        f"{hours:02}:{miutes:02}:{secs:02},"
        f"{milliseconds:03}"
    )

def generate_srt(
        segments, output_path):
    with open(output_path, "w", encoding="utf-8") as file:
        for index, segment in enumerate( 
        segments, start=1):
            file.write(f"{segment['text']}n\n")