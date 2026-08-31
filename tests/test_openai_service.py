import math

from ai_media_lab.common.openai_service import _segments_from_payload


def test_segments_ignore_non_finite_and_zero_length_timestamps():
    payload = {
        "segments": [
            {"start": "not-a-number", "end": 2, "text": "bad start"},
            {"start": 5, "end": 4, "text": "reversed"},
            {"start": 1, "end": 3, "text": "valid"},
            {"start": 3, "end": math.inf, "text": "infinite"},
        ]
    }

    segments = _segments_from_payload(payload, "fallback text.")

    assert [(segment.start, segment.end, segment.text) for segment in segments] == [
        (1.0, 3.0, "valid")
    ]


def test_segments_fall_back_to_text_when_all_payload_segments_are_invalid():
    payload = {"segments": [{"start": 1, "end": 1, "text": "empty"}]}

    segments = _segments_from_payload(payload, "fallback text.")

    assert segments
    assert segments[0].text == "fallback text."
