<#
.SYNOPSIS
  Back up the Dispatch AI SQLite database to a timestamped snapshot.

.DESCRIPTION
  Copies the live dispatch.db (bound to the Windows host at DISPATCH_DATA_DIR)
  into a backups/ subfolder next to it, and prunes old backups keeping the
  most recent $Retention.

  The live DB and backups live at:
    C:\Users\adamm\.dispatch-ai\dispatch.db
    C:\Users\adamm\.dispatch-ai\backups\dispatch-YYYYMMDD-HHMMSS.db

.NOTES
  Run from the project root. Optionally pass -Retention to change how many
  snapshots are kept (default 14). Optionally stop/omit the backend for a
  fully quiescent copy; the file is small so an online copy is fine.
#>
[CmdletBinding()]
param(
    [int]$Retention = 14
)

$ErrorActionPreference = 'Stop'

# Resolve the data directory (same source Docker Compose uses).
# Precedence: DISPATCH_DATA_DIR env var, then .env, then default.
$dataDir = $env:DISPATCH_DATA_DIR
if ([string]::IsNullOrWhiteSpace($dataDir)) {
    $envFile = Join-Path $PSScriptRoot '..\.env'
    if (Test-Path $envFile) {
        $line = (Get-Content $envFile | Where-Object { $_ -match '^\s*DISPATCH_DATA_DIR\s*=' } | Select-Object -First 1)
        if ($line) {
            $dataDir = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
        }
    }
}
if ([string]::IsNullOrWhiteSpace($dataDir)) {
    $dataDir = Join-Path $HOME '.dispatch-ai'
}

$dbPath = Join-Path $dataDir 'dispatch.db'
if (-not (Test-Path $dbPath)) {
    Write-Warning "No database found at $dbPath. Is the backend running / data initialized?"
    exit 1
}

$backupDir = Join-Path $dataDir 'backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $backupDir "dispatch-$stamp.db"
Copy-Item -Path $dbPath -Destination $target -Force

Write-Host "Backed up $(Get-Item $dbPath | Select-Object -ExpandProperty Length) bytes -> $target"

# Prune old backups, keep the newest $Retention (based on name sort which is time-sorted).
$old = Get-ChildItem -Path $backupDir -Filter 'dispatch-*.db' |
    Sort-Object Name -Descending |
    Select-Object -Skip $Retention
foreach ($f in $old) {
    Remove-Item -Path $f.FullName -Force
    Write-Host "Pruned old backup: $($f.Name)"
}

