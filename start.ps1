# FinBot — Start all services locally (backend, frontend, MCP bridge)
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FinBot — Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Backend
Write-Host "[1/3] Starting backend (port 8000)..." -ForegroundColor Yellow
Start-Process -FilePath python -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000 --reload" -WorkingDirectory "$root\backend" -NoNewWindow
Start-Sleep -Seconds 2

$health = try { Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 3 } catch { $null }
if ($health.status -eq "ok") {
    Write-Host "  Backend running: http://localhost:8000" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Backend may not be ready yet." -ForegroundColor Red
}

# MCP Bridge
Write-Host "[2/3] Starting n8n MCP Bridge (port 5679)..." -ForegroundColor Yellow
Start-Process -FilePath python -ArgumentList "server.py" -WorkingDirectory "$root\n8n-mcp-bridge" -NoNewWindow
Start-Sleep -Seconds 2
Write-Host "  MCP Bridge: http://localhost:5679/sse" -ForegroundColor Green

# Frontend
Write-Host "[3/3] Starting frontend (port 5173)..." -ForegroundColor Yellow
Start-Process -FilePath npm -ArgumentList "run dev -- --host 0.0.0.0 --port 5173" -WorkingDirectory "$root\frontend" -NoNewWindow
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FinBot is running!" -ForegroundColor Green
Write-Host "  Frontend:   http://localhost:5173" -ForegroundColor Green
Write-Host "  Backend:    http://localhost:8000" -ForegroundColor Green
Write-Host "  API Docs:   http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  MCP Bridge: http://localhost:5679/sse" -ForegroundColor Green
Write-Host "  n8n:        http://localhost:5678" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "n8n Webhooks: configure ngrok URL in N8N_WEBHOOK_URL if needed" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop all services..." -ForegroundColor Gray
