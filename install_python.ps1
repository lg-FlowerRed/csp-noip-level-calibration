# Python 一键安装脚本（Windows）
# 用法：右键“使用 PowerShell 运行”，或双击同目录的 install_python.bat
# 说明：优先用 winget 安装 Python 3.12；失败则下载 python.org 官方安装包静默安装。

$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    foreach ($cmd in @("py", "python")) {
        $c = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    return $null
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Find-PythonExe {
    $roots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "C:\Program Files\Python312",
        "C:\Program Files\Python313",
        "C:\Program Files\Python314"
    )
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $exe = Get-ChildItem $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
                   Select-Object -First 1
            if ($exe) { return $exe.FullName }
        }
    }
    return $null
}

function Install-ProjectDependencies {
    param([string]$PythonExe)
    $requirements = Join-Path $PSScriptRoot "requirements.txt"
    if (-not (Test-Path $requirements)) { return }
    Write-Host "正在安装统计计算依赖..." -ForegroundColor Yellow
    & $PythonExe -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) {
        throw "依赖安装失败，请手动运行：$PythonExe -m pip install -r requirements.txt"
    }
    Write-Host "依赖安装完成。" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Python 安装助手 ===" -ForegroundColor Cyan
Write-Host ""

$existing = Get-PythonCommand
if (-not $existing) {
    Refresh-Path
    $existing = Get-PythonCommand
}
if (-not $existing) {
    $existing = Find-PythonExe
}
if ($existing) {
    Write-Host "已检测到 Python：$existing" -ForegroundColor Green
    & $existing --version
    Install-ProjectDependencies $existing
    Write-Host ""
    Write-Host "Python 与项目依赖均已就绪。"
    Read-Host "按回车退出"
    exit 0
}

$installed = $false

# 方案一：winget（Windows 11 自带）
$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($winget) {
    Write-Host "正在用 winget 安装 Python 3.12 ..." -ForegroundColor Yellow
    try {
        winget install -e --id Python.Python.3.12 `
            --accept-source-agreements --accept-package-agreements
        $installed = $true
    } catch {
        Write-Host "winget 安装失败，尝试官方安装包..." -ForegroundColor Yellow
    }
    Refresh-Path
} else {
    Write-Host "未找到 winget，直接使用官方安装包。" -ForegroundColor Yellow
}

# 方案二：官方安装包
if (-not (Get-PythonCommand) -and -not (Find-PythonExe)) {
    $version = "3.12.10"
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
    $url = "https://www.python.org/ftp/python/$version/python-$version-$arch.exe"
    $installer = Join-Path $env:TEMP "python-$version-$arch.exe"

    Write-Host "正在下载：$url" -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        Write-Host "正在静默安装（当前用户，自动加入 PATH）..." -ForegroundColor Yellow
        Start-Process -FilePath $installer -Wait -ArgumentList @(
            "/quiet",
            "InstallAllUsers=0",
            "PrependPath=1",
            "Include_test=0",
            "Include_launcher=1"
        )
        $installed = $true
    } catch {
        Write-Host ("官方安装包下载或安装失败：" + $_.Exception.Message) -ForegroundColor Red
    } finally {
        if (Test-Path $installer) { Remove-Item $installer -Force -ErrorAction SilentlyContinue }
    }
    Refresh-Path
}

# 验证
$python = Get-PythonCommand
if (-not $python) { $python = Find-PythonExe }

Write-Host ""
if ($python) {
    Write-Host "安装成功：$python" -ForegroundColor Green
    & $python --version
    Install-ProjectDependencies $python
    Write-Host ""
    Write-Host "请关闭当前窗口，重新打开终端，然后运行：" -ForegroundColor Cyan
    Write-Host "  py calc_rating_matched.py" -ForegroundColor White
    Write-Host "或双击 run_gui.bat 打开图形界面。" -ForegroundColor Cyan
} else {
    Write-Host "自动安装未成功。" -ForegroundColor Red
    Write-Host ""
    Write-Host "请手动安装（二选一）："
    Write-Host "  1. 打开 PowerShell，运行：winget install -e --id Python.Python.3.12"
    Write-Host "  2. 打开 https://www.python.org/downloads/windows/ 下载安装包"
    Write-Host "     安装时务必勾选 'Add python.exe to PATH'"
}

Write-Host ""
Read-Host "按回车退出"
