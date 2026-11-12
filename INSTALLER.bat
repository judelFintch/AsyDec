@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python scripts\installer.py
) else (
    py -3 scripts\installer.py
)
set "resultat=%errorlevel%"
if not "%resultat%"=="0" echo Installation incomplete. Python 3.10 ou plus recent avec Tkinter est necessaire.
pause
exit /b %resultat%
