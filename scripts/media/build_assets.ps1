[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path (Split-Path $root -Parent) -Parent
& (Join-Path $repoRoot '.venv/Scripts/python.exe') (Join-Path $root "build_assets.py")
if ($LASTEXITCODE -ne 0) { throw "Crystal asset build failed with exit code $LASTEXITCODE" }
