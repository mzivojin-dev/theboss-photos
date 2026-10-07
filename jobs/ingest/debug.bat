@echo off
setlocal

set "REPO_ROOT=%~dp0..\.."
set "INGEST_DIR=%~dp0"
set "ENV_FILE=%REPO_ROOT%\.env"

if not exist "%ENV_FILE%" (
    echo Missing %ENV_FILE%
    echo Create the repository .env file before starting the ingestion debugger.
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$root = '%REPO_ROOT%';" ^
  "$envFile = Join-Path $root '.env';" ^
  "Get-Content -LiteralPath $envFile | ForEach-Object {" ^
  "  if ($_ -match '^\s*([^#][^=]*)=(.*)$') {" ^
  "    $name = $matches[1].Trim();" ^
  "    $value = $matches[2].Trim();" ^
  "    if ($value.Length -ge 2 -and (($value[0] -eq [char]34 -and $value[-1] -eq [char]34) -or ($value[0] -eq [char]39 -and $value[-1] -eq [char]39))) { $value = $value.Substring(1, $value.Length - 2) }" ^
  "    [Environment]::SetEnvironmentVariable($name, $value, 'Process')" ^
  "  }" ^
  "};" ^
  "$required = 'GCP_PROJECT_ID', 'PREVIEWS_BUCKET', 'ORIGINALS_BUCKET', 'DRIVE_FOLDER_ID';" ^
  "foreach ($name in $required) { if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) { throw ('Missing ' + $name + ' in ' + $envFile) } };" ^
  "$env:GOOGLE_APPLICATION_CREDENTIALS = Join-Path $env:APPDATA 'gcloud\application_default_credentials.json';" ^
  "if (-not (Test-Path -LiteralPath $env:GOOGLE_APPLICATION_CREDENTIALS -PathType Leaf)) { throw ('ADC credentials file not found: ' + $env:GOOGLE_APPLICATION_CREDENTIALS) };" ^
  "$env:DELETE_PROCESSED_DRIVE_FILES = 'false';" ^
  "Set-Location '%INGEST_DIR%';" ^
  "python -m pip show debugpy >$null 2>$null;" ^
  "if ($LASTEXITCODE -ne 0) { throw 'debugpy is not installed. Run: python -m pip install -r requirements-dev.txt' };" ^
  "Write-Host 'Waiting for VS Code debugger to attach on 127.0.0.1:5678...';" ^
  "python -m debugpy --listen 127.0.0.1:5678 --wait-for-client -m src.main;"

exit /b %ERRORLEVEL%
