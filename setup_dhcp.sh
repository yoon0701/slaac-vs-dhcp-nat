#!/bin/bash
# DHCP 설정 파일 생성 (멀티스위치 토폴로지)
# 사용법: sudo bash setup_dhcp.sh [스위치 수]  (기본값: 5)
# 참고: ipv4_test.py 실행 시 이 파일을 자동으로 덮어씁니다.
K=${1:-5}

conf="default-lease-time 600;\nmax-lease-time 7200;\n"
for i in $(seq 1 "$K"); do
    conf+="subnet 10.0.${i}.0 netmask 255.255.255.0 {\n"
    conf+="  range 10.0.${i}.2 10.0.${i}.254;\n"
    conf+="  option routers 10.0.${i}.1;\n"
    conf+="}\n"
done

printf "$conf" > /etc/dhcp/dhcpd.conf
echo "✅ DHCP 설정 완료: ${K}개 스위치 (10.0.1.0/24 ~ 10.0.${K}.0/24)"
