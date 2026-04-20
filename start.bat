@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Forensic Report System

echo ============================================================
echo   Forensic Report System
echo ============================================================
echo.

:: Check Python
if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
    echo [OK] Using embedded Python
) else (
    where python >nul 2>&1
    if !errorlevel!==0 (
        set "PYTHON=python"
        echo [OK] Using system Python
    ) else (
        where python3 >nul 2>&1
        if !errorlevel!==0 (
            set "PYTHON=python3"
            echo [OK] Using system Python3
        ) else (
            echo [ERROR] Python not found. Please install Python 3.9+
            echo         Download: https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
            echo         Extract to: %~dp0python\
            pause
            exit /b 1
        )
    )
)

:: Show Python version
echo.
echo Python version:
"!PYTHON!" --version
echo.

:: Install dependencies (pip skips already-installed packages)
echo [INFO] Installing/verifying dependencies...
"!PYTHON!" -m pip install -r "%~dp0backend\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if !errorlevel! neq 0 (
    echo.
    echo [WARN] Tsinghua mirror failed, trying official PyPI...
    "!PYTHON!" -m pip install -r "%~dp0backend\requirements.txt"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies. Check error messages above.
        pause
        exit /b 1
    )
)
echo [OK] Dependencies ready
echo.

:: Set environment
set PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

:: Start server
echo [*] Starting server...
echo [*] Open browser: http://localhost:8000
echo [*] Press Ctrl+C to stop
echo.

cd /d "%~dp0backend"
"!PYTHON!" -m uvicorn main:app --host 0.0.0.0 --port 8000

echo.
echo [INFO] Server stopped.
pause
