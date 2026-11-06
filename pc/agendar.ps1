# Agenda o robo do PC para rodar a cada 15 minutos, sem janela, inclusive na bateria.
$script = Join-Path $PSScriptRoot 'robo_pc.py'
$acao = New-ScheduledTaskAction -Execute 'pyw.exe' -Argument ('"' + $script + '"') -WorkingDirectory $PSScriptRoot
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 14) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'Econolife Robo PC' -Action $acao -Trigger $gatilho -Settings $ajustes -Force | Out-Null
