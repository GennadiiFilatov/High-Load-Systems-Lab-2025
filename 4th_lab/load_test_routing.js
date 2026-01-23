// Lab 7&8: Read Routing Test
// Task 5: Monitor CPU as more reads go to replica

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    scenarios: {
        // Phase 1: 0% replica reads (all to master)
        phase1_master_only: {
            executor: 'constant-arrival-rate',
            rate: 50,
            timeUnit: '1s',
            duration: '3m',
            preAllocatedVUs: 20,
            exec: 'readMaster',
            startTime: '0s',
        },
        // Phase 2: 50% replica reads
        phase2_mixed: {
            executor: 'constant-arrival-rate',
            rate: 50,
            timeUnit: '1s',
            duration: '3m',
            preAllocatedVUs: 20,
            exec: 'readAuto',
            startTime: '3m',
        },
        // Phase 3: 100% replica reads
        phase3_replica_only: {
            executor: 'constant-arrival-rate',
            rate: 50,
            timeUnit: '1s',
            duration: '3m',
            preAllocatedVUs: 20,
            exec: 'readReplica',
            startTime: '6m',
        },
    },
};

const BASE_URL = 'http://localhost:8000';

export function readMaster() {
    const res = http.get(`${BASE_URL}/read/master`);
    check(res, { 'master read ok': (r) => r.status === 200 });
}

export function readReplica() {
    const res = http.get(`${BASE_URL}/read/replica`);
    check(res, { 'replica read ok': (r) => r.status === 200 });
}

export function readAuto() {
    const res = http.get(`${BASE_URL}/read`);
    check(res, { 'auto read ok': (r) => r.status === 200 });
}
