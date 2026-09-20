$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if (Test-Path (Join-Path $ProjectDir '..\.venv\Scripts\python.exe')) { Join-Path $ProjectDir '..\.venv\Scripts\python.exe' } elseif (Test-Path 'D:\python\python.exe') { 'D:\python\python.exe' } else { 'python' }
Set-Location $ProjectDir
$env:PYTHONIOENCODING = 'utf-8'
& $Python "$ProjectDir\refresh_adstar_cookie.py" --reuse-session --timeout 1800
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python "$ProjectDir\sync_configured_table.py"
exit $LASTEXITCODE
