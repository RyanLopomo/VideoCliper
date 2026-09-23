import json

from app.services.clip_finder import fallback_clips, normalize_clips


def transcript_with_segments(count=12, step=20):
    return {
        "duration": count * step,
        "segments": [
            {
                "start": index * step,
                "end": (index + 1) * step,
                "text": f"Momento importante numero {index}.",
            }
            for index in range(count)
        ],
    }


def test_normalize_clips_limits_count_and_duration():
    transcript = transcript_with_segments()
    raw = [
        {"title": f"Clip {index}", "start_time": index * 20, "end_time": index * 20 + 60}
        for index in range(6)
    ]

    clips = normalize_clips(raw, transcript, target_clips=3, target_duration=60)

    assert len(clips) == 3
    assert all(15 <= clip["end_time"] - clip["start_time"] <= 60 for clip in clips)


def test_normalize_clips_allows_three_minute_shorts_target():
    transcript = {
        "duration": 220,
        "segments": [
            {"start": 0, "end": 90, "text": "Historia completa."},
            {"start": 90, "end": 175, "text": "Conclusao importante."},
        ],
    }

    clips = normalize_clips(
        [{"title": "Longo", "start_time": 0, "end_time": 175}],
        transcript,
        target_clips=1,
        target_duration=180,
    )

    assert len(clips) == 1
    assert clips[0]["end_time"] - clips[0]["start_time"] == 175


def test_fallback_returns_fewer_clips_when_transcript_has_few_candidates():
    transcript = transcript_with_segments(count=2, step=20)

    clips = fallback_clips(transcript, target_clips=5, target_duration=60)

    assert 1 <= len(clips) < 5
    assert len(json.dumps(clips)) > 2


def test_repeated_candidates_stop_without_reaching_target():
    transcript = transcript_with_segments(count=8, step=20)
    raw = [
        {"title": "Mesmo trecho", "start_time": 0, "end_time": 40},
        {"title": "Mesmo trecho duplicado", "start_time": 1, "end_time": 39},
        {"title": "Mesmo trecho novamente", "start_time": 0, "end_time": 40},
    ]

    clips = normalize_clips(raw, transcript, target_clips=5, target_duration=60)

    assert len(clips) == 1
