$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

& .\tools\start-stack.ps1
Write-Host "Starting exporter in this terminal. Ctrl+C stops only the exporter; Docker services keep running." -ForegroundColor Yellow
& .\tools\start-exporter.ps1
