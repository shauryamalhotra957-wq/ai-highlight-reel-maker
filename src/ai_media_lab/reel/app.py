from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ai_media_lab.common.files import UploadTooLargeError
from fastapi.staticfiles import StaticFiles

from ai_media_lab.reel.service import job_file, process_reel_upload


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="AI Highlight Reel Maker",
    description="Upload long-form footage or transcript and generate highlight clips, captions, titles, and an edit decision list.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "highlight-reel-maker"}


@app.post("/api/highlights")
async def highlights(
    file: Annotated[UploadFile, File(...)],
    clip_count: Annotated[int, Form()] = 5,
    platform: Annotated[str, Form()] = "YouTube Shorts",
    captions: Annotated[bool, Form()] = True,
    demo_mode: Annotated[bool, Form()] = False,
):
    try:
        return await process_reel_upload(
            upload=file,
            clip_count=clip_count,
            platform=platform,
            captions=captions,
            demo_mode=demo_mode,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/files/{filename}")
def download_job_file(job_id: str, filename: str) -> FileResponse:
    try:
        path = job_file(job_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "video/mp4" if path.suffix == ".mp4" else "text/plain"
    return FileResponse(path, media_type=media_type, filename=path.name)

