from __future__ import annotations

import subprocess
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from ai_media_lab.common import openai_service
from ai_media_lab.common.ffmpeg_service import (
    CommandResult,
    FFmpegCancelledError,
    FFmpegError,
    FFmpegProcessLimits,
    FFmpegRunner,
    FFmpegTimeoutError,
)
from ai_media_lab.common.openai_service import _audio_chunks
from ai_media_lab.common.schemas import TranscriptResult, TranscriptSegment
from ai_media_lab.reel import service as reel_service
from ai_media_lab.reel.app import app


class HangingProcess:
    def __init__(self, on_wait=None) -> None:
        self.returncode = None
        self.on_wait = on_wait
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.terminated or self.killed:
            self.returncode = -15
            return self.returncode
        if self.on_wait is not None:
            callback = self.on_wait
            self.on_wait = None
            callback()
        raise subprocess.TimeoutExpired("fake-ffmpeg", timeout)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class CompletedProcess:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    def poll(self):
        return self.returncode


def make_limits(**overrides) -> FFmpegProcessLimits:
    values = {
        "probe_timeout_seconds": 0.02,
        "process_timeout_seconds": 0.02,
        "termination_grace_seconds": 0.02,
        "poll_interval_seconds": 0.001,
    }
    values.update(overrides)
    return FFmpegProcessLimits(**values)


def test_process_limits_are_configurable_from_environment() -> None:
    limits = FFmpegProcessLimits.from_environment(
        {
            "AI_MEDIA_FFPROBE_TIMEOUT_SECONDS": "4.5",
            "AI_MEDIA_FFMPEG_TIMEOUT_SECONDS": "90",
            "AI_MEDIA_FFMPEG_TERMINATION_GRACE_SECONDS": "0.75",
        }
    )

    assert limits.probe_timeout_seconds == 4.5
    assert limits.process_timeout_seconds == 90.0
    assert limits.termination_grace_seconds == 0.75


@pytest.mark.parametrize("configured_value", ["0", "-1", "invalid"])
def test_process_limits_reject_invalid_configuration(configured_value: str) -> None:
    with pytest.raises(ValueError, match="must be a positive number"):
        FFmpegProcessLimits.from_environment(
            {"AI_MEDIA_FFMPEG_TIMEOUT_SECONDS": configured_value}
        )


def test_timeout_terminates_and_reaps_process(monkeypatch) -> None:
    process = HangingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    runner = FFmpegRunner(executable="fake-ffmpeg", limits=make_limits())

    with pytest.raises(FFmpegTimeoutError, match="exceeded"):
        runner.run(["-version"])

    assert process.terminated
    assert process.returncode == -15


def test_cancellation_terminates_and_reaps_process(monkeypatch) -> None:
    cancellation = Event()
    process = HangingProcess(on_wait=cancellation.set)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    runner = FFmpegRunner(
        executable="fake-ffmpeg",
        limits=make_limits(process_timeout_seconds=1.0),
        cancel_event=cancellation,
    )

    with pytest.raises(FFmpegCancelledError, match="cancelled"):
        runner.run(["-version"])

    assert process.terminated
    assert process.returncode == -15


def test_process_launch_errors_are_wrapped(monkeypatch) -> None:
    def fail_to_start(*_args, **_kwargs):
        raise FileNotFoundError("missing binary")

    monkeypatch.setattr(subprocess, "Popen", fail_to_start)
    runner = FFmpegRunner(executable="missing-ffmpeg", limits=make_limits())

    with pytest.raises(FFmpegError, match="Could not start FFmpeg"):
        runner.run(["-version"])


def test_nonzero_process_errors_include_captured_stderr(monkeypatch) -> None:
    def complete_with_error(_command, **kwargs):
        kwargs["stderr"].write(b"invalid media input")
        return CompletedProcess(returncode=9)

    monkeypatch.setattr(subprocess, "Popen", complete_with_error)
    runner = FFmpegRunner(executable="fake-ffmpeg", limits=make_limits())

    with pytest.raises(FFmpegError, match="code 9: invalid media input"):
        runner.run(["-i", "broken.mp4"])


def test_atomic_media_output_is_promoted_only_after_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "clip.mp4"
    runner = FFmpegRunner(executable="fake-ffmpeg", limits=make_limits())

    def write_output(args, **_kwargs):
        Path(args[-1]).write_bytes(b"complete output")
        return CommandResult(0, "", "")

    monkeypatch.setattr(runner, "run", write_output)

    runner.cut_clip(tmp_path / "source.mp4", 0.0, 5.0, target)

    assert target.read_bytes() == b"complete output"
    assert not list(tmp_path.glob(".clip-*.mp4"))


@pytest.mark.parametrize(
    "failure",
    [
        FFmpegError("encoding failed"),
        FFmpegTimeoutError("encoding timed out"),
        FFmpegCancelledError("encoding cancelled"),
    ],
    ids=["error", "timeout", "cancel"],
)
def test_atomic_media_output_cleans_partial_files_and_preserves_target(
    tmp_path: Path,
    monkeypatch,
    failure: FFmpegError,
) -> None:
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"previous output")
    runner = FFmpegRunner(executable="fake-ffmpeg", limits=make_limits())
    temporary_paths: list[Path] = []

    def fail_after_partial_output(args, **_kwargs):
        temporary_path = Path(args[-1])
        temporary_path.write_bytes(b"partial output")
        temporary_paths.append(temporary_path)
        raise failure

    monkeypatch.setattr(runner, "run", fail_after_partial_output)

    with pytest.raises(type(failure)):
        runner.cut_clip(tmp_path / "source.mp4", 0.0, 5.0, target)

    assert target.read_bytes() == b"previous output"
    assert temporary_paths
    assert all(not path.exists() for path in temporary_paths)


class ChunkRunner:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.chunk_dir: Path | None = None

    def available(self) -> bool:
        return True

    def run(self, args, **_kwargs):
        pattern = Path(args[-1])
        self.chunk_dir = pattern.parent
        Path(str(pattern).replace("%03d", "000")).write_bytes(b"chunk")
        if self.failure is not None:
            raise self.failure
        return CommandResult(0, "", "")


@pytest.mark.parametrize(
    "body_failure",
    [None, RuntimeError("transcription failed"), FFmpegCancelledError("cancelled")],
    ids=["success", "failure", "cancel"],
)
def test_audio_chunk_directory_is_cleaned_after_use(
    tmp_path: Path,
    monkeypatch,
    body_failure: Exception | None,
) -> None:
    source = tmp_path / "large.wav"
    source.write_bytes(b"large")
    monkeypatch.setattr(openai_service, "OPENAI_UPLOAD_LIMIT_BYTES", 1)
    runner = ChunkRunner()

    if body_failure is None:
        with _audio_chunks(source, runner=runner) as chunks:
            assert chunks[0].read_bytes() == b"chunk"
    else:
        with pytest.raises(type(body_failure)):
            with _audio_chunks(source, runner=runner) as chunks:
                assert chunks[0].exists()
                raise body_failure

    assert runner.chunk_dir is not None
    assert not runner.chunk_dir.exists()


def test_audio_chunk_directory_is_cleaned_when_ffmpeg_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "large.wav"
    source.write_bytes(b"large")
    monkeypatch.setattr(openai_service, "OPENAI_UPLOAD_LIMIT_BYTES", 1)
    runner = ChunkRunner(failure=FFmpegError("chunking failed"))

    with pytest.raises(FFmpegError, match="chunking failed"):
        with _audio_chunks(source, runner=runner):
            pass

    assert runner.chunk_dir is not None
    assert not runner.chunk_dir.exists()


class FakeReelRunner:
    def __init__(self) -> None:
        self.audio_path: Path | None = None

    def available(self) -> bool:
        return True

    def probe_duration(self, _source: Path) -> float:
        return 20.0

    def detect_scene_changes(self, _source: Path) -> list[float]:
        return []

    def has_audio_stream(self, _source: Path) -> bool:
        return True

    def extract_audio(self, _source: Path, target: Path) -> Path:
        target.write_bytes(b"temporary audio")
        self.audio_path = target
        return target

    def cut_clip(
        self,
        _source: Path,
        _start: float,
        _duration: float,
        target: Path,
    ) -> Path:
        target.write_bytes(b"rendered clip")
        return target


def sample_transcript() -> TranscriptResult:
    return TranscriptResult(
        text="A strong highlight moment.",
        segments=[
            TranscriptSegment(
                start=1.0,
                end=10.0,
                text="A strong highlight moment.",
            )
        ],
        provider="test",
    )


def post_fake_video(client: TestClient):
    return client.post(
        "/api/highlights",
        files={"file": ("input.mp4", b"fake video", "video/mp4")},
        data={"clip_count": "1", "demo_mode": "true"},
    )


def test_extracted_audio_is_cleaned_after_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_MEDIA_DATA_DIR", str(tmp_path / "data"))
    runner = FakeReelRunner()
    monkeypatch.setattr(reel_service, "FFmpegRunner", lambda: runner)
    monkeypatch.setattr(
        reel_service,
        "transcribe_media",
        lambda *_args, **_kwargs: sample_transcript(),
    )

    response = post_fake_video(TestClient(app))

    assert response.status_code == 200
    assert runner.audio_path is not None
    assert not runner.audio_path.exists()


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("transcription failed"), FFmpegCancelledError("cancelled")],
    ids=["failure", "cancel"],
)
def test_extracted_audio_is_cleaned_after_failure_or_cancel(
    tmp_path: Path,
    monkeypatch,
    failure: Exception,
) -> None:
    monkeypatch.setenv("AI_MEDIA_DATA_DIR", str(tmp_path / "data"))
    runner = FakeReelRunner()
    monkeypatch.setattr(reel_service, "FFmpegRunner", lambda: runner)

    def fail_transcription(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(reel_service, "transcribe_media", fail_transcription)

    response = post_fake_video(TestClient(app, raise_server_exceptions=False))

    assert response.status_code == 500
    assert runner.audio_path is not None
    assert not runner.audio_path.exists()
