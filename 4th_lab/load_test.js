// Lab 7&8: Basic Load Test - Read and Write Operations
// Task 4: Store data to master and read from replica/master

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '30s', target: 10 },  // Ramp up
        { duration: '3m', target: 10 },   // Steady
        { duration: '30s', target: 0 },   // Ramp down
    ],
};

const BASE_URL = 'http://localhost:8000';

export default function () {
    // Write to master
    const writeRes = http.post(`${BASE_URL}/write`, 
        JSON.stringify({ name: `user_${__VU}_${__ITER}` }),
        { headers: { 'Content-Type': 'application/json' } }
    );
    check(writeRes, { 'write success': (r) => r.status === 200 });

    sleep(0.1);

    // Read (auto-routed to master or replica)
    const readRes = http.get(`${BASE_URL}/read`);
    check(readRes, { 'read success': (r) => r.status === 200 });

    sleep(0.1);
}
