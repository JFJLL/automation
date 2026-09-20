$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if (Test-Path (Join-Path $ProjectDir '..\.venv\Scripts\python.exe')) { Join-Path $ProjectDir '..\.venv\Scripts\python.exe' } elseif (Test-Path 'D:\python\python.exe') { 'D:\python\python.exe' } else { 'python' }
Set-Location $ProjectDir
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Path "$ProjectDir\logs" -Force | Out-Null
$LogFile = Join-Path "$ProjectDir\logs" ("daily_"+(Get-Date -Format yyyyMMdd_HHmmss)+'.log')
$Failed = $false
Start-Transcript -Path $LogFile | Out-Null
try {
    & $Python "$ProjectDir\refresh_session.py"
    if ($LASTEXITCODE -ne 0) { throw '聚光浏览器登录检查失败，请查看日志；必要时运行 refresh_session.py --login。' }
    & $Python "$ProjectDir\daily.py"
    if ($LASTEXITCODE -ne 0) { throw '聚光同步存在失败项，请查看 logs\last_run.json。' }
} catch {
    $Failed = $true
    Write-Warning $_.Exception.Message
} finally {
    Stop-Transcript | Out-Null
}
if ($Failed) { exit 1 }
exit 0
