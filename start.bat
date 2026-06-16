@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title PrimeIceAGI v2 - 大模型内容安全红队自动化测试

set "APP_NAME=PrimeIceAGI v2"
set "APP_PORT=5020"
set "APP_URL=http://localhost:%APP_PORT%"
set "HEALTH_URL=%APP_URL%/api/health"
set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "PYTHON_CMD="
set "PIP_CMD="
set "APP_PID="
set "CHECK_FAILED=0"

cls
echo.
echo   ==================================================
echo     %APP_NAME%
echo     大模型内容安全红队自动化测试平台
echo     基于 TC260-003 五大类三十一小类
echo   ==================================================
echo.

cd /d "%~dp0"

echo   [0/6] 当前目录: %cd%
echo.

call :ensure_project_file "app.py" "项目入口 app.py"
call :ensure_project_file "requirements.txt" "Python 依赖 requirements.txt"
if "%CHECK_FAILED%"=="1" goto :missing_requirements

echo   [1/6] 检查 Python 3.10+ ...
call :find_python
if not defined PYTHON_CMD goto :missing_python
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :python_too_old
for /f "delims=" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VERSION=%%v"
echo         OK: !PYTHON_VERSION!

echo   [2/6] 准备 Python 虚拟环境 ...
if not exist "%VENV_PY%" (
    echo         未发现 .venv，正在创建隔离环境...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto :venv_failed
)
set "PYTHON_CMD="%VENV_PY%""
set "PIP_CMD="%VENV_PIP%""
%PYTHON_CMD% -m pip --version >nul 2>&1
if errorlevel 1 goto :pip_missing
echo         OK: %VENV_DIR%

echo   [3/6] 安装/更新 Python 依赖 ...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :pip_install_failed
echo         OK: requirements.txt

echo   [4/6] 检查 Node.js / npm / Claude Code CLI ...
node --version >nul 2>&1
if errorlevel 1 goto :missing_node
for /f "delims=" %%v in ('node --version 2^>^&1') do set "NODE_VERSION=%%v"
node -e "const major = Number(process.versions.node.split('.')[0]); process.exit(major >= 18 ? 0 : 1)" >nul 2>&1
if errorlevel 1 goto :node_too_old
echo         OK: Node.js !NODE_VERSION!

call npm --version >nul 2>&1
if errorlevel 1 goto :missing_npm
for /f "delims=" %%v in ('call npm --version 2^>^&1') do set "NPM_VERSION=%%v"
echo         OK: npm !NPM_VERSION!

call claude --version >nul 2>&1
if errorlevel 1 goto :missing_claude
for /f "delims=" %%v in ('call claude --version 2^>^&1') do set "CLAUDE_VERSION=%%v"
echo         OK: Claude Code CLI !CLAUDE_VERSION!

if not exist "config\agent_home\.claude\settings.json" (
    echo         INFO: Agent API is not configured yet.
    echo         Configure Agent URL / Key / Model in the web UI after launch.
) else (
    echo         OK: Claude agent config file detected
)

echo   [5/6] 检查端口 %APP_PORT% ...
call :check_port
if "%CHECK_FAILED%"=="1" goto :port_maybe_existing
echo         OK: 端口可用

if exist ".app_pid" del ".app_pid" >nul 2>&1

echo   [6/6] 即将启动服务: %APP_URL%
echo.
echo   正在打开浏览器...
start "" "%APP_URL%"
echo.
echo   Flask 请求日志会显示在本窗口；按 Ctrl+C 可停止服务。
echo.
%PYTHON_CMD% app.py %APP_PORT%
goto :server_exited

:server_exited
echo.
echo   服务已退出。
pause
endlocal
exit /b 0

:open_browser
echo.
echo   正在打开浏览器...
start "" "%APP_URL%"
echo.
echo   已连接到正在运行的 PrimeIceAGI 服务。
echo   注意: 这个窗口不会显示已有服务的请求日志；如需查看日志，请先关闭旧服务后重新双击本脚本。
pause
endlocal
exit /b 0

:ensure_project_file
if not exist "%~1" (
    echo   [错误] 缺少 %~2: %~1
    set "CHECK_FAILED=1"
)
exit /b 0

:find_python
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    exit /b 0
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)
python3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python3"
    exit /b 0
)
exit /b 0

:check_port
set "CHECK_FAILED=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=%APP_PORT%; $c=Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($c) { exit 1 } else { exit 0 }" >nul 2>&1
if errorlevel 1 set "CHECK_FAILED=1"
exit /b 0

:probe_existing_service
set "CHECK_FAILED=0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 3; if ($r.StatusCode -eq 200 -and $r.Content -match 'PrimeIceAGI') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 set "CHECK_FAILED=1"
exit /b 0

:missing_requirements
echo.
echo   请确认你是在 PrimeIceAGI 项目根目录双击 start.bat。
goto :fail

:missing_python
echo.
echo   [错误] 未找到 Python。
echo   请安装 Python 3.9+，并勾选 Add python.exe to PATH。
echo   下载地址: https://www.python.org/downloads/
goto :fail

:python_too_old
echo.
echo   [错误] Python 版本过低，需要 Python 3.10+。
echo   当前版本:
%PYTHON_CMD% --version
echo   下载地址: https://www.python.org/downloads/
goto :fail

:venv_failed
echo.
echo   [错误] 创建 .venv 虚拟环境失败。
echo   请确认 Python 安装完整，并尝试重新打开 start.bat。
goto :fail

:pip_missing
echo.
echo   [错误] 虚拟环境中 pip 不可用。
echo   可尝试删除 .venv 后重新运行 start.bat。
goto :fail

:pip_install_failed
echo.
echo   [错误] Python 依赖安装失败。
echo   请检查网络或代理后重试，也可手动执行:
echo   %VENV_PY% -m pip install -r requirements.txt
goto :fail

:missing_node
echo.
echo   [错误] 未找到 Node.js。Claude Code CLI 需要 Node.js 18+。
echo   下载地址: https://nodejs.org/
goto :fail

:node_too_old
echo.
echo   [错误] Node.js 版本过低，需要 Node.js 18+。
echo   当前版本:
node --version
echo   下载地址: https://nodejs.org/
goto :fail

:missing_npm
echo.
echo   [错误] 未找到 npm。请重新安装 Node.js，并确保 npm 已加入 PATH。
goto :fail

:missing_claude
echo.
echo   [错误] 未找到 Claude Code CLI，提示词生成智能体依赖此工具。
echo   安装命令:
echo   npm install -g @anthropic-ai/claude-code
echo.
echo   安装后请重新打开一个命令行窗口，确认以下命令可用:
echo   claude --version
goto :fail

:port_maybe_existing
echo         端口 %APP_PORT% 已被占用，正在检查是否已有 PrimeIceAGI 服务...
call :probe_existing_service
if "%CHECK_FAILED%"=="1" goto :port_in_use
echo         OK: 端口 %APP_PORT% 已有可用的 PrimeIceAGI 服务。
set "APP_PID="
goto :open_browser

:port_in_use
echo.
echo   [错误] 端口 %APP_PORT% 已被占用，服务无法启动。
echo   请关闭占用该端口的程序后重试，或手动修改 start.bat 中的 APP_PORT。
echo   查看占用进程:
echo   netstat -ano ^| findstr :%APP_PORT%
goto :fail

:startup_timeout
echo.
echo   [错误] Python 服务启动超时，未生成 .app_pid。
echo   请查看 logs\primeice.log 或直接运行以下命令定位错误:
echo   %VENV_PY% app.py %APP_PORT%
goto :fail

:fail
echo.
echo   启动未完成。请按提示处理后重新双击 start.bat。
pause
endlocal
exit /b 1
