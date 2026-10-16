@echo off
title NVR Cast Hub v0.1.0-beta — Dependency Installer
color 0B
cd /d "%~dp0\.."

echo ============================================================================
echo   NVR CAST HUB v0.1.0-beta — AUTOMATIC DEPENDENCY SETUP
echo ============================================================================
echo.

echo [1/3] Checking Python packages (yt-dlp, mss, pyaudiowpatch, pyinstaller)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo [2/3] Checking FFmpeg installation...
where ffmpeg >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo FFmpeg not found on PATH. Installing via WinGet...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
) else (
    echo FFmpeg is already installed!
)

echo.
echo [3/3] Checking Node.js runtime (for YouTube 1080p JS extraction)...
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Node.js not found on PATH. Installing via WinGet...
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
) else (
    echo Node.js is already installed!
)

echo.
echo ============================================================================
echo   SETUP COMPLETE! Run scripts\Run_Desktop_App.bat or NVR_Cast_Hub.exe
echo ============================================================================
pause
