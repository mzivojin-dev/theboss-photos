@echo off
setlocal

if not exist ".env" (
    echo Missing .env. Copy .env.example to .env and edit its values first.
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Start Docker Desktop, then try again.
    exit /b 1
)

docker compose build app ingest
if errorlevel 1 (
    echo Docker image build failed.
    exit /b 1
)

docker compose --profile compile build compile
if errorlevel 1 (
    echo Docker image build failed.
    exit /b 1
)

echo Docker images built successfully.
exit /b 0
