import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const dbQueryRate = new Trend('db_query_duration');

export const options = {
  stages: [
    { duration: '1m', target: 50 },    // Ramp up to 50 VUs
    { duration: '3m', target: 100 },   // Further to 100 VUs (~500 RPS)
    { duration: '5m', target: 100 },   // Maintain for 5 minutes
    { duration: '2m', target: 50 },    // Ramp down
    { duration: '1m', target: 0 },     // Final ramp down
  ],
  
  thresholds: {
    'http_req_duration': [
      'p(50)<500',
      'p(95)<2000',
      'p(99)<5000',
    ],
    'http_req_failed': ['rate<0.1'],
  },
};

export default function () {
  group('Database Direct Access (NO CACHE)', function () {
    const res = http.get('http://localhost/api/products/db');
    
    check(res, {
      'status 200': (r) => r.status === 200,
      'response time < 500ms': (r) => r.timings.duration < 500,
      'has products': (r) => r.body.includes('products'),
    });
    
    duration.add(res.timings.duration);
    dbQueryRate.add(res.timings.duration);
    
    if (res.status === 200) {
      successCount.add(1);
    } else {
      errorRate.add(1);
    }
  });
  
  sleep(0.1);
}