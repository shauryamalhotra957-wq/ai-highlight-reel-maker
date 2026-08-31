import math

from ai_media_lab.common.schemas import TranscriptResult, TranscriptSegment
from ai_media_lab.reel.service import _finite_segment_duration, select_highlights


def test_select_highlights_scores_energy_and_outputs_captions():
    transcript = TranscriptResult(
        text="",
        provider="test",
        segments=[
            TranscriptSegment(start=0, end=8, text="This intro sets the stage."),
            TranscriptSegment(start=12, end=22, text="This is the best turning moment and a massive win!"),
            TranscriptSegment(start=42, end=52, text="The final quote is unbelievable and very important."),
        ],
    )

    clips = select_highlights(transcript, clip_count=2, platform="Sports", duration=70, scene_changes=[12.4])

    assert clips[0].title.startswith("This Is The Best")
    assert clips[0].caption
    assert clips[0].hashtags
    assert clips[0].score >= clips[-1].score


def test_finite_segment_duration_ignores_invalid_timestamps():
    segments = [
        TranscriptSegment(start=0, end=math.nan, text="unknown"),
        TranscriptSegment(start=math.inf, end=math.inf, text="invalid"),
        TranscriptSegment(start=1, end=4, text="valid"),
    ]

    assert _finite_segment_duration(segments) == 4


def test_finite_segment_duration_returns_none_without_valid_segments():
    segments = [
        TranscriptSegment(start=math.nan, end=math.nan, text="unknown"),
        TranscriptSegment(start=4, end=2, text="reversed"),
    ]

    assert _finite_segment_duration(segments) is None
