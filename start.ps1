# LUMINA AI 一键启动脚本 (PowerShell)
# 同时启动前端和后台服务

$host.UI.RawUI.WindowTitle = "LUMINA AI - 启动服务"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LUMINA AI - 启动中..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Node.js
Write-Host "[检查] Node.js..." -ForegroundColor Yellow
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未检测到 Node.js，请先安装 Node.js" -ForegroundColor Red
    pause
    exit 1
}
$nodeVersion = node --version
Write-Host "[成功] Node.js 已安装 ($nodeVersion)" -ForegroundColor Green

# 检查 Python
Write-Host "[检查] Python..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未检测到 Python，请先安装 Python" -ForegroundColor Red
    pause
    exit 1
}
$pythonVersion = python --version
Write-Host "[成功] Python 已安装 ($pythonVersion)" -ForegroundColor Green

# Python venv
if (-not $env:VIRTUAL_ENV) {
    $venvDir = Join-Path $PSScriptRoot ".venv"
    $activate = Join-Path $venvDir "Scripts\\Activate.ps1"
    if (-not (Test-Path $activate)) {
        Write-Host "[创建] 虚拟环境 (.venv)..." -ForegroundColor Yellow
        python -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "venv create failed" }
    }
    . $activate
}

Write-Host "[检查] Python 依赖..." -ForegroundColor Yellow
python -c "import fastapi, uvicorn" *> $null
if ($LASTEXITCODE -ne 0) {
    if (Test-Path (Join-Path $PSScriptRoot "requirements.txt")) {
        Write-Host "[安装] Python 依赖..." -ForegroundColor Yellow
        python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    }
}
Write-Host "[成功] Python 依赖已就绪" -ForegroundColor Green

Write-Host "[检查] npm 依赖..." -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $PSScriptRoot "node_modules"))) {
    Write-Host "[安装] npm 依赖..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
}
Write-Host "[成功] npm 依赖已就绪" -ForegroundColor Green

Write-Host ""
Write-Host "[启动] 后台服务 (端口 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn server:app --host 0.0.0.0 --port 8000" -WorkingDirectory $PSScriptRoot

Start-Sleep -Seconds 2

Write-Host "[启动] 前端服务 (端口 3000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:VITE_API_BASE_URL='/api'; npm run dev" -WorkingDirectory $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  所有服务已启动！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  后台服务: " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan
Write-Host "  前端服务: " -NoNewline; Write-Host "http://localhost:3000" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "提示: 关闭此窗口不会停止服务" -ForegroundColor Yellow
Write-Host "      要停止服务，请关闭对应的 PowerShell 窗口" -ForegroundColor Yellow
Write-Host ""
pause
