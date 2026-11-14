@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem one click: tray icon in the notification area starts everything
wscript "%~dp0tools\tray\start_tray.vbs"
exit /b 0
