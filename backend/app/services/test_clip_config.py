import pytest

from app.services.clip_config import clip_suggestion, normalize_clip_targets


@pytest.mark.parametrize(
    ("duration", "count"),
    [
        (300, 5),
        (600, 10),
        (1800, 30),
        (3600, 60),
        (150, 3),
        (80, 1),
        (120, 2),
    ],
)
def test_clip_suggestion_uses_one_clip_per_minute(duration, count):
    assert clip_suggestion(duration)["recommended_count"] == count


def test_normalize_clip_targets_accepts_manual_values():
    assert normalize_clip_targets(1800, 20, 120) == (20, 120)


@pytest.mark.parametrize(
    ("count", "duration", "message"),
    [
        (0, 60, "Quantidade"),
        (1, 14, "pelo menos 15"),
        (1, 181, "180 segundos"),
    ],
)
def test_normalize_clip_targets_validates_shorts_limits(count, duration, message):
    with pytest.raises(ValueError, match=message):
        normalize_clip_targets(1800, count, duration)
