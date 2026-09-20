$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ProjectDir 'run_daily_jzt.ps1'
$TaskName = 'JztQicuiFeishuSync'
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    $BackupDir = Join-Path $ProjectDir 'backups'
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Export-ScheduledTask -TaskName $TaskName | Set-Content -LiteralPath (Join-Path $BackupDir ('task_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.xml')) -Encoding Unicode
}
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Runner`" -Categories qicui" -WorkingDirectory $ProjectDir
$DailyTrigger = New-ScheduledTaskTrigger -Daily -At '13:30'
$MondayTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -WeeksInterval 1 -At '09:00'
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($DailyTrigger, $MondayTrigger) -Settings $Settings -Principal $Principal -Description 'Qicui Feishu sync: daily 13:30 plus Monday 09:00. CAPTCHA/SMS waits for user. See project logs.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object NextRunTime, LastTaskResult
