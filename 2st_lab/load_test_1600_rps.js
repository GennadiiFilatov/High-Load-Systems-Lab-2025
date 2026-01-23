import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

// Custom metrics for deep analysis
const errorRate = new Rate('errors');
const duration = new Trend('duration');
const successCount = new Counter('successful_requests');
const p95Latency = new Trend('p95_latency');
const p99Latency = new Trend('p99_latency');
const activeVUsers = new Gauge('active_vusers');

// Test configuration: Target 1600 RPS
// With think time between requests, this translates to VUs needed
export const options = {
  stages: [
    // Ramp up phase: gradually increase load
    { duration: '30s', target: 100 },   // Ramp up to 100 VUs
    { duration: '60s', target: 200 },   // Further ramp up to 200 VUs
    { duration: '60s', target: 320 },   // Reach ~1600 RPS (5 requests per VU, think time ~1s)
    
    // Sustained load phase
    { duration: '7m', target: 320 },    // Maintain load for 7 minutes
    
    // Ramp down phase
    { duration: '60s', target: 100 },   // Ramp down to 100 VUs
    { duration: '30s', target: 0 },     // Final ramp down
  ],
  
  thresholds: {
    // These thresholds define pass/fail criteria
    'http_req_duration': [
      'p(50)<200',    // Median response < 200ms
      'p(95)<500',    // 95th percentile < 500ms
      'p(99)<2000',   // 99th percentile < 2s
    ],
    'http_req_failed': ['rate<0.05'],   // Error rate < 5%
    'errors': ['rate<0.05'],             // Custom error rate < 5%
  },
  
  ext: {
    loadimpact: {
      projectID: 0,  // If using Grafana Cloud, add your project ID
    },
  },
};

export default function () {
  activeVUsers.add(1);

  // Test 1: Health Check (1 request)
  group('Health Check', function () {
    const res = http.get('http://localhost/');
    check(res, {
      'health: status 200': (r) => r.status === 200,
      'health: response time < 100ms': (r) => r.timings.duration < 100,
    });
    
    duration.add(res.timings.duration);
    if (res.status === 200) {
      successCount.add(1);
    } else {
      errorRate.add(1);
    }
  });
  
  sleep(0.1);

  // Test 2: Data Endpoint (1 request)
  group('Data Endpoint', function () {
    const res = http.get('http://localhost/api/data');
    check(res, {
      'data: status 200': (r) => r.status === 200,
      'data: response time < 300ms': (r) => r.timings.duration < 300,
    });
    
    duration.add(res.timings.duration);
    if (res.status === 200) {
      successCount.add(1);
    } else {
      errorRate.add(1);
    }
  });
  
  sleep(0.1);

  // Test 3: Slow Endpoint (1 request) - this is intentionally slow
  group('Slow Endpoint', function () {
    const res = http.get('http://localhost/api/slow');
    check(res, {
      'slow: status 200': (r) => r.status === 200,
    });
    
    duration.add(res.timings.duration);
    if (res.status === 200) {
      successCount.add(1);
    } else {
      errorRate.add(1);
    }
  });
  
  sleep(0.1);

  // Test 4: Random Error Endpoint (1 request)
  group('Random Error', function () {
    const res = http.get('http://localhost/api/random_error');
    check(res, {
      'random_error: status 200 or 500': (r) => r.status === 200 || r.status === 500,
    });
    
    duration.add(res.timings.duration);
    if (res.status === 200) {
      successCount.add(1);
    } else {
      errorRate.add(1);
    }
  });

  activeVUsers.add(-1);
  sleep(0.1);  // Think time between VU iterations
}

// Summary function for results
export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
  };
}

function textSummary(data, options = {}) {
  // Simple text formatting of k6 summary
  const summary = `
  Requests: ${data.metrics.http_reqs?.values?.count || 'N/A'}
  Errors: ${data.metrics.http_req_failed?.values?.sum || 'N/A'}
  P(50): ${data.metrics.http_req_duration?.values?.['p(50)'] || 'N/A'} ms
  P(95): ${data.metrics.http_req_duration?.values?.['p(95)'] || 'N/A'} ms
  P(99): ${data.metrics.http_req_duration?.values?.['p(99)'] || 'N/A'} ms
  `;
  return summary;
}
