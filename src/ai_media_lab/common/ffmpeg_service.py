from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from threading import Event
from typing import BinaryIO
from uuid import uuid4

from ai_media_lab.common.schemas import TranscriptSegment


class FFmpegError(RuntimeError):
    pass


class FFmpegTimeoutError(FFmpegError, TimeoutError):
    pass


class FFmpegCancelledError(FFmpegError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class FFmpegProcessLimits:
    probe_timeout_seconds: float = 30.0
    process_timeout_seconds: float = 600.0
    termination_grace_seconds: float = 2.0
    poll_interval_seconds: float = 0.1

    def __post_init__(self) -> None:
        for field_name, value in vars(self).items():
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be a positive number")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "FFmpegProcessLimits":
        values = os.environ if environment is None else environment
        return cls(
            probe_timeout_seconds=_configured_seconds(
                values,
                "AI_MEDIA_FFPROBE_TIMEOUT_SECONDS",
                cls.probe_timeout_seconds,
            ),
            process_timeout_seconds=_configured_seconds(
                values,
                "AI_MEDIA_FFMPEG_TIMEOUT_SECONDS",
                cls.process_timeout_seconds,
            ),
            termination_grace_seconds=_configured_seconds(
                values,
                "AI_MEDIA_FFMPEG_TERMINATION_GRACE_SECONDS",
                cls.termination_grace_seconds,
            ),
        )


class FFmpegRunner:
    def __init__(
        self,
        executable: str | None = None,
        *,
        limits: FFmpegProcessLimits | None = None,
        cancel_event: Event | None = None,
    ) -> None:
        self.executable = executable or os.getenv("FFMPEG_BINARY") or self._bundled_executable()
        self.limits = limits or FFmpegProcessLimits.from_environment()
        self._cancel_event = cancel_event or Event()

    @staticmethod
    def _bundled_executable() -> str:
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def cancel(self) -> None:
        """Request cancellation of the active or next media command."""
        self._cancel_event.set()

    def run(
        self,
        args: list[str],
        timeout: float | None = None,
        check: bool = True,
    ) -> CommandResult:
        effective_timeout = (
            self.limits.process_timeout_seconds if timeout is None else float(timeout)
        )
        if not isfinite(effective_timeout) or effective_timeout <= 0:
            raise ValueError("timeout must be a positive number")
        if self._cancel_event.is_set():
            raise FFmpegCancelledError("FFmpeg execution was cancelled")

        command = [self.executable, *args]
        with tempfile.TemporaryFile() as stdout_buffer, tempfile.TemporaryFile() as stderr_buffer:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_buffer,
                    stderr=stderr_buffer,
                )
            except OSError as error:
                raise FFmpegError(f"Could not start FFmpeg: {error}") from error

            try:
                self._wait_for_process(process, effective_timeout)
            except BaseException:
                self._stop_process(process)
                raise

            stdout = _decode_buffer(stdout_buffer)
            stderr = _decode_buffer(stderr_buffer)

        result = CommandResult(process.returncode, stdout, stderr)
        if check and process.returncode != 0:
            tail = (stderr or stdout)[-1200:]
            raise FFmpegError(f"FFmpeg failed with code {process.returncode}: {tail}")
        return result

    def _wait_for_process(
        self,
        process: subprocess.Popen[bytes],
        timeout: float,
    ) -> None:
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if self._cancel_event.is_set():
                raise FFmpegCancelledError("FFmpeg execution was cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FFmpegTimeoutError(
                    f"FFmpeg exceeded its {timeout:g}-second timeout"
                )
            try:
                process.wait(
                    timeout=min(self.limits.poll_interval_seconds, remaining)
                )
            except subprocess.TimeoutExpired:
                continue

    def _stop_process(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=self.limits.termination_grace_seconds)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            process.kill()
            process.wait(timeout=self.limits.termination_grace_seconds)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FFmpegError("FFmpeg could not be stopped cleanly") from error

    def available(self) -> bool:
        try:
            result = self.run(
                ["-version"],
                timeout=self.limits.probe_timeout_seconds,
                check=False,
            )
            return result.returncode == 0
        except FFmpegCancelledError:
            raise
        except Exception:
            return False

    def probe_duration(self, source: Path) -> float | None:
        result = self.run(
            ["-hide_banner", "-i", str(source)],
            timeout=self.limits.probe_timeout_seconds,
            check=False,
        )
        return parse_duration(result.stderr)

    def has_audio_stream(self, source: Path) -> bool:
        result = self.run(
            ["-hide_banner", "-i", str(source)],
            timeout=self.limits.probe_timeout_seconds,
            check=False,
        )
        return "Audio:" in result.stderr

    def extract_audio(self, source: Path, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run_to_target(
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
            ],
            target,
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
            check=False,
        )
        times = [float(match) for match in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
        return sorted(set(round(value, 2) for value in times))

    def cut_clip(self, source: Path, start: float, duration: float, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run_to_target(
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
            ],
            target,
        )
        return target

    def _run_to_target(
        self,
        args: list[str],
        target: Path,
    ) -> CommandResult:
        temporary_target = target.with_name(
            f".{target.stem}-{uuid4().hex}{target.suffix}"
        )
        try:
            result = self.run([*args, str(temporary_target)])
            temporary_target.replace(target)
            return result
        finally:
            temporary_target.unlink(missing_ok=True)


def _configured_seconds(
    environment: Mapping[str, str],
    name: str,
    default: float,
) -> float:
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _decode_buffer(buffer: BinaryIO) -> str:
    buffer.flush()
    buffer.seek(0)
    return buffer.read().decode("utf-8", errors="replace")


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
