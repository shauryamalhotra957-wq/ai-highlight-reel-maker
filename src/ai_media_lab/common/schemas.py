from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float = 0.0
    end: float = 0.0
    text: str


class TranscriptResult(BaseModel):
    text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    language: str | None = None
    provider: str
    model: str | None = None


class KeyConcept(BaseModel):
    concept: str
    why_it_matters: str
    evidence: str


class QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list)
    answer: str
    explanation: str


class Flashcard(BaseModel):
    front: str
    back: str


class StudyGuide(BaseModel):
    focus_areas: list[str] = Field(default_factory=list)
    review_plan: list[str] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)
    exam_tips: list[str] = Field(default_factory=list)


class LectureAnalysis(BaseModel):
    title: str
    clean_transcript: str
    summary: list[str] = Field(default_factory=list)
    clean_notes: str
    key_concepts: list[KeyConcept] = Field(default_factory=list)
    quiz_questions: list[QuizQuestion] = Field(default_factory=list)
    study_guide: StudyGuide


class LectureJobResult(BaseModel):
    job_id: str
    filename: str
    transcript: TranscriptResult
    analysis: LectureAnalysis
    markdown_url: str
    json_url: str


class HighlightClip(BaseModel):
    clip_id: str
    title: str
    start: float
    end: float
    duration: float
    score: float
    reason: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    source_text: str
    video_url: str | None = None
    srt_url: str | None = None


class ReelJobResult(BaseModel):
    job_id: str
    filename: str
    transcript: TranscriptResult
    duration: float | None = None
    scene_changes: list[float] = Field(default_factory=list)
    clips: list[HighlightClip] = Field(default_factory=list)
    edit_decision_list_url: str
    status: str
    warnings: list[str] = Field(default_factory=list)

