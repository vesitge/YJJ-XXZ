@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Stop ONLY the voice assistant's own python processes (runtime python + ports 9890/9888).
rem All the logic lives in tools\voicechat\stop_voice.ps1.
rem This file stays pure ASCII on purpose: cmd mis-parses UTF-8 Chinese batch lines.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\voicechat\stop_voice.ps1"
if errorlevel 1 echo   WARNING: something is still running.
ping -n 6 127.0.0.1 >nul
exit /b 0
