[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $root "build_assets.py")
if ($LASTEXITCODE -ne 0) { throw "Crystal asset build failed with exit code $LASTEXITCODE" }
