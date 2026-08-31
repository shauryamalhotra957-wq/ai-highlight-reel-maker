from fastapi.testclient import TestClient

from ai_media_lab.common import files as file_utils
from ai_media_lab.common.ffmpeg_service import FFmpegRunner
from ai_media_lab.reel.app import app


def test_reel_upload_returns_planned_clips_and_edl(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AI_MEDIA_FORCE_DEMO", "1")
    client = TestClient(app)

    response = client.post(
        "/api/highlights",
        files={
            "file": (
                "show.txt",
                (
                    b"The opener is calm. This is the best surprising moment and it changes everything! "
                    b"The guest explains a massive mistake in simple words. The producer adds context about the stakes. "
                    b"The middle section has a crazy reveal that reframes the entire story. The analyst pauses and gives "
                    b"a key lesson for creators. Later, the room reacts to an unbelievable final quote. "
                    b"The ending gives a final takeaway."
                ),
                "text/plain",
            )
        },
        data={
            "clip_count": "3",
            "platform": "YouTube Shorts",
            "captions": "true",
            "demo_mode": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planned"
    assert len(payload["clips"]) >= 2
    assert payload["clips"][0]["caption"]
    assert payload["edit_decision_list_url"]

    edl = client.get(payload["edit_decision_list_url"])
    assert edl.status_code == 200
    assert "Highlight Reel EDL" in edl.text


def test_reel_upload_handles_video_without_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AI_MEDIA_FORCE_DEMO", "1")
    video_path = tmp_path / "silent.mp4"
    runner = FFmpegRunner()
    runner.run(
        [
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=4:size=320x180:rate=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        timeout=60,
    )
    client = TestClient(app)

    with video_path.open("rb") as handle:
        response = client.post(
            "/api/highlights",
            files={"file": ("silent.mp4", handle, "video/mp4")},
            data={
                "clip_count": "2",
                "platform": "YouTube Shorts",
                "captions": "true",
                "demo_mode": "true",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rendered"
    assert payload["clips"][0]["video_url"]
    assert not any("FFmpeg preprocessing failed" in warning for warning in payload["warnings"])
    assert payload["transcript"]["provider"] == "visual-only"
 

def test_reel_upload_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(file_utils, "MAX_UPLOAD_BYTES", 4)
    monkeypatch.setenv("AI_MEDIA_DATA_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/highlights",
        files={"file": ("show.txt", b"too large", "text/plain")},
    )

    assert response.status_code == 413

def test_reel_clip_count_and_platform_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_MEDIA_DATA_DIR", str(tmp_path))
    client = TestClient(app)

    too_many = client.post(
        "/api/highlights",
        files={"file": ("show.txt", b"content", "text/plain")},
        data={"clip_count": "13", "platform": "YouTube Shorts"},
    )
    too_long = client.post(
        "/api/highlights",
        files={"file": ("show.txt", b"content", "text/plain")},
        data={"clip_count": "1", "platform": "x" * 81},
    )

    assert too_many.status_code == 422
    assert too_long.status_code == 422
