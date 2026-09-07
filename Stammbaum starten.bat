@echo off
setlocal EnableExtensions
rem ---------------------------------------------------------------------------
rem  Startet das Programm aus dem Quelltext daneben - ohne den Umweg ueber
rem  Stammbaum.exe.
rem
rem  Warum: die exe ist ein Schnappschuss. Sie wird gebaut, und danach weiss sie
rem  nichts mehr davon, dass neben ihr neuer Code liegt. Wer sie zum Arbeiten
rem  benutzt, arbeitet frueher oder spaeter mit einem alten Stand, ohne es zu
rem  merken - genau das ist am 07.09.2026 passiert. Aus dem Quelltext gestartet
rem  kann das nicht sein: es gibt nichts dazwischen, was veralten koennte.
rem
rem  Die exe bleibt trotzdem, und wird beim Release gebaut. Sie ist fuer die
rem  Leute, die kein Python haben - nicht fuer den, der das Programm schreibt.
rem
rem  Diese Datei liegt im Repo. Jeder Worktree hat also seine eigene, und die
rem  startet den Code ihres Worktrees. Mehrere Fassungen nebeneinander sind
rem  damit kein Sonderfall: jede laeuft aus ihrem eigenen Ordner, und weil das
rem  Programm sich seinen Netzwerkport selbst sucht, stehen sie sich nicht im
rem  Weg.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
title Stammbaum

if not exist "tools\edit_server.py" (
    echo.
    echo   Neben dieser Datei fehlt der Ordner "tools".
    echo   Sie gehoert in den Programmordner, nicht daneben.
    echo.
    pause
    exit /b 2
)

rem  Python muss da sein - das ist der Preis dafuer, aus dem Quelltext zu
rem  starten. Wer das nicht hat, nimmt die exe.
where pythonw.exe >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python wurde nicht gefunden.
    echo   Entweder Python installieren, oder Stammbaum.exe benutzen.
    echo.
    pause
    exit /b 2
)

rem  Laeuft hier ein Worktree, dann nicht auf der echten Familie. Der
rem  Datenordner steht ausserhalb des Programms, also naehme ein Worktree ohne
rem  dies hier denselben wie der Hauptordner - und ein halbfertiger Umbau
rem  schriebe in die Baeume, um die es geht. Ein eigener Ordner je Worktree ist
rem  leer und bleibt es, bis dort jemand bewusst etwas einliest.
rem
rem  Geprueft wird mit einer Textersetzung statt mit `find`: `find` ist auch der
rem  Name eines ganz anderen Programms, und wessen PATH das zuerst findet, ist
rem  nicht vorhersagbar. Das hier braucht nichts ausser cmd selbst.
set "HIER=%CD%"
if not "%HIER%"=="%HIER:\worktrees\=%" goto :zweig

rem  Der Hauptordner: ohne Konsolenfenster, so wie ein Doppelklick auf die exe.
start "" pythonw.exe "tools\edit_server.py" %*
exit /b 0

:zweig
for %%A in ("%CD%") do set "ZWEIG=%%~nxA"
set "AHNEN_DATEN=%LOCALAPPDATA%\Ahnenprogramm\Testdaten\%ZWEIG%"
if not exist "%AHNEN_DATEN%" md "%AHNEN_DATEN%" 2>nul
title Stammbaum - Zweig %ZWEIG%
echo.
echo   ZWEIG %ZWEIG%
echo   Es wird NICHT auf den echten Stammbaeumen gearbeitet.
echo   Testdaten: %AHNEN_DATEN%
echo.
echo   Dieses Fenster gehoert zum Programm - zu bleibt es, wenn das Programm
echo   beendet wird.
echo.
rem  Mit Konsole, damit sichtbar bleibt, dass hier ein Zweig laeuft und nicht
rem  der Hauptordner.
python.exe "tools\edit_server.py" %*
exit /b %ERRORLEVEL%
