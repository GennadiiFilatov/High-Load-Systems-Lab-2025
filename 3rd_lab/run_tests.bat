@echo off
REM ============================================
REM HAHL Labs 5-6: Quick Test Runner
REM Run from: d:\Projects\High-Load-Systems-Lab-2025\3rd_lab
REM ============================================

echo.
echo ===================================================
echo    HAHL Labs 5-6: Load Testing Suite
echo ===================================================
echo.
echo Choose a test to run:
echo.
echo [1] Test 1: Database Direct (No Cache)
echo [2] Test 2: Cache-Aside Pattern
echo [3] Test 3: Thundering Herd (Original)
echo [4] Test 3b: Thundering Herd (Improved)
echo [5] Test 4: TTL Simulation (30s)
echo [6] Start Docker Services
echo [7] Stop Docker Services
echo [8] View Container Logs
echo [9] Check Service Health
echo [0] Exit
echo.

set /p choice="Enter your choice: "

if "%choice%"=="1" (
    echo Running Test 1: Database Direct...
    k6 run load_test_db_endpoint.js
    goto end
)
if "%choice%"=="2" (
    echo Running Test 2: Cache-Aside...
    k6 run load_test_cached_endpoint.js
    goto end
)
if "%choice%"=="3" (
    echo Running Test 3: Thundering Herd (Original)...
    k6 run load_test_thundering_herd.js
    goto end
)
if "%choice%"=="4" (
    echo Running Test 3b: Thundering Herd (Improved)...
    k6 run load_test_thundering_herd_v2.js
    goto end
)
if "%choice%"=="5" (
    echo Running Test 4: TTL Simulation...
    k6 run load_test_with_ttl.js
    goto end
)
if "%choice%"=="6" (
    echo Starting Docker services...
    docker-compose -f docker-compose-caching.yml up --build -d
    echo.
    echo Waiting for services to start...
    timeout /t 30
    docker-compose -f docker-compose-caching.yml ps
    goto end
)
if "%choice%"=="7" (
    echo Stopping Docker services...
    docker-compose -f docker-compose-caching.yml down
    goto end
)
if "%choice%"=="8" (
    echo Showing container logs...
    docker-compose -f docker-compose-caching.yml logs -f --tail=100
    goto end
)
if "%choice%"=="9" (
    echo Checking service health...
    echo.
    echo === Container Status ===
    docker-compose -f docker-compose-caching.yml ps
    echo.
    echo === Application Health ===
    curl -s http://localhost/ | findstr /C:"OK"
    echo.
    echo === Redis Health ===
    docker exec redis-cache redis-cli PING
    echo.
    echo === PostgreSQL Health ===
    docker exec postgres-db pg_isready -U postgres
    echo.
    echo === Prometheus Targets ===
    curl -s http://localhost:9090/api/v1/targets | findstr /C:"health"
    goto end
)
if "%choice%"=="0" (
    exit /b
)

echo Invalid choice. Please try again.

:end
echo.
echo Test completed! Check Grafana at http://localhost:3000
echo.
pause
