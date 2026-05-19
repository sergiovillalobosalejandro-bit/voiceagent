$root = $PSScriptRoot

$envFile = Join-Path $root "backend\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.*)") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SoundBot - Starting Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "[1/2] Starting backend on port 8000..." -ForegroundColor Yellow
$backendDir = Join-Path $root "backend"
Start-Process python -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000" -WorkingDirectory $backendDir -WindowStyle Normal
Start-Sleep 4

$healthOk = $false
try { $r = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5; $healthOk = $true } catch {}
if ($healthOk) { Write-Host "  Backend: OK - http://localhost:8000" -ForegroundColor Green }
else { Write-Host "  Backend: FAIL" -ForegroundColor Red }

Write-Host "[2/2] Starting frontend on port 5173..." -ForegroundColor Yellow
$frontendDir = Join-Path $root "frontend"
Start-Process cmd -ArgumentList "/c cd /d $frontendDir && npm run dev -- --host 0.0.0.0 --port 5173" -WindowStyle Normal
Start-Sleep 4

$frontOk = $false
try { $r = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 5; $frontOk = $true } catch {
    try { $r = Invoke-WebRequest -Uri "http://localhost:5174" -TimeoutSec 5; $frontOk = $true } catch {}
}
if ($frontOk) { Write-Host "  Frontend: OK - http://localhost:5173" -ForegroundColor Green }
else { Write-Host "  Frontend: NOT READY - check Vite window" -ForegroundColor Yellow }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Open http://localhost:5173 in browser" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
