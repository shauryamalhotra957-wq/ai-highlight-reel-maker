"""
Scene Energy & Highlight Scoring Engine.
Combines acoustic RMS intensity and visual optic flow motion energy
to isolate the most engaging temporal intervals for highlight reels.
"""
from typing import List, Dict

class HighlightInterval:
    def __init__(self, start_sec: float, end_sec: float, energy_score: float):
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.energy_score = energy_score

    def to_dict(self) -> Dict:
        return {
            "start_sec": round(self.start_sec, 2),
            "end_sec": round(self.end_sec, 2),
            "duration": round(self.end_sec - self.start_sec, 2),
            "energy_score": round(self.energy_score, 4),
        }

class SceneEnergyDetector:
    def __init__(self, audio_weight: float = 0.6, visual_weight: float = 0.4):
        self.audio_weight = audio_weight
        self.visual_weight = visual_weight

    def score_window(self, audio_rms: float, visual_motion: float) -> float:
        norm_audio = max(0.0, min(1.0, audio_rms))
        norm_visual = max(0.0, min(1.0, visual_motion))
        return round((self.audio_weight * norm_audio) + (self.visual_weight * norm_visual), 4)

    def extract_top_highlights(self, window_data: List[Dict], top_k: int = 3, min_duration: float = 5.0) -> List[Dict]:
        scored = []
        for w in window_data:
            score = self.score_window(w.get("audio_rms", 0.0), w.get("motion", 0.0))
            scored.append(HighlightInterval(w["start_sec"], w["end_sec"], score))

        # Filter by minimum duration and sort descending by score
        valid = [s for s in scored if (s.end_sec - s.start_sec) >= min_duration]
        valid.sort(key=lambda s: s.energy_score, reverse=True)
        return [item.to_dict() for item in valid[:top_k]]
