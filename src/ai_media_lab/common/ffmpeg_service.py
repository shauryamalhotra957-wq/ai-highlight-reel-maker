from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_media_lab.common.schemas import TranscriptSegment


class FFmpegError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class FFmpegRunner:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or os.getenv("FFMPEG_BINARY") or self._bundled_executable()

    @staticmethod
    def _bundled_executable() -> str:
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def run(self, args: list[str], timeout: int = 180, check: bool = True) -> CommandResult:
        command = [self.executable, *args]
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        result = CommandResult(process.returncode, process.stdout, process.stderr)
        if check and process.returncode != 0:
            tail = (process.stderr or process.stdout)[-1200:]
            raise FFmpegError(f"FFmpeg failed with code {process.returncode}: {tail}")
        return result

    def available(self) -> bool:
        try:
            result = self.run(["-version"], timeout=10, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def probe_duration(self, source: Path) -> float | None:
        result = self.run(["-hide_banner", "-i", str(source)], timeout=30, check=False)
        return parse_duration(result.stderr)

    def extract_audio(self, source: Path, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                "-hide_banner",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(target),
            ],
            timeout=240,
        )
        return target

    def detect_scene_changes(self, source: Path, threshold: float = 0.35) -> list[float]:
        expression = f"select=gt(scene\\,{threshold}),showinfo"
        result = self.run(
            [
                "-hide_banner",
                "-i",
                str(source),
                "-filter:v",
                expression,
                "-an",
                "-f",
                "null",
                "-",
            ],
            timeout=240,
            check=False,
        )
        times = [float(match) for match in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
        return sorted(set(round(value, 2) for value in times))

    def cut_clip(self, source: Path, start: float, duration: float, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                "-hide_banner",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(source),
                "-vf",
                "scale=720:-2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(target),
            ],
            timeout=300,
        )
        return target


def parse_duration(ffmpeg_stderr: str) -> float | None:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", ffmpeg_stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining:06.3f}".replace(".", ",")


def write_srt(path: Path, segments: list[TranscriptSegment], clip_start: float, clip_end: float, fallback_text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    matching = [
        segment
        for segment in segments
        if segment.end >= clip_start and segment.start <= clip_end and segment.text.strip()
    ]
    if not matching:
        matching = [TranscriptSegment(start=clip_start, end=clip_end, text=fallback_text)]

    blocks: list[str] = []
    for index, segment in enumerate(matching, start=1):
        start = max(0.0, segment.start - clip_start)
        end = max(start + 1.0, min(clip_end - clip_start, segment.end - clip_start))
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_timestamp(start)} --> {format_timestamp(end)}",
                    segment.text.strip(),
                ]
            )
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return path

