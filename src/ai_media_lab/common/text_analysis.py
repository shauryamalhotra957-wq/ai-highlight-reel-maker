from __future__ import annotations

import re
from collections import Counter

from ai_media_lab.common.schemas import (
    Flashcard,
    KeyConcept,
    LectureAnalysis,
    QuizQuestion,
    StudyGuide,
    TranscriptSegment,
)


STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "been",
    "before",
    "being",
    "between",
    "could",
    "during",
    "each",
    "from",
    "have",
    "into",
    "just",
    "like",
    "more",
    "most",
    "other",
    "over",
    "should",
    "some",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "using",
    "very",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}


def clean_transcript(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text


def split_sentences(text: str) -> list[str]:
    normalized = clean_transcript(text)
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text)
        if token.lower() not in STOPWORDS
    ]


def extract_keywords(text: str, limit: int = 10) -> list[str]:
    counts = Counter(tokenize(text))
    return [word for word, _ in counts.most_common(limit)]


def title_from_text(text: str, fallback: str = "Study Notes") -> str:
    sentences = split_sentences(text)
    if not sentences:
        return fallback
    first = re.sub(r"^(today|now|so|okay|welcome)[, ]+", "", sentences[0], flags=re.I)
    words = first.split()[:9]
    title = " ".join(words).strip(" .,:;")
    return title.title() if title else fallback


def _important_sentences(sentences: list[str], keywords: list[str], limit: int) -> list[str]:
    if not sentences:
        return []
    keyword_set = set(keywords)
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        words = tokenize(sentence)
        score = len(set(words) & keyword_set) + min(len(words) / 18, 1.5)
        if "?" in sentence:
            score += 0.5
        scored.append((score, index, sentence))
    winners = sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]
    return [sentence for _, _, sentence in sorted(winners, key=lambda item: item[1])]


def build_key_concepts(text: str, limit: int = 8) -> list[KeyConcept]:
    sentences = split_sentences(text)
    keywords = extract_keywords(text, limit=limit * 2)
    concepts: list[KeyConcept] = []
    used: set[str] = set()
    for keyword in keywords:
        evidence = next((s for s in sentences if keyword.lower() in s.lower()), "")
        if not evidence or keyword in used:
            continue
        used.add(keyword)
        concept = keyword.replace("-", " ").title()
        concepts.append(
            KeyConcept(
                concept=concept,
                why_it_matters=f"{concept} anchors one of the lecture's recurring ideas.",
                evidence=evidence,
            )
        )
        if len(concepts) >= limit:
            break
    return concepts


def build_quiz(concepts: list[KeyConcept], limit: int = 6) -> list[QuizQuestion]:
    questions: list[QuizQuestion] = []
    concept_names = [concept.concept for concept in concepts]
    for index, concept in enumerate(concepts[:limit]):
        distractors = [name for name in concept_names if name != concept.concept][:3]
        while len(distractors) < 3:
            distractors.append(["Background detail", "Unrelated example", "Minor tangent"][len(distractors)])
        options = [concept.concept, *distractors]
        questions.append(
            QuizQuestion(
                question=f"Which concept best matches this lecture evidence: {concept.evidence}",
                options=options,
                answer=concept.concept,
                explanation=concept.why_it_matters,
            )
        )
    return questions


def build_study_guide(summary: list[str], concepts: list[KeyConcept]) -> StudyGuide:
    focus_areas = [concept.concept for concept in concepts[:6]]
    review_plan = [
        "Read the clean notes once for structure.",
        "Turn each key concept into a one-sentence explanation.",
        "Answer the quiz without looking, then review missed concepts.",
        "Teach the strongest summary bullets out loud in your own words.",
    ]
    flashcards = [
        Flashcard(front=f"What is {concept.concept}?", back=concept.why_it_matters)
        for concept in concepts[:8]
    ]
    exam_tips = [
        "Prioritize relationships between concepts, not isolated definitions.",
        "Use the evidence snippets as memory anchors.",
        "Revisit any quiz item that takes more than 30 seconds to answer.",
    ]
    if summary:
        exam_tips.insert(0, f"Main takeaway: {summary[0]}")
    return StudyGuide(
        focus_areas=focus_areas,
        review_plan=review_plan,
        flashcards=flashcards,
        exam_tips=exam_tips,
    )


def build_clean_notes(title: str, summary: list[str], concepts: list[KeyConcept], sentences: list[str]) -> str:
    detailed = _important_sentences(sentences, [concept.concept.lower() for concept in concepts], limit=10)
    lines = [f"# {title}", "", "## Executive Summary"]
    lines.extend(f"- {item}" for item in summary)
    lines.extend(["", "## Detailed Notes"])
    lines.extend(f"- {item}" for item in detailed)
    lines.extend(["", "## Key Concepts"])
    lines.extend(f"- **{concept.concept}:** {concept.why_it_matters}" for concept in concepts)
    lines.extend(["", "## Review Questions"])
    lines.extend(f"- How does {concept.concept} connect to the lecture's main argument?" for concept in concepts[:5])
    return "\n".join(lines).strip() + "\n"


def analyze_lecture_text(text: str, topic: str | None = None) -> LectureAnalysis:
    cleaned = clean_transcript(text)
    sentences = split_sentences(cleaned)
    keywords = extract_keywords(cleaned, limit=12)
    summary = _important_sentences(sentences, keywords, limit=5)
    if not summary and cleaned:
        summary = [cleaned[:220]]
    title = topic.strip().title() if topic else title_from_text(cleaned, "Lecture Notes")
    concepts = build_key_concepts(cleaned)
    quiz = build_quiz(concepts)
    guide = build_study_guide(summary, concepts)
    notes = build_clean_notes(title, summary, concepts, sentences)
    return LectureAnalysis(
        title=title,
        clean_transcript=cleaned,
        summary=summary,
        clean_notes=notes,
        key_concepts=concepts,
        quiz_questions=quiz,
        study_guide=guide,
    )


def segment_text(text: str, seconds_per_sentence: float = 7.0) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    cursor = 0.0
    for sentence in split_sentences(text):
        word_count = max(4, len(sentence.split()))
        duration = max(4.0, min(18.0, word_count * 0.45 or seconds_per_sentence))
        segments.append(TranscriptSegment(start=cursor, end=cursor + duration, text=sentence))
        cursor += duration + 0.35
    return segments

