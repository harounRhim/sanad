# Lance l'API de correction Tajweed (modèle chargé une fois, gardé chaud).
# Usage :  .\server\run.ps1   (depuis la racine du projet)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$env:HF_HOME = Join-Path $root ".hf_cache"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:PYTHONIOENCODING = "utf-8"
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m uvicorn server.app:app --host 0.0.0.0 --port 8000
