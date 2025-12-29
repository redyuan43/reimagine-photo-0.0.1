@echo off
chcp 65001 >nul
title LUMINA AI - 启动服务

echo ========================================
echo   LUMINA AI - 启动中...
echo ========================================
echo.

echo [检查] Node.js...
where node >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)
echo [成功] Node.js 已安装

echo [检查] Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python
    pause
    exit /b 1
)
echo [成功] Python 已安装

echo.
echo [启动] 后台服务 (端口 8000)...
start "LUMINA AI - 后台服务" cmd /k "python server.py"
timeout /t 2 /nobreak >nul

echo [启动] 前端服务 (端口 5173)...
start "LUMINA AI - 前端服务" cmd /k "npm run dev"

echo.
echo ========================================
echo   所有服务已启动！
echo ========================================
echo   后台服务: http://localhost:8000
echo   前端服务: http://localhost:5173
echo ========================================
echo.
echo 提示: 关闭此窗口不会停止服务
echo       要停止服务，请关闭对应的窗口
echo.
pause
