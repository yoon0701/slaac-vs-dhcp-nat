cat <<EOF > /etc/dhcp/dhcpd.conf
default-lease-time 600;
max-lease-time 7200;
subnet 10.0.0.0 netmask 255.0.0.0 {
  range 10.0.1.0 10.0.250.254;
  option routers 10.0.0.1;
}
EOF