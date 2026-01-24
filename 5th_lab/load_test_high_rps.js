/**
 * Lab 9&10: HIGH LOAD Test Script - Generate Kafka Lag > 1000
 * 
 * This script generates high traffic to create significant Kafka consumer lag.
 * Use this AFTER the basic test to observe lag buildup.
 * 
 * Usage:
 *   k6 run load_test_high_rps.js
 */

import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';

// Custom metrics
const asyncLatency = new Trend('async_latency');
const asyncRequests = new Counter('async_requests');

// Configuration - HIGH RPS to generate lag!
const TOTAL_RPS = parseInt(__ENV.RPS) || 500;  // 500 RPS by default
const DURATION = __ENV.DURATION || '3m';
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

export const options = {
    scenarios: {
        // Only async endpoint - to generate Kafka messages fast
        async_flood: {
            exec: 'asyncEndpoint',
            executor: 'constant-arrival-rate',
            duration: DURATION,
            rate: TOTAL_RPS,
            timeUnit: '1s',
            preAllocatedVUs: 100,
            maxVUs: 500,
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<2000'],
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
    });
}

export function handleSummary(data) {
    console.log('\n========================================');
    console.log('     HIGH LOAD TEST COMPLETE');
    console.log('========================================\n');
    
    if (data.metrics.async_latency) {
        console.log('ASYNC Endpoint (High Load):');
        console.log(`  - Average Latency: ${data.metrics.async_latency.values.avg.toFixed(2)} ms`);
        console.log(`  - P99 Latency: ${data.metrics.async_latency.values['p(99)'].toFixed(2)} ms`);
        console.log(`  - Total Requests: ${data.metrics.async_requests.values.count}`);
    }
    
    console.log('\n========================================');
    console.log('  CHECK GRAFANA NOW!');
    console.log('  Kafka lag should be > 1000 messages');
    console.log('========================================\n');
    
    return {
        'stdout': '',
        'summary_high_rps.json': JSON.stringify(data, null, 2),
    };
}
