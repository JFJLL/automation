Set-Location (Split-Path -Parent System.Management.Automation.InvocationInfo.MyCommand.Path)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
