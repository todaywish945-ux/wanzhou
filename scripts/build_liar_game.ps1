#Requires -Version 5.1
<#
.SYNOPSIS
    骗子酒馆（PySide6 移植版）独立打包：PyInstaller onedir，产物并入桌宠便携包。

.DESCRIPTION
    产物：dist\wanzhou-pet\liar-game\{liar-game.exe, _internal\}
    与 wanzhou-pet.exe 同层，桌宠冻结后在 exe 同层目录找 liar-game\liar-game.exe。

    --paths 指向仓库根：把 pet.quit_all 收进包，牌局能监视桌宠进程存活；
    收不到时游戏自动降级（不监视），不影响牌局本体。
#>
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
[System.IO.Directory]::SetCurrentDirectory($Root)
$Python = Join-Path $Root 'venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Python = 'python'
}
$DistDir = Join-Path $Root 'dist'
$BuildDir = Join-Path $Root 'build'

$GameDir = Join-Path $Root '骗子酒馆'
$Entry = Join-Path $GameDir 'liar_game.py'
if (-not (Test-Path $Entry)) {
    throw "找不到骗子酒馆入口：$Entry"
}

$pyArgs = @(
    '--noconfirm', '--clean', '--onedir', '--windowed',
    '--icon', (Join-Path $GameDir 'assets\liar_bar.ico'),
    '--name', 'liar-game',
    '--distpath', (Join-Path $DistDir 'liar-game-build'),
    '--workpath', (Join-Path $BuildDir 'liar-game'),
    '--specpath', (Join-Path $BuildDir 'liar-game'),
    '--paths', $Root,
    '--add-data', "$GameDir\assets;assets"
)

Write-Host '== PyInstaller: liar-game =='
& $Python -m PyInstaller $pyArgs $Entry
if ($LASTEXITCODE -ne 0) {
    throw '骗子酒馆构建失败'
}

$Built = Join-Path $DistDir 'liar-game-build\liar-game'
if (-not (Test-Path (Join-Path $Built 'liar-game.exe'))) {
    throw "构建产物缺少 liar-game.exe：$Built"
}

$Target = Join-Path $DistDir 'wanzhou-pet\liar-game'
if (Test-Path $Target) {
    Remove-Item $Target -Recurse -Force
}
New-Item -ItemType Directory -Path $Target -Force | Out-Null
Copy-Item (Join-Path $Built 'liar-game.exe') $Target -Force
Copy-Item (Join-Path $Built '_internal') $Target -Recurse -Force

Write-Host "完成：$Target\liar-game.exe（已并入桌宠便携包目录）"
