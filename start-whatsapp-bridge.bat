@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

title ClinicFlux AI - WhatsApp Bridge
echo Iniciando WhatsApp Bridge...
echo.
echo Repo: %CD%
echo Python: %PYTHON_EXE%
echo.

"%PYTHON_EXE%" apps\msg\whatsapp_web.py bridge

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo O bridge foi encerrado com erro. Codigo: %EXIT_CODE%
  pause
)

exit /b %EXIT_CODE%
