import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');

export const options = {
  stages: [
    { duration: '30s', target: 100 },
    { duration: '2m', target: 100 },  // Normal load for 2 minutes
    { duration: '10s', target: 200 }, // Increase after invalidation
    { duration: '2m', target: 200 },  // Heavy load after invalidation
    { duration: '1m', target: 0 },    // Ramp down
  ],
  
  thresholds: {
    'http_req_duration': [
      'p(95)<3000',
    ],
  },
};

let cacheInvalidated = false;

export default function () {
  // First phase: normal cached requests
  if (__VU <= 100) {
    group('Phase 1: Normal Cached Load', function () {
      const res = http.get('http://localhost/api/products/cached');
      
      check(res, {
        'status 200': (r) => r.status === 200,
      });
      
      duration.add(res.timings.duration);
      if (res.status === 200) {
        successCount.add(1);
      } else {
        errorRate.add(1);
      }
    });
  } 
  // Second phase: invalidate cache and increase load (THUNDERING HERD)
  else if (!cacheInvalidated) {
    if (__VU === 101) {  // One VU invalidates cache
      group('Invalidating Cache', function () {
        const res = http.post('http://localhost/cache/invalidate');
        check(res, {
          'cache invalidated': (r) => r.status === 200,
        });
      });
      cacheInvalidated = true;
    }
    
    group('Phase 2: Post-Invalidation Heavy Load', function () {
      const res = http.get('http://localhost/api/products/cached');
      
      check(res, {
        'status 200': (r) => r.status === 200,
      });
      
      duration.add(res.timings.duration);
      if (res.status === 200) {
        successCount.add(1);
      } else {
        errorRate.add(1);
      }
    });
  }
  
  sleep(0.5);
}