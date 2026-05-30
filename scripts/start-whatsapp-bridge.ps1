$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "Iniciando WhatsApp Bridge..." -ForegroundColor Cyan
Write-Host "Repo: $repoRoot"
Write-Host "Python: $pythonExe"
Write-Host ""

& $pythonExe "apps/msg/whatsapp_web.py" "bridge"
