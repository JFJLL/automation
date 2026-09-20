param([string]$Categories = 'qicui')
$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if (Test-Path (Join-Path $ProjectDir '..\.venv\Scripts\python.exe')) { Join-Path $ProjectDir '..\.venv\Scripts\python.exe' } elseif (Test-Path 'D:\python\python.exe') { 'D:\python\python.exe' } else { 'python' }
$LogDir = Join-Path $ProjectDir 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Set-Location $ProjectDir
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$RunLog = Join-Path $LogDir ('daily_jzt_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
$RunCode = 1
Start-Transcript -Path $RunLog | Out-Null
try {
    $CategoryArgs = @()
    if ($Categories) { $CategoryArgs = @('--categories') + ($Categories -split '\s+') }
    & $Python (Join-Path $ProjectDir 'daily.py') --login-timeout 1800 @CategoryArgs
    $RunCode = $LASTEXITCODE
    if ($RunCode -ne 0) { Write-Host "JZT sync needs attention. Exit code: $RunCode. See logs/last_run.json." }
} finally {
    Stop-Transcript | Out-Null
}
exit $RunCode
