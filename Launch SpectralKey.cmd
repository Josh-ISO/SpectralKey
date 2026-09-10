@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0scripts\launch.ps1"
pause
