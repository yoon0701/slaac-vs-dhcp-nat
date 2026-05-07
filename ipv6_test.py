from mininet.net import Mininet
from mininet.node import OVSBridge
from mininet.log import setLogLevel
from base_topology import IoTExperimentTopo, NUM_SWITCHES
import subprocess
import time
import threading
import os
import logging

EXTERNAL_IP6 = '2001:db8:ffff::2'
TIMEOUT = 30

LOG_FILE = '/tmp/ipv6_experiment.log'

log = logging.getLogger('ipv6')
log.setLevel(logging.INFO)
log.propagate = False
_fh = logging.FileHandler(LOG_FILE, mode='a')
_fh.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', '%H:%M:%S'))
_sh = logging.StreamHandler()
_sh.setLevel(logging.ERROR)  # 콘솔에는 오류만
_sh.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', '%H:%M:%S'))
log.addHandler(_fh)
log.addHandler(_sh)


def measure_total_v6(host, results, lock):
    intf = host.defaultIntf().name

    host.cmd(f'ip -6 addr flush dev {intf} scope global')
    host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=0 > /dev/null')
    t1 = time.time()
    host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=2 > /dev/null')

    t_ra       = None
    t_assigned = None

    while time.time() - t1 < TIMEOUT:
        if t_ra is None:
            tentative = host.cmd(
                f'ip -6 addr show {intf} | grep "scope global" | grep tentative'
            ).strip()
            if tentative:
                t_ra = time.time()

        preferred = host.cmd(
            f'ip -6 addr show {intf} | grep "scope global" | grep -v tentative'
        ).strip()
        if preferred:
            t_assigned = time.time()
            if t_ra is None:
                t_ra = t_assigned
            break

        time.sleep(0.05)
    else:
        addr_state = host.cmd(f'ip -6 addr show {intf}').strip()
        log.error(f'[{host.name}] SLAAC 타임아웃 ({TIMEOUT}s) | {addr_state}')
        with lock:
            results['fail'] += 1
        print(f"[{host.name}] SLAAC 타임아웃 ({TIMEOUT}s)")
        return

    output = host.cmd(f'ping6 -c 1 -W 2 {EXTERNAL_IP6}')
    success = ' 1 received' in output
    t2 = time.time()

    if not success:
        log.error(f'[{host.name}] ping6 실패 | {output.strip()}')

    ra_wait   = t_ra - t1
    dad_lat   = t_assigned - t_ra
    addr_lat  = t_assigned - t1
    pkt_lat   = t2 - t_assigned
    total_lat = t2 - t1

    with lock:
        if success:
            results['success'].append({
                'host':         host.name,
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
    net = Mininet(topo=topo, switch=OVSBridge, controller=None)
    net.start()

    # MLD 스누핑 비활성화: OVS가 RA 멀티캐스트를 모든 포트에 플러딩하도록
    for i in range(1, num_switches + 1):
        os.system(f'ovs-vsctl set Bridge s{i} mcast_snooping_enable=false')

    r1  = net.get('r1')
    ext = net.get('ext')

    r1.cmd('sysctl -w net.ipv6.conf.all.forwarding=1 > /dev/null')

    # r1 내부 인터페이스: scope global만 flush (link-local 유지 → radvd 소스 주소 보존)
    for i in range(1, num_switches + 1):
        intf = f'r1-eth{i - 1}'
        r1.cmd(f'ip -6 addr flush dev {intf} scope global')
        r1.cmd(f'ip -6 addr add 2001:db8:{i}::1/64 dev {intf}')
        r1.cmd(f'ip link set {intf} up')

    # r1 외부 인터페이스
    ext_intf = f'r1-eth{num_switches}'
    r1.cmd(f'ip -6 addr flush dev {ext_intf} scope global')
    r1.cmd(f'ip -6 addr add 2001:db8:ffff::1/64 dev {ext_intf}')
    r1.cmd(f'ip link set {ext_intf} up')

    # 외부 서버 설정
    ext.cmd('ip -6 addr flush dev ext-eth0 scope global')
    ext.cmd(f'ip -6 addr add {EXTERNAL_IP6}/64 dev ext-eth0')
    ext.cmd('ip link set ext-eth0 up')
    ext.cmd('ip -6 route add default via 2001:db8:ffff::1')

    # radvd 설정 파일 생성
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

    # radvd 시작
    os.system('pkill -f radvd 2>/dev/null')
    for _ in range(20):
        if os.system('pgrep -f radvd > /dev/null 2>&1') != 0:
            break
        time.sleep(0.1)
    r1.cmd('rm -f /run/radvd.pid /var/run/radvd.pid /var/run/radvd/radvd.pid 2>/dev/null')
    r1.cmd('radvd -n -C /etc/radvd.conf -m stderr >> /tmp/radvd.log 2>&1 &')
    time.sleep(1)

    radvd_pid = r1.cmd('pgrep -n radvd').strip()
    if not radvd_pid:
        radvd_log = open('/tmp/radvd.log').read().strip()
        log.error(f'radvd 시작 실패\n{radvd_log}')
        net.stop()
        return None

    # radvd가 r1 namespace 안에서 실행되는지 확인
    def ns_of(pid):
        try:
            return subprocess.check_output(
                f'readlink /proc/{pid}/ns/net', shell=True, text=True
            ).strip()
        except Exception:
            return None

    radvd_ns = ns_of(radvd_pid)
    r1_ns    = ns_of(r1.pid)
    if radvd_ns and r1_ns and radvd_ns != r1_ns:
        log.error(
            f'radvd namespace 불일치 — radvd={radvd_ns} r1={r1_ns} '
            f'(radvd가 호스트 namespace에서 실행 중)'
        )
        net.stop()
        return None

    log.info(f'IPv6 실험 시작: n={n} switches={num_switches} radvd_pid={radvd_pid}')

    time.sleep(2)

    # accept_ra 초기 설정
    for i in range(1, n + 1):
        host = net.get(f'iot{i}')
        intf = host.defaultIntf().name
        host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=2 > /dev/null')

    print(f"\n--- {n}대 기기 / {num_switches}개 스위치 / IPv6 지연 측정 시작 ---")
    threads = []
    results = {'success': [], 'fail': 0}
    lock = threading.Lock()

    for i in range(1, n + 1):
        host = net.get(f'iot{i}')
        t = threading.Thread(target=measure_total_v6, args=(host, results, lock))
        threads.append(t)
        t.start()
        # 순차 부팅 시뮬레이션: SLAAC 요청을 분산 (현실성 개선)
        time.sleep(0.05)

    for t in threads:
        t.join()

    success_list = results['success']
    fail_count   = results['fail']

    def mean_of(key):
        vals = [r[key] for r in success_list if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    success_rate = round(len(success_list) / n * 100, 1)
    avg_total    = round(
        sum(r['total'] for r in success_list) / len(success_list), 4
    ) if success_list else None

    result = {
        'n':                        n,
        'num_switches':             num_switches,
        'protocol':                 'IPv6',
        'success':                  len(success_list),
        'fail':                     fail_count,
        'success_rate':             success_rate,
        'avg_ra_wait':              mean_of('ra_wait'),
        'avg_dad_latency':          mean_of('dad'),
        'avg_address_latency':      mean_of('address'),
        'avg_first_packet_latency': mean_of('first_packet'),
        'avg_total_latency':        avg_total,
        'raw':                      success_list,
    }

    print(f"\n{'='*55}")
    print(f"✅ IPv6 실험 결과 (n={n}, switches={num_switches})")
    print(f"   성공률: {len(success_list)}/{n}대 ({success_rate:.1f}%)")
    if result['avg_address_latency'] is not None:
        print(f"   RA 대기:           {result['avg_ra_wait']:.4f}s  [T_ra - T1]")
        print(f"   DAD 지연:          {result['avg_dad_latency']:.4f}s  [T_assigned - T_ra]")
        print(f"   주소 할당 (SLAAC): {result['avg_address_latency']:.4f}s  [T_assigned - T1]")
        print(f"   첫 패킷 (ND+RTT):  {result['avg_first_packet_latency']:.4f}s  [T2 - T_assigned]")
        print(f"   전체 평균:         {avg_total:.4f}s  [T2 - T1, 성공 기기 기준]")
    else:
        print("   ❌ 전원 연결 실패")
    print(f"{'='*55}")

    log.info(
        f'IPv6 실험 종료: n={n} 성공={len(success_list)} 실패={fail_count} '
        f'성공률={success_rate}% avg_total={avg_total:.4f}s'
    )

    net.stop()
    return result


if __name__ == '__main__':
    setLogLevel('error')
    run_total_v6_experiment(50)
