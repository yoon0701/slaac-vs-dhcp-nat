from mininet.topo import Topo

NUM_SWITCHES = 5

class IoTExperimentTopo(Topo):
    def build(self, n=100, num_switches=NUM_SWITCHES, with_external=False):
        router = self.addHost('r1', ip=None)

        switches = []
        for i in range(1, num_switches + 1):
            s = self.addSwitch(f's{i}')
            switches.append(s)
            self.addLink(router, s)

        for i in range(1, n + 1):
            sw_idx = (i - 1) % num_switches
            host = self.addHost(f'iot{i}', ip=None)
            self.addLink(host, switches[sw_idx])

        if with_external:
            ext = self.addHost('ext', ip=None)
            self.addLink(router, ext)
