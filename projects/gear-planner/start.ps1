$ErrorActionPreference = 'Stop'
$prototypeRoot = $PSScriptRoot
$repositoryRoot = (Resolve-Path (Join-Path $prototypeRoot '..\..')).Path
$prototypeUrl = 'http://127.0.0.1:8765'
$isRunning = $false
try {
    $probe = Invoke-RestMethod "$prototypeUrl/api/bootstrap" -TimeoutSec 2
    $isRunning = $probe.version -eq '12.1.0.69587 · c1935b9'
} catch { }
if (-not $isRunning) {
    $pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
    Start-Process -FilePath $pythonPath -ArgumentList ('"' + (Join-Path $prototypeRoot 'server.py') + '"') -WorkingDirectory $prototypeRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $prototypeRoot 'server.log') -RedirectStandardError (Join-Path $prototypeRoot 'server-error.log') | Out-Null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        try { $probe = Invoke-RestMethod "$prototypeUrl/api/bootstrap" -TimeoutSec 1; $isRunning = $probe.version -eq '12.1.0.69587 · c1935b9'; if ($isRunning) { break } } catch { }
    }
}
if (-not $isRunning) { throw '原型启动失败，请检查端口 8765 是否被占用，以及 server-error.log。' }
Start-Process $prototypeUrl
