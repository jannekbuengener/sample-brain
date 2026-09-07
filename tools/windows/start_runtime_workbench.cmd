@echo off
setlocal

REM This launcher must live inside the dedicated runtime worktree.
cd /d "%~dp0..\.."
set "RUNTIME_ROOT=%CD%"
set "PY=%RUNTIME_ROOT%\.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [ERROR] Runtime-Python fehlt: "%PY%"
    exit /b 1
)

"%PY%" -m src.runtime_provenance --check --runtime-root "%RUNTIME_ROOT%"
if errorlevel 1 exit /b %errorlevel%

"%PY%" -m src.cli workbench
endlocal
