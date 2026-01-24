"""
Lab 9&10: Kafka Sync/Async Endpoints
- Sync endpoint: simulates work with thread.sleep
- Async endpoint: produces message to Kafka and returns immediately
- Kafka consumer: consumes messages from the topic
"""

import os
import time
import json
import logging
import threading
import atexit
from flask import Flask, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import NoBrokersAvailable
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'async_messages')
SYNC_SLEEP_MS = int(os.getenv('SYNC_SLEEP_MS', '300'))  # milliseconds
INSTANCE_ID = os.getenv('INSTANCE_ID', 'app-1')

# Kafka clients
producer: Optional[KafkaProducer] = None
consumer: Optional[KafkaConsumer] = None
consumer_thread_running = False

# Prometheus metrics
REQUEST_COUNT = Counter(
    'app_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'app_request_latency_seconds',
    'Request latency in seconds',
    ['endpoint'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

KAFKA_MESSAGES_PRODUCED = Counter(
    'kafka_messages_produced_total',
    'Total messages produced to Kafka',
    ['topic']
)

KAFKA_MESSAGES_CONSUMED = Counter(
    'kafka_messages_consumed_total',
    'Total messages consumed from Kafka',
    ['topic', 'instance']
)

KAFKA_PRODUCER_ERRORS = Counter(
    'kafka_producer_errors_total',
    'Total Kafka producer errors'
)

KAFKA_CONSUMER_ERRORS = Counter(
    'kafka_consumer_errors_total',
    'Total Kafka consumer errors'
)

SYNC_REQUESTS_IN_PROGRESS = Gauge(
    'sync_requests_in_progress',
    'Number of sync requests currently in progress'
)

ASYNC_REQUESTS_IN_PROGRESS = Gauge(
    'async_requests_in_progress',
    'Number of async requests currently in progress'
)


def get_kafka_producer(max_retries=10, retry_delay=3):
    """Initialize Kafka producer with retry logic"""
    global producer
    if producer is not None:
        return producer
    
    retries = 0
    while retries < max_retries:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3,
                api_version=(2, 0, 2)
            )
            logger.info(f"Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
            return producer
        except NoBrokersAvailable as e:
            retries += 1
            logger.warning(f"Kafka brokers unavailable (attempt {retries}/{max_retries}): {e}")
            if retries >= max_retries:
                raise
            time.sleep(retry_delay)
        except Exception as e:
            retries += 1
            logger.error(f"Failed to create Kafka producer (attempt {retries}/{max_retries}): {e}")
            if retries >= max_retries:
                raise
            time.sleep(retry_delay)
    return None


def get_kafka_consumer(max_retries=10, retry_delay=3):
    """Initialize Kafka consumer with retry logic"""
    global consumer
    if consumer is not None:
        return consumer
    
    retries = 0
    while retries < max_retries:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                group_id='async_consumer_group',
                enable_auto_commit=False,
                auto_offset_reset='earliest',
                api_version=(2, 0, 2),
                max_poll_interval_ms=300000,
                session_timeout_ms=30000
            )
            logger.info(f"Kafka consumer connected, subscribed to topic: {KAFKA_TOPIC}")
            return consumer
        except Exception as e:
            retries += 1
            logger.error(f"Failed to create Kafka consumer (attempt {retries}/{max_retries}): {e}")
            if retries >= max_retries:
                raise
            time.sleep(retry_delay)
    return None


def consume_messages():
    """Background thread to consume Kafka messages"""
    global consumer_thread_running
    consumer_thread_running = True
    
    logger.info("Starting Kafka consumer thread...")
    
    while consumer_thread_running:
        try:
            consumer_instance = get_kafka_consumer()
            if consumer_instance is None:
                logger.error("Could not create consumer, retrying...")
                time.sleep(5)
                continue
                
            logger.info("Consumer ready, starting message consumption...")
            
            for message in consumer_instance:
                if not consumer_thread_running:
                    break
                
                try:
                    # Process message (simulate some work)
                    msg_value = message.value
                    logger.info(f"[{INSTANCE_ID}] Consumed message: {msg_value}")
                    
                    # Simulate message processing time
                    time.sleep(0.05)  # 50ms processing per message
                    
                    # Update metrics
                    KAFKA_MESSAGES_CONSUMED.labels(
                        topic=message.topic,
                        instance=INSTANCE_ID
                    ).inc()
                    
                    # Commit offset
                    consumer_instance.commit()
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    KAFKA_CONSUMER_ERRORS.inc()
                    
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            KAFKA_CONSUMER_ERRORS.inc()
            time.sleep(5)
    
    logger.info("Consumer thread stopped")


def shutdown_consumer():
    """Gracefully shutdown Kafka clients"""
    global consumer, producer, consumer_thread_running
    consumer_thread_running = False
    
    if consumer:
        try:
            consumer.close()
            logger.info("Kafka consumer closed")
        except Exception as e:
            logger.error(f"Error closing consumer: {e}")
        finally:
            consumer = None
    
    if producer:
        try:
            producer.close()
            logger.info("Kafka producer closed")
        except Exception as e:
            logger.error(f"Error closing producer: {e}")
        finally:
            producer = None


@app.route('/health')
def health():
    """Health check endpoint"""
    kafka_healthy = False
    try:
        if producer:
            kafka_healthy = True
    except:
        pass
    
    return jsonify({
        'status': 'ok',
        'instance': INSTANCE_ID,
        'kafka_producer': producer is not None,
        'kafka_consumer': consumer is not None
    })


@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/sync')
def sync_endpoint():
    """
    Synchronous endpoint - simulates work by sleeping.
    This endpoint blocks the thread for a configurable amount of time.
    """
    start_time = time.time()
    SYNC_REQUESTS_IN_PROGRESS.inc()
    
    try:
        # Simulate synchronous work (blocking)
        time.sleep(SYNC_SLEEP_MS / 1000.0)
        
        latency = time.time() - start_time
        REQUEST_LATENCY.labels(endpoint='/sync').observe(latency)
        REQUEST_COUNT.labels(method='GET', endpoint='/sync', status='200').inc()
        
        return jsonify({
            'status': 'completed',
            'type': 'sync',
            'processing_time_ms': SYNC_SLEEP_MS,
            'actual_latency_ms': round(latency * 1000, 2),
            'instance': INSTANCE_ID
        })
    finally:
        SYNC_REQUESTS_IN_PROGRESS.dec()


@app.route('/async')
def async_endpoint():
    """
    Asynchronous endpoint - produces message to Kafka and returns immediately.
    The actual processing is done by the consumer in the background.
    """
    start_time = time.time()
    ASYNC_REQUESTS_IN_PROGRESS.inc()
    
    try:
        kafka_producer = get_kafka_producer()
        if kafka_producer is None:
            REQUEST_COUNT.labels(method='GET', endpoint='/async', status='503').inc()
            KAFKA_PRODUCER_ERRORS.inc()
            return jsonify({
                'status': 'error',
                'message': 'Kafka producer unavailable'
            }), 503
        
        # Create message
        message = {
            'timestamp': time.time(),
            'instance': INSTANCE_ID,
            'data': f'Async message from {INSTANCE_ID}'
        }
        
        # Send to Kafka (non-blocking)
        kafka_producer.send(KAFKA_TOPIC, value=message)
        kafka_producer.flush()  # Ensure message is sent
        
        latency = time.time() - start_time
        REQUEST_LATENCY.labels(endpoint='/async').observe(latency)
        REQUEST_COUNT.labels(method='GET', endpoint='/async', status='200').inc()
        KAFKA_MESSAGES_PRODUCED.labels(topic=KAFKA_TOPIC).inc()
        
        return jsonify({
            'status': 'accepted',
            'type': 'async',
            'message': 'Message sent to Kafka',
            'actual_latency_ms': round(latency * 1000, 2),
            'instance': INSTANCE_ID
        })
        
    except Exception as e:
        logger.error(f"Error in async endpoint: {e}")
        REQUEST_COUNT.labels(method='GET', endpoint='/async', status='500').inc()
        KAFKA_PRODUCER_ERRORS.inc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        ASYNC_REQUESTS_IN_PROGRESS.dec()


@app.route('/')
def root():
    """Root endpoint with API documentation"""
    return jsonify({
        'service': 'Kafka Sync/Async Lab',
        'instance': INSTANCE_ID,
        'endpoints': {
            '/': 'This info',
            '/health': 'Health check',
            '/metrics': 'Prometheus metrics',
            '/sync': f'Synchronous endpoint (sleeps {SYNC_SLEEP_MS}ms)',
            '/async': 'Asynchronous endpoint (produces to Kafka)'
        },
        'kafka_topic': KAFKA_TOPIC
    })


# Start consumer thread when app starts
consumer_thread = threading.Thread(target=consume_messages, daemon=True)
consumer_thread.start()

# Register shutdown handler
atexit.register(shutdown_consumer)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, threaded=True)
