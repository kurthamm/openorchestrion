from openorchestrion.models import PerformanceType, PlaybackIntent


def test_dinner_music_intent_model() -> None:
    intent = PlaybackIntent(
        mode="station",
        duration_minutes=120,
        themes=["dinner"],
        moods=["relaxed"],
        familiarity="high",
        performance_types=[PerformanceType.SOLO_PIANO, PerformanceType.MULTI_INSTRUMENT],
    )
    assert intent.duration_minutes == 120
    assert "dinner" in intent.themes


def test_intent_rejects_excessive_duration() -> None:
    try:
        PlaybackIntent(mode="station", duration_minutes=2000)
    except ValueError:
        return
    raise AssertionError("duration validation should fail")
