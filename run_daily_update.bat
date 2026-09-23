@echo off
title Job Hunter AI - Actualizacion Diaria de Vacantes
echo ======================================================================
echo           JOB HUNTER AI - ACTUALIZACION DIARIA DE VACANTES
echo ======================================================================
cd /d "%~dp0"
echo Ejecutando busqueda diaria de vacantes y regenerando dashboard...
echo.
uv run python daily_updater.py
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo [EXITO] Actualizacion finalizada con exito.
    echo Abriendo dashboard actualizado en el navegador...
    echo ======================================================================
    start "" index.html
) else (
    echo.
    echo ======================================================================
    echo [ERROR] Se produjo un error durante la ejecucion del autobuscador.
    echo ======================================================================
)
echo.
pause
