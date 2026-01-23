import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

/**
 * ⚡ THUNDERING HERD SIMULATION - IMPROVED VERSION
 * 
 * This test simulates a real thundering herd problem:
 * 1. Phase 1: Warm cache with normal load
 * 2. Phase 2: INVALIDATE cache and IMMEDIATELY hit with heavy load
 * 3. Phase 3: Observe recovery
 * 
 * What to observe:
 * - Latency SPIKE during invalidation moment
 * - Database CPU spike (in Grafana cAdvisor metrics)
 * - Multiple simultaneous DB queries (all cache misses)
 * - Error rate increase (timeouts, connection pool exhaustion)
 */

const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const cacheInvalidations = new Counter('cache_invalidations');

export const options = {
  scenarios: {
    // Main load - continuous requests
    main_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },    // Warm up with cache
        { duration: '2m', target: 100 },    // Normal load
        { duration: '30s', target: 200 },   // Heavy load (HERD!)
        { duration: '2m', target: 200 },    // Maintain heavy load
        { duration: '1m', target: 0 },      // Ramp down
      ],
      exec: 'mainTest',
    },
    
    // Invalidator - triggers at 2m30s (just before heavy load)
    cache_invalidator: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 5,       // 5 invalidations total
      startTime: '2m30s',  // Start just when load increases
      maxDuration: '2m',   // Over 2 minutes
      exec: 'invalidateCache',
    },
  },
  
  thresholds: {
    // We EXPECT these to be violated during thundering herd!
    'http_req_duration': [
      'p(50)<500',
      'p(95)<3000',
      'p(99)<8000',
    ],
    'errors': ['rate<0.15'],  // Allow up to 15% errors during herd
  },
};

// Main load test
export function mainTest() {
  const res = http.get('http://localhost/api/products/cached', {
    timeout: '30s',  // Longer timeout for heavy load
  });
  
  check(res, {
    'status 200': (r) => r.status === 200,
    'has products': (r) => r.body && r.body.includes('products'),
  });
  
  duration.add(res.timings.duration);
  errorRate.add(res.status !== 200 ? 1 : 0);
  if (res.status === 200) successCount.add(1);
  
  sleep(0.05);  // Very fast requests to simulate high concurrency
}

// Cache invalidator - causes thundering herd
export function invalidateCache() {
  console.log('🔥 INVALIDATING CACHE - THUNDERING HERD INCOMING!');
  
  const res = http.post('http://localhost/cache/invalidate', null, {
    timeout: '10s',
  });
  
  check(res, {
    'invalidation success': (r) => r.status === 200,
  });
  
  if (res.status === 200) {
    const body = JSON.parse(res.body);
    console.log(`✅ Cache invalidated: ${body.invalidated_keys} keys deleted`);
    cacheInvalidations.add(1);
  } else {
    console.log(`❌ Invalidation failed: ${res.status}`);
  }
  
  // Wait 20s before next invalidation
  sleep(20);
}
