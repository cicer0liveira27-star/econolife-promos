@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Rodando o robo do PC agora (pode levar alguns minutos)...
py robo_pc.py
pause
