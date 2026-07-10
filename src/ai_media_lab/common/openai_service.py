from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_media_lab.common.config import get_settings
from ai_media_lab.common.files import read_text
from ai_media_lab.common.schemas import TranscriptResult, TranscriptSegment
from ai_media_lab.common.text_analysis import clean_transcript, segment_text


TEXT_EXTENSIONS = {".txt", ".md", ".srt", ".vtt"}
OPENAI_UPLOAD_LIMIT_BYTES = 24 * 1024 * 1024


def _demo_transcript(path: Path, kind: str) -> str:
    label = path.stem.replace("-", " ").replace("_", " ").strip() or "uploaded media"
    if kind == "reel":
        return (
            f"This is a demo transcript for {label}. The host opens with a strong hook, "
            "then lands a surprising insight about the main story. The middle section has "
            "a high-energy explanation, a memorable quote, and a clear emotional turn. "
            "Near the end, the speaker gives a crisp takeaway that would work well as a "
            "short social clip with captions."
        )
    return (
        f"This is a demo transcript for {label}. The lecture introduces the central problem, "
        "defines the important vocabulary, and explains why the topic matters. It compares "
        "several approaches, walks through an example, and highlights common mistakes. "
        "The final section summarizes the key concepts and gives a practical study strategy."
    )


def _coerce_openai_response(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return {"text": payload}
    return {"text": str(payload)}


def _segments_from_payload(payload: dict[str, Any], text: str) -> list[TranscriptSegment]:
    raw_segments = payload.get("segments") or []
    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        segment_text_value = clean_transcript(str(item.get("text") or ""))
        if not segment_text_value:
            continue
        segments.append(
            TranscriptSegment(
                start=float(item.get("start") or 0.0),
                end=float(item.get("end") or 0.0),
                text=segment_text_value,
            )
        )
    return segments or segment_text(text)


def _shift_segments(segments: list[TranscriptSegment], offset: float) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=segment.start + offset, end=segment.end + offset, text=segment.text)
        for segment in segments
    ]


def _chunk_audio_if_needed(path: Path) -> list[Path]:
    if path.stat().st_size <= OPENAI_UPLOAD_LIMIT_BYTES:
        return [path]

    from ai_media_lab.common.ffmpeg_service import FFmpegRunner

    runner = FFmpegRunner()
    if not runner.available():
        return [path]

    chunk_dir = path.parent / f"{path.stem}-openai-chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    target_pattern = chunk_dir / "chunk-%03d.mp3"
    runner.run(
        [
            "-hide_banner",
            "-y",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            "-f",
            "segment",
            "-segment_time",
            "600",
            "-reset_timestamps",
            "1",
            str(target_pattern),
        ],
        timeout=600,
    )
    chunks = sorted(chunk_dir.glob("chunk-*.mp3"))
    return chunks or [path]


def _probe_duration(path: Path) -> float:
    try:
        from ai_media_lab.common.ffmpeg_service import FFmpegRunner

        duration = FFmpegRunner().probe_duration(path)
        return float(duration or 0.0)
    except Exception:
        return 0.0


def transcribe_media(path: Path, kind: str, prefer_segments: bool = False, force_demo: bool = False) -> TranscriptResult:
    settings = get_settings()
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        text = clean_transcript(read_text(path))
        return TranscriptResult(
            text=text,
            segments=segment_text(text),
            provider="uploaded-text",
            model=None,
        )

    if force_demo or not settings.openai_enabled:
        text = _demo_transcript(path, kind)
        return TranscriptResult(
            text=text,
            segments=segment_text(text),
            provider="demo",
            model=None,
        )

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.transcribe_model
    all_text: list[str] = []
    all_segments: list[TranscriptSegment] = []
    cursor = 0.0
    for chunk in _chunk_audio_if_needed(path):
        with chunk.open("rb") as audio_file:
            request: dict[str, Any] = {"model": model, "file": audio_file}
            if model == "whisper-1" and prefer_segments:
                request["response_format"] = "verbose_json"
                request["timestamp_granularities"] = ["segment"]
            if model == "whisper-1" and all_text:
                request["prompt"] = " ".join(" ".join(all_text).split()[-80:])
            response = client.audio.transcriptions.create(**request)

        payload = _coerce_openai_response(response)
        chunk_text = clean_transcript(str(payload.get("text") or ""))
        chunk_segments = _segments_from_payload(payload, chunk_text)
        all_text.append(chunk_text)
        all_segments.extend(_shift_segments(chunk_segments, cursor))
        cursor += _probe_duration(chunk) or max((segment.end for segment in chunk_segments), default=0.0)

    text = clean_transcript(" ".join(all_text))
    return TranscriptResult(
        text=text,
        segments=all_segments or segment_text(text),
        language=None,
        provider="openai",
        model=model,
    )


def generate_json_with_openai(instructions: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.openai_enabled:
        return None

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.responses.create(
            model=settings.text_model,
            reasoning={"effort": "low"},
            instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False),
        )
    except Exception:
        return None
    text = getattr(response, "output_text", "") or ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
