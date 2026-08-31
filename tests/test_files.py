from ai_media_lab.common.files import new_job_id, safe_filename


def test_safe_filename_strips_parent_directories():
    assert safe_filename("../../private/video.mp4") == "video.mp4"


def test_safe_filename_replaces_unsafe_characters_and_has_fallback():
    assert safe_filename("my video (final).mp4") == "my-video-final-.mp4"
    assert safe_filename("...") == "upload.bin"


def test_new_job_id_contains_prefix_and_unique_suffix():
    first = new_job_id("reel")
    second = new_job_id("reel")

    assert first.startswith("reel-")
    assert len(first.rsplit("-", 1)[-1]) == 8
    assert first != second
