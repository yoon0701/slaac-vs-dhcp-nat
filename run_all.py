"""
IPv4 vs IPv6 스케일 비교 실험 (멀티스위치 토폴로지)
n = [1, 5, 10, 20, 50, 100], N_RUNS = 5회 반복
결과: 평균 ± 표준편차를 CSV로 저장 (중간 저장으로 크래시 복구 가능)
"""
import csv
import os
import time
import statistics
from mininet.log import setLogLevel

from base_topology import NUM_SWITCHES
from ipv4_test import run_total_v4_experiment
from ipv6_test import run_total_v6_experiment

N_VALUES    = [1, 5, 10, 20, 50, 100]
N_RUNS      = 5
RESULT_FILE = 'results.csv'
RAW_FILE    = 'results_raw.csv'

setLogLevel('error')

AGG_FIELDNAMES = [
    'n', 'num_switches', 'protocol', 'runs',
    'mean_success_rate',
    'mean_address_latency',      'std_address_latency',
    'mean_ra_wait',              'std_ra_wait',
    'mean_dad_latency',          'std_dad_latency',
    'mean_first_packet_latency', 'std_first_packet_latency',
    'mean_total_latency',        'std_total_latency',
]
RAW_FIELDNAMES = [
    'n', 'num_switches', 'protocol', 'run', 'host',
    'address_latency', 'first_packet_latency', 'total_latency',
    'ra_wait', 'dad_latency',
]

# 파일 초기화: 헤더만 작성 (실험 시작 시 한 번만)
for path, fieldnames in [(RESULT_FILE, AGG_FIELDNAMES), (RAW_FILE, RAW_FIELDNAMES)]:
    if not os.path.exists(path):
        with open(path, 'w', newline='') as f:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()


def append_rows(path, fieldnames, new_rows):
    """결과 행을 CSV에 즉시 append."""
    with open(path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerows(new_rows)


def aggregate(run_results, key):
    """N_RUNS 개 실행 결과에서 key의 평균과 표준편차를 반환."""
    vals = [r[key] for r in run_results if r and r.get(key) is not None]
    if not vals:
        return None, None
    mean = round(sum(vals) / len(vals), 4)
    std  = round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0
    return mean, std


rows = []  # 최종 테이블 출력용 (메모리 유지)

for n in N_VALUES:
    print(f"\n{'#'*65}")
    print(f"# 실험 시작: n={n}, switches={NUM_SWITCHES}, runs={N_RUNS}")
    print(f"{'#'*65}")

    # ── IPv4: N_RUNS 반복 ──────────────────────────────────────────
    v4_runs    = []
    v4_raw_buf = []
    for run_idx in range(1, N_RUNS + 1):
        print(f"\n[IPv4] n={n}  run {run_idx}/{N_RUNS}")
        r = run_total_v4_experiment(n, NUM_SWITCHES)
        if r:
            v4_runs.append(r)
            for rec in r.get('raw', []):
                v4_raw_buf.append({
                    'n': n, 'num_switches': NUM_SWITCHES,
                    'protocol': 'IPv4', 'run': run_idx,
                    'host':                 rec['host'],
                    'address_latency':      rec['address'],
                    'first_packet_latency': rec['first_packet'],
                    'total_latency':        rec['total'],
                    'ra_wait': None, 'dad_latency': None,
                })
        time.sleep(3)

    if v4_runs:
        mean_sr,   _        = aggregate(v4_runs, 'success_rate')
        mean_addr, std_addr = aggregate(v4_runs, 'avg_address_latency')
        mean_pkt,  std_pkt  = aggregate(v4_runs, 'avg_first_packet_latency')
        mean_tot,  std_tot  = aggregate(v4_runs, 'avg_total_latency')
        agg_row = {
            'n': n, 'num_switches': NUM_SWITCHES, 'protocol': 'IPv4',
            'runs': len(v4_runs), 'mean_success_rate': mean_sr,
            'mean_address_latency': mean_addr, 'std_address_latency': std_addr,
            'mean_ra_wait': None,  'std_ra_wait': None,
            'mean_dad_latency': None, 'std_dad_latency': None,
            'mean_first_packet_latency': mean_pkt, 'std_first_packet_latency': std_pkt,
            'mean_total_latency': mean_tot, 'std_total_latency': std_tot,
        }
        rows.append(agg_row)
        append_rows(RESULT_FILE, AGG_FIELDNAMES, [agg_row])
        append_rows(RAW_FILE,    RAW_FIELDNAMES,  v4_raw_buf)
        print(f"[중간 저장] n={n} IPv4 완료 → {RESULT_FILE}, {RAW_FILE}")

    # ── IPv6: N_RUNS 반복 ──────────────────────────────────────────
    v6_runs    = []
    v6_raw_buf = []
    for run_idx in range(1, N_RUNS + 1):
        print(f"\n[IPv6] n={n}  run {run_idx}/{N_RUNS}")
        r = run_total_v6_experiment(n, NUM_SWITCHES)
        if r:
            v6_runs.append(r)
            for rec in r.get('raw', []):
                v6_raw_buf.append({
                    'n': n, 'num_switches': NUM_SWITCHES,
                    'protocol': 'IPv6', 'run': run_idx,
                    'host':                 rec['host'],
                    'address_latency':      rec['address'],
                    'first_packet_latency': rec['first_packet'],
                    'total_latency':        rec['total'],
                    'ra_wait':              rec.get('ra_wait'),
                    'dad_latency':          rec.get('dad'),
                })
        time.sleep(3)

    if v6_runs:
        mean_sr,  _         = aggregate(v6_runs, 'success_rate')
        mean_ra,  std_ra    = aggregate(v6_runs, 'avg_ra_wait')
        mean_dad, std_dad   = aggregate(v6_runs, 'avg_dad_latency')
        mean_addr, std_addr = aggregate(v6_runs, 'avg_address_latency')
        mean_pkt,  std_pkt  = aggregate(v6_runs, 'avg_first_packet_latency')
        mean_tot,  std_tot  = aggregate(v6_runs, 'avg_total_latency')
        agg_row = {
            'n': n, 'num_switches': NUM_SWITCHES, 'protocol': 'IPv6',
            'runs': len(v6_runs), 'mean_success_rate': mean_sr,
            'mean_address_latency': mean_addr, 'std_address_latency': std_addr,
            'mean_ra_wait': mean_ra,   'std_ra_wait': std_ra,
            'mean_dad_latency': mean_dad, 'std_dad_latency': std_dad,
            'mean_first_packet_latency': mean_pkt, 'std_first_packet_latency': std_pkt,
            'mean_total_latency': mean_tot, 'std_total_latency': std_tot,
        }
        rows.append(agg_row)
        append_rows(RESULT_FILE, AGG_FIELDNAMES, [agg_row])
        append_rows(RAW_FILE,    RAW_FIELDNAMES,  v6_raw_buf)
        print(f"[중간 저장] n={n} IPv6 완료 → {RESULT_FILE}, {RAW_FILE}")

# ── 결과 테이블 출력 ───────────────────────────────────────────────
def fmt(val, std=None):
    if val is None:
        return '   N/A  '
    s = f'{val:.4f}'
    if std is not None:
        s += f'±{std:.4f}'
    return s

print(f"\n{'='*95}")
print(f"{'n':>5} | {'sw':>2} | {'proto':^6} | {'runs':>4} | "
      f"{'success%':>8} | {'addr_lat(avg±std)':^18} | "
      f"{'pkt_lat(avg±std)':^18} | {'total_lat(avg±std)':^19}")
print(f"{'-'*95}")

for r in rows:
    addr = fmt(r['mean_address_latency'], r['std_address_latency'])
    pkt  = fmt(r['mean_first_packet_latency'], r['std_first_packet_latency'])
    tot  = fmt(r['mean_total_latency'], r['std_total_latency'])
    ra_info = ''
    if r['protocol'] == 'IPv6' and r['mean_ra_wait'] is not None:
        ra_info = (f"  └ RA대기={r['mean_ra_wait']:.4f}s  "
                   f"DAD={r['mean_dad_latency']:.4f}s")

    print(f"{r['n']:>5} | {r['num_switches']:>2} | {r['protocol']:^6} | "
          f"{r['runs']:>4} | {r['mean_success_rate']:>7.1f}% | "
          f"{addr:^18} | {pkt:^18} | {tot:^19}")
    if ra_info:
        print(f"{'':>5}   {'':>2}   {'':^6}   {'':>4}   {'':>8}   {ra_info}")

print(f"{'='*95}")
print(f"\n결과 저장 완료: {RESULT_FILE}  |  raw: {RAW_FILE}")
