import numpy as np

class Neuron(object):
    """description of class"""

    def __init__(self, iw):
        self.inputWeights = iw

    def __str__(self):
        return 'Weights:' + str(self.inputWeights)

    def learn(self):
        return 0

    def evaluate(self, x):
        inputs = [1]
        inputs.extend(x)
        if len(inputs) == len(self.inputWeights):
            value = np.dot(inputs, self.inputWeights)
            return (1/(1 + np.exp(-value)))
        return None
        


