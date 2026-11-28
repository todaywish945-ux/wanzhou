#Requires -Version 5.1
<#
.SYNOPSIS
    挽昼桌宠 Windows 出包：PyInstaller onedir + 便携 zip（无 Inno Setup）。

.DESCRIPTION
    产物：
      dist\wanzhou-pet\                 onedir 目录，双击 wanzhou-pet.exe 出三只桌宠
      dist\wanzhou-<版本>-portable.zip  传百度网盘的压缩包

    启动器语义：exe 不带参数时拉起三个子进程（slot 1/2/3 = 角色 A/B/C）；
    带 --slot 参数时该进程就是其中一只桌宠。

    前置：
      venv\Scripts\python.exe -m pip install -r scripts\requirements-build.txt
#>
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
# PyInstaller 分析入口时只会把「入口所在目录」和「当前工作目录」塞进 sys.path；
# 不切到仓库根的话，pet 包根本进不了包，exe 一跑就是 ModuleNotFoundError。
[System.IO.Directory]::SetCurrentDirectory($Root)
$Python = Join-Path $Root 'venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Python = 'python'
}
$DistDir = Join-Path $Root 'dist'
$BuildDir = Join-Path $Root 'build'

$VersionLine = Select-String -Path (Join-Path $Root 'pet\__init__.py') -Pattern "__version__\s*=\s*'([^']+)'"
if (-not $VersionLine) {
    throw 'pet/__init__.py 里找不到 __version__'
}
$AppVersion = $VersionLine.Matches[0].Groups[1].Value
Write-Host "构建版本 v$AppVersion（源自 pet/__init__.py）"

Write-Host '== 构建前密钥门禁 =='
& $Python (Join-Path $Root 'scripts\check_no_secrets.py')
if ($LASTEXITCODE -ne 0) {
    throw '源码里发现疑似硬编码密钥，构建已中止；清理后再打。'
}

$keyringCollect = @('--collect-all', 'keyring')
$win32Collect = @('--collect-all', 'win32ctypes')
$edgeCollect = @('--collect-all', 'edge_tts')
$certifiCollect = @('--collect-all', 'certifi')
$rapidocrData = @('--add-data', "resources\rapidocr_models;resources\rapidocr_models")
$rapidocrHidden = @('--hidden-import', 'pet.screen_capture.ocr', '--hidden-import', 'pet.screen_capture.ocr_worker')
$assetData = @('--add-data', 'assets;assets')
# pet 包内也有运行时读取的 JSON（人设预置、默认菜单模板），PyInstaller 只收
# .py，不收这些；漏了会在冻结包里看到「预置缺失」的降级日志。
$petData = @(
    '--add-data', 'pet\persona_presets;pet\persona_presets',
    '--add-data', 'pet\menu_templates;pet\menu_templates'
)

$pyArgs = @(
    '--noconfirm', '--clean', '--onedir', '--windowed',
    '--icon', (Join-Path $Root 'assets\icon.ico'),
    '--name', 'wanzhou-pet',
    '--distpath', $DistDir,
    '--workpath', (Join-Path $BuildDir 'wanzhou-pet'),
    '--specpath', $Root,
    '--paths', $Root
) + $assetData + $petData + $rapidocrData + $keyringCollect + $win32Collect + $edgeCollect + $certifiCollect + $rapidocrHidden

Write-Host '== PyInstaller: wanzhou-pet =='
# 等价命令（解释器取上面解析出的 venv 绝对路径）：
# python -m PyInstaller @pyArgs @rapidocrData @keyringCollect @rapidocrHidden packaging\pet_entry.py
& $Python -m PyInstaller $pyArgs (Join-Path $Root 'packaging\pet_entry.py')
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller 构建失败'
}

$Bundle = Join-Path $DistDir 'wanzhou-pet'
if (-not (Test-Path (Join-Path $Bundle 'wanzhou-pet.exe'))) {
    throw "构建产物缺少 wanzhou-pet.exe：$Bundle"
}

Write-Host '== 构建骗子酒馆（随包独立 exe）=='
$PowerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
& $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'scripts\build_liar_game.ps1')
if ($LASTEXITCODE -ne 0) {
    throw '骗子酒馆（liar-game）构建失败'
}

Write-Host '== 发布前端到端验证（隔离 APPDATA 跑真实产物）=='
& $Python (Join-Path $Root 'scripts\pre_release_smoke.py') --bundle $Bundle
if ($LASTEXITCODE -ne 0) {
    throw '发布前验证未通过，已中止出包；修复后重跑构建脚本。'
}

$Zip = Join-Path $DistDir "wanzhou-$AppVersion-portable.zip"
if (Test-Path $Zip) {
    Remove-Item $Zip -Force
}
Compress-Archive -Path $Bundle -DestinationPath $Zip -CompressionLevel Optimal

Write-Host '== 文件级差分更新资产（清单 + 与上一版的差分包）=='
$ManifestDir = Join-Path $Root 'manifests'
$CurrentManifest = Join-Path $ManifestDir "manifest-$AppVersion.json"
& $Python (Join-Path $Root 'scripts\make_file_manifest.py') --bundle $Bundle --version $AppVersion --out $CurrentManifest
if ($LASTEXITCODE -ne 0) {
    throw '文件清单生成失败'
}
# 差分基线 = manifest-*.json 里比当前版本旧的最高一份（常见：上一版）。
# 没有历史清单（首次启用/全新版本线）就跳过差分，只出全量——不阻塞出包。
$prevManifest = Get-ChildItem $ManifestDir -Filter 'manifest-*.json' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "manifest-$AppVersion.json" } |
    ForEach-Object {
        if ($_.BaseName -match '^manifest-(.+)$') {
            [pscustomobject]@{ Path = $_.FullName; Version = $Matches[1] }
        }
    } |
    Sort-Object { [version]($_.Version -replace '^v', '') } -Descending |
    Select-Object -First 1
if ($prevManifest -ne $null) {
    $DeltaZip = Join-Path $DistDir "wanzhou-$AppVersion-delta-from-$($prevManifest.Version).zip"
    & $Python (Join-Path $Root 'scripts\make_delta_zip.py') --from $prevManifest.Path --to $CurrentManifest --bundle $Bundle --out $DeltaZip
    if ($LASTEXITCODE -ne 0) {
        throw '差分包生成失败'
    }
    Write-Host "差分包就绪：$DeltaZip (baseline $($prevManifest.Version))"
} else {
    Write-Host 'manifests/ 里没有历史清单，跳过差分包（只出全量）'
}

Write-Host "完成：$Zip"
Write-Host '双击解压目录里的 wanzhou-pet.exe 即可同时出现三只桌宠。'
