// Lab 7&8: Big Boom Test
// Task 6: Huge insert that creates replication lag

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    scenarios: {
        // Continuous reads to monitor lag impact
        continuous_reads: {
            executor: 'constant-arrival-rate',
            rate: 20,
            timeUnit: '1s',
            duration: '2m',
            preAllocatedVUs: 10,
            exec: 'readBoth',
        },
        // Big boom at 30 seconds
        big_boom: {
            executor: 'shared-iterations',
            vus: 1,
            iterations: 1,
            startTime: '30s',
            exec: 'bigBoom',
        },
    },
};

const BASE_URL = 'http://localhost:8000';

export function readBoth() {
    // Read from master
    http.get(`${BASE_URL}/read/master`);
    
    // Read from replica
    http.get(`${BASE_URL}/read/replica`);
    
    // Check replication lag
    const lagRes = http.get(`${BASE_URL}/replication-lag`);
    if (lagRes.status === 200) {
        const lag = JSON.parse(lagRes.body).lag_bytes;
        if (lag > 0) {
            console.log(`Replication lag: ${lag} bytes`);
        }
    }
}

export function bigBoom() {
    console.log('BIG BOOM! Starting massive insert...');
    
    // Insert 10,000 records with 5KB each = ~50MB of data
    const res = http.post(`${BASE_URL}/bulk-insert`,
        JSON.stringify({ count: 10000, size: 5000 }),
        { 
            headers: { 'Content-Type': 'application/json' },
            timeout: '120s'
        }
    );
    
    check(res, { 'bulk insert success': (r) => r.status === 200 });
    
    if (res.status === 200) {
        const result = JSON.parse(res.body);
        console.log(`Inserted ${result.inserted} records (${result.total_bytes} bytes) in ${result.elapsed_seconds}s`);
    }
}
