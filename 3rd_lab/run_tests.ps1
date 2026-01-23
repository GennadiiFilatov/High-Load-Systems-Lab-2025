# ============================================
# HAHL Labs 5-6: Quick Test Runner (PowerShell)
# Run from: d:\Projects\High-Load-Systems-Lab-2025\3rd_lab
# ============================================

param(
    [Parameter(Position=0)]
    [ValidateSet("db", "cached", "herd", "herd2", "ttl", "start", "stop", "logs", "health", "help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Continue"

function Show-Help {
    Write-Host ""
    Write-Host "==================================================="  -ForegroundColor Cyan
    Write-Host "   HAHL Labs 5-6: Load Testing Suite"               -ForegroundColor Cyan
    Write-Host "==================================================="  -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\run_tests.ps1 <command>" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Green
    Write-Host "  db      - Run Test 1: Database Direct (No Cache)"
    Write-Host "  cached  - Run Test 2: Cache-Aside Pattern"
    Write-Host "  herd    - Run Test 3: Thundering Herd (Original)"
    Write-Host "  herd2   - Run Test 3b: Thundering Herd (Improved)"
    Write-Host "  ttl     - Run Test 4: TTL Simulation (30s)"
    Write-Host "  start   - Start Docker services"
    Write-Host "  stop    - Stop Docker services"
    Write-Host "  logs    - View container logs"
    Write-Host "  health  - Check service health"
    Write-Host "  help    - Show this help"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\run_tests.ps1 start   # Start all services"
    Write-Host "  .\run_tests.ps1 db      # Run DB direct test"
    Write-Host "  .\run_tests.ps1 cached  # Run cache-aside test"
    Write-Host ""
    Write-Host "URLs:" -ForegroundColor Green
    Write-Host "  Application: http://localhost/"
    Write-Host "  Grafana:     http://localhost:3000 (admin/admin123)"
    Write-Host "  Prometheus:  http://localhost:9090"
    Write-Host "  cAdvisor:    http://localhost:8080"
    Write-Host ""
}

function Start-Services {
    Write-Host "Starting Docker services..." -ForegroundColor Green
    docker-compose -f docker-compose-caching.yml up --build -d
    
    Write-Host ""
    Write-Host "Waiting for services to start (30 seconds)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    
    Write-Host ""
    docker-compose -f docker-compose-caching.yml ps
    
    Write-Host ""
    Write-Host "Services started! Opening Grafana..." -ForegroundColor Green
    Start-Process "http://localhost:3000"
}

function Stop-Services {
    Write-Host "Stopping Docker services..." -ForegroundColor Yellow
    docker-compose -f docker-compose-caching.yml down
    Write-Host "Services stopped." -ForegroundColor Green
}

function Show-Logs {
    Write-Host "Showing container logs (Ctrl+C to exit)..." -ForegroundColor Yellow
    docker-compose -f docker-compose-caching.yml logs -f --tail=100
}

function Check-Health {
    Write-Host ""
    Write-Host "=== Container Status ===" -ForegroundColor Cyan
    docker-compose -f docker-compose-caching.yml ps
    
    Write-Host ""
    Write-Host "=== Application Health ===" -ForegroundColor Cyan
    try {
        $response = Invoke-RestMethod -Uri "http://localhost/" -TimeoutSec 5
        Write-Host "Application: OK - $($response.message)" -ForegroundColor Green
    } catch {
        Write-Host "Application: FAILED - $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "=== Redis Health ===" -ForegroundColor Cyan
    $redisPing = docker exec redis-cache redis-cli PING 2>&1
    if ($redisPing -eq "PONG") {
        Write-Host "Redis: OK - PONG" -ForegroundColor Green
    } else {
        Write-Host "Redis: FAILED - $redisPing" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "=== PostgreSQL Health ===" -ForegroundColor Cyan
    $pgReady = docker exec postgres-db pg_isready -U postgres 2>&1
    Write-Host "PostgreSQL: $pgReady"
    
    Write-Host ""
    Write-Host "=== Database Row Counts ===" -ForegroundColor Cyan
    docker exec postgres-db psql -U postgres -d hahl_lab -c "SELECT 'products' as table_name, COUNT(*) FROM products UNION ALL SELECT 'userprofiles', COUNT(*) FROM userprofiles;"
    
    Write-Host ""
}

function Run-Test {
    param([string]$TestFile, [string]$TestName)
    
    Write-Host ""
    Write-Host "Running: $TestName" -ForegroundColor Cyan
    Write-Host "Test file: $TestFile" -ForegroundColor Gray
    Write-Host ""
    
    # Check if k6 is installed
    if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: k6 is not installed!" -ForegroundColor Red
        Write-Host "Install it from: https://k6.io/docs/getting-started/installation/" -ForegroundColor Yellow
        Write-Host "Or use: choco install k6" -ForegroundColor Yellow
        return
    }
    
    k6 run $TestFile
    
    Write-Host ""
    Write-Host "Test completed! Check Grafana at http://localhost:3000" -ForegroundColor Green
}

# Main switch
switch ($Command) {
    "db"     { Run-Test "load_test_db_endpoint.js" "Test 1: Database Direct (No Cache)" }
    "cached" { Run-Test "load_test_cached_endpoint.js" "Test 2: Cache-Aside Pattern" }
    "herd"   { Run-Test "load_test_thundering_herd.js" "Test 3: Thundering Herd (Original)" }
    "herd2"  { Run-Test "load_test_thundering_herd_v2.js" "Test 3b: Thundering Herd (Improved)" }
    "ttl"    { Run-Test "load_test_with_ttl.js" "Test 4: TTL Simulation (30s)" }
    "start"  { Start-Services }
    "stop"   { Stop-Services }
    "logs"   { Show-Logs }
    "health" { Check-Health }
    "help"   { Show-Help }
    default  { Show-Help }
}
