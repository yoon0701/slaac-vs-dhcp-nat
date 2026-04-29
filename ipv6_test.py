from mininet.net import Mininet
from mininet.node import OVSController
from mininet.log import setLogLevel
from base_topology import IoTExperimentTopo
import time
import threading
import os

EXTERNAL_IP6 = '2001:db8:2::8888'
TIMEOUT = 30

def measure_total_v6(host, results, lock):
    intf = host.defaultIntf().name

    # global 주소만 초기화 (link-local 유지 → OVS 포트 연결 유지)
    # ip link set down/up은 OVS가 포트를 리셋해 RS/RA 패킷을 차단함
    host.cmd(f'ip -6 addr flush dev {intf} scope global')
    start_time = time.time()

    # RA 수신 + SLAAC + DAD(~1s) 완료 대기
    # tentative 상태는 DAD 진행 중이므로 아직 통신 불가 → 제외
    # sleep 0.5s: 50스레드 동시 host.cmd() 과부하 방지
    TIMEOUT = 30
    while time.time() - start_time < TIMEOUT:
        out = host.cmd(
            f'ip -6 addr show {intf} | grep "scope global" | grep -v tentative'
        )
        if out.strip():
            break
        time.sleep(0.5)
    else:
        with lock:
            results['fail'] += 1
        print(f"[{host.name}] SLAAC 타임아웃 ({TIMEOUT}s)")
        return

    # 외부망 첫 패킷 도달 확인 (IPv6는 NAT 없이 직접 라우팅)
    output = host.cmd(f'ping -6 -c 1 -W 2 {EXTERNAL_IP6}')
    success = ' 1 received' in output

    end_time = time.time()
    latency = end_time - start_time

    with lock:
        if success:
            results['success'].append(latency)
            print(f"[{host.name}] 통합 연결 완료! (SLAAC+DAD+Ping): {latency:.4f}s")
        else:
            results['fail'] += 1
            print(f"[{host.name}] Ping 실패 (SLAAC 또는 라우팅 오류)")

def run_total_v6_experiment(n=50):
    topo = IoTExperimentTopo(n=n, with_external=True)
    net = Mininet(topo=topo, controller=OVSController)
    net.start()

    r1 = net.get('r1')
    ext = net.get('ext')

    # 외부 서버 IPv6 설정
    ext.cmd(f'ip -6 addr add {EXTERNAL_IP6}/64 dev ext-eth0')
    ext.cmd('ip -6 route add default via 2001:db8:2::1')

    # r1 포워딩 및 외부 인터페이스 설정
    r1.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
    r1.cmd('ip -6 addr add 2001:db8:2::1/64 dev r1-eth1')

    # radvd 실행 전 이전 실행 잔존 프로세스 정리
    # net.stop()이 호출돼도 &로 실행된 radvd는 고아 프로세스로 남아
    # /run/radvd.pid를 잠근 채 새 radvd 시작을 막음
    os.system('pkill -f radvd 2>/dev/null; sleep 0.3')
    r1.cmd('rm -f /run/radvd.pid')

    # radvd 실행 (내부망 r1-eth0, /etc/radvd.conf 기준)
    r1.cmd('ip -6 addr add 2001:db8:1::1/64 dev r1-eth0')
    r1.cmd('radvd -C /etc/radvd.conf -m stderr &')
    time.sleep(0.5)

    # radvd 기동 확인
    if not r1.cmd('pgrep radvd').strip():
        print("❌ radvd 시작 실패. setup_slaac.sh를 먼저 실행했는지 확인하세요.")
        net.stop()
        return

    time.sleep(2)

    # accept_ra 일괄 설정 (인터페이스는 DOWN 없이 유지 → OVS 연결 보존)
    for i in range(1, n + 1):
        host = net.get(f'iot{i}')
        intf = host.defaultIntf().name
        host.cmd(f'sysctl -w net.ipv6.conf.{intf}.accept_ra=2')

    print(f"\n--- {n}대 기기 IPv6 통합 지연 시간 측정 시작 ---")
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

    success = results['success']
    fail_count = results['fail']
    success_rate = len(success) / n * 100
    avg_success = sum(success) / len(success) if success else None
    avg_total   = (sum(success) + fail_count * TIMEOUT) / n if success else TIMEOUT

    print(f"\n{'='*50}")
    print(f"✅ IPv6 실험 결과 (n={n})")
    print(f"   성공률: {len(success)}/{n}대 ({success_rate:.1f}%)")
    if avg_success:
        print(f"   성공 평균 레이턴시:  {avg_success:.4f}s")
        print(f"   전체 평균 레이턴시:  {avg_total:.4f}s  (실패={TIMEOUT}s 처리)")
    else:
        print("   ❌ 전원 연결 실패")
    print(f"{'='*50}")

    net.stop()
    return {
        'n': n, 'protocol': 'IPv6',
        'success': len(success), 'fail': fail_count,
        'success_rate': round(success_rate, 1),
        'avg_success_latency': round(avg_success, 4) if avg_success else None,
        'avg_total_latency':   round(avg_total,   4),
    }

if __name__ == '__main__':
    setLogLevel('error')
    run_total_v6_experiment(50)
