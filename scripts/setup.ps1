<#
.SYNOPSIS
  Installation initiale de MultiDoc AI sous Windows (à lancer une seule fois). Aucun Docker requis.
.DESCRIPTION
  Vérifie les prérequis, installe les dépendances Python (uv, dont PostgreSQL + pgvector embarqué)
  et Node (npm), télécharge le modèle LLM dans Ollama et précharge les modèles BGE.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Test-Command($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

Write-Host "== Vérification des prérequis ==" -ForegroundColor Cyan
$missing = @()
foreach ($c in "uv", "node", "npm", "ollama") { if (-not (Test-Command $c)) { $missing += $c } }
$tess = (Test-Command "tesseract") -or (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")
if (-not $tess) { $missing += "tesseract (https://github.com/UB-Mannheim/tesseract/wiki)" }
if ($missing.Count) { throw "Prérequis manquants : $($missing -join ', ')" }

Write-Host "== Dépendances backend (uv) ==" -ForegroundColor Cyan
Push-Location "$Root\backend"; uv sync --python 3.12; Pop-Location

Write-Host "== Dépendances frontend (npm) ==" -ForegroundColor Cyan
Push-Location "$Root\frontend"; npm install; Pop-Location

Write-Host "== Modèle LLM (Ollama) ==" -ForegroundColor Cyan
ollama pull qwen2.5:7b

Write-Host "== Base PostgreSQL embarquée + modèles BGE-M3 / BGE Reranker (téléchargement unique, ~4,5 Go) ==" -ForegroundColor Cyan
Push-Location "$Root\backend"
$env:PYTHONIOENCODING = "utf-8"
uv run python -c "from app.db.session import init_db; init_db(); from app.embeddings.embedder import get_st_model; from app.reranking.reranker import get_reranker; get_st_model(); get_reranker(); print('Base et modèles prêts')"
Pop-Location

Write-Host "`nInstallation terminée. Lancez : .\scripts\start.ps1" -ForegroundColor Green
