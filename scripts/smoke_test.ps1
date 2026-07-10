param(
  [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$result = Invoke-RestMethod "http://127.0.0.1:$Port/api/health"
if ($result.status -ne "ok") {
  throw "Highlight Reel Maker health check failed"
}
Write-Host "AI Highlight Reel Maker is healthy."

