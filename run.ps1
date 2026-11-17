# Run Job Hunter locally (Windows PowerShell).
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
# Normally GitHub Actions runs it every morning; use this for a manual local run.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Pull the latest seen-jobs database from GitHub first so you don't get duplicates.
if ((Test-Path .git) -and (git remote)) { git pull --rebase --autostash }

if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
& .\.venv\Scripts\python.exe main.py @args
