#!/bin/bash
# radvd 설정 파일 생성 (멀티스위치 토폴로지)
# 사용법: sudo bash setup_slaac.sh [스위치 수]  (기본값: 5)
# 참고: ipv6_test.py 실행 시 이 파일을 자동으로 덮어씁니다.
K=${1:-5}

conf=""
for i in $(seq 1 "$K"); do
    idx=$((i - 1))
    conf+="interface r1-eth${idx}\n"
    conf+="{\n"
    conf+="    AdvSendAdvert on;\n"
    conf+="    MinRtrAdvInterval 3;\n"
    conf+="    MaxRtrAdvInterval 4;\n"
    conf+="    prefix 2001:db8:${i}::/64\n"
    conf+="    {\n"
    conf+="        AdvOnLink on;\n"
    conf+="        AdvAutonomous on;\n"
    conf+="        AdvRouterAddr on;\n"
    conf+="    };\n"
    conf+="};\n"
done

printf "$conf" > /etc/radvd.conf
echo "✅ radvd 설정 완료: ${K}개 스위치 (2001:db8:1::/64 ~ 2001:db8:${K}::/64)"
