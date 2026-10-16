@echo off
echo =======================================================
echo GreenPulse Smart Irrigation & Garden Monitoring System
echo Starting Local Backend Server...
echo =======================================================

cd /d "%~dp0"
python run_server.py
pause
