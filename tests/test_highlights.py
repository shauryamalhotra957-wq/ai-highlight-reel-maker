from ai_media_lab.common.schemas import TranscriptResult, TranscriptSegment
from ai_media_lab.reel.service import select_highlights


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

