@echo off
cd /d "%~dp0"
set "TEMP=%~dp0tmp"
set "TMP=%~dp0tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
if exist "%~dp0RomOSTinyVideo.exe" (
    start "" "%~dp0RomOSTinyVideo.exe"
    exit /b
)
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" pyw -3.13 -m videofactorio.gui
    exit /b
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m videofactorio.gui
exit /b
