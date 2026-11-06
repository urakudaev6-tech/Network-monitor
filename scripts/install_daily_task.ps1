$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$script = Join-Path $root 'scripts\send_daily_report.py'
if (-not (Test-Path $python)) { throw "Не найден $python" }
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $script + '"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName 'NetworkMonitor-DailyEmail' -Action $action -Trigger $trigger -Settings $settings -Description 'Ежедневный отчёт о кандидатах на свободные IP' -Force | Out-Null
Write-Host 'Задание NetworkMonitor-DailyEmail создано на 09:00 (локальное время Windows).'
Write-Host 'Задание работает от текущей учётной записи: проверьте его выполнение в Планировщике.'
