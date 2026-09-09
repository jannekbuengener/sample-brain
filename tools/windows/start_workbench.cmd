@echo off
setlocal

REM Compatibility launcher: never start a mutable developer checkout as producer UI.
set "RUNTIME_ROOT=%LOCALAPPDATA%\SampleBrain\runtime"
set "RUNTIME_START=%RUNTIME_ROOT%\tools\windows\start_runtime_workbench.cmd"

if not exist "%RUNTIME_START%" (
    echo [ERROR] Verifizierte Sample-Brain-Runtime fehlt: "%RUNTIME_ROOT%"
    echo Installieren: powershell -ExecutionPolicy Bypass -File ".\tools\windows\install_runtime_workbench.ps1" -CreateShortcut
    exit /b 1
)

call "%RUNTIME_START%"
exit /b %errorlevel%

endlocal
