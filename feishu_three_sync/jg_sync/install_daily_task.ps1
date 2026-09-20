$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Name = 'JuguangChildStoryDailyFeishuSync'
$Existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if ($Existing) {
    New-Item -ItemType Directory -Path "$ProjectDir\backups" -Force | Out-Null
    Export-ScheduledTask -TaskName $Name | Set-Content -LiteralPath "$ProjectDir\backups\task_before_update.xml" -Encoding UTF8
}
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$ProjectDir+'\run_daily.ps1"') -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description '聚光童年故事四张飞书底表：浏览器登录检查、T-1补数、近三日校准、备份及回读。' -Force | Out-Null
Get-ScheduledTaskInfo -TaskName $Name | Select-Object NextRunTime
