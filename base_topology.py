from mininet.topo import Topo

NUM_SWITCHES = 5

class IoTExperimentTopo(Topo):
    def build(self, n=100, num_switches=NUM_SWITCHES, with_external=False):
        router = self.addHost('r1', ip=None)

        switches = []
        for i in range(1, num_switches + 1):
            s = self.addSwitch(f's{i}')
            switches.append(s)
            # 라우터-스위치 링크에 지연 추가 (현실성 개선)
            self.addLink(router, s, delay='10ms', loss=0.5)

        for i in range(1, n + 1):
            sw_idx = (i - 1) % num_switches
            host = self.addHost(f'iot{i}', ip=None)
            # 호스트-스위치 링크에 지연 추가 (현실성 개선)
            self.addLink(host, switches[sw_idx], delay='5ms', loss=0.1)

        if with_external:
            ext = self.addHost('ext', ip=None)
            # 외부 링크에 지연 추가
            self.addLink(router, ext, delay='15ms', loss=0.5)
