"""
실험 결과 시각화
사용법: python3 plot_results.py
출력:  graphs/ 폴더에 PNG 파일 저장
  - graph1_total_latency.png  : n vs total_lat 비교선 그래프
  - graph2_breakdown.png      : 구간별(addr/pkt) stacked bar
  - graph3_distribution.png   : n=50 기준 total_lat 분포 (히스토그램)
  - graph4_ra_dad.png         : IPv6 RA대기 vs DAD 비교선 그래프
"""
import csv
import os
import collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RESULT_FILE = 'results.csv'
RAW_FILE    = 'results_raw.csv'
OUT_DIR     = 'graphs'

os.makedirs(OUT_DIR, exist_ok=True)

# ── 데이터 로드 ────────────────────────────────────────────────────

def load_agg(path):
    rows = {'IPv4': {}, 'IPv6': {}}
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            proto = r['protocol']
            n     = int(r['n'])
            rows[proto][n] = {k: float(v) if v not in ('', 'None') else None
                              for k, v in r.items() if k not in ('protocol', 'n', 'num_switches')}
    return rows


def load_raw(path):
    """protocol → n → [total_latency, ...] 구조로 반환."""
    data = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            proto = r['protocol']
            n     = int(r['n'])
            val   = r['total_latency']
            if val not in ('', 'None'):
                data[proto][n].append(float(val))
    return data


agg = load_agg(RESULT_FILE)
raw = load_raw(RAW_FILE)

ns_v4 = sorted(agg['IPv4'].keys())
ns_v6 = sorted(agg['IPv6'].keys())
ns    = sorted(set(ns_v4) | set(ns_v6))

COLORS = {'IPv4': '#E05C5C', 'IPv6': '#5C8BE0'}


# ── 그래프 1: n vs total latency 비교선 ───────────────────────────

fig, ax = plt.subplots(figsize=(7, 4.5))

for proto, ns_list in [('IPv4', ns_v4), ('IPv6', ns_v6)]:
    d    = agg[proto]
    xs   = ns_list
    ys   = [d[n]['mean_total_latency'] for n in xs]
    errs = [d[n]['std_total_latency']  for n in xs]
    ax.errorbar(xs, ys, yerr=errs, marker='o', linewidth=2,
                capsize=4, label=proto, color=COLORS[proto])

ax.set_xlabel('Number of IoT Devices (n)', fontsize=12)
ax.set_ylabel('Total Latency (s)', fontsize=12)
ax.set_title('Initial Connection Latency: IPv4 vs IPv6', fontsize=13)
ax.legend(fontsize=11)
ax.xaxis.set_major_locator(ticker.FixedLocator(ns))
ax.grid(axis='y', linestyle='--', alpha=0.5)
fig.tight_layout()
fig.savefig(f'{OUT_DIR}/graph1_total_latency.png', dpi=150)
plt.close(fig)
print(f"저장: {OUT_DIR}/graph1_total_latency.png")


# ── 그래프 2: 구간별 stacked bar (addr_lat / pkt_lat) ────────────

fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

for ax, proto, ns_list in zip(axes, ['IPv4', 'IPv6'], [ns_v4, ns_v6]):
    d        = agg[proto]
    xs       = ns_list
    x_pos    = range(len(xs))
    addr_lat = [d[n]['mean_address_latency'] or 0 for n in xs]
    pkt_lat  = [d[n]['mean_first_packet_latency'] or 0 for n in xs]

    bar1 = ax.bar(x_pos, addr_lat, label='Address Assignment', color=COLORS[proto], alpha=0.85)
    bar2 = ax.bar(x_pos, pkt_lat, bottom=addr_lat, label='First Packet (NAT/ND+RTT)',
                  color=COLORS[proto], alpha=0.45, hatch='//')

    ax.set_xticks(list(x_pos))
    ax.set_xticklabels([str(n) for n in xs])
    ax.set_xlabel('Number of IoT Devices (n)', fontsize=11)
    ax.set_ylabel('Latency (s)', fontsize=11)
    ax.set_title(f'{proto}: Latency Breakdown', fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

fig.tight_layout()
fig.savefig(f'{OUT_DIR}/graph2_breakdown.png', dpi=150)
plt.close(fig)
print(f"저장: {OUT_DIR}/graph2_breakdown.png")


# ── 그래프 3: n=50 기준 total_lat 분포 히스토그램 ────────────────

HIST_N = 50
fig, ax = plt.subplots(figsize=(7, 4.5))

has_data = False
for proto in ['IPv4', 'IPv6']:
    vals = raw[proto].get(HIST_N, [])
    if vals:
        ax.hist(vals, bins=15, alpha=0.6, label=proto, color=COLORS[proto], edgecolor='white')
        has_data = True

if has_data:
    ax.set_xlabel('Total Latency (s)', fontsize=12)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title(f'Latency Distribution at n={HIST_N}', fontsize=13)
    ax.legend(fontsize=11)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    fig.tight_layout()
    fig.savefig(f'{OUT_DIR}/graph3_distribution.png', dpi=150)
    print(f"저장: {OUT_DIR}/graph3_distribution.png")
else:
    print(f"[건너뜀] graph3: n={HIST_N} raw 데이터 없음")
plt.close(fig)


# ── 그래프 4: IPv6 RA대기 vs DAD 비교선 ──────────────────────────

d_v6 = agg['IPv6']
ns_v6_with_ra = [n for n in ns_v6 if d_v6[n].get('mean_ra_wait') is not None]

if ns_v6_with_ra:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ra_vals  = [d_v6[n]['mean_ra_wait']    for n in ns_v6_with_ra]
    dad_vals = [d_v6[n]['mean_dad_latency'] for n in ns_v6_with_ra]

    ax.plot(ns_v6_with_ra, ra_vals,  marker='s', linewidth=2,
            label='RA Wait (RS → tentative)', color='#5C8BE0')
    ax.plot(ns_v6_with_ra, dad_vals, marker='^', linewidth=2,
            label='DAD (~1s fixed)', color='#3DB07A')

    ax.set_xlabel('Number of IoT Devices (n)', fontsize=12)
    ax.set_ylabel('Latency (s)', fontsize=12)
    ax.set_title('IPv6 SLAAC: RA Wait vs DAD Latency', fontsize=13)
    ax.legend(fontsize=11)
    ax.xaxis.set_major_locator(ticker.FixedLocator(ns_v6_with_ra))
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    fig.tight_layout()
    fig.savefig(f'{OUT_DIR}/graph4_ra_dad.png', dpi=150)
    plt.close(fig)
    print(f"저장: {OUT_DIR}/graph4_ra_dad.png")
else:
    print("[건너뜀] graph4: IPv6 RA 데이터 없음")

print("\n완료. 그래프 파일 위치:", OUT_DIR)
