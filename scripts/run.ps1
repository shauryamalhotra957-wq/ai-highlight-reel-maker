param(
  [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (!(Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:PYTHONPATH = Join-Path $Root "src"
.\.venv\Scripts\python.exe -m uvicorn ai_media_lab.reel.app:app --host 127.0.0.1 --port $Port --reload

