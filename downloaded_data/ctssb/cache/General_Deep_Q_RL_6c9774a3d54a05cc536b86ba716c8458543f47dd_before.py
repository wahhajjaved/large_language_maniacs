import numpy as np
from mpl_toolkits.axes_grid1 import host_subplot
import mpl_toolkits.axisartist as AA
import matplotlib.pyplot as plt
import theano
from base_classes import Environment
from IPython import embed
import copy

class MyEnv(Environment):
    def __init__(self, rng):
        """ Initialize environment

        Arguments:
            rng - the numpy random number generator            
        """
        # Defining the type of environment
        self._nActions = 2                     # The environment allows two different actions to be taken at each time step
        self._lastPonctualObservation = [0, 0] # At each time step, the observation is made up of two elements, each scalar
        self._batchDimensions = [(6,), (1,)]   # We consider a belief state made up of an history of 
                                               # - the last six for the first element obtained 
                                               # - the last one for the second element
        
        self._randomState = rng
                
        # Building a price signal with some patterns
        self._priceSignal=[]
        for i in range (1000):
            price = np.array([0.,0.,0.,-1.,0.,1.,0., 0., 0.])
            price += self._randomState.uniform(0, 3)
            self._priceSignal.extend(price.tolist())
       
        self._priceSignalTrain = self._priceSignal[:len(self._priceSignal)/2]
        self._priceSignalValid = self._priceSignal[len(self._priceSignal)/2:]
        self._prices = None
        self._counter = 1
                
    def reset(self, mode):
        """ Reset environment for a new episode.

        Arguments:
            testing - whether we are in test mode or train mode (boolean)  
        """
        if mode == -1:
            self.prices = self._priceSignalTrain
        else:
            self.prices = self._priceSignalValid
            
        
        self._lastPonctualObservation = [self.prices[0], 0]

        self._counter = 1
        return [[0, 0, 0, 0], 0]
        
        
    def act(self, action, mode):
        """
        Performs one time step on the environment
        Arguments:
            action - chosen action (integer)
            testing - whether we are in test mode or train mode (boolean)  
        Returns:
           reward - obtained reward for this transition
        """
        reward = 0
        
        if (action == 0 and self._lastPonctualObservation[1] == 1):
            reward = self.prices[self._counter-1] - 0.5
        if (action == 1 and self._lastPonctualObservation[1] == 0):
            reward = -self.prices[self._counter-1] - 0.5

        self._lastPonctualObservation[0] = self.prices[self._counter]
        self._lastPonctualObservation[1] = action

        self._counter += 1
        
        return reward



    def summarizePerformance(self, mode, test_data_set):
        """
        This function is called at every PERIOD_BTW_SUMMARY_PERFS.
        Arguments:
            test_data_set
        """
    
        print "Summary Perf"
        
        observations = test_data_set.observations()
        prices = observations[0]
        invest = observations[1]
        
        steps=np.arange(len(prices))
        steps_long=np.arange(len(prices)*10)/10.
        
        #print steps,invest,prices
        host = host_subplot(111, axes_class=AA.Axes)
        plt.subplots_adjust(right=0.9, left=0.1)
    
        par1 = host.twinx()
    
        host.set_xlabel("Time")
        host.set_ylabel("Price")
        par1.set_ylabel("Investment")
    
        p1, = host.plot(steps_long, np.repeat(prices,10), lw=3, c = 'b', alpha=0.8, ls='-', label = 'Price')
        p2, = par1.plot(steps, invest, marker='o', lw=3, c = 'g', alpha=0.5, ls='-', label = 'Investment')
    
        par1.set_ylim(-0.09, 1.09)
    
    
        host.axis["left"].label.set_color(p1.get_color())
        par1.axis["right"].label.set_color(p2.get_color())
    
        plt.savefig("plot.png")
    
        plt.draw()
        plt.show()

    def batchDimensions(self):
        return self._batchDimensions

    def nActions(self):
        return self._nActions

    def inTerminalState(self):
        return False

    def observe(self):
        return np.array(self._lastPonctualObservation)

                


def main():
    # Can be used for debug purposes
    rng = np.random.RandomState(123456)
    myenv = MyEnv(rng)
    myenv.reset(False)
    
    myenv.act(1, False)
    myenv.act(1, False)
    myenv.act(0, False)
    myenv.act(0, False)
    myenv.act(1, False)

    print myenv._state
    
if __name__ == "__main__":
    main()
