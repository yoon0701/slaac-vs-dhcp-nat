from mininet.net import Mininet
from mininet.node import OVSController
from mininet.log import setLogLevel
from base_topology import IoTExperimentTopo, NUM_SWITCHES
import time
import threading
import os

EXTERNAL_IP6 = '2001:db8:ffff::2'
TIMEOUT = 30

def measure_total_v6(host, results, lock):
    intf = host.defaultIntf().name

    # global 주소만 초기화 (link-local 유지 → OVS 포트 연결 보존)
    host.cmd(f'ip -6 addr flush dev {intf} scope global')

    # accept_ra를 0→2로 토글해 커널이 RS를 재전송하도록 유도
    host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=0 > /dev/null')
    t1 = time.time()
    host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=2 > /dev/null')

    t_ra       = None  # tentative 주소 출현 → RA 수신 완료
    t_assigned = None  # preferred 주소 확정  → DAD 완료

    while time.time() - t1 < TIMEOUT:
        # RA 수신 시점: tentative 상태의 global 주소가 처음 나타날 때
        if t_ra is None:
            tentative = host.cmd(
                f'ip -6 addr show {intf} | grep "scope global" | grep tentative'
            ).strip()
            if tentative:
                t_ra = time.time()

        # DAD 완료 시점: preferred(non-tentative) global 주소 확정
        preferred = host.cmd(
            f'ip -6 addr show {intf} | grep "scope global" | grep -v tentative'
        ).strip()
        if preferred:
            t_assigned = time.time()
            if t_ra is None:
                # tentative 구간을 0.5s 폴링에서 놓친 경우
                t_ra = t_assigned
            break

        time.sleep(0.05)   # 0.5s → 0.05s: 폴링 오차 ±500ms → ±50ms
    else:
        with lock:
            results['fail'] += 1
        print(f"[{host.name}] SLAAC 타임아웃 ({TIMEOUT}s)")
        return

    output = host.cmd(f'ping6 -c 1 -W 2 {EXTERNAL_IP6}')
    success = ' 1 received' in output
    t2 = time.time()

    ra_wait  = t_ra - t1        # RA 대기 시간 (RS 전송 → tentative 주소 출현)
    dad_lat  = t_assigned - t_ra  # DAD 지연 (~1s 고정)
    addr_lat = t_assigned - t1  # ra_wait + dad_lat
    pkt_lat  = t2 - t_assigned  # ND 해소 + ping RTT
    total_lat = t2 - t1

    with lock:
        if success:
            results['success'].append({
                'ra_wait':      ra_wait,
                'dad':          dad_lat,
                'address':      addr_lat,
                'first_packet': pkt_lat,
                'total':        total_lat,
            })
            print(
                f"[{host.name}] 완료: "
                f"ra={ra_wait:.3f}s  dad={dad_lat:.3f}s  "
                f"addr={addr_lat:.3f}s  pkt={pkt_lat:.3f}s  total={total_lat:.3f}s"
            )
        else:
            results['fail'] += 1
            print(f"[{host.name}] Ping 실패 (SLAAC 또는 라우팅 오류)")


def run_total_v6_experiment(n=50, num_switches=NUM_SWITCHES):
    topo = IoTExperimentTopo(n=n, num_switches=num_switches, with_external=True)
    net = Mininet(topo=topo, controller=OVSController)
    net.start()

    r1  = net.get('r1')
    ext = net.get('ext')

    r1.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')

    # r1 내부 인터페이스: 스위치별 /64 prefix (2001:db8:i::1)
    for i in range(1, num_switches + 1):
        intf = f'r1-eth{i - 1}'
        r1.cmd(f'ip -6 addr flush dev {intf}')
        r1.cmd(f'ip -6 addr add 2001:db8:{i}::1/64 dev {intf}')
        r1.cmd(f'ip link set {intf} up')

    # r1 외부 인터페이스
    ext_intf = f'r1-eth{num_switches}'
    r1.cmd(f'ip -6 addr flush dev {ext_intf}')
    r1.cmd(f'ip -6 addr add 2001:db8:ffff::1/64 dev {ext_intf}')
    r1.cmd(f'ip link set {ext_intf} up')

    # 외부 서버 설정
    ext.cmd('ip -6 addr flush dev ext-eth0')
    ext.cmd(f'ip -6 addr add {EXTERNAL_IP6}/64 dev ext-eth0')
    ext.cmd('ip link set ext-eth0 up')
    ext.cmd('ip -6 route add default via 2001:db8:ffff::1')

    # radvd 설정 파일 동적 생성 (스위치별 interface 스탠자)
    radvd_conf = ""
    for i in range(1, num_switches + 1):
        radvd_conf += (
            f"interface r1-eth{i - 1}\n"
            f"{{\n"
            f"    AdvSendAdvert on;\n"
            f"    MinRtrAdvInterval 3;\n"
            f"    MaxRtrAdvInterval 4;\n"
            f"    prefix 2001:db8:{i}::/64\n"
            f"    {{\n"
            f"        AdvOnLink on;\n"
            f"        AdvAutonomous on;\n"
            f"        AdvRouterAddr on;\n"
            f"    }};\n"
            f"}};\n"
        )
    with open('/etc/radvd.conf', 'w') as f:
        f.write(radvd_conf)

    # radvd 시작 (기존 프로세스 완전 종료 후 기동)
    os.system('pkill -f radvd 2>/dev/null')
    for _ in range(20):          # 최대 2s 대기 → 포트 해제 확인
        if os.system('pgrep -f radvd > /dev/null 2>&1') != 0:
            break
        time.sleep(0.1)
    r1.cmd('rm -f /run/radvd.pid')
    r1.cmd('radvd -C /etc/radvd.conf -m stderr &')
    time.sleep(0.5)

    if not r1.cmd('pgrep radvd').strip():
        print("❌ radvd 시작 실패.")
        net.stop()
        return None

    time.sleep(2)

    # accept_ra 초기 설정 (측정 전 일괄 적용)
    for i in range(1, n + 1):
        host = net.get(f'iot{i}')
        intf = host.defaultIntf().name
        host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=2')

    print(f"\n--- {n}대 기기 / {num_switches}개 스위치 / IPv6 지연 측정 시작 ---")
    threads = []
    results = {'success': [], 'fail': 0}
    lock = threading.Lock()

    for i in range(1, n + 1):
        host = net.get(f'iot{i}')
        t = threading.Thread(target=measure_total_v6, args=(host, results, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    success_list = results['success']
    fail_count   = results['fail']

    def mean_of(key):
        vals = [r[key] for r in success_list if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    success_rate = round(len(success_list) / n * 100, 1)
    avg_total    = round(
        (sum(r['total'] for r in success_list) + fail_count * TIMEOUT) / n, 4
    )

    result = {
        'n':                        n,
        'num_switches':             num_switches,
        'protocol':                 'IPv6',
        'success':                  len(success_list),
        'fail':                     fail_count,
        'success_rate':             success_rate,
        'avg_ra_wait':              mean_of('ra_wait'),
        'avg_dad_latency':          mean_of('dad'),
        'avg_address_latency':      mean_of('address'),      # RA 대기 + DAD
        'avg_first_packet_latency': mean_of('first_packet'), # ND + ping RTT
        'avg_total_latency':        avg_total,
    }

    print(f"\n{'='*55}")
    print(f"✅ IPv6 실험 결과 (n={n}, switches={num_switches})")
    print(f"   성공률: {len(success_list)}/{n}대 ({success_rate:.1f}%)")
    if result['avg_address_latency'] is not None:
        print(f"   RA 대기:           {result['avg_ra_wait']:.4f}s  [T_ra - T1]")
        print(f"   DAD 지연:          {result['avg_dad_latency']:.4f}s  [T_assigned - T_ra]")
        print(f"   주소 할당 (SLAAC): {result['avg_address_latency']:.4f}s  [T_assigned - T1]")
        print(f"   첫 패킷 (ND+RTT):  {result['avg_first_packet_latency']:.4f}s  [T2 - T_assigned]")
        print(f"   전체 평균:         {avg_total:.4f}s  [T2 - T1, 실패={TIMEOUT}s 처리]")
    else:
        print("   ❌ 전원 연결 실패")
    print(f"{'='*55}")

    net.stop()
    return result


if __name__ == '__main__':
    setLogLevel('error')
    run_total_v6_experiment(50)
