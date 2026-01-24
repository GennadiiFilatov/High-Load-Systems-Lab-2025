/**
 * Lab 9&10: Load Test Script for Sync vs Async Endpoints
 * 
 * Usage:
 *   k6 run load_test.js                    # Default 40 RPS for 5 minutes
 *   k6 run --env RPS=100 load_test.js      # Custom RPS
 *   k6 run --env DURATION=10m load_test.js # Custom duration
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

// Custom metrics
const syncLatency = new Trend('sync_latency');
const asyncLatency = new Trend('async_latency');
const syncRequests = new Counter('sync_requests');
const asyncRequests = new Counter('async_requests');

// Configuration
const TOTAL_RPS = parseInt(__ENV.RPS) || 40;
const DURATION = __ENV.DURATION || '5m';
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';  // nginx load balancer

// Helper function
function rate(percentage) {
    return Math.floor(TOTAL_RPS * percentage);
}

export const options = {
    scenarios: {
        // Async endpoint - 65% of traffic
        async_endpoint: {
            exec: 'asyncEndpoint',
            executor: 'constant-arrival-rate',
            duration: DURATION,
            rate: rate(0.65),
            timeUnit: '1s',
            preAllocatedVUs: 50,
            maxVUs: 200,
        },
        // Sync endpoint - 35% of traffic
        sync_endpoint: {
            exec: 'syncEndpoint',
            executor: 'constant-arrival-rate',
            duration: DURATION,
            rate: rate(0.35),
            timeUnit: '1s',
            preAllocatedVUs: 50,
            maxVUs: 200,
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<1000'],  // 95% of requests should complete within 1s
        'async_latency': ['p(99)<100'],     // Async should be very fast
    },
};

export function asyncEndpoint() {
    const startTime = Date.now();
    const response = http.get(`${BASE_URL}/async`);
    const latency = Date.now() - startTime;
    
    asyncLatency.add(latency);
    asyncRequests.add(1);
    
    check(response, {
        'async status is 200': (r) => r.status === 200,
        'async response has status': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'accepted';
            } catch {
                return false;
            }
        },
    });
}

export function syncEndpoint() {
    const startTime = Date.now();
    const response = http.get(`${BASE_URL}/sync`);
    const latency = Date.now() - startTime;
    
    syncLatency.add(latency);
    syncRequests.add(1);
    
    check(response, {
        'sync status is 200': (r) => r.status === 200,
        'sync response has status': (r) => {
            try {
                const body = JSON.parse(r.body);
                return body.status === 'completed';
            } catch {
                return false;
            }
        },
    });
}

export function handleSummary(data) {
    console.log('\n========================================');
    console.log('       SYNC vs ASYNC COMPARISON');
    console.log('========================================\n');
    
    if (data.metrics.sync_latency && data.metrics.sync_latency.values) {
        const sync = data.metrics.sync_latency.values;
        console.log('SYNC Endpoint:');
        console.log(`  - Average Latency: ${sync.avg ? sync.avg.toFixed(2) : 'N/A'} ms`);
        console.log(`  - P90 Latency: ${sync['p(90)'] ? sync['p(90)'].toFixed(2) : 'N/A'} ms`);
        console.log(`  - P95 Latency: ${sync['p(95)'] ? sync['p(95)'].toFixed(2) : 'N/A'} ms`);
        console.log(`  - Total Requests: ${data.metrics.sync_requests ? data.metrics.sync_requests.values.count : 'N/A'}`);
    }
    
    console.log('');
    
    if (data.metrics.async_latency && data.metrics.async_latency.values) {
        const async = data.metrics.async_latency.values;
        console.log('ASYNC Endpoint:');
        console.log(`  - Average Latency: ${async.avg ? async.avg.toFixed(2) : 'N/A'} ms`);
        console.log(`  - P90 Latency: ${async['p(90)'] ? async['p(90)'].toFixed(2) : 'N/A'} ms`);
        console.log(`  - P95 Latency: ${async['p(95)'] ? async['p(95)'].toFixed(2) : 'N/A'} ms`);
        console.log(`  - Total Requests: ${data.metrics.async_requests ? data.metrics.async_requests.values.count : 'N/A'}`);
    }
    
    console.log('\n========================================');
    console.log('  Async should be faster than Sync!');
    console.log('  Check Grafana for Kafka lag metrics.');
    console.log('========================================\n');
    
    return {
        'stdout': '',
        'summary.json': JSON.stringify(data, null, 2),
    };
}
