import pytest
from highlight_maker.energy_detector import SceneEnergyDetector

def test_score_window_clamping():
    detector = SceneEnergyDetector(audio_weight=0.5, visual_weight=0.5)
    assert detector.score_window(1.0, 1.0) == 1.0
    assert detector.score_window(0.0, 0.0) == 0.0
    assert detector.score_window(0.4, 0.8) == 0.6

def test_extract_top_highlights():
    detector = SceneEnergyDetector()
    windows = [
        {"start_sec": 0.0, "end_sec": 10.0, "audio_rms": 0.2, "motion": 0.1},
        {"start_sec": 15.0, "end_sec": 25.0, "audio_rms": 0.9, "motion": 0.8}, # Top 1
        {"start_sec": 30.0, "end_sec": 40.0, "audio_rms": 0.7, "motion": 0.6}, # Top 2
        {"start_sec": 45.0, "end_sec": 47.0, "audio_rms": 0.99, "motion": 0.99}, # Too short (<5s)
    ]
    top = detector.extract_top_highlights(windows, top_k=2, min_duration=5.0)
    assert len(top) == 2
    assert top[0]["start_sec"] == 15.0
    assert top[1]["start_sec"] == 30.0
