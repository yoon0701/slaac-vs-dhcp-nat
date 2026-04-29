from mininet.net import Mininet
from mininet.node import OVSController, OVSSwitch, Node
from mininet.topo import Topo
from mininet.log import setLogLevel
import time

class IoTExperimentTopo(Topo):
    def build(self, n=100, with_external=False):
        s1 = self.addSwitch('s1')
        router = self.addHost('r1', ip='10.0.0.1/8')
        self.addLink(router, s1)

        for i in range(1, n + 1):
            host = self.addHost(f'iot{i}', ip=None)
            self.addLink(host, s1)

        if with_external:
            ext = self.addHost('ext', ip=None)
            self.addLink(router, ext)

def start_experiment(num_devices):
    topo = IoTExperimentTopo(n=num_devices)
    net = Mininet(topo=topo, controller=OVSController, waitConnected=True)
    net.start()
    print(f"\n✅ --- {num_devices}개의 IoT 기기 및 라우터 구성 완료 ---")
    time.sleep(2)

if __name__ == '__main__':
    setLogLevel('info')
    start_experiment(50)
