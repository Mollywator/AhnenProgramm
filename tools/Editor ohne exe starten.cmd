@echo off
chcp 65001 >nul
rem  Eine Ebene hoeher, in den Programmordner: der Editor sucht seine
rem  Sachen von dort aus, und diese Datei liegt in tools\.
cd /d "%~dp0.."
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
