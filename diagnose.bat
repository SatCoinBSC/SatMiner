@echo off
cd /d "%~dp0"
chcp 65001 >nul 2>&1
python diagnose.py
pause
