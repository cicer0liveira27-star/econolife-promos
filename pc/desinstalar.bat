@echo off
chcp 65001 >nul
powershell -NoProfile -Command "Unregister-ScheduledTask -TaskName 'Econolife Robo PC' -Confirm:$false" 2>nul
echo Agendamento do robo do PC removido. Pode apagar esta pasta se quiser.
pause
