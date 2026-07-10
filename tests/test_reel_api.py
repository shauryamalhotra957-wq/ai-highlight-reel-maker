from fastapi.testclient import TestClient

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
