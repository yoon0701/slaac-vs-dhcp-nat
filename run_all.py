"""
IPv4 vs IPv6 스케일 비교 실험
n = [10, 50, 100, 200, 500] 순서로 자동 실행 후 CSV 저장
"""
import csv
import time
import os
from mininet.log import setLogLevel

from ipv4_test import run_total_v4_experiment
from ipv6_test import run_total_v6_experiment

N_VALUES = [10, 50, 100, 200, 500]
RESULT_FILE = 'results.csv'

setLogLevel('error')

rows = []

for n in N_VALUES:
    print(f"\n{'#'*60}")
    print(f"# 실험 시작: n={n}")
    print(f"{'#'*60}")

    # IPv4 실험
    print(f"\n[IPv4] n={n} 시작...")
    v4 = run_total_v4_experiment(n)
    rows.append(v4)
    time.sleep(3)  # 네트워크 정리 대기

    # IPv6 실험
    print(f"\n[IPv6] n={n} 시작...")
    v6 = run_total_v6_experiment(n)
    rows.append(v6)
    time.sleep(3)

# CSV 저장
fieldnames = ['n', 'protocol', 'success', 'fail',
              'success_rate', 'avg_success_latency', 'avg_total_latency']

with open(RESULT_FILE, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# 결과 테이블 출력
print(f"\n{'='*75}")
print(f"{'n':>6} | {'프로토콜':^6} | {'성공률':>8} | {'성공 평균(s)':>12} | {'전체 평균(s)':>12}")
print(f"{'-'*75}")
for r in rows:
    avg_s = f"{r['avg_success_latency']:.4f}" if r['avg_success_latency'] else "  N/A  "
    print(f"{r['n']:>6} | {r['protocol']:^6} | "
          f"{r['success_rate']:>7.1f}% | "
          f"{avg_s:>12} | "
          f"{r['avg_total_latency']:>11.4f}s")
print(f"{'='*75}")
print(f"\n결과 저장 완료: {RESULT_FILE}")
