<#
.SYNOPSIS
  Lance les tests. -Integration ajoute les tests de bout en bout (PostgreSQL + Ollama requis).
#>
param([switch]$Integration)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location "$Root\backend"
$env:PYTHONIOENCODING = "utf-8"
uv run pytest -W ignore::DeprecationWarning
if ($Integration) { uv run pytest -m integration -v -W ignore::DeprecationWarning }
Pop-Location
Push-Location "$Root\frontend"
npx tsc --noEmit; npm run lint
Pop-Location
