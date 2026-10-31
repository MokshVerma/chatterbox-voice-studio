@echo off
cd /d "%~dp0"
python chatterbox_app.py
if errorlevel 1 pause
