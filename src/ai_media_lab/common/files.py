from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str | None, fallback: str = "upload.bin") -> str:
    name = Path(filename or fallback).name.strip() or fallback
    cleaned = SAFE_NAME_RE.sub("-", name).strip(".-")
    return cleaned or fallback


def new_job_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid4().hex[:8]}"


async def save_upload(upload: UploadFile, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(upload.filename)
    path = destination_dir / f"{uuid4().hex}-{filename}"
    with path.open("wb") as output:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    await upload.seek(0)
    return path


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def read_text(path: Path, max_chars: int = 300_000) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return handle.read(max_chars)


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

