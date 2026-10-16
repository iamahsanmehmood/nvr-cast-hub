@echo off
title Building Single-File Portable Executable — NVR_Cast_Hub.exe (v0.1.0-beta)
color 0B
cd /d "%~dp0\.."

echo ============================================================================
echo   BUILDING SINGLE-FILE EXECUTABLE: NVR_Cast_Hub.exe (v0.1.0-beta)
echo ============================================================================
echo.

python -m pip install --upgrade pyinstaller yt-dlp mss pyaudiowpatch

python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
    --name "NVR_Cast_Hub" ^
    --add-data "bin\mediamtx.exe;bin" ^
    --add-data "chrome_extension;chrome_extension" ^
    --hidden-import "desktop_app" ^
    --hidden-import "desktop_app.engine" ^
    --hidden-import "desktop_app.gui" ^
    --hidden-import "web_studio" ^
    --hidden-import "web_studio.server" ^
    --hidden-import "yt_dlp" ^
    --hidden-import "mss" ^
    --hidden-import "pyaudiowpatch" ^
    nvr_cast_app.py

if exist "dist\NVR_Cast_Hub.exe" (
    copy /Y "dist\NVR_Cast_Hub.exe" "NVR_Cast_Hub.exe" >nul
    echo.
    echo ============================================================================
    echo   SUCCESS! Portable Single-File EXE created at:
    echo   %~dp0..\NVR_Cast_Hub.exe
    echo ============================================================================
) else (
    echo.
    echo [ERROR] Build failed. Check output above.
)
pause
