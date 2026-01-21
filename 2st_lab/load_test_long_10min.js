import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const activeVUsers = new Gauge('active_vusers');

export const options = {
  stages: [
    // 10-minute sustained load test at 1600 RPS
    { duration: '30s', target: 100 },   // Ramp up: 30s
    { duration: '30s', target: 320 },   // Ramp to target: 30s
    { duration: '9m', target: 320 },    // Sustained load: 9 minutes
    { duration: '1m', target: 0 },      // Ramp down: 1 minute
  ],
  
  thresholds: {
    'http_req_duration': ['p(95)<500', 'p(99)<2000'],
    'http_req_failed': ['rate<0.05'],
  },
};

export default function () {
  activeVUsers.add(1);

  // Simple health check
  group('Request', function () {
    const res = http.get('http://localhost/api/data');
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

  activeVUsers.add(-1);
  sleep(0.05);
}
