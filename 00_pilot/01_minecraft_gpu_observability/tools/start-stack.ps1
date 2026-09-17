$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Review it if you want PresentMon or a fixed Minecraft PID." -ForegroundColor Yellow
}

docker compose up -d
Write-Host "Prometheus: http://localhost:9090" -ForegroundColor Cyan
Write-Host "Grafana:    http://localhost:3000" -ForegroundColor Cyan
