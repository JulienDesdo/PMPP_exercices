$ErrorActionPreference = "SilentlyContinue"

function Check-Cmd($name, $args) {
    Write-Host -NoNewline ("{0,-18}" -f $name)
    $cmd = Get-Command $name
    if (-not $cmd) { Write-Host "MISSING" -ForegroundColor Red; return $false }
    $out = & $name @args 2>&1 | Select-Object -First 1
    Write-Host "OK  $out" -ForegroundColor Green
    return $true
}

$ok = $true
$ok = (Check-Cmd "python" @("--version")) -and $ok
$ok = (Check-Cmd "docker" @("--version")) -and $ok
$ok = (Check-Cmd "nvidia-smi" @("--version")) -and $ok

Write-Host -NoNewline ("{0,-18}" -f "PresentMon")
$pm = Get-Command PresentMon.exe
if ($pm) {
    Write-Host "OK  $($pm.Source)" -ForegroundColor Green
} else {
    Write-Host "OPTIONAL / NOT FOUND" -ForegroundColor Yellow
    Write-Host "  FPS/frametime panels require PresentMon. GPU/system panels do not."
}

if ($ok) { exit 0 } else { exit 1 }
