# 🚀 Complete Lab 5-6 Guide: Redis Caching & High-Load Testing

## 📋 Prerequisites

Make sure you have installed:
- **Docker Desktop for Windows** (with WSL 2 backend)
- **k6** for load testing: https://k6.io/docs/getting-started/installation/
- **Git** (optional, for version control)

```powershell
# Install k6 on Windows using Chocolatey
choco install k6

# Or download from: https://dl.k6.io/msi/k6-latest-amd64.msi
```

---

## 📂 Project Structure

Your `3rd_lab` folder should have:

```
3rd_lab/
├── app.py                          # Main Flask app (unoptimized)
├── optimized_app.py                # Flask app with request coalescing
├── docker-compose-caching.yml      # Main compose file
├── Dockerfile
├── nginx.conf
├── prometheus.yml
├── requirements.txt
├── alert_rules_caching.yml
├── load_test_db_endpoint.js        # Test 1: DB direct
├── load_test_cached_endpoint.js    # Test 2: Cache-aside
├── load_test_thundering_herd.js    # Test 3: Thundering herd
├── load_test_thundering_herd_v2.js # Test 3: Improved version
├── load_test_with_ttl.js           # Test 4: TTL simulation
└── grafana/
    └── provisioning/
        ├── dashboards/
        │   ├── dashboard.yml
        │   └── monitoring-dashboard.json
        └── datasources/
            └── prometheus.yml
```

---

## 🔧 Step 1: Verify Docker Compose Configuration

Your `docker-compose-caching.yml` already includes all required services:

| Service | Purpose | Port |
|---------|---------|------|
| `postgres` | PostgreSQL 15 database | 5432 |
| `redis` | Redis 7 cache | 6379 |
| `postgres-exporter` | PostgreSQL metrics for Prometheus | 9187 |
| `cadvisor` | Container CPU/memory metrics | 8080 |
| `nginx` | Load balancer | 80 |
| `app-instance-1..4` | Flask application instances | internal |
| `prometheus` | Metrics collection | 9090 |
| `grafana` | Visualization | 3000 |

---

## 🚀 Step 2: Start All Services

```powershell
# Navigate to the lab folder
cd d:\Projects\High-Load-Systems-Lab-2025\3rd_lab

# Build and start all containers
docker-compose -f docker-compose-caching.yml up --build -d

# Wait for all services to be healthy (~30-60 seconds)
docker-compose -f docker-compose-caching.yml ps

# Check logs if needed
docker-compose -f docker-compose-caching.yml logs -f
```

### Verify Services Are Running

Open in browser:
- **Application:** http://localhost/ → Should show `{"message": "Service running", "status": "OK"}`
- **Grafana:** http://localhost:3000 → Login: `admin` / `admin123`
- **Prometheus:** http://localhost:9090 → Check targets are UP
- **cAdvisor:** http://localhost:8080 → Container metrics

---

## 🗃️ Step 3: Verify Database Initialization

The database is automatically initialized with test data when the app starts.

```powershell
# Connect to PostgreSQL and verify data
docker exec -it postgres-db psql -U postgres -d hahl_lab -c "SELECT COUNT(*) FROM products;"
# Should show: 1000 rows

docker exec -it postgres-db psql -U postgres -d hahl_lab -c "SELECT COUNT(*) FROM userprofiles;"
# Should show: 500 rows
```

---

## 📊 Step 4: Open Grafana Dashboard

1. Go to http://localhost:3000
2. Login: `admin` / `admin123`
3. Navigate to **Dashboards** → **Browse**
4. Open **"HAHL Labs 5-6: Complete Caching Performance Analysis"**

If the dashboard doesn't appear automatically:
1. Go to **Dashboards** → **Import**
2. Upload the file: `grafana/provisioning/dashboards/monitoring-dashboard.json`

---

## 🧪 Step 5: Run Load Tests

### Test 1: Database Direct Access (No Cache)

This test shows baseline performance when hitting the database directly.

```powershell
cd d:\Projects\High-Load-Systems-Lab-2025\3rd_lab
k6 run load_test_db_endpoint.js
```

**What to observe in Grafana:**
- High latency (P95 > 100ms)
- Database CPU spike
- Every request hits PostgreSQL

**Expected Results:**
- P50 latency: 50-200ms
- P95 latency: 200-500ms
- High PostgreSQL CPU usage

---

### Test 2: Cache-Aside Pattern

This test shows improved performance with Redis caching.

```powershell
k6 run load_test_cached_endpoint.js
```

**What to observe in Grafana:**
- Much lower latency after cache warm-up
- Redis serving most requests
- Minimal database load

**Expected Results:**
- P50 latency: 5-20ms (10x faster!)
- P95 latency: 50-100ms
- Low PostgreSQL CPU
- High cache hit rate (>99%)

---

### Test 3: Thundering Herd Problem

This test demonstrates what happens when cache is invalidated under high load.

```powershell
# Use the improved version
k6 run load_test_thundering_herd_v2.js
```

**What to observe in Grafana:**
- Latency SPIKE at invalidation moments
- Database CPU spike to 100%
- Multiple simultaneous DB queries
- Possible timeouts/errors

**Expected Results:**
- P95 spike to 2000-5000ms during invalidation
- DB queries/sec jump from 0 to 100+
- Error rate may increase temporarily
- Active requests pile up

**Analysis for Report:**
> The thundering herd occurs because when cache expires, ALL concurrent requests simultaneously become cache misses. Each request tries to query the database and write to cache, causing:
> 1. Database connection pool exhaustion
> 2. Increased query latency due to load
> 3. Request timeouts and errors
> 4. Cascading failures

---

### Test 4: TTL Configuration (30-second expiration)

This test simulates periodic cache expiration with TTL=30s.

```powershell
k6 run load_test_with_ttl.js
```

**What to observe in Grafana:**
- "Sawtooth" pattern in latency graph
- Periodic spikes every 30 seconds
- DB queries spike periodically

**Expected Results:**
- Regular latency spikes every 30 seconds
- Pattern repeats throughout the test
- Each spike is a mini "thundering herd"

**Analysis for Report:**
> With a short TTL (30 seconds), we see periodic latency spikes because:
> 1. Cache expires → all requests miss
> 2. Multiple requests hit database simultaneously
> 3. Cache repopulates → low latency until next expiration
> This creates a predictable "sawtooth" pattern.

---

## 🔧 Step 6: Fix Thundering Herd with Request Coalescing

Now let's use the optimized application with request coalescing.

### Update Dockerfile to Use Optimized App

```powershell
# Edit Dockerfile to use optimized_app.py
# Change: COPY app.py .
# To:     COPY optimized_app.py ./app.py
```

Or run this command:
```powershell
# Stop current containers
docker-compose -f docker-compose-caching.yml down

# Modify Dockerfile
(Get-Content Dockerfile) -replace 'COPY app.py .', 'COPY optimized_app.py ./app.py' | Set-Content Dockerfile

# Rebuild and restart
docker-compose -f docker-compose-caching.yml up --build -d
```

### Run Thundering Herd Test Again

```powershell
k6 run load_test_thundering_herd_v2.js
```

**What to observe (OPTIMIZED):**
- Much smaller latency spikes
- Only 1 DB query per cache miss (not 100+)
- No error rate increase
- Stable throughput

**Expected Results:**
- P95 spike reduced from 5000ms to 500ms
- DB queries stay low (coalesced)
- Error rate ~0%

**Analysis for Report:**
> Request coalescing (also known as "single-flight") prevents thundering herd by:
> 1. First request acquires a lock and fetches from DB
> 2. Other concurrent requests WAIT for the first one
> 3. First request populates cache
> 4. Waiting requests read from cache
> 
> Result: Only 1 DB query instead of 100+, dramatically reducing load spikes.

---

## 📝 Step 7: Additional Experiments (Task 9 - Discovery)

### Experiment A: Compare Different TTL Values

```powershell
# Change TTL in docker-compose-caching.yml
# CACHE_TTL=30 (short) vs CACHE_TTL=300 (long)
```

### Experiment B: Connection Pool Size

Modify `app.py` to use connection pooling:

```python
from psycopg2 import pool

connection_pool = pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=20,
    dsn=DATABASE_URL
)
```

### Experiment C: Redis Memory Analysis

```powershell
# Check Redis memory usage
docker exec -it redis-cache redis-cli INFO memory

# Monitor Redis in real-time
docker exec -it redis-cache redis-cli MONITOR
```

### Experiment D: PostgreSQL Query Analysis

```powershell
# Enable slow query log
docker exec -it postgres-db psql -U postgres -d hahl_lab -c "
ALTER SYSTEM SET log_min_duration_statement = 100;
SELECT pg_reload_conf();
"

# View slow queries
docker logs postgres-db 2>&1 | grep "duration"
```

---

## 📊 Step 8: Collect Screenshots for Report

Take screenshots of Grafana dashboard during each test:

1. **Test 1 (DB Direct):** High latency baseline
2. **Test 2 (Cache-Aside):** Low latency with caching
3. **Test 3 (Thundering Herd):** Latency spike during invalidation
4. **Test 4 (TTL):** Sawtooth pattern
5. **Test 5 (Optimized):** Flat latency even during invalidation

Key metrics to capture:
- Request Latency (P50, P95, P99)
- Throughput (RPS)
- Database Query Rate
- Cache Hit/Miss Ratio
- Container CPU Usage
- Error Rate

---

## 📄 Step 9: Create Google Doc Report

Structure your report like this:

### Report Template

```
HAHL Labs 5-6: Redis Caching Performance Analysis
=================================================

1. Introduction
   - Lab objectives
   - Environment setup (Windows 11, Docker, etc.)

2. Architecture Overview
   - Diagram showing: Nginx → Flask Apps → Redis/PostgreSQL
   - Docker services configuration

3. Experiment 1: Database Direct Access
   - Test configuration
   - Results (screenshots)
   - Analysis

4. Experiment 2: Cache-Aside Pattern
   - Implementation details
   - Results comparison with Exp 1
   - Cache hit rate analysis

5. Experiment 3: Thundering Herd Problem
   - Problem description
   - Test results (latency spike screenshots)
   - Impact analysis

6. Experiment 4: TTL Configuration
   - TTL=30s test results
   - Sawtooth pattern analysis
   - Optimal TTL recommendations

7. Experiment 5: Request Coalescing Solution
   - Implementation code
   - Before/After comparison
   - Performance improvement metrics

8. Additional Discovery (Optional)
   - Connection pooling
   - Redis memory optimization
   - etc.

9. Conclusions
   - Key learnings
   - Best practices for caching

10. References
    - https://github.com/AnnaNik334743/hahl2025
```

---

## 🛑 Step 10: Cleanup

```powershell
# Stop all containers
docker-compose -f docker-compose-caching.yml down

# Remove volumes (optional - deletes all data)
docker-compose -f docker-compose-caching.yml down -v

# Clean up Docker resources
docker system prune -f
```

---

## 📧 Step 11: Submit Report

1. Make your Google Doc accessible with comments enabled
2. Send email to: `davladimirov@itmo.ru`
3. Subject: `HAHL2025_<YOUR SURNAME YOUR NAME>_LAB0506`

---

## ❓ Troubleshooting

### cAdvisor Not Working on Windows

cAdvisor has limited Windows support. You may see errors. Options:
1. Use WSL 2 to run Docker (recommended)
2. Skip cAdvisor metrics
3. Use Docker Desktop's built-in resource monitoring

### Connection Errors

```powershell
# Restart services
docker-compose -f docker-compose-caching.yml restart

# Check container logs
docker logs flask-app-1 --tail 100
```

### Redis Connection Failed

```powershell
# Test Redis connectivity
docker exec -it redis-cache redis-cli PING
# Should return: PONG
```

### k6 Not Found

```powershell
# Verify k6 installation
k6 version

# If not installed, use Docker alternative:
docker run -i loadimpact/k6 run - < load_test_cached_endpoint.js
```

---

## 📚 Key Concepts Summary

| Concept | Description |
|---------|-------------|
| **Cache-Aside** | App checks cache first, fetches from DB on miss, stores in cache |
| **TTL (Time-To-Live)** | Cache expiration time; too short = frequent DB hits; too long = stale data |
| **Thundering Herd** | All requests hit DB simultaneously when cache expires |
| **Request Coalescing** | Only one request fetches from DB, others wait for cache |
| **cAdvisor** | Container metrics (CPU, memory, network) |
| **Prometheus** | Time-series database for metrics |

---

Good luck with your lab! 🎓
