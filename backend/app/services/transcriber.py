import json
from pathlib import Path
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")


def transcribe_audio(audio_path, output_path, language="pt", beam_size=5):
    segments, info = model.transcribe(audio_path, beam_size=beam_size, language=language)
    transcript = {"language": info.language, "duration": info.duration, "segments": []}
    for segment in segments:
        transcript["segments"].append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
        })
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(transcript, file, ensure_ascii=False, indent=2)
    return transcript