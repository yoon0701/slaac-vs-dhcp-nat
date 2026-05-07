from mininet.net import Mininet
from mininet.node import OVSBridge
from mininet.log import setLogLevel
from base_topology import IoTExperimentTopo, NUM_SWITCHES
import time
import threading
import os

EXTERNAL_IP = '203.0.113.2'
TIMEOUT = 30

def measure_total_v4(host, results, lock):
    intf = host.defaultIntf().name

    host.cmd(f'ip addr flush dev {intf}')
    t1 = time.time()

    host.cmd(f'dhclient {intf}')

    t_assigned = None
    while time.time() - t1 < TIMEOUT:
        if host.cmd(f'ip -4 addr show {intf} | grep "inet "').strip():
            t_assigned = time.time()
            break
        time.sleep(0.05)   # 0.5s → 0.05s: 폴링 오차 ±500ms → ±50ms
    else:
        with lock:
            results['fail'] += 1
        print(f"[{host.name}] DHCP 타임아웃")
        return

    output = host.cmd(f'ping -c 1 -W 2 {EXTERNAL_IP}')
    success = ' 1 received' in output
    t2 = time.time()

    addr_lat = t_assigned - t1        # DHCP 4-way handshake 시간
    pkt_lat  = t2 - t_assigned        # ARP + NAT 엔트리 생성 + ping RTT
    total_lat = t2 - t1

    with lock:
        if success:
            results['success'].append({
                'host':         host.name,
                'address':      addr_lat,
                'first_packet': pkt_lat,
                'total':        total_lat,
            })
            print(f"[{host.name}] 완료: addr={addr_lat:.3f}s  pkt={pkt_lat:.3f}s  total={total_lat:.3f}s")
        else:
            results['fail'] += 1
            print(f"[{host.name}] Ping 실패 (IP 할당 후 NAT/라우팅 오류)")


def run_total_v4_experiment(n=50, num_switches=NUM_SWITCHES):
    topo = IoTExperimentTopo(n=n, num_switches=num_switches, with_external=True)
    net = Mininet(topo=topo, switch=OVSBridge, controller=None)
    net.start()

    r1  = net.get('r1')
    ext = net.get('ext')

    # r1 내부 인터페이스: 스위치별 서브넷 (10.0.i.1/24)
    for i in range(1, num_switches + 1):
        intf = f'r1-eth{i - 1}'
        r1.cmd(f'ip addr flush dev {intf}')
        r1.cmd(f'ip addr add 10.0.{i}.1/24 dev {intf}')
        r1.cmd(f'ip link set {intf} up')

    # r1 외부 인터페이스
    ext_intf = f'r1-eth{num_switches}'
    r1.cmd(f'ip addr flush dev {ext_intf}')
    r1.cmd(f'ip addr add 203.0.113.1/24 dev {ext_intf}')
    r1.cmd(f'ip link set {ext_intf} up')

    r1.cmd('sysctl -w net.ipv4.ip_forward=1')
    r1.cmd('iptables -t nat -F')
    r1.cmd(f'iptables -t nat -A POSTROUTING -o {ext_intf} -j MASQUERADE')

    # 외부 서버 설정
    ext.cmd('ip addr flush dev ext-eth0')
    ext.cmd('ip addr add 203.0.113.2/24 dev ext-eth0')
    ext.cmd('ip link set ext-eth0 up')
    ext.cmd('ip route add default via 203.0.113.1')

    # DHCP 설정 파일 동적 생성 (스위치별 서브넷)
    dhcp_conf = "default-lease-time 600;\nmax-lease-time 7200;\n"
    for i in range(1, num_switches + 1):
        dhcp_conf += (
            f"subnet 10.0.{i}.0 netmask 255.255.255.0 {{\n"
            f"  range 10.0.{i}.2 10.0.{i}.254;\n"
            f"  option routers 10.0.{i}.1;\n"
            f"}}\n"
        )
    with open('/etc/dhcp/dhcpd.conf', 'w') as f:
        f.write(dhcp_conf)

    # DHCP 서버 시작 (기존 프로세스 완전 종료 후 기동)
    os.system('pkill -f dhcpd 2>/dev/null')
    for _ in range(20):          # 최대 2s 대기 → 포트 해제 확인
        if os.system('pgrep -f dhcpd > /dev/null 2>&1') != 0:
            break
        time.sleep(0.1)

    os.system('mkdir -p /var/lib/dhcp && touch /var/lib/dhcp/dhcpd.leases && chmod 666 /var/lib/dhcp/dhcpd.leases')
    internal_intfs = ' '.join(f'r1-eth{i - 1}' for i in range(1, num_switches + 1))
    r1.cmd(f'dhcpd -4 -f -lf /var/lib/dhcp/dhcpd.leases -cf /etc/dhcp/dhcpd.conf {internal_intfs} > /tmp/dhcpd.log 2>&1 &')

    time.sleep(2)

    # dhcpd 기동 확인
    if not r1.cmd('pgrep dhcpd').strip():
        print("❌ dhcpd 시작 실패. 로그:")
        print(open('/tmp/dhcpd.log').read())
        net.stop()
        return None

    print("[dhcpd 로그] /tmp/dhcpd.log 확인 가능")

    print(f"\n--- {n}대 기기 / {num_switches}개 스위치 / IPv4 지연 측정 시작 ---")
    threads = []
    results = {'success': [], 'fail': 0}
    lock = threading.Lock()

    for i in range(1, n + 1):
        host = net.get(f'iot{i}')
        t = threading.Thread(target=measure_total_v4, args=(host, results, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # dhclient 프로세스 정리 (다음 실험 오염 방지)
    for i in range(1, n + 1):
        net.get(f'iot{i}').cmd('pkill -f dhclient 2>/dev/null')

    success_list = results['success']
    fail_count   = results['fail']

    def mean_of(key):
        vals = [r[key] for r in success_list]
        return round(sum(vals) / len(vals), 4) if vals else None

    success_rate = round(len(success_list) / n * 100, 1)
    avg_total    = round(
        sum(r['total'] for r in success_list) / len(success_list), 4
    ) if success_list else None

    result = {
        'n':                        n,
        'num_switches':             num_switches,
        'protocol':                 'IPv4',
        'success':                  len(success_list),
        'fail':                     fail_count,
        'success_rate':             success_rate,
        'avg_address_latency':      mean_of('address'),      # DHCP 시간
        'avg_first_packet_latency': mean_of('first_packet'), # ARP+NAT+RTT
        'avg_total_latency':        avg_total,
        'avg_ra_wait':              None,
        'avg_dad_latency':          None,
        'raw':                      success_list,
    }

    print(f"\n{'='*55}")
    print(f"✅ IPv4 실험 결과 (n={n}, switches={num_switches})")
    print(f"   성공률: {len(success_list)}/{n}대 ({success_rate:.1f}%)")
    if result['avg_address_latency'] is not None:
        print(f"   주소 할당 (DHCP):  {result['avg_address_latency']:.4f}s  [T_assigned - T1]")
        print(f"   첫 패킷 (ARP+NAT): {result['avg_first_packet_latency']:.4f}s  [T2 - T_assigned]")
        print(f"   전체 평균:         {avg_total:.4f}s  [T2 - T1, 성공 기기 기준]")
    else:
        print("   ❌ 전원 연결 실패")
    print(f"{'='*55}")

    net.stop()
    return result


if __name__ == '__main__':
    setLogLevel('error')
    run_total_v4_experiment(50)
