from mininet.net import Mininet
from mininet.node import OVSController
from mininet.log import setLogLevel
from base_topology import IoTExperimentTopo
import time
import threading
import os

EXTERNAL_IP = '203.0.113.2'
TIMEOUT = 30

def measure_total_v4(host, results, lock):
    intf = host.defaultIntf().name

    # T1 직전에 IP 초기화 (DHCP 요청 전 클린 상태 보장)
    host.cmd(f'ip addr flush dev {intf}')
    start_time = time.time()

    # 1. DHCP로 IP 할당
    # dhclient는 플래그 없이 실행 시 즉시 데몬화되어 리턴 → IP 할당까지 폴링 필요
    host.cmd(f'dhclient {intf}')

    while time.time() - start_time < TIMEOUT:
        if host.cmd(f'ip -4 addr show {intf} | grep "inet "').strip():
            break
        time.sleep(0.5)
    else:
        with lock:
            results['fail'] += 1
        print(f"[{host.name}] DHCP 타임아웃")
        return

    # 2. NAT 테이블 생성 + 외부망 첫 패킷 도달 확인
    output = host.cmd(f'ping -c 1 -W 2 {EXTERNAL_IP}')
    success = ' 1 received' in output

    end_time = time.time()
    latency = end_time - start_time

    with lock:
        if success:
            results['success'].append(latency)
            print(f"[{host.name}] 통합 연결 완료! (DHCP+NAT+Ping): {latency:.4f}s")
        else:
            results['fail'] += 1
            print(f"[{host.name}] Ping 실패 (IP 할당 후 NAT/라우팅 오류)")

def run_total_v4_experiment(n=50):
    # with_external=True: net.start() 이전에 ext 호스트와 r1-eth1 링크 생성
    topo = IoTExperimentTopo(n=n, with_external=True)
    net = Mininet(topo=topo, controller=OVSController)
    net.start()

    r1 = net.get('r1')
    ext = net.get('ext')

    # 외부 서버 IPv4 설정
    ext.cmd(f'ifconfig ext-eth0 {EXTERNAL_IP} netmask 255.255.255.0')
    ext.cmd('route add default gw 203.0.113.1')

    # r1 외부 인터페이스 및 NAT 설정
    r1.cmd('ifconfig r1-eth1 203.0.113.1 netmask 255.255.255.0')
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')
    r1.cmd('iptables -t nat -A POSTROUTING -o r1-eth1 -j MASQUERADE')

    # DHCP 서버 실행 (이전 실행 잔존 dhcpd 정리)
    os.system('pkill -f dhcpd 2>/dev/null; sleep 0.3')
    r1.cmd('touch /var/lib/dhcp/dhcpd.leases')
    r1.cmd('dhcpd -4 -f -cf /etc/dhcp/dhcpd.conf r1-eth0 &')

    time.sleep(2)

    print(f"\n--- {n}대 기기 IPv4 통합 지연 시간 측정 시작 ---")
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

    success = results['success']
    fail_count = results['fail']
    success_rate = len(success) / n * 100
    avg_success = sum(success) / len(success) if success else None
    avg_total   = (sum(success) + fail_count * TIMEOUT) / n if success else TIMEOUT

    print(f"\n{'='*50}")
    print(f"✅ IPv4 실험 결과 (n={n})")
    print(f"   성공률: {len(success)}/{n}대 ({success_rate:.1f}%)")
    if avg_success:
        print(f"   성공 평균 레이턴시:  {avg_success:.4f}s")
        print(f"   전체 평균 레이턴시:  {avg_total:.4f}s  (실패={TIMEOUT}s 처리)")
    else:
        print("   ❌ 전원 연결 실패")
    print(f"{'='*50}")

    net.stop()
    return {
        'n': n, 'protocol': 'IPv4',
        'success': len(success), 'fail': fail_count,
        'success_rate': round(success_rate, 1),
        'avg_success_latency': round(avg_success, 4) if avg_success else None,
        'avg_total_latency':   round(avg_total,   4),
    }

if __name__ == '__main__':
    setLogLevel('error')
    run_total_v4_experiment(50)
