@echo off
setlocal

REM Repo root: this script lives in tools\windows\
cd /d "%~dp0..\.."

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" -m src.cli workbench

endlocal
