from pymorphous import *
# the device to run

class BlueConsensusDemo(ExtrasDevice):
    """
    Consensus demo from paper
    """
    def run(self, epsilon):
        let([(x, 1 if once(random(0,50)) else 0)], 
            self.blue(self.consensus(epsilon, init)))

# stuff to run the simulation

spawn_cloud(num_devices=1000, klass=BlueConsensusDemo, args=[0.02])

