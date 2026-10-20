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
echo [3/4] Checking Node.js runtime (for YouTube 1080p JS extraction)...
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Node.js not found on PATH. Installing via WinGet...
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
) else (
    echo Node.js is already installed!
)

echo.
echo [4/4] Generating default Pakistani & Sports Channel Config + VLC Playlist...
python -c "from desktop_app.engine import NVRCastEngine; e = NVRCastEngine(); print('Generated:', e.export_vlc_m3u()); print('Saved Config:', e.save_persistent_config())"

echo.
echo ============================================================================
echo   SETUP COMPLETE!
echo   - Default Config JSON: config\nvr_cast_config.json
echo   - Default VLC Playlist: config\NVR_Cast_Hub_Channels_VLC.m3u
echo   Run scripts\Run_Desktop_App.bat or NVR_Cast_Hub.exe
echo ============================================================================
pause
