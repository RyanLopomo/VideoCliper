import json
from pathlib import Path
from faster_whisper import WhisperModel

from app.utils.pipeline_logger import log

model = WhisperModel("small", device="cpu", compute_type="int8")


def transcribe_audio(audio_path, output_path, language="pt", beam_size=5, progress_callback=None):
    log("WHISPER", "Iniciando...")
    segments, info = model.transcribe(audio_path, beam_size=beam_size, language=language)
    transcript = {"language": info.language, "duration": info.duration, "segments": []}
    for segment in segments:
        transcript["segments"].append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
        })
        if progress_callback and info.duration:
            progress_callback(min(99, round((float(segment.end) / float(info.duration)) * 100)))
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(transcript, file, ensure_ascii=False, indent=2)
    if progress_callback:
        progress_callback(100)
    log("WHISPER", "Finalizado.")
    return transcript
