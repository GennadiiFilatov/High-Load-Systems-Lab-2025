import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const invalidations = new Counter('cache_invalidations');

/**
 * ⏱️ TTL TEST - Simulates periodic cache expiration
 * 
 * This test shows what happens when TTL is set to 30 seconds:
 * - Cache expires every 30 seconds
 * - First request after expiration hits the database
 * - Creates periodic "sawtooth" latency pattern
 * 
 * The invalidator simulates what happens naturally with TTL
 * but allows us to control and observe it clearly.
 */
export const options = {
  scenarios: {
    // Main load - continuous requests
    main_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 100 },
        { duration: '8m', target: 100 },
        { duration: '1m', target: 0 },
      ],
      exec: 'mainTest',
    },
    
    // Invalidation every 30 sec (simulates TTL=30s)
    cache_invalidator: {
      executor: 'constant-arrival-rate',
      rate: 1,            // 1 call per timeUnit
      timeUnit: '30s',    // Every 30 seconds
      duration: '10m',    // For full test duration
      preAllocatedVUs: 1,
      exec: 'invalidateCache',
    },
  },
  
  thresholds: {
    'http_req_duration': [
      'p(50)<200',
      'p(95)<2000',
      'p(99)<5000',
    ],
    'errors': ['rate<0.05'],
  },
};

// Main load test
export function mainTest() {
  const res = http.get('http://localhost/api/products/cached');
  
  check(res, {
    'status 200': (r) => r.status === 200,
    'has data': (r) => r.body && r.body.includes('products'),
  });
  
  duration.add(res.timings.duration);
  errorRate.add(res.status !== 200 ? 1 : 0);
  if (res.status === 200) successCount.add(1);
  
  sleep(0.1);
}

// Cache invalidator - simulates TTL expiration
export function invalidateCache() {
  console.log('⏱️ [TTL SIMULATION] Cache expired - invalidating...');
  
  const res = http.post('http://localhost/cache/invalidate');
  
  check(res, {
    'invalidate success': (r) => r.status === 200,
  });
  
  if (res.status === 200) {
    invalidations.add(1);
    console.log('✅ Cache invalidated - next request will hit DB');
  }
}