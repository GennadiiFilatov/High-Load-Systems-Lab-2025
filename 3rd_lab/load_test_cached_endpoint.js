import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const cachedResponseTime = new Trend('cached_response_time');

export const options = {
  stages: [
    { duration: '1m', target: 50 },
    { duration: '3m', target: 100 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 50 },
    { duration: '1m', target: 0 },
  ],
  
  thresholds: {
    'http_req_duration': [
      'p(50)<100',    // Cached should be much faster
      'p(95)<200',
      'p(99)<500',
    ],
    'http_req_failed': ['rate<0.1'],
  },
};

export default function () {
  group('Cached Access (CACHE-ASIDE PATTERN)', function () {
    const res = http.get('http://localhost/api/products/cached');
    
    check(res, {
      'status 200': (r) => r.status === 200,
      'response time < 100ms': (r) => r.timings.duration < 100,
      'has products': (r) => r.body.includes('products'),
      'source is database or cache': (r) => 
        r.body.includes('database') || r.body.includes('cache'),
    });
    
    duration.add(res.timings.duration);
    cachedResponseTime.add(res.timings.duration);
    
    if (res.status === 200) {
      successCount.add(1);
    } else {
      errorRate.add(1);
    }
  });
  
  sleep(0.1);
}