@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title PrimeIceAGI v2 - LLM Content Safety Red Team

set "APP_NAME=PrimeIceAGI v2"
set "APP_PORT=5020"
set "APP_URL=http://localhost:%APP_PORT%"
set "HEALTH_URL=%APP_URL%/api/health"
set "PYTHON_CMD=%~dp0runtime\python\python.exe"
set "CHECK_FAILED=0"

cls
echo.
echo   ==================================================
echo     %APP_NAME%
echo     LLM Content Safety Red Team Platform
echo     TC260-003 / 5 Categories / 31 Subcategories
echo   ==================================================
echo.

cd /d "%~dp0"

echo   [1/3] Checking runtime ...
if not exist "%PYTHON_CMD%" goto :missing_runtime
"%PYTHON_CMD%" -c "import flask, requests" >nul 2>&1
if errorlevel 1 goto :missing_packages
for /f "delims=" %%v in ('""%PYTHON_CMD%"" --version 2^>^&1') do set "PY_VER=%%v"
echo         OK: !PY_VER! (embedded runtime)

echo   [2/3] Checking port %APP_PORT% ...
call :check_port
if "%CHECK_FAILED%"=="1" goto :port_maybe_existing
echo         OK: port available

echo   [3/3] Starting service: %APP_URL%
echo.
start "" "%APP_URL%"
echo   Press Ctrl+C to stop.
echo.
"%PYTHON_CMD%" app.py %APP_PORT%
goto :server_exited

:server_exited
echo.
echo   Server exited.
pause
endlocal
exit /b 0

:open_browser
echo.
start "" "%APP_URL%"
echo   Connected to running PrimeIceAGI service.
pause
endlocal
exit /b 0

:check_port
set "CHECK_FAILED=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $null = Get-NetTCPConnection -LocalPort %APP_PORT% -State Listen -ErrorAction Stop; exit 1 } catch { exit 0 }" >nul 2>&1
if errorlevel 1 set "CHECK_FAILED=1"
exit /b 0

:probe_existing_service
set "CHECK_FAILED=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 3; if ($r.StatusCode -eq 200 -and $r.Content -match 'PrimeIceAGI') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 set "CHECK_FAILED=1"
exit /b 0

:missing_runtime
echo.
echo   [ERROR] Embedded Python runtime not found.
echo   Ensure runtime\python\ directory is intact.
goto :fail

:missing_packages
echo.
echo   [ERROR] Runtime packages missing.
echo   Ensure runtime\packages\ directory is intact.
goto :fail

:port_maybe_existing
echo         Port %APP_PORT% in use, probing for existing service...
call :probe_existing_service
if "%CHECK_FAILED%"=="1" goto :port_in_use
echo         OK: Found running PrimeIceAGI service.
goto :open_browser

:port_in_use
echo.
echo   [ERROR] Port %APP_PORT% is occupied.
echo   Check: netstat -ano ^| findstr :%APP_PORT%
goto :fail

:fail
echo.
pause
endlocal
exit /b 1
