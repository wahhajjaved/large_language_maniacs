from pymorphous import *

class BlueNeighborCount(Device):
    def run(self):
        let([(x, 1)], sum_hood(self.nbr(x)))
        
        
spawn_cloud(num_devices = 1000, klass=BlueNeighborCount)