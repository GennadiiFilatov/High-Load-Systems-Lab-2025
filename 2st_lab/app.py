# Flask Service - Minimal Version (if above is too complex)

from flask import Flask, jsonify, request, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
import random

app = Flask(__name__)

# METRICS
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])
ACTIVE_REQUESTS = Gauge('http_requests_active', 'Active HTTP requests', ['method', 'endpoint'])

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
        except Exception:
            status = 500
            raise
        finally:
            duration = time.time() - start
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status=str(status)
            ).inc()
            REQUEST_LATENCY.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            ACTIVE_REQUESTS.labels(
                method=method,
                endpoint=endpoint
            ).dec()
    return decorated_function

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

@app.route('/metrics', methods=['GET'])
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route('/api/random_error', methods=['GET'])
@track_metrics
def random_error():
    if random.random() < 0.1:
        return jsonify({'error': 'Random error occurred'}), 500
    return jsonify({'message': 'Success'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
