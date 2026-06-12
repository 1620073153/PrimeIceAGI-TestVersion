@echo off
chcp 65001 >nul
title PrimeIceAGI v2 — 大模型内容安全红队自动化测试

echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║   ◆ PrimeIceAGI v2                            ║
echo   ║   ◆ 大模型内容安全红队自动化测试平台            ║
echo   ║   ◆ 基于 TC260-003 五大类三十一小类             ║
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
echo   [1/2] 检查依赖...
pip install -r requirements.txt -q 2>nul

:: 启动
echo   [2/2] 启动服务 (http://localhost:5020) ...
echo.
start "" http://localhost:5020
python app.py 5020

pause
