@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stammbaum bearbeiten

python "tools\edit_server.py"
if errorlevel 1 (
  echo.
  echo FEHLER - der Editor konnte nicht starten.
  echo Ist Python installiert? Gibt es schon eine Stammbaum.html?
  echo Wenn nicht: einmal build.cmd laufen lassen.
  pause
)
exit /b 0
