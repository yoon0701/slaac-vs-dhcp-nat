# IPv4 DHCP+NAT vs IPv6 SLAAC: IoT 초기 접속 지연 비교 실험

> **Comparing Initial Connection Latency: IPv4 (DHCP+NAT) vs IPv6 (SLAAC) for IoT Devices**
>
> Mininet 에뮬레이션 환경에서 IoT 기기 수(n)를 늘려가며 두 프로토콜의 초기 접속 지연을 측정합니다.

---

## 시나리오 (Scenario)

스마트홈, 산업 현장, 캠퍼스 등에 수십~수백 대의 IoT 기기가 **동시에 전원을 켜서** 인터넷에 첫 접속하는 상황을 가정합니다.

| 구분 | IPv4 방식 | IPv6 방식 |
|------|-----------|-----------|
| 주소 할당 | DHCP 4-way 핸드셰이크 (Discover → Offer → Request → ACK) | SLAAC: RS → RA 수신 → 주소 자동 생성 → DAD |
| 인터넷 연결 | NAT (MASQUERADE) | 글로벌 유니캐스트 주소로 직접 라우팅 |
| 서버 부하 | 기기 수 증가 시 DHCP 서버 부하 증가 | 분산형 (기기가 스스로 주소 생성) |

**핵심 질문:** 기기 수가 늘어날수록 어느 프로토콜이 더 빠르게 첫 패킷을 전달하는가?

---

## 네트워크 토폴로지 (Network Topology)

```
  [iot1] [iot2]     [iotN]
     \     |    ...   /
      [s1: OVS Switch]
           |
      [r1: Router] ──── [s2] ──── [iot...]
           |       ──── [s3] ──── [iot...]
           |       ──── [s4] ──── [iot...]
           |       ──── [s5] ──── [iot...]
           |
      [ext: External Server]
        (203.0.113.2 / 2001:db8:ffff::2)
```

- **r1**: 소프트웨어 라우터 (Linux 네임스페이스). DHCP 서버(dhcpd), radvd, NAT(iptables) 실행
- **s1~s5**: OVS 브리지 스위치 5개. IoT 기기를 라운드로빈으로 분산 연결
- **iot1~iotN**: 실험 대상 IoT 기기 (n = 1, 5, 10, 20, 50, 100)
- **ext**: 외부 인터넷을 대표하는 서버. ping 응답 역할

**IPv4 서브넷 구성 (스위치별)**
| 스위치 | 서브넷 | DHCP 범위 |
|--------|--------|-----------|
| s1 | 10.0.1.0/24 | 10.0.1.2 ~ 10.0.1.254 |
| s2 | 10.0.2.0/24 | 10.0.2.2 ~ 10.0.2.254 |
| ... | ... | ... |
| s5 | 10.0.5.0/24 | 10.0.5.2 ~ 10.0.5.254 |

**IPv6 프리픽스 구성 (스위치별)**
| 스위치 | 프리픽스 |
|--------|----------|
| s1 | 2001:db8:1::/64 |
| s2 | 2001:db8:2::/64 |
| ... | ... |
| s5 | 2001:db8:5::/64 |

---

## 측정 방법론 (Measurement Methodology)

각 IoT 기기마다 별도 쓰레드에서 다음 타임스탬프를 기록합니다.

```
T1         T_assigned        T2
|                |             |
|←── addr_lat ──→|←─ pkt_lat ─→|
|←──────────── total_lat ──────→|
```

| 타임스탬프 | 의미 |
|-----------|------|
| **T1** | 주소 요청 시작 (accept_ra=2 설정 또는 dhclient 호출 직전) |
| **T_assigned** | 유효한 IP 주소가 인터페이스에 나타난 시점 (폴링 감지, 50ms 간격) |
| **T2** | `ping -c 1` 완료 시점 |

| 지표 | 공식 | 의미 |
|------|------|------|
| `addr_lat` | T_assigned − T1 | 주소 획득 소요 시간 |
| `pkt_lat` | T2 − T_assigned | 첫 패킷 전달 소요 시간 (ARP/ND + NAT 엔트리 + RTT) |
| `total_lat` | T2 − T1 | 전체 초기 접속 지연 |

**IPv6 추가 지표**

| 지표 | 공식 | 의미 |
|------|------|------|
| `ra_wait` | T_ra − T1 | RS 전송 후 RA 수신까지 대기 시간 |
| `dad_lat` | T_assigned − T_ra | DAD(Duplicate Address Detection) 소요 시간 (~1s 고정) |

> **주의:** `total_lat`는 성공한 기기만 포함하는 평균입니다. 타임아웃(30s) 기기는 제외하여 과대평가를 방지합니다.

---

## 파일 구조 (File Structure)

```
slaac-vs-dhcp-nat/
├── base_topology.py      # Mininet 토폴로지 정의 (IoTExperimentTopo)
├── ipv4_test.py          # IPv4 실험: DHCP+NAT 지연 측정
├── ipv6_test.py          # IPv6 실험: SLAAC 지연 측정
├── run_all.py            # 전체 실험 자동화 (n × protocol × N_RUNS)
├── plot_results.py       # 결과 시각화 (graphs/ 생성)
├── experiment_env.txt    # 실험 환경 정보 및 주요 발견 정리
├── results.csv           # 집계 결과 (n별 평균±표준편차)
├── results_raw.csv       # 기기별 개별 측정값 전체
└── graphs/
    ├── graph1_total_latency.png   # n vs total_lat 비교선
    ├── graph2_breakdown.png       # addr_lat/pkt_lat stacked bar
    ├── graph3_distribution.png    # n=50 기준 분포 히스토그램
    └── graph4_ra_dad.png          # IPv6 RA대기 vs DAD 비교
```

---

## 실험 환경 (Environment)

| 항목 | 값 |
|------|----|
| 플랫폼 | AWS EC2 (Linux 6.17.0-1007-aws) |
| Python | 3.12.3 |
| Mininet | Open vSwitch 3.3.4 기반 |
| DHCP 서버 | isc-dhcpd 4.4.3-P1 |
| RA 데몬 | radvd 2.19 |

**실험 파라미터**

| 파라미터 | 값 |
|----------|-----|
| n (기기 수) | 1, 5, 10, 20, 50, 100 |
| N_RUNS (반복 횟수) | 5 |
| NUM_SWITCHES | 5 |
| TIMEOUT | 30s |
| radvd MaxRtrAdvInterval | 4s (실험용 단축; 실제 RFC 값은 600s) |

---

## 사전 준비 (Prerequisites)

```bash
# Mininet 및 Open vSwitch
sudo apt-get install -y mininet openvswitch-switch

# DHCP 서버 (ISC dhcpd)
sudo apt-get install -y isc-dhcp-server

# radvd (IPv6 RA 데몬)
sudo apt-get install -y radvd

# Python 의존성
pip3 install matplotlib
```

---

## 실행 방법 (How to Run)

> **중요:** Mininet은 Linux 네트워크 네임스페이스와 OVS를 직접 조작하므로 **반드시 `sudo`로 실행**해야 합니다. AWS EC2 환경에서는 `root` 또는 `sudo` 권한이 필수입니다.

### 전체 실험 실행

```bash
# 전체 실험 (n × protocol × 5회 반복, 약 30~60분 소요)
sudo python3 run_all.py
```

실행 중 각 n이 완료될 때마다 `results.csv`와 `results_raw.csv`에 중간 저장됩니다. 크래시가 발생해도 이미 저장된 결과는 보존됩니다.

### 개별 실험 실행

```bash
# IPv4만 실행 (n=50)
sudo python3 ipv4_test.py

# IPv6만 실행 (n=50)
sudo python3 ipv6_test.py
```

### 결과 시각화

```bash
# 실험 완료 후 그래프 생성 (sudo 불필요)
python3 plot_results.py
# → graphs/ 폴더에 PNG 4장 저장
```

### sudo가 필요한 이유

| 작업 | 이유 |
|------|------|
| Mininet 실행 | Linux 네트워크 네임스페이스 생성 (CAP_NET_ADMIN) |
| OVS 브리지 생성 | `ovs-vsctl` 커널 모듈 조작 |
| iptables NAT 설정 | 커널 netfilter 테이블 수정 |
| dhcpd 실행 | 포트 67/UDP 바인딩 (privileged port) |
| radvd 실행 | 원시 ICMPv6 소켓 사용 |
| `/etc/radvd.conf` 쓰기 | 시스템 설정 파일 수정 |

---

## 실행 흐름 (Execution Flow)

```
run_all.py
  └─ for n in [1, 5, 10, 20, 50, 100]:
       ├─ for run in 1..5:
       │    └─ run_total_v4_experiment(n)       # ipv4_test.py
       │         ├─ Mininet 토폴로지 생성 및 시작
       │         ├─ r1 인터페이스 IP 설정
       │         ├─ iptables NAT (MASQUERADE) 설정
       │         ├─ dhcpd 설정 파일 생성 및 시작
       │         ├─ n개 쓰레드 동시 시작
       │         │    └─ 각 iot: dhclient → 폴링 → ping → T1/T2 기록
       │         ├─ 결과 집계
       │         └─ Mininet 종료
       │
       ├─ results.csv 중간 저장 (IPv4 n 완료)
       │
       ├─ for run in 1..5:
       │    └─ run_total_v6_experiment(n)       # ipv6_test.py
       │         ├─ Mininet 토폴로지 생성 및 시작
       │         ├─ OVS MLD 스누핑 비활성화 (RA 멀티캐스트 플러딩)
       │         ├─ r1 인터페이스 IPv6 주소 설정
       │         ├─ radvd 설정 파일 생성 및 시작
       │         ├─ n개 쓰레드 동시 시작
       │         │    └─ 각 iot: accept_ra=2 → 폴링(tentative/preferred) → ping6 → T1/T2 기록
       │         ├─ 결과 집계
       │         └─ Mininet 종료
       │
       └─ results.csv 중간 저장 (IPv6 n 완료)

  └─ plot_results.py → graphs/*.png 생성
```

---

## 주요 결과 (Key Results)

| n | IPv4 total_lat | IPv6 total_lat |
|---|---------------|---------------|
| 1 | 1.12 ± 0.02 s | 2.79 ± 0.39 s |
| 5 | 1.17 ± 0.00 s | 2.51 ± 0.20 s |
| 10 | 1.30 ± 0.02 s | 2.54 ± 0.07 s |
| 20 | 1.55 ± 0.09 s | 2.50 ± 0.04 s |
| 50 | 1.96 ± 0.13 s | 2.39 ± 0.02 s |
| 100 | **2.93 ± 0.10 s** | **2.55 ± 0.29 s** |

**주요 발견:**

- **IPv4 addr_lat**: n=1(1.12s) → n=100(2.89s), **약 2.6배 증가** — DHCP 서버 병목 확인
- **IPv6 addr_lat**: n=1~100 전 구간 2.37~2.78s **수평** — SLAAC의 분산형 확장성 확인
- **교차점**: n≈70~80 구간에서 IPv6가 IPv4보다 빠르게 역전
- **성공률**: IPv6 전 구간 100%, IPv4는 n=5(96%), n=20(98%)에서 소수 실패

### 그래프

| 그래프 | 설명 |
|--------|------|
| `graph1_total_latency.png` | n 증가에 따른 total_lat 비교선 (오차막대 포함) |
| `graph2_breakdown.png` | addr_lat / pkt_lat stacked bar (IPv4, IPv6 각각) |
| `graph3_distribution.png` | n=50에서의 total_lat 분포 히스토그램 |
| `graph4_ra_dad.png` | IPv6 RA 대기 시간 vs DAD 지연 비교선 |

---

## 한계 및 주의사항 (Limitations)

| 항목 | 내용 |
|------|------|
| 에뮬레이션 환경 | Mininet은 단일 물리 호스트 위에서 네임스페이스로 격리. 실제 물리 네트워크의 전파 지연, 패킷 손실, 혼잡은 반영되지 않음 |
| 절대 수치 | 실험 목적은 **상대적 스케일링 비교**. 절대 지연 수치는 실제 환경과 다를 수 있음 |
| radvd 간격 | MaxRtrAdvInterval=4s (실제 RFC 기본값 600s). 실제 환경에서는 RA 대기가 훨씬 길어질 수 있음 |
| DAD 오버헤드 | DAD 완료 감지를 폴링(50ms 간격)으로 수행하므로 실제 DAD 완료 시각보다 최대 50ms 지연 포함 |
| CPU 경합 | n=100 시 100개 쓰레드가 단일 코어에서 경합하므로 고부하 환경 특성이 일부 반영됨 |
| warmup 없음 | 각 실험 run은 독립적으로 Mininet을 재시작. OVS 플로우 테이블 warmup 효과 없음 |

---

## 로그 파일

| 파일 | 내용 |
|------|------|
| `/tmp/dhcpd.log` | ISC dhcpd 실행 로그 (DHCP 요청/응답 추적) |
| `/tmp/radvd.log` | radvd 실행 로그 (RA 전송 확인) |
| `/tmp/ipv6_experiment.log` | IPv6 실험 상세 로그 (SLAAC 타임아웃 등) |

---

## 라이선스

MIT License