@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === 1/3  PDF lesen ===
python "tools\extract_pdf.py"
if errorlevel 1 goto fehler

echo.
echo === 2/3  Daten bauen und pruefen ===
python "tools\build_data.py"
if errorlevel 1 goto fehler

echo.
echo === 3/3  Seite bauen ===
rem  Aus dem Bericht, weil das hier die Kette aus der PDF ist. Ohne den
rem  Schalter baut build_site.py aus dem gepflegten Baum - das ist der
rem  normale Weg, wenn im Editor gearbeitet wurde.
python "tools\build_site.py" --aus-bericht
if errorlevel 1 goto fehler

echo.
echo Fertig. Stammbaum.html wurde aus dem Bericht neu erzeugt.
echo Der Pruefbericht steht im Baumordner unter data\validation-report.txt
echo.
echo Im Editor gemachte Aenderungen sind hierin NICHT enthalten - dafuer
echo im Editor "Uebernehmen" druecken oder "python tools\build_site.py"
echo ohne Schalter aufrufen.
pause
exit /b 0

:fehler
echo.
echo FEHLER - Abbruch.
echo Ist Python installiert und "pip install pymupdf pillow" gelaufen?
pause
exit /b 1
