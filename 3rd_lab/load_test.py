#!/usr/bin/env python3
"""
Load testing script for cache performance analysis
Tests both cached and uncached endpoints with configurable load
"""

import requests
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import argparse


class LoadTester:
    def __init__(self, base_url='http://localhost', num_workers=10, duration=30):
        self.base_url = base_url
        self.num_workers = num_workers
        self.duration = duration
        self.results = {
            'cached': {'times': [], 'errors': 0},
            'uncached': {'times': [], 'errors': 0}
        }
    
    def test_endpoint(self, endpoint, endpoint_type):
        """Test single endpoint"""
        start = time.time()
        try:
            response = requests.get(f'{self.base_url}{endpoint}', timeout=5)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                self.results[endpoint_type]['times'].append(elapsed)
            else:
                self.results[endpoint_type]['errors'] += 1
        except Exception as e:
            self.results[endpoint_type]['errors'] += 1
            print(f'? Error: {e}')
    
    def run_load_test(self):
        """Run concurrent load test"""
        print(f'\n?? Starting load test...')
        print(f'Workers: {self.num_workers}, Duration: {self.duration}s')
        print(f'Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        
        start_time = time.time()
        request_count = 0
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = []
            
            while time.time() - start_time < self.duration:
                # Alternate between cached and uncached
                future_cached = executor.submit(
                    self.test_endpoint, 
                    '/api/products/cached', 
                    'cached'
                )
                future_uncached = executor.submit(
                    self.test_endpoint, 
                    '/api/products/db', 
                    'uncached'
                )
                
                futures.extend([future_cached, future_uncached])
                request_count += 2
                
                # Small delay between submissions
                time.sleep(0.05)
            
            # Wait for remaining requests
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f'Future error: {e}')
        
        self._print_results(request_count, time.time() - start_time)
    
    def _print_results(self, total_requests, elapsed_time):
        """Print formatted results"""
        print('\n' + '='*70)
        print('?? LOAD TEST RESULTS')
        print('='*70)
        
        print(f'\nTotal Requests: {total_requests}')
        print(f'Elapsed Time: {elapsed_time:.2f}s')
        print(f'Requests/sec: {total_requests/elapsed_time:.2f}\n')
        
        for endpoint_type in ['cached', 'uncached']:
            data = self.results[endpoint_type]
            times = data['times']
            errors = data['errors']
            
            if not times:
                print(f'\n??  {endpoint_type.upper()}: No successful requests')
                continue
            
            success_rate = len(times) / (len(times) + errors) * 100
            
            print(f'\n?? {endpoint_type.upper()} ENDPOINT:')
            print(f'  ? Successful: {len(times)}')
            print(f'  ? Errors: {errors}')
            print(f'  ?? Success Rate: {success_rate:.1f}%')
            print(f'  ??  Min Response: {min(times)*1000:.2f}ms')
            print(f'  ??  Max Response: {max(times)*1000:.2f}ms')
            print(f'  ?? Mean Response: {statistics.mean(times)*1000:.2f}ms')
            print(f'  ?? Median Response: {statistics.median(times)*1000:.2f}ms')
            
            if len(times) > 1:
                stdev = statistics.stdev(times)
                print(f'  ?? Std Dev: {stdev*1000:.2f}ms')
            
            # Calculate percentiles
            sorted_times = sorted(times)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)
            
            print(f'  ?? P95 Response: {sorted_times[p95_idx]*1000:.2f}ms')
            if len(sorted_times) > p99_idx:
                print(f'  ?? P99 Response: {sorted_times[p99_idx]*1000:.2f}ms')
        
        print('\n' + '='*70)
        print('? Load test completed!')
        print('='*70 + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Load test caching performance')
    parser.add_argument('--workers', type=int, default=10, help='Number of concurrent workers')
    parser.add_argument('--duration', type=int, default=30, help='Test duration in seconds')
    parser.add_argument('--url', default='http://localhost', help='Base URL of the service')
    
    args = parser.parse_args()
    
    tester = LoadTester(
        base_url=args.url,
        num_workers=args.workers,
        duration=args.duration
    )
    tester.run_load_test()
