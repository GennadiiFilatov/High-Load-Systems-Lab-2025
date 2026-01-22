from flask import Flask, jsonify, request, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import json
import os
import logging
import threading

app = Flask(__name__)

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@postgres:5432/hahl_lab')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CACHE_TTL = int(os.getenv('CACHE_TTL', 30))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis Connection
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Redis connected successfully")
except Exception as e:
    logger.error(f"Redis connection failed: {e}")
    redis_client = None

# Request coalescing: lock per cache key
request_locks = {}
lock_manager_lock = threading.Lock()

def get_key_lock(cache_key):
    """Get or create a lock for a cache key (thread-safe)"""
    with lock_manager_lock:
        if cache_key not in request_locks:
            request_locks[cache_key] = threading.Lock()
        return request_locks[cache_key]

# PostgreSQL Connection
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', 
                       ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', 
                           ['method', 'endpoint'])
ACTIVE_REQUESTS = Gauge('http_requests_active', 'Active HTTP requests', 
                       ['method', 'endpoint'])

# Cache-specific metrics
CACHE_HITS = Counter('cache_hits_total', 'Total cache hits', ['endpoint'])
CACHE_MISSES = Counter('cache_misses_total', 'Total cache misses', ['endpoint'])
CACHE_WAITS = Counter('cache_waits_total', 'Requests waiting for cache population', ['endpoint'])
DB_QUERY_TIME = Histogram('db_query_duration_seconds', 'Database query latency', 
                         ['query_type', 'endpoint'])
DB_QUERY_COUNT = Counter('db_queries_total', 'Total database queries', 
                        ['query_type', 'endpoint'])

def track_metrics(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        method = request.method
        endpoint = request.path
        ACTIVE_REQUESTS.labels(method=method, endpoint=endpoint).inc()
        start = time.time()
        status = 500
        
        try:
            response = f(*args, **kwargs)
            if isinstance(response, tuple):
                if len(response) >= 2:
                    status = response[1]
                else:
                    status = 200
            else:
                status = getattr(response, "status_code", 200)
            return response
        except Exception as e:
            status = 500
            logger.error(f"Error in {endpoint}: {e}")
            raise
        finally:
            duration = time.time() - start
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
            ACTIVE_REQUESTS.labels(method=method, endpoint=endpoint).dec()
    
    return decorated_function

def cache_aside_with_coalescing(cache_key, ttl=CACHE_TTL):
    """
    Cache-aside pattern with REQUEST COALESCING to prevent thundering herd
    
    Ensures only one request queries the database for a cache key,
    while other concurrent requests wait for the cache to be populated.
    
    This dramatically reduces database load when cache expires.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            endpoint = request.path
            
            # STEP 1: Try to get from cache (fast path)
            if redis_client:
                try:
                    cached_value = redis_client.get(cache_key)
                    if cached_value:
                        CACHE_HITS.labels(endpoint=endpoint).inc()
                        logger.info(f"Cache HIT for {cache_key}")
                        return json.loads(cached_value), 200
                except Exception as e:
                    logger.warning(f"Cache read error: {e}")
            
            # STEP 2: Cache MISS - Use request coalescing
            CACHE_MISSES.labels(endpoint=endpoint).inc()
            logger.info(f"Cache MISS for {cache_key}")
            
            # Get lock for this specific key
            key_lock = get_key_lock(cache_key)
            
            # STEP 3: Try to acquire lock
            acquired = key_lock.acquire(blocking=False)
            
            if acquired:
                # This request will populate the cache
                logger.info(f"Request acquired lock for {cache_key}, fetching from database")
                try:
                    result = f(*args, **kwargs)
                    
                    # Store in cache only if successful
                    if redis_client and isinstance(result, tuple) and result[1] == 200:
                        try:
                            redis_client.setex(cache_key, ttl, json.dumps(result[0]))
                            logger.info(f"Cached {cache_key} for {ttl}s")
                        except Exception as e:
                            logger.warning(f"Cache write error: {e}")
                    
                    return result
                finally:
                    key_lock.release()
            else:
                # Other requests wait for cache to be populated
                CACHE_WAITS.labels(endpoint=endpoint).inc()
                logger.info(f"Request waiting for {cache_key} to be cached")
                
                # Wait for other request to populate cache
                with key_lock:
                    logger.info(f"Lock released for {cache_key}, checking cache")
                    
                    # Check cache again (double-check pattern)
                    if redis_client:
                        try:
                            cached_value = redis_client.get(cache_key)
                            if cached_value:
                                CACHE_HITS.labels(endpoint=endpoint).inc()
                                logger.info(f"Got {cache_key} from cache after waiting")
                                return json.loads(cached_value), 200
                        except Exception as e:
                            logger.warning(f"Cache read after wait failed: {e}")
                    
                    # Cache still missing - fetch from DB
                    logger.warning(f"Cache still missing for {cache_key}, fetching directly")
                    return f(*args, **kwargs)
        
        return wrapper
    return decorator

def init_database():
    """Initialize database with test data"""
    conn = get_db_connection()
    if not conn:
        logger.error("Cannot initialize database: no connection")
        return
    
    try:
        cursor = conn.cursor()
        
        # Create products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                price DECIMAL(10, 2),
                stock INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create user_profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255),
                profile_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Check if data already exists
        cursor.execute("SELECT COUNT(*) FROM products")
        if cursor.fetchone()[0] == 0:
            logger.info("Inserting sample products...")
            products_data = [(
                f"Product {i}",
                f"Description for product {i}: High-quality item suitable for various applications",
                round(random.uniform(10, 1000), 2),
                random.randint(10, 1000)
            ) for i in range(1, 1001)]
            
            cursor.executemany("""
                INSERT INTO products (name, description, price, stock)
                VALUES (%s, %s, %s, %s)
            """, products_data)
            
        cursor.execute("SELECT COUNT(*) FROM user_profiles")
        if cursor.fetchone()[0] == 0:
            logger.info("Inserting sample user profiles...")
            users_data = [(
                f"user_{i}",
                f"user_{i}@example.com",
                json.dumps({"age": random.randint(18, 80), "country": "RU"})
            ) for i in range(1, 501)]
            
            cursor.executemany("""
                INSERT INTO user_profiles (username, email, profile_data)
                VALUES (%s, %s, %s)
            """, users_data)
        
        conn.commit()
        logger.info("Database initialization completed")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        conn.rollback()
    finally:
        conn.close()

@app.route('/', methods=['GET'])
@track_metrics
def health():
    return jsonify({'status': 'OK', 'message': 'Service running'}), 200

@app.route('/api/data', methods=['GET'])
@track_metrics
def data():
    time.sleep(random.uniform(0.01, 0.3))
    return jsonify({'data': [1, 2, 3]}), 200

@app.route('/api/slow', methods=['GET'])
@track_metrics
def slow():
    time.sleep(random.uniform(0.5, 2.0))
    return jsonify({'message': 'Slow response'}), 200

@app.route('/api/random_error', methods=['GET'])
@track_metrics
def random_error():
    if random.random() < 0.1:
        return jsonify({'error': 'Random error occurred'}), 500
    return jsonify({'message': 'Success'}), 200

@app.route('/api/products/db', methods=['GET'])
@track_metrics
def get_products_db():
    """Get products directly from database (no caching)"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        start = time.time()
        cursor.execute("""
            SELECT id, name, price, stock 
            FROM products 
            ORDER BY id 
            LIMIT 100
        """)
        products = cursor.fetchall()
        query_time = time.time() - start
        
        DB_QUERY_COUNT.labels(query_type='select', endpoint='/api/products/db').inc()
        DB_QUERY_TIME.labels(query_type='select', endpoint='/api/products/db').observe(query_time)
        
        logger.info(f"DB query time: {query_time:.4f}s")
        
        return jsonify({
            'products': products,
            'count': len(products),
            'source': 'database'
        }), 200
    
    except Exception as e:
        logger.error(f"Database query error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/products/cached', methods=['GET'])
@track_metrics
@cache_aside_with_coalescing(cache_key='products:all:limit100', ttl=CACHE_TTL)
def get_products_cached():
    """Get products with cache-aside pattern and request coalescing (OPTIMIZED)"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        start = time.time()
        cursor.execute("""
            SELECT id, name, price, stock 
            FROM products 
            ORDER BY id 
            LIMIT 100
        """)
        products = cursor.fetchall()
        query_time = time.time() - start
        
        DB_QUERY_COUNT.labels(query_type='select', endpoint='/api/products/cached').inc()
        DB_QUERY_TIME.labels(query_type='select', endpoint='/api/products/cached').observe(query_time)
        
        logger.info(f"DB query time: {query_time:.4f}s")
        
        return jsonify({
            'products': products,
            'count': len(products),
            'source': 'database'
        })
    
    except Exception as e:
        logger.error(f"Database query error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/users/cached', methods=['GET'])
@track_metrics
@cache_aside_with_coalescing(cache_key='users:all:limit50', ttl=CACHE_TTL)
def get_users_cached():
    """Get user profiles with cache-aside pattern and request coalescing (OPTIMIZED)"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        start = time.time()
        cursor.execute("""
            SELECT id, username, email, profile_data 
            FROM user_profiles 
            ORDER BY id 
            LIMIT 50
        """)
        users = cursor.fetchall()
        query_time = time.time() - start
        
        DB_QUERY_COUNT.labels(query_type='select', endpoint='/api/users/cached').inc()
        DB_QUERY_TIME.labels(query_type='select', endpoint='/api/users/cached').observe(query_time)
        
        logger.info(f"DB query time: {query_time:.4f}s")
        
        return jsonify({
            'users': users,
            'count': len(users),
            'source': 'database'
        })
    
    except Exception as e:
        logger.error(f"Database query error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/cache/invalidate', methods=['POST'])
def invalidate_cache():
    """Invalidate all cache keys (thundering herd simulation)"""
    if not redis_client:
        return jsonify({'error': 'Redis not available'}), 500
    
    try:
        keys_to_delete = redis_client.keys('*')
        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
            logger.warning(f"Cache invalidated: {len(keys_to_delete)} keys deleted")
            return jsonify({
                'status': 'success',
                'invalidated_keys': len(keys_to_delete)
            }), 200
        else:
            return jsonify({'status': 'success', 'invalidated_keys': 0}), 200
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/cache/stats', methods=['GET'])
def cache_stats():
    """Get cache statistics"""
    if not redis_client:
        return jsonify({'error': 'Redis not available'}), 500
    
    try:
        info = redis_client.info('memory')
        keys_count = redis_client.dbsize()
        
        return jsonify({
            'memory_used': info.get('used_memory', 0),
            'memory_peak': info.get('used_memory_peak', 0),
            'keys_count': keys_count,
            'status': 'healthy'
        }), 200
    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/metrics', methods=['GET'])
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)