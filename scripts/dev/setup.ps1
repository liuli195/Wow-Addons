# 本机和远端共用；仅写仓库内缓存，不修改系统环境或游戏文件。
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $repoRoot
$versions = Get-Content scripts/dev/versions.json -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force .tools/downloads | Out-Null

function Get-Artifact($spec, $path) {
    if (-not (Test-Path -LiteralPath $path)) {
        Invoke-WebRequest -Uri $spec.url -OutFile $path
    }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $spec.sha256) {
        throw "下载校验失败：$path；保留文件供调查。"
    }
}

Get-Artifact $versions.luals '.tools/downloads/luals.zip'
Get-Artifact $versions.luacheck '.tools/downloads/luacheck.exe'
Get-Artifact $versions.lua '.tools/downloads/lua.tar.gz'
Expand-Archive .tools/downloads/luals.zip .tools/luals -Force
if (-not (Test-Path '.tools/lua-5.1.5/src/lua.c')) {
    tar -xzf .tools/downloads/lua.tar.gz -C .tools
}
if (-not (Test-Path '.tools/lua-5.1.5/src/lua.exe')) {
    $vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw '需要微软 C++ 编译工具；请先安装该组件。' }
    $vcvars = "$vs/VC/Auxiliary/Build/vcvars64.bat"
    $luaSource = Join-Path $repoRoot '.tools/lua-5.1.5/src'
    $sources = (Get-ChildItem -LiteralPath $luaSource -Filter '*.c' |
        Where-Object { $_.Name -notin @('luac.c', 'print.c') } |
        ForEach-Object { $_.Name }) -join ' '
    $batch = @"
@echo off
call "$vcvars"
if errorlevel 1 exit /b %errorlevel%
cd /d "$luaSource"
cl /nologo /O2 /D_CRT_SECURE_NO_WARNINGS /DLUA_USE_WINDOWS $sources /Fe:lua.exe
exit /b %errorlevel%
"@
    $batchPath = Join-Path $repoRoot '.tools/build-lua.cmd'
    Set-Content -LiteralPath $batchPath -Value $batch -Encoding ascii
    & cmd.exe /d /c "`"$batchPath`""
}

foreach ($entry in $versions.repositories.PSObject.Properties) {
    $path = ".tools/$($entry.Name)"
    $spec = $entry.Value
    if (-not (Test-Path -LiteralPath $path)) {
        git init --quiet $path
        git -C $path remote add origin $spec.url
    }
    if ((git -C $path remote get-url origin) -ne $spec.url) {
        throw "缓存来源与版本记录不一致：$path"
    }
    $head = try { git -C $path rev-parse --verify HEAD 2>$null } catch { '' }
    if ($head -ne $spec.commit) {
        if (git -C $path status --porcelain) { throw "缓存包含修改：$path" }
        git -C $path fetch --depth 1 origin $spec.commit
        git -C $path checkout --detach FETCH_HEAD
    }
}
git -C .tools/wow-api submodule update --init --recursive --depth 1
$expected = "$($versions.client.version).$($versions.client.build)"
if ((Get-Content .tools/wow-ui-source/version.txt).Trim() -ne $expected) {
    throw '界面源码构建号不匹配。'
}
if (-not (Test-Path '.venv/Scripts/python.exe')) { python -m venv .venv }
& .venv/Scripts/python.exe -m pip install --disable-pip-version-check -r scripts/dev/requirements.txt
& .tools/lua-5.1.5/src/lua.exe -e 'assert(_VERSION == "Lua 5.1"); print(_VERSION)'
& .tools/downloads/luacheck.exe --version
& .tools/luals/bin/lua-language-server.exe --version
Write-Output '本地工具与版本资料已准备。运行验证请使用 build-and-verify（构建与验证）。'
