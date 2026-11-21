<#
.SYNOPSIS
  Démarre MultiDoc AI : backend FastAPI (port 8000, avec PostgreSQL + pgvector embarqué)
  et frontend Next.js (port 3000). Aucun Docker requis.
.PARAMETER Dev
  Lance le frontend en mode développement (rechargement à chaud) au lieu du build de production.
#>
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

try { Invoke-RestMethod http://localhost:11434/api/tags -TimeoutSec 3 | Out-Null }
catch { Write-Host "Ollama ne répond pas : démarrage..." -ForegroundColor Yellow; Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }

Write-Host "== Backend FastAPI + PostgreSQL embarqué (http://localhost:8000) ==" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\backend'; `$env:PYTHONIOENCODING='utf-8'; uv run uvicorn app.main:app --host 127.0.0.1 --port 8000" -WindowStyle Normal

Write-Host "== Frontend Next.js (http://localhost:3000) ==" -ForegroundColor Cyan
if ($Dev) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run dev" -WindowStyle Normal
} else {
    Push-Location "$Root\frontend"; npm run build; Pop-Location
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run start" -WindowStyle Normal
}

Write-Host "Attente du backend..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    try { Invoke-RestMethod http://localhost:8000/api/health -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { Start-Sleep 1; Write-Host "." -NoNewline }
}
if (-not $ready) { throw "Le backend ne répond pas : consultez sa fenêtre PowerShell." }
Write-Host "`nMultiDoc AI est prêt : http://localhost:3000" -ForegroundColor Green
Start-Process "http://localhost:3000"
