@echo off
chcp 65001 >nul
title PrimeIceAGI v2 — Mock 测试模式

echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║   ◆ PrimeIceAGI v2  [Mock 测试模式]          ║
echo   ║   ◆ 用本地虚假模型验证完整流程                 ║
echo   ╚══════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 检查并安装依赖
echo   [1/3] 检查依赖...
pip install -r requirements.txt -q 2>nul

:: 启动 Mock API 服务器 (端口 9090)
echo   [2/3] 启动 Mock API 服务器 (localhost:9090) ...
start "Mock-API" /min cmd /c "cd /d %~dp0 && python mock_server.py 9090"

:: 等 Mock 就绪
echo   等待 Mock 服务器就绪...
:wait_mock
timeout /t 1 /nobreak >nul
curl -s http://localhost:9090/ >nul 2>&1
if %errorlevel% neq 0 goto wait_mock

:: 启动 Flask
echo   [3/3] 启动 Web 服务 (http://localhost:5020) ...
echo.
echo   页面会自动填入 Mock 配置，直接点"开始测试"即可
echo.
start "" http://localhost:5020
python app.py 5020

pause
