<#
.SYNOPSIS
  One-time setup for Dispatch AI on Windows (no Docker needed).

.DESCRIPTION
  Provisions everything the app needs to run natively:
    1. Checks Python 3.11+ is available (installs via winget if possible).
    2. Creates/updates backend\.venv and installs backend\requirements.txt.
    3. Installs frontend npm deps and builds the Tauri app (the .exe/.msi
       installers land in frontend\src-tauri\target\release\bundle\).

  Autostart is handled by the app itself: the first time it runs it registers
  a "Run at logon" entry (tauri-plugin-autostart), which on Windows points at
  the built executable. So after this script, just launch the app and it'll
  keep itself + the backend running on login.

.NOTES
  Run from PowerShell as the current user (no admin required):
      powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
  Idempotent — safe to re-run to update dependencies after a pull.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

Write-Host "Dispatch AI setup" -ForegroundColor Cyan
Write-Host "  project root: $root" -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# 1. Python 3.11+
# ---------------------------------------------------------------------------
function Find-Python {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) {
    try {
      $ver = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") 2>$null
      if ($ver -and [version]$ver -ge [version]"3.11") {
        return (Get-Command python).Source
      }
    } catch {}
  }
  return $null
}

$python = Find-Python
if (-not $python) {
  Write-Host "Python 3.11+ not found. Attempting install via winget..." -ForegroundColor Yellow
  try {
    winget install --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
  } catch {
    Write-Error "Automatic Python install failed. Install Python 3.12+ from https://www.python.org/downloads and re-run this script."
    exit 1
  }
  $python = Find-Python
  if (-not $python) {
    Write-Error "Python still not found after install. Restart the shell and re-run this script."
    exit 1
  }
}
Write-Host "Python: $python" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Backend venv + dependencies
# ---------------------------------------------------------------------------
$venv = Join-Path $backend '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Host "Creating virtualenv at backend\.venv ..." -ForegroundColor Yellow
  & python -m venv $venv
  if ($LASTEXITCODE -ne 0) { exit 1 }
}
Write-Host "Installing requirements..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $backend 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }

# ---------------------------------------------------------------------------
# 3. Frontend deps + build the Tauri app
# ---------------------------------------------------------------------------
Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location $frontend
try {
  if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    npm install
    if ($LASTEXITCODE -ne 0) { exit 1 }
  }
  Write-Host "Building Tauri app (this may take a while)..." -ForegroundColor Yellow
  npx tauri build
  if ($LASTEXITCODE -ne 0) { Write-Error "Tauri build failed"; exit 1 }
} finally {
  Pop-Location
}

# ---------------------------------------------------------------------------
# 4. Summary
# ---------------------------------------------------------------------------
$bundle = Join-Path $frontend 'src-tauri\target\release\bundle'
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
if (Test-Path $bundle) {
  Write-Host "Installers:" -ForegroundColor Cyan
  Get-ChildItem (Join-Path $bundle 'nsis') -Filter *.exe -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $($_.FullName)" }
  Get-ChildItem (Join-Path $bundle 'msi') -Filter *.msi -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $($_.FullName)" }
} else {
  Write-Host "Run 'npx tauri build' in frontend/ to produce installers." -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Launch the built app once. It will register itself to run at logon."
Write-Host "  2. It also spawns the backend automatically and shuts it down with the app."
Write-Host "  3. For quick manual backend testing: $venvPython -m uvicorn main:app --host 127.0.0.1 --port 8000 (run in backend/)"
