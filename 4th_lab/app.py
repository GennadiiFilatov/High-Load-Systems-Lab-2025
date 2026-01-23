"""
Lab 7&8: Flask App with PostgreSQL Read/Write Routing
- Writes go to Master
- Reads can be routed to Master or Replica based on REPLICA_READ_PERCENT
"""

import os
import random
import time
import psycopg2
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# Configuration
MASTER_HOST = os.getenv('MASTER_HOST', 'pg-master')
REPLICA_HOST = os.getenv('REPLICA_HOST', 'pg-replica')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'appdb')
DB_USER = os.getenv('DB_USER', 'appuser')
DB_PASS = os.getenv('DB_PASS', 'apppass')
REPLICA_READ_PERCENT = int(os.getenv('REPLICA_READ_PERCENT', '50'))

# Prometheus metrics
REQUEST_COUNT = Counter('app_requests_total', 'Total requests', ['method', 'endpoint', 'target'])
REQUEST_LATENCY = Histogram('app_request_latency_seconds', 'Request latency', ['endpoint'])
REPLICATION_LAG = Gauge('app_replication_lag_bytes', 'Replication lag in bytes')
DB_CONNECTIONS = Gauge('app_db_connections', 'Active DB connections', ['target'])

def get_connection(target='master'):
    """Get database connection to master or replica"""
    host = MASTER_HOST if target == 'master' else REPLICA_HOST
    return psycopg2.connect(
        host=host,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=5
    )

def init_db():
    """Initialize database table"""
    for _ in range(30):
        try:
            conn = get_connection('master')
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            cur.close()
            conn.close()
            print("Database initialized")
            return
        except Exception as e:
            print(f"Waiting for database... {e}")
            time.sleep(2)

def get_replication_lag():
    """Get replication lag from master"""
    try:
        conn = get_connection('master')
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(
                pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn), 0
            ) as lag_bytes
            FROM pg_stat_replication
            LIMIT 1
        """)
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else 0
    except:
        return 0

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/metrics')
def metrics():
    # Update replication lag metric
    REPLICATION_LAG.set(get_replication_lag())
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/write', methods=['POST'])
def write():
    """Write data to master"""
    start = time.time()
    try:
        data = request.json or {}
        name = data.get('name', f'item_{random.randint(1, 10000)}')
        payload = data.get('data', 'x' * 100)
        
        conn = get_connection('master')
        cur = conn.cursor()
        cur.execute("INSERT INTO items (name, data) VALUES (%s, %s) RETURNING id", (name, payload))
        item_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        REQUEST_COUNT.labels('POST', '/write', 'master').inc()
        REQUEST_LATENCY.labels('/write').observe(time.time() - start)
        return jsonify({'id': item_id, 'target': 'master'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/read')
def read():
    """Read data - routed to master or replica based on REPLICA_READ_PERCENT"""
    start = time.time()
    target = 'replica' if random.randint(1, 100) <= REPLICA_READ_PERCENT else 'master'
    
    try:
        conn = get_connection(target)
        cur = conn.cursor()
        cur.execute("SELECT id, name, created_at FROM items ORDER BY id DESC LIMIT 10")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        REQUEST_COUNT.labels('GET', '/read', target).inc()
        REQUEST_LATENCY.labels('/read').observe(time.time() - start)
        return jsonify({
            'items': [{'id': r[0], 'name': r[1], 'created_at': str(r[2])} for r in rows],
            'target': target
        })
    except Exception as e:
        return jsonify({'error': str(e), 'target': target}), 500

@app.route('/read/master')
def read_master():
    """Force read from master"""
    start = time.time()
    try:
        conn = get_connection('master')
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM items")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        REQUEST_COUNT.labels('GET', '/read/master', 'master').inc()
        REQUEST_LATENCY.labels('/read/master').observe(time.time() - start)
        return jsonify({'count': count, 'target': 'master'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/read/replica')
def read_replica():
    """Force read from replica"""
    start = time.time()
    try:
        conn = get_connection('replica')
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM items")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        REQUEST_COUNT.labels('GET', '/read/replica', 'replica').inc()
        REQUEST_LATENCY.labels('/read/replica').observe(time.time() - start)
        return jsonify({'count': count, 'target': 'replica'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bulk-insert', methods=['POST'])
def bulk_insert():
    """Big Boom! Insert large amount of data to create replication lag"""
    start = time.time()
    data = request.json or {}
    count = data.get('count', 1000)
    size = data.get('size', 1000)  # bytes per record
    
    try:
        conn = get_connection('master')
        cur = conn.cursor()
        
        payload = 'X' * size
        for i in range(count):
            cur.execute("INSERT INTO items (name, data) VALUES (%s, %s)", 
                       (f'bulk_{i}', payload))
        
        conn.commit()
        cur.close()
        conn.close()
        
        elapsed = time.time() - start
        REQUEST_COUNT.labels('POST', '/bulk-insert', 'master').inc()
        return jsonify({
            'inserted': count,
            'size_per_record': size,
            'total_bytes': count * size,
            'elapsed_seconds': elapsed,
            'target': 'master'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/replication-lag')
def replication_lag():
    """Get current replication lag"""
    lag = get_replication_lag()
    return jsonify({'lag_bytes': lag})

@app.route('/set-replica-percent/<int:percent>')
def set_replica_percent(percent):
    """Dynamically change replica read percentage"""
    global REPLICA_READ_PERCENT
    REPLICA_READ_PERCENT = max(0, min(100, percent))
    return jsonify({'replica_read_percent': REPLICA_READ_PERCENT})

@app.route('/')
def index():
    return jsonify({
        'endpoints': {
            'POST /write': 'Write to master',
            'GET /read': f'Read (auto-route, {REPLICA_READ_PERCENT}% to replica)',
            'GET /read/master': 'Force read from master',
            'GET /read/replica': 'Force read from replica',
            'POST /bulk-insert': 'Bulk insert (creates replication lag)',
            'GET /replication-lag': 'Get current replication lag',
            'GET /set-replica-percent/<int>': 'Change replica read %',
            'GET /metrics': 'Prometheus metrics'
        }
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8000, debug=False)
