import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const activeVUsers = new Gauge('active_vusers');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 5 },    // Ramp up to 5 users over 30s
    { duration: '1m', target: 10 },    // Ramp up to 10 users over 1m
    { duration: '2m', target: 20 },    // Spike to 20 users
    { duration: '30s', target: 10 },   // Ramp down to 10 users
    { duration: '30s', target: 0 },    // Ramp down to 0
  ],
  thresholds: {
    'http_req_duration': ['p(95)<500', 'p(99)<1000'], // 95% of requests < 500ms, 99% < 1s
    'http_req_failed': ['rate<0.1'], // Error rate < 10%
  },
};

export default function () {
  activeVUsers.add(1);

  group('Health Check', function () {
    const res = http.get('http://localhost:5000/');
    check(res, {
      'status is 200': (r) => r.status === 200,
      'response time < 200ms': (r) => r.timings.duration < 200,
    });
    duration.add(res.timings.duration);
    if (res.status !== 200) {
      errorRate.add(1);
    } else {
      successCount.add(1);
    }
  });

  sleep(1);

  group('Data Endpoint', function () {
    const res = http.get('http://localhost:5000/api/data');
    check(res, {
      'status is 200': (r) => r.status === 200,
      'has data': (r) => r.json('data').length > 0,
      'response time < 500ms': (r) => r.timings.duration < 500,
    });
    duration.add(res.timings.duration);
    if (res.status !== 200) {
      errorRate.add(1);
    } else {
      successCount.add(1);
    }
  });

  sleep(1);

  group('Slow Endpoint', function () {
    const res = http.get('http://localhost:5000/api/slow');
    check(res, {
      'status is 200': (r) => r.status === 200,
    });
    duration.add(res.timings.duration);
    if (res.status !== 200) {
      errorRate.add(1);
    } else {
      successCount.add(1);
    }
  });

  sleep(2);

  group('Random Error Endpoint', function () {
    const res = http.get('http://localhost:5000/api/random_error');
    check(res, {
      'status is 200 or 500': (r) => r.status === 200 || r.status === 500,
    });
    duration.add(res.timings.duration);
    if (res.status !== 200) {
      errorRate.add(1);
    } else {
      successCount.add(1);
    }
  });

  activeVUsers.add(-1);
  sleep(1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
  };
}