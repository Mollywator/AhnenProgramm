@echo off
setlocal EnableExtensions
rem ---------------------------------------------------------------------------
rem  Baut Stammbaum.exe - und zwar aus main, egal von wo aus geklickt wird.
rem
rem  Warum von Hand: die exe entsteht sonst nirgends. Der Ship-Weg baut sie
rem  nicht mit; er merged, versioniert und raeumt auf, aber PyInstaller laeuft
rem  dabei nicht. Die exe im Hauptordner ist darum immer so alt wie der letzte
rem  Bau - und das ist genau die Falle, wegen der es "Stammbaum starten.bat"
rem  gibt. Diese Datei ist die andere Haelfte davon: sie holt die exe auf den
rem  aktuellen Stand, wenn eine gebraucht wird.
rem
rem  Warum aus main: eine exe ist zum Weitergeben da. Was weitergegeben wird,
rem  ist der Stand, auf den sich alles geeinigt hat - nicht der halbfertige
rem  Umbau, in dessen Zweigordner die Datei gerade angeklickt wurde. Der
rem  Hauptordner wird darum bei Git erfragt, nicht geraten, und die exe landet
rem  dort.
rem
rem  Wer doch den Zweig bauen will, in dem er steht, haengt "hier" an:
rem      "Stammbaum bauen.bat" hier
rem
rem  Die Arbeit selbst macht tools\build_exe.py; die Aufrufe an PyInstaller
rem  stehen dort und nur dort. Diese Datei ist der Doppelklick davor: sie sucht
rem  den richtigen Ordner, sucht Python, prueft PyInstaller und laesst das
rem  Fenster am Ende offen, damit auch eine Fehlermeldung gelesen werden kann.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
title Stammbaum bauen
chcp 65001 >nul

rem  Den Hauptordner sagt Git, nicht der Pfad: die erste Zeile von
rem  "git worktree list" ist immer der Hauptordner, auch wenn die Zweige ganz
rem  woanders liegen. Ohne Git - etwa in einem entpackten Abzug ohne .git -
rem  bleibt es bei dem Ordner, in dem diese Datei liegt.
set "ZIEL=%CD%"
if /i "%~1"=="hier" goto :ordner_steht

for /f "usebackq tokens=1,* delims= " %%A in (`git worktree list --porcelain 2^>nul`) do (
    if /i "%%A"=="worktree" if not defined HAUPT set "HAUPT=%%B"
)
if defined HAUPT set "ZIEL=%HAUPT%"

:ordner_steht
if not exist "%ZIEL%\tools\build_exe.py" (
    echo.
    echo   Im Ordner
    echo       %ZIEL%
    echo   liegt kein "tools\build_exe.py". Da ist nichts zu bauen.
    goto :halt
)
cd /d "%ZIEL%"

rem  Was gleich gebaut wird, wird vorher gesagt. Ein Zweigname an dieser Stelle
rem  ist kein Fehler - aber er ist der Grund, warum eine exe spaeter etwas
rem  anderes tut als erwartet, und dann will man sich erinnern, ihn gesehen zu
rem  haben.
for /f "usebackq delims=" %%B in (`git rev-parse --abbrev-ref HEAD 2^>nul`) do set "AST=%%B"
echo.
echo   Ordner: %CD%
if defined AST echo   Stand:  %AST%
if defined AST if /i not "%AST%"=="main" (
    echo.
    echo   ACHTUNG: das ist nicht main. Die exe traegt dann diesen Stand.
)
git diff --quiet 2>nul
if errorlevel 1 echo   Hinweis: dort liegen ungespeicherte Aenderungen - die kommen mit.

rem  Hier wird bewusst python.exe genommen und nicht pythonw.exe: ein Bau ohne
rem  Ausgabe waere nutzlos - man will sehen, woran er scheitert.
set "PY="
where python.exe >nul 2>&1 && set "PY=python.exe"
if not defined PY (
    rem  Der Starter py.exe kennt auch Installationen, die nicht im PATH stehen.
    where py.exe >nul 2>&1 && set "PY=py.exe -3"
)
if not defined PY (
    echo.
    echo   Python wurde nicht gefunden.
    echo   Ohne Python laesst sich die exe nicht bauen - sie wird ja daraus
    echo   gemacht. Also erst Python installieren.
    goto :halt
)

rem  Vorher gefragt statt hinterher: build_exe.py bricht ohne PyInstaller zwar
rem  sauber ab, kann aber nichts dagegen tun. Hier ist noch jemand da, den man
rem  fragen kann.
%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   PyInstaller fehlt. Das ist das Werkzeug, das aus dem Python-Code
    echo   eine exe macht - ohne das geht es nicht weiter.
    echo.
    choice /c jn /n /m "   Jetzt nachinstallieren? [J/N] "
    if errorlevel 2 goto :abgebrochen
    echo.
    %PY% -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo   Die Installation ist gescheitert.
        goto :halt
    )
)

echo.
%PY% "tools\build_exe.py"
if errorlevel 1 (
    echo.
    echo   Der Bau ist gescheitert. Was schiefging, steht darueber.
    goto :halt
)

echo   Sie liegt hier: %CD%\Stammbaum.exe
echo.
pause
exit /b 0

:abgebrochen
echo.
echo   Abgebrochen. Es wurde nichts gebaut und nichts installiert.
echo.
pause
exit /b 1

:halt
echo.
pause
exit /b 2
