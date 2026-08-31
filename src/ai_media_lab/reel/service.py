from __future__ import annotations

import math
from pathlib import Path

from fastapi import UploadFile

from ai_media_lab.common.config import service_path
from ai_media_lab.common.ffmpeg_service import FFmpegError, FFmpegRunner, write_srt
from ai_media_lab.common.files import new_job_id, save_upload, write_json
from ai_media_lab.common.openai_service import TEXT_EXTENSIONS, transcribe_media
from ai_media_lab.common.schemas import HighlightClip, ReelJobResult, TranscriptResult, TranscriptSegment
from ai_media_lab.common.text_analysis import extract_keywords, split_sentences


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
ENERGY_WORDS = {
    "amazing",
    "best",
    "breakthrough",
    "crazy",
    "critical",
    "decisive",
    "final",
    "first",
    "highlight",
    "important",
    "insane",
    "key",
    "massive",
    "mistake",
    "moment",
    "never",
    "secret",
    "surprising",
    "turning",
    "unbelievable",
    "win",
}


def _target_duration(platform: str) -> tuple[float, float]:
    normalized = platform.lower()
    if "podcast" in normalized:
        return 35.0, 55.0
    if "sports" in normalized:
        return 12.0, 28.0
    if "tiktok" in normalized or "short" in normalized or "reel" in normalized:
        return 18.0, 38.0
    return 22.0, 45.0


def _clip_title(text: str) -> str:
    words = [word.strip(".,!?;:") for word in text.split() if word.strip(".,!?;:")]
    if not words:
        return "Highlight Moment"
    title = " ".join(words[:8]).strip()
    return title.title()


def _caption(text: str, platform: str) -> str:
    sentence = split_sentences(text)[0] if split_sentences(text) else text
    sentence = sentence.strip()
    if not sentence:
        return f"Best moment for {platform}"
    return sentence[:140].rstrip(" ,.;:") + ("..." if len(sentence) > 140 else "")


def _hashtags(text: str, platform: str) -> list[str]:
    tags = [f"#{word.title().replace('-', '')}" for word in extract_keywords(text, limit=4)]
    platform_tag = "#" + platform.replace(" ", "").replace("-", "").title()
    tags.insert(0, platform_tag)
    unique: list[str] = []
    for tag in tags:
        if tag not in unique:
            unique.append(tag)
    return unique[:5]


def _score_segment(segment: TranscriptSegment, scene_changes: list[float]) -> tuple[float, str]:
    text = segment.text
    tokens = {word.lower().strip(".,!?;:") for word in text.split()}
    energy_hits = len(tokens & ENERGY_WORDS)
    punctuation = text.count("!") * 0.7 + text.count("?") * 0.35
    length_score = min(2.0, max(0.2, len(text.split()) / 16))
    scene_bonus = 0.0
    if scene_changes:
        midpoint = (segment.start + segment.end) / 2
        nearest = min(abs(midpoint - scene) for scene in scene_changes)
        scene_bonus = max(0.0, 1.2 - nearest / 4)
    score = energy_hits * 1.4 + punctuation + length_score + scene_bonus
    reason_parts = []
    if energy_hits:
        reason_parts.append("high-signal wording")
    if punctuation:
        reason_parts.append("strong delivery cue")
    if scene_bonus:
        reason_parts.append("near a scene change")
    return score, ", ".join(reason_parts) or "clear standalone idea"


def _finite_segment_duration(segments: list[TranscriptSegment]) -> float | None:
    ends = [
        segment.end
        for segment in segments
        if math.isfinite(segment.start)
        and math.isfinite(segment.end)
        and segment.end > segment.start
    ]
    return max(ends) if ends else None


def _fallback_segments(transcript: TranscriptResult) -> list[TranscriptSegment]:
    if transcript.segments:
        return transcript.segments
    cursor = 0.0
    segments: list[TranscriptSegment] = []
    for sentence in split_sentences(transcript.text):
        duration = max(5.0, min(18.0, len(sentence.split()) * 0.5))
        segments.append(TranscriptSegment(start=cursor, end=cursor + duration, text=sentence))
        cursor += duration + 0.4
    return segments


def build_visual_only_transcript(filename: str, duration: float | None, scene_changes: list[float]) -> TranscriptResult:
    media_duration = max(10.0, float(duration or 30.0))
    label = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "uploaded video"
    anchors = [scene for scene in scene_changes if 0 <= scene <= media_duration]
    if not anchors:
        anchors = [media_duration * 0.25, media_duration * 0.5, media_duration * 0.75]

    segments: list[TranscriptSegment] = []
    for index, anchor in enumerate(anchors[:8], start=1):
        start = max(0.0, anchor - 4.0)
        end = min(media_duration, max(start + 4.0, anchor + 4.0))
        segments.append(
            TranscriptSegment(
                start=start,
                end=end,
                text=f"{label} visual highlight candidate {index}. Strong motion or composition change around {anchor:.1f} seconds.",
            )
        )

    text = " ".join(segment.text for segment in segments)
    return TranscriptResult(text=text, segments=segments, provider="visual-only", model=None)


def select_highlights(
    transcript: TranscriptResult,
    clip_count: int,
    platform: str,
    duration: float | None,
    scene_changes: list[float],
) -> list[HighlightClip]:
    min_duration, max_duration = _target_duration(platform)
    segments = _fallback_segments(transcript)
    scored: list[tuple[float, TranscriptSegment, str]] = []
    for segment in segments:
        score, reason = _score_segment(segment, scene_changes)
        scored.append((score, segment, reason))
    scored.sort(key=lambda item: (-item[0], item[1].start))

    selected: list[HighlightClip] = []
    occupied: list[tuple[float, float]] = []
    media_duration = duration or (segments[-1].end if segments else max_duration)
    for score, segment, reason in scored:
        desired = min(max_duration, max(min_duration, segment.end - segment.start + 10.0))
        center = (segment.start + segment.end) / 2
        start = max(0.0, center - desired / 2)
        end = min(media_duration, start + desired)
        start = max(0.0, end - desired)
        if any(not (end <= taken_start or start >= taken_end) for taken_start, taken_end in occupied):
            continue
        clip_index = len(selected) + 1
        selected.append(
            HighlightClip(
                clip_id=f"clip-{clip_index:02d}",
                title=_clip_title(segment.text),
                start=round(start, 2),
                end=round(end, 2),
                duration=round(end - start, 2),
                score=round(score, 2),
                reason=reason,
                caption=_caption(segment.text, platform),
                hashtags=_hashtags(segment.text, platform),
                source_text=segment.text,
            )
        )
        occupied.append((start, end))
        if len(selected) >= max(1, min(12, clip_count)):
            break

    if selected:
        return selected

    total = media_duration or 60.0
    chunks = max(1, min(clip_count, 4))
    chunk_duration = min(max_duration, max(min_duration, total / (chunks + 1)))
    for index in range(chunks):
        start = max(0.0, (index + 1) * total / (chunks + 1) - chunk_duration / 2)
        end = min(total, start + chunk_duration)
        selected.append(
            HighlightClip(
                clip_id=f"clip-{index + 1:02d}",
                title=f"Highlight {index + 1}",
                start=round(start, 2),
                end=round(end, 2),
                duration=round(end - start, 2),
                score=1.0,
                reason="evenly sampled fallback",
                caption="A compact highlight candidate from the source media.",
                hashtags=[f"#{platform.replace(' ', '').title()}", "#Highlight"],
                source_text="",
            )
        )
    return selected


def render_edl(result: ReelJobResult) -> str:
    lines = [
        f"# Highlight Reel EDL: {result.filename}",
        "",
        f"- Job: {result.job_id}",
        f"- Status: {result.status}",
        f"- Duration: {result.duration if result.duration is not None else 'unknown'} seconds",
        "",
        "| Clip | In | Out | Length | Title | Caption |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for clip in result.clips:
        lines.append(
            f"| {clip.clip_id} | {clip.start:.2f} | {clip.end:.2f} | {clip.duration:.2f} | "
            f"{clip.title} | {clip.caption} |"
        )
    if result.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(["", "## Titles And Hashtags"])
    for clip in result.clips:
        lines.append(f"- {clip.title}: {' '.join(clip.hashtags)}")
    return "\n".join(lines).strip() + "\n"


async def process_reel_upload(
    upload: UploadFile,
    clip_count: int = 5,
    platform: str = "YouTube Shorts",
    captions: bool = True,
    demo_mode: bool = False,
) -> ReelJobResult:
    job_id = new_job_id("reel")
    uploads_dir = service_path("reel", "uploads")
    job_dir = service_path("reel", "jobs", job_id)
    input_path = await save_upload(upload, uploads_dir)
    job_source = job_dir / input_path.name
    input_path.replace(job_source)

    runner = FFmpegRunner()
    ffmpeg_ready = runner.available()
    warnings: list[str] = []
    duration: float | None = None
    scene_changes: list[float] = []
    media_for_transcript = job_source
    has_audio = True
    suffix = job_source.suffix.lower()

    if suffix in VIDEO_EXTENSIONS and ffmpeg_ready:
        try:
            duration = runner.probe_duration(job_source)
            scene_changes = runner.detect_scene_changes(job_source)
            has_audio = runner.has_audio_stream(job_source)
            if has_audio:
                media_for_transcript = runner.extract_audio(job_source, job_dir / "audio.wav")
            else:
                media_for_transcript = None
        except (FFmpegError, TimeoutError) as error:
            warnings.append(f"FFmpeg preprocessing failed: {error}")
            media_for_transcript = job_source
    elif suffix in VIDEO_EXTENSIONS:
        warnings.append("FFmpeg is unavailable; returning an edit decision list without rendered MP4 clips.")

    if media_for_transcript is None:
        transcript = build_visual_only_transcript(upload.filename or job_source.name, duration, scene_changes)
    else:
        transcript = transcribe_media(media_for_transcript, kind="reel", prefer_segments=True, force_demo=demo_mode)
    if duration is None:
        duration = _finite_segment_duration(transcript.segments)

    clips = select_highlights(
        transcript=transcript,
        clip_count=clip_count,
        platform=platform,
        duration=duration,
        scene_changes=scene_changes,
    )

    can_render_video = suffix in VIDEO_EXTENSIONS and ffmpeg_ready
    for clip in clips:
        srt_path = job_dir / f"{clip.clip_id}.srt"
        if captions:
            write_srt(
                srt_path,
                transcript.segments,
                clip_start=clip.start,
                clip_end=clip.end,
                fallback_text=clip.caption,
            )
            clip.srt_url = f"/api/jobs/{job_id}/files/{srt_path.name}"
        if can_render_video:
            try:
                clip_path = job_dir / f"{clip.clip_id}.mp4"
                runner.cut_clip(job_source, clip.start, clip.duration, clip_path)
                clip.video_url = f"/api/jobs/{job_id}/files/{clip_path.name}"
            except (FFmpegError, TimeoutError) as error:
                warnings.append(f"Could not render {clip.clip_id}: {error}")

    result = ReelJobResult(
        job_id=job_id,
        filename=upload.filename or job_source.name,
        transcript=transcript,
        duration=duration,
        scene_changes=scene_changes,
        clips=clips,
        edit_decision_list_url=f"/api/jobs/{job_id}/files/edit-decision-list.md",
        status="rendered" if any(clip.video_url for clip in clips) else "planned",
        warnings=warnings,
    )
    write_json(job_dir / "result.json", result.model_dump(mode="json"))
    (job_dir / "edit-decision-list.md").write_text(render_edl(result), encoding="utf-8")
    return result


def job_file(job_id: str, filename: str) -> Path:
    if not job_id.startswith("reel-") or "/" in filename or "\\" in filename or filename.startswith("."):
        raise FileNotFoundError(filename)
    return service_path("reel", "jobs", job_id) / filename
