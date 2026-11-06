@echo off
chcp 65001 >nul
title Econolife Promos - Instalar robo do PC
cd /d "%~dp0"
echo.
echo  ===== Econolife Promos - robo do PC =====
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo  [!] Python nao encontrado.
  echo      Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH"
  echo      e rode este instalar.bat de novo.
  pause
  exit /b 1
)

echo  1/4 Instalando o navegador automatico (Playwright)...
py -m pip install --upgrade --quiet playwright
if errorlevel 1 ( echo  [!] Falha ao instalar o Playwright. & pause & exit /b 1 )
py -m playwright install chromium
if errorlevel 1 ( echo  [!] Falha ao baixar o Chromium. & pause & exit /b 1 )

echo.
echo  2/4 Configurando sua chave do GitHub e fazendo um teste...
py robo_pc.py --configurar

echo.
echo  3/4 Agendando para rodar a cada 15 minutos (sem abrir janela)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agendar.ps1"
if errorlevel 1 ( echo  [!] Nao consegui criar o agendamento. & pause & exit /b 1 )

echo.
echo  4/4 Pronto! O robo do PC roda sozinho a cada 15 minutos enquanto o computador estiver ligado.
echo      O historico fica em robo_pc.log nesta pasta.
echo.
pause
