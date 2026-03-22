# build_installer.ps1 — 一键构建 exe + NSIS 安装包
# 用法: .\build_installer.ps1 [-Icon app.ico] [-SkipBuild] [-SkipInstaller]

param(
    [string]$Icon = "",          # ICO 文件路径（可选）
    [switch]$SkipBuild,          # 跳过 PyInstaller 构建（已有 exe 时）
    [switch]$SkipInstaller       # 跳过 NSIS 打包
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

# 从 main.py 读取版本号（单一来源）——去掉开头的 'v'
$rawVersion = (Select-String -Path "$ProjectDir\main.py" -Pattern 'VERSION\s*=\s*"v?([\d\.]+)"').Matches[0].Groups[1].Value
$Version = $rawVersion
$AppName = "AzureAISpeechDemo"
$Venv = "$ProjectDir\.venv\Scripts"

Write-Host "`n===== Azure AI 语音演示台 构建脚本 v$Version =====" -ForegroundColor Cyan

# ── Step 1: 检查环境 ─────────────────────────────────────────
Write-Host "`n[1/4] 检查构建环境..." -ForegroundColor Yellow

if (-not (Test-Path "$Venv\python.exe")) {
    Write-Host "ERROR: 未找到 Python venv ($Venv\python.exe)" -ForegroundColor Red
    exit 1
}

# 检查 ICO 文件
$IconPath = ""
if ($Icon -and (Test-Path $Icon)) {
    $IconPath = (Resolve-Path $Icon).Path
    Write-Host "  图标: $IconPath" -ForegroundColor Green
} elseif (Test-Path "$ProjectDir\app.ico") {
    $IconPath = "$ProjectDir\app.ico"
    Write-Host "  图标: $IconPath (自动检测)" -ForegroundColor Green
} else {
    Write-Host "  图标: 未指定（使用默认图标）" -ForegroundColor DarkGray
    Write-Host "  提示: 将 .ico 文件放在项目根目录命名为 app.ico，或使用 -Icon 参数指定" -ForegroundColor DarkGray
}

# ── Step 2: PyInstaller 构建 ─────────────────────────────────
if (-not $SkipBuild) {
    Write-Host "`n[2/4] PyInstaller 构建 exe..." -ForegroundColor Yellow

    # 清理旧产物
    if (Test-Path "$ProjectDir\dist") { Remove-Item "$ProjectDir\dist" -Recurse -Force }
    if (Test-Path "$ProjectDir\build\$AppName") { Remove-Item "$ProjectDir\build\$AppName" -Recurse -Force }

    # 调用独立的 Python 构建脚本（避免 PowerShell here-string 解析问题）
    $buildArgs = @("_build_exe.py", "--name", $AppName, "--version", $Version)
    if ($IconPath) { $buildArgs += @("--icon", $IconPath) }

    $ErrorActionPreference = "Continue"
    & "$Venv\python.exe" -u @buildArgs 2>&1 | ForEach-Object { Write-Host "  $_" }
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($buildExit -ne 0) {
        Write-Host "ERROR: PyInstaller 构建失败" -ForegroundColor Red
        exit 1
    }

    if (Test-Path "$ProjectDir\dist\$AppName.exe") {
        $size = [math]::Round((Get-Item "$ProjectDir\dist\$AppName.exe").Length / 1MB, 1)
        Write-Host "  构建成功: dist\$AppName.exe - ${size} MB" -ForegroundColor Green
    } else {
        Write-Host "ERROR: 未找到输出文件 dist\$AppName.exe" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`n[2/4] 跳过 PyInstaller 构建（使用已有 exe）" -ForegroundColor DarkGray
}

# ── Step 3: 安全检查 ─────────────────────────────────────────
Write-Host "`n[3/4] 安全检查（确认无 API Key 泄漏）..." -ForegroundColor Yellow
$exePath = "$ProjectDir\dist\$AppName.exe"
if (Test-Path $exePath) {
    $bytes = [System.IO.File]::ReadAllBytes($exePath)
    $content = [System.Text.Encoding]::UTF8.GetString($bytes)
    $checks = @("speech_api_key", "voicelive_api_key", "openai_api_key")
    $leaked = $false
    foreach ($key in $checks) {
        if ($content.Contains($key + '":"') -and $content.Contains('gAAAAAB')) {
            Write-Host "  WARNING: 可能包含加密的 $key" -ForegroundColor Red
            $leaked = $true
        }
    }
    if (-not $leaked) {
        Write-Host "  安全: 未发现 API Key 数据" -ForegroundColor Green
    }
}

# ── Step 4: NSIS 安装包 ──────────────────────────────────────
if (-not $SkipInstaller) {
    Write-Host "`n[4/4] NSIS 安装包..." -ForegroundColor Yellow

    # 检查 NSIS 是否安装
    $makensis = $null
    $nsisCmd = Get-Command makensis -ErrorAction SilentlyContinue
    $nsisLocations = @(
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )
    if ($nsisCmd) { $nsisLocations += $nsisCmd.Source }
    foreach ($loc in $nsisLocations) {
        if ($loc -and (Test-Path $loc)) {
            $makensis = $loc
            break
        }
    }

    if ($makensis) {
        Write-Host "  NSIS: $makensis" -ForegroundColor Green
        $ErrorActionPreference = "Continue"
        & $makensis /INPUTCHARSET UTF8 "/DPRODUCT_VERSION=$Version" "$ProjectDir\installer.nsi" 2>&1
        $nsisExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($nsisExit -eq 0) {
            $setupFile = "dist\${AppName}_Setup_$Version.exe"
            if (Test-Path "$ProjectDir\$setupFile") {
                $setupSize = [math]::Round((Get-Item "$ProjectDir\$setupFile").Length / 1MB, 1)
                Write-Host "  安装包: $setupFile - ${setupSize} MB" -ForegroundColor Green
            }
        } else {
            Write-Host "  WARNING: NSIS 打包失败" -ForegroundColor Red
        }
    } else {
        Write-Host "  NSIS 未安装，跳过安装包生成" -ForegroundColor DarkGray
        Write-Host "  安装 NSIS: https://nsis.sourceforge.io/Download" -ForegroundColor DarkGray
        Write-Host "  安装后运行: makensis installer.nsi" -ForegroundColor DarkGray
    }
} else {
    Write-Host "`n[4/4] 跳过 NSIS 安装包" -ForegroundColor DarkGray
}

# ── 完成 ─────────────────────────────────────────────────────
Write-Host "`n===== 构建完成 =====" -ForegroundColor Cyan
Write-Host "产物位置:"
Write-Host "  exe:   dist\$AppName.exe"
Write-Host "  安装包: dist\${AppName}_Setup_$Version.exe (如已生成)"
Write-Host ""
