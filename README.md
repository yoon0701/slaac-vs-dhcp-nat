# IPv4 DHCP+NAT vs IPv6 SLAAC: IoT Initial Connection Latency Comparison

Measuring and comparing the initial connection latency of IPv4 (DHCP+NAT) and IPv6 (SLAAC) as the number of IoT devices scales up, using Mininet network emulation on AWS EC2.

---

## Scenario

Imagine a smart home, industrial site, or campus where dozens to hundreds of IoT devices **power on simultaneously** and attempt their first connection to the internet.

| Aspect | IPv4 | IPv6 |
|--------|------|------|
| Address assignment | DHCP 4-way handshake (Discover → Offer → Request → ACK) via centralized server | SLAAC: RS → RA → auto-generate address → DAD |
| Internet connectivity | NAT (MASQUERADE via iptables) | Direct routing with global unicast address |
| Server load | Increases with device count | Distributed — each device generates its own address |

**Key question:** As the number of devices grows, which protocol delivers the first packet to the internet faster?

---

## Network Topology

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

- **r1** — Software router (Linux network namespace). Runs dhcpd, radvd, and iptables NAT.
- **s1–s5** — Five OVS bridge switches. IoT devices are distributed across them in round-robin fashion.
- **iot1–iotN** — IoT device hosts under test (n = 1, 5, 10, 20, 50, 100).
- **ext** — External internet server. Responds to ping requests.

**IPv4 subnet layout (per switch)**
| Switch | Subnet | DHCP Pool |
|--------|--------|-----------|
| s1 | 10.0.1.0/24 | 10.0.1.2 – 10.0.1.254 |
| s2 | 10.0.2.0/24 | 10.0.2.2 – 10.0.2.254 |
| … | … | … |
| s5 | 10.0.5.0/24 | 10.0.5.2 – 10.0.5.254 |

**IPv6 prefix layout (per switch)**
| Switch | Prefix |
|--------|--------|
| s1 | 2001:db8:1::/64 |
| s2 | 2001:db8:2::/64 |
| … | … |
| s5 | 2001:db8:5::/64 |

---

## Measurement Methodology

A separate thread is spawned per IoT device. Three timestamps are recorded:

```
T1         T_assigned        T2
|                |             |
|←── addr_lat ──→|←─ pkt_lat ─→|
|←──────────── total_lat ──────→|
```

| Timestamp | Meaning |
|-----------|---------|
| **T1** | Address request begins (accept_ra=2 set for IPv6, or `dhclient` invoked for IPv4) |
| **T_assigned** | A valid IP address appears on the interface (detected by polling every 50 ms) |
| **T2** | `ping -c 1` completes |

| Metric | Formula | Meaning |
|--------|---------|---------|
| `addr_lat` | T_assigned − T1 | Time to acquire an IP address |
| `pkt_lat` | T2 − T_assigned | First packet delivery (ARP/ND + NAT entry creation + RTT) |
| `total_lat` | T2 − T1 | End-to-end initial connection latency |

**IPv6-only additional metrics**

| Metric | Formula | Meaning |
|--------|---------|---------|
| `ra_wait` | T_ra − T1 | Time from RS send to RA receive (first tentative address appears) |
| `dad_lat` | T_assigned − T_ra | DAD (Duplicate Address Detection) duration (~1 s fixed) |

> `total_lat` is averaged over **successful devices only**. Timed-out devices (30 s) are excluded to avoid inflating the average.

---

## File Structure

```
slaac-vs-dhcp-nat/
├── base_topology.py      # Mininet topology definition (IoTExperimentTopo)
├── ipv4_test.py          # IPv4 experiment: DHCP+NAT latency measurement
├── ipv6_test.py          # IPv6 experiment: SLAAC latency measurement
├── run_all.py            # Full experiment runner (n × protocol × N_RUNS)
├── plot_results.py       # Result visualization (generates graphs/)
├── experiment_env.txt    # Environment info and key findings summary
├── results.csv           # Aggregated results (mean ± std per n per protocol)
├── results_raw.csv       # Per-device raw measurements
└── graphs/
    ├── graph1_total_latency.png   # n vs total_lat comparison line graph
    ├── graph2_breakdown.png       # addr_lat / pkt_lat stacked bar chart
    ├── graph3_distribution.png    # total_lat distribution histogram at n=50
    └── graph4_ra_dad.png          # IPv6 RA wait vs DAD latency line graph
```

---

## Environment

| Item | Value |
|------|-------|
| Platform | AWS EC2 (Linux 6.17.0-1007-aws) |
| Python | 3.12.3 |
| Mininet | Open vSwitch 3.3.4 |
| DHCP server | isc-dhcpd 4.4.3-P1 |
| RA daemon | radvd 2.19 |

**Experiment parameters**

| Parameter | Value |
|-----------|-------|
| n (device count) | 1, 5, 10, 20, 50, 100 |
| N_RUNS (repetitions per n) | 5 |
| NUM_SWITCHES | 5 |
| TIMEOUT | 30 s |
| radvd MaxRtrAdvInterval | 4 s (shortened for experiment; RFC default is 600 s) |

---

## Prerequisites

```bash
# Mininet and Open vSwitch
sudo apt-get install -y mininet openvswitch-switch

# ISC DHCP server
sudo apt-get install -y isc-dhcp-server

# radvd (IPv6 Router Advertisement daemon)
sudo apt-get install -y radvd

# Python dependencies
pip3 install matplotlib
```

---

## How to Run

> **Important:** Mininet directly manipulates Linux network namespaces and OVS kernel modules. **All experiment scripts must be run with `sudo`.** On AWS EC2, `root` or `sudo` access is required.

### Full experiment

```bash
# Runs all n values × both protocols × 5 repetitions (~30–60 minutes)
sudo python3 run_all.py
```

Results are saved incrementally to `results.csv` and `results_raw.csv` after each (n, protocol) pair completes. If the process crashes, already-saved results are preserved.

### Individual experiment

```bash
# IPv4 only (n=50 by default)
sudo python3 ipv4_test.py

# IPv6 only (n=50 by default)
sudo python3 ipv6_test.py
```

### Visualization

```bash
# After experiments complete (sudo not required)
python3 plot_results.py
# → Saves 4 PNG files to graphs/
```

### Why sudo is required

| Operation | Reason |
|-----------|--------|
| Mininet startup | Creates Linux network namespaces (CAP_NET_ADMIN) |
| OVS bridge creation | Manipulates OVS kernel module via `ovs-vsctl` |
| iptables NAT rules | Modifies kernel netfilter tables |
| dhcpd startup | Binds to port 67/UDP (privileged port) |
| radvd startup | Uses raw ICMPv6 sockets |
| `/etc/radvd.conf` write | Modifies system configuration file |

---

## Execution Flow

```
run_all.py
  └─ for n in [1, 5, 10, 20, 50, 100]:
       ├─ for run in 1..5:
       │    └─ run_total_v4_experiment(n)          # ipv4_test.py
       │         ├─ Build and start Mininet topology
       │         ├─ Configure r1 interface IPs (10.0.i.1/24 per switch)
       │         ├─ Set up iptables MASQUERADE NAT
       │         ├─ Generate dhcpd.conf and start dhcpd in r1 namespace
       │         ├─ Start n threads simultaneously
       │         │    └─ each iot: flush IP → dhclient → poll → ping → record T1/T2
       │         ├─ Aggregate results
       │         └─ Stop Mininet
       │
       ├─ Append IPv4 results to results.csv / results_raw.csv
       │
       ├─ for run in 1..5:
       │    └─ run_total_v6_experiment(n)          # ipv6_test.py
       │         ├─ Build and start Mininet topology
       │         ├─ Disable OVS MLD snooping (flood RA multicast to all ports)
       │         ├─ Configure r1 interface IPv6 addresses (2001:db8:i::1/64)
       │         ├─ Generate radvd.conf and start radvd in r1 namespace
       │         ├─ Start n threads simultaneously
       │         │    └─ each iot: flush global addr → accept_ra=2 → poll tentative/preferred → ping6 → record T1/T2
       │         ├─ Aggregate results
       │         └─ Stop Mininet
       │
       └─ Append IPv6 results to results.csv / results_raw.csv
```

---

## Key Results

| n | IPv4 total_lat (s) | IPv6 total_lat (s) |
|---|-------------------|-------------------|
| 1 | 1.12 ± 0.02 | 2.79 ± 0.39 |
| 5 | 1.17 ± 0.00 | 2.51 ± 0.20 |
| 10 | 1.30 ± 0.02 | 2.54 ± 0.07 |
| 20 | 1.55 ± 0.09 | 2.50 ± 0.04 |
| 50 | 1.96 ± 0.13 | 2.39 ± 0.02 |
| 100 | **2.93 ± 0.10** | **2.55 ± 0.29** |

**Key findings:**

- **IPv4 addr_lat** grows from 1.12 s (n=1) to 2.89 s (n=100) — a **~2.6× increase**, confirming DHCP server bottleneck under load.
- **IPv6 addr_lat** stays flat at 2.37–2.78 s across all n — confirming SLAAC's distributed scalability.
- **Crossover point** near n≈70–80: beyond this point IPv6 becomes faster end-to-end.
- **Success rate**: IPv6 maintains 100% across all n. IPv4 shows minor failures at n=5 (96%) and n=20 (98%).

---

## Limitations

| Item | Detail |
|------|--------|
| Emulated environment | Mininet runs everything on a single physical host using Linux namespaces. Real-world propagation delay, packet loss, and congestion are not modeled. |
| Absolute latency values | The goal is **relative scaling comparison**, not absolute benchmarking. Actual values will differ on real hardware. |
| radvd RA interval | MaxRtrAdvInterval=4 s (RFC default is 600 s). In production, RA wait would be significantly longer without Router Solicitation triggering an immediate response. |
| Polling overhead | T_assigned is detected by polling every 50 ms, so measured DAD duration may be up to 50 ms longer than the actual kernel completion time. |
| CPU contention | At n=100, 100 threads compete on the same host CPU, introducing scheduling jitter not present in real distributed deployments. |
| No warmup | Each run restarts Mininet from scratch. OVS flow table warmup effects are absent. |

---

## Log Files

| File | Contents |
|------|----------|
| `/tmp/dhcpd.log` | ISC dhcpd runtime log (DHCP request/response trace) |
| `/tmp/radvd.log` | radvd runtime log (RA transmission confirmation) |
| `/tmp/ipv6_experiment.log` | IPv6 experiment detail log (SLAAC timeouts, namespace checks) |

---

## License

MIT License
