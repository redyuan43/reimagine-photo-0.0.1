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

Write-Host ""
Write-Host "[启动] 后台服务 (端口 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python server.py" -WorkingDirectory $PSScriptRoot

Start-Sleep -Seconds 2

Write-Host "[启动] 前端服务 (端口 5173)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm run dev" -WorkingDirectory $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  所有服务已启动！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  后台服务: " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan
Write-Host "  前端服务: " -NoNewline; Write-Host "http://localhost:5173" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "提示: 关闭此窗口不会停止服务" -ForegroundColor Yellow
Write-Host "      要停止服务，请关闭对应的 PowerShell 窗口" -ForegroundColor Yellow
Write-Host ""
pause
