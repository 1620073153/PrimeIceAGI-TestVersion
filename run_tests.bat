@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   运行测试套件...
echo.
python -m pytest tests/ -v --tb=short
echo.
pause
