import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  // Test that will trigger "No Traffic" alert by running then stopping
  stages: [
    { duration: '10s', target: 5 },     // Generate traffic
    { duration: '1m', target: 0 },      // Stop traffic (will trigger "No Traffic" alert)
  ],
  thresholds: {
    'http_req_failed': ['rate<0.2'],
  },
};

export default function () {
  // Heavy load to potentially trigger "High Latency" or "High Error Rate"
  http.batch([
    ['GET', 'http://localhost:5000/'],
    ['GET', 'http://localhost:5000/api/data'],
    ['GET', 'http://localhost:5000/api/slow'],
    ['GET', 'http://localhost:5000/api/random_error'],
  ]);

  sleep(1);
}