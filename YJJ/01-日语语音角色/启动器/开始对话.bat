@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0"
echo ==== 打字对话启动器 ====
rem 手动开助手 = 重新允许插件自动拉起
del /q "%ROOT%tools\voicechat\autostart.off" >nul 2>&1
netstat -ano | findstr ":9888" | findstr LISTENING >nul
if errorlevel 1 (
  echo [1/2] TTS 服务没在跑，先启动它...
  start "TTS API" /min "%ROOT%GPT-SoVITS-v5\start_tts_api.bat"
  echo       等待模型加载，约 60 秒...
  timeout /t 60 /nobreak >nul
) else (
  echo [1/2] TTS 服务已在运行
)
echo [2/2] 打开对话页面...
start "" http://127.0.0.1:9890
"%ROOT%GPT-SoVITS-v5\runtime\python.exe" "%ROOT%tools\voicechat\server.py"
echo 服务已退出。
pause
