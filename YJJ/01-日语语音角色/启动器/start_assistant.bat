@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
netstat -ano | findstr ":9888" | findstr LISTENING >nul
if errorlevel 1 start "" /min "%~dp0GPT-SoVITS-v5\start_tts_api.bat"
start "RiYu Assistant - close this window to stop" /min "%~dp0GPT-SoVITS-v5\runtime\python.exe" "%~dp0tools\voicechat\server.py"
timeout /t 8 /nobreak >nul
start "" http://127.0.0.1:9890
exit /b 0
