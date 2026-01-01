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

echo [检查] Python 虚拟环境...
if not defined VIRTUAL_ENV (
    if exist "venv\\Scripts\\activate.bat" (
        set "VENV_DIR=venv"
    ) else if exist ".venv\\Scripts\\activate.bat" (
        set "VENV_DIR=.venv"
    ) else (
        set "VENV_DIR=.venv"
        echo [创建] 虚拟环境 (%VENV_DIR%)...
        python -m venv "%VENV_DIR%"
        if errorlevel 1 (
            echo [错误] 虚拟环境创建失败
            pause
            exit /b 1
        )
    )
    call "%VENV_DIR%\\Scripts\\activate.bat"
)
echo [成功] 虚拟环境已就绪

echo [检查] Python 依赖...
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    if exist "requirements.txt" (
        echo [安装] Python 依赖...
        python -m pip install -r requirements.txt
        if errorlevel 1 (
            echo [错误] Python 依赖安装失败
            pause
            exit /b 1
        )
    )
)
echo [成功] Python 依赖已就绪

echo [检查] npm 依赖...
if not exist "node_modules" (
    echo [安装] npm 依赖...
    npm install
    if errorlevel 1 (
        echo [错误] npm 依赖安装失败
        pause
        exit /b 1
    )
)
echo [成功] npm 依赖已就绪

echo.
echo [启动] 后台服务 (端口 8000)...
start "LUMINA AI - 后台服务" cmd /k "python -m uvicorn server:app --host 0.0.0.0 --port 8000"
timeout /t 2 /nobreak >nul

echo [启动] 前端服务 (端口 3000)...
start "LUMINA AI - 前端服务" cmd /k "set VITE_API_BASE_URL=/api && npm run dev"

echo.
echo ========================================
echo   所有服务已启动！
echo ========================================
echo   后台服务: http://localhost:8000
echo   前端服务: http://localhost:3000
echo ========================================
echo.
echo 提示: 关闭此窗口不会停止服务
echo       要停止服务，请关闭对应的窗口
echo.
pause
