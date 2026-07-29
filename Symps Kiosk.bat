@echo off
REM Demarre le Symp's Kiosk. Double-cliquez ce fichier.
setlocal
cd /d "%~dp0"

REM Le lanceur "py" est installe avec Python sur Windows ; on le prefere.
where py >/dev/null 2>&1
if %errorlevel%==0 (
    py -3 symps.py %*
    goto fin
)

where python >/dev/null 2>&1
if %errorlevel%==0 (
    python symps.py %*
    goto fin
)

echo.
echo   Python 3 est introuvable sur cette machine.
echo.
echo   Installez-le depuis https://www.python.org/downloads/
echo   en cochant "Add python.exe to PATH" pendant l'installation.
echo.
pause
exit /b 1

:fin
if %errorlevel% neq 0 pause
