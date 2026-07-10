from pathlib import Path

from ai_media_lab.common.ffmpeg_service import FFmpegRunner, format_timestamp, parse_duration, write_srt
from ai_media_lab.common.schemas import TranscriptSegment


def test_parse_duration_from_ffmpeg_stderr():
    stderr = "Input #0\n  Duration: 00:01:02.50, start: 0.000000, bitrate: 512 kb/s"

    assert parse_duration(stderr) == 62.5


def test_format_timestamp_for_srt():
    assert format_timestamp(3661.234) == "01:01:01,234"


def test_write_srt_uses_relative_clip_times(tmp_path: Path):
    target = tmp_path / "clip.srt"
    write_srt(
        target,
        [TranscriptSegment(start=10, end=14, text="The key quote lands here.")],
        clip_start=8,
        clip_end=18,
        fallback_text="Fallback",
    )

    content = target.read_text(encoding="utf-8")
    assert "00:00:02,000 --> 00:00:06,000" in content
    assert "The key quote lands here." in content


def test_bundled_ffmpeg_is_available_after_install():
    assert FFmpegRunner().available()

