# AI Highlight Reel Maker

[![tests](https://github.com/shauryamalhotra957-wq/ai-highlight-reel-maker/actions/workflows/tests.yml/badge.svg)](https://github.com/shauryamalhotra957-wq/ai-highlight-reel-maker/actions/workflows/tests.yml)

Upload long-form sports, podcast, or vlog footage and automatically find the best clips, captions, and titles.

Tech stack: Python, FastAPI, OpenAI Whisper-compatible transcription API, FFmpeg.

## Project Snapshot

| Area | Detail |
| --- | --- |
| Experience | Highlight planning and reel-production assistant |
| Core system | FFmpeg preprocessing, transcript scoring, clip selection, captions, EDL export |
| Design signal | Clear creator workflow from source media to shareable clip plan |
| Quality signal | Pytest CI on Python 3.11 and 3.12 |

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\run.ps1
```

Open http://127.0.0.1:8010

## OpenAI Setup

The app runs in demo mode without secrets. For real transcription:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set:

```text
OPENAI_API_KEY=sk-...
OPENAI_TRANSCRIBE_MODEL=whisper-1
```

## Features

- Video/audio/transcript upload
- FFmpeg audio extraction
- Scene-change detection
- OpenAI transcription path with deterministic demo fallback
- Automatic long-audio chunking for API upload limits
- Highlight scoring from transcript energy, punctuation cues, timing, and scene proximity
- Captions as `.srt`
- Titles and hashtags
- MP4 clip rendering when source video is uploaded
- Markdown edit decision list export

## API

- `GET /api/health`
- `POST /api/highlights`
- `GET /api/jobs/{job_id}/files/{filename}`

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

GitHub Actions runs the same pytest suite on Python 3.11 and 3.12 for pushes and pull requests.

## Samples

- `sample_assets/reel-transcript.txt` for instant transcript testing
- `sample_assets/sample-reel.mp4` for FFmpeg-rendered clip testing

Regenerate the sample video:

```powershell
.\.venv\Scripts\python.exe .\scripts\make_sample_assets.py
```

## Experience Design

The editing workspace follows the [Highlight Reel design system](design-system/ai-highlight-reel-maker/MASTER.md), with cinematic contrast, clear job states, accessible upload controls, responsive surfaces, and reduced-motion support.

