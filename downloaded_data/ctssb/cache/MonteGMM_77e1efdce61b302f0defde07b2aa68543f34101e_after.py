
import numpy as np
from MFCCArrayGen import getCorpus, getIndiviudalData, emotions, speakers

# from sklearn.metrics import confusion_matrix
from RobustLikelihoodClass import Likelihood

import sys, os

def BayesProb(utterance, numMixtures, means, diagCovs, weights):
    """

    Given the MCMC values from a run, calculate probability of belonging to that class

    :param utterance: np.array of shape [size][dim]
    :param numMixtures:
    :param means: np.array [numMCMCRuns][numMixtures][dim]
    :param diagCovs: np.array [numMCMCRuns][numMixtures][dim]
    :param weights: np.array [numMCMCRuns][numMixtures]
    :return:
    """
    sys.stdout = open(os.devnull, "w")
    llEval = Likelihood(utterance, numMixtures=8)
    sys.stdout = sys.__stdout__

    prob = 0

    for i in xrange(means.shape[0]):
        prob+= llEval.loglikelihood(means[i], diagCovs[i], weights[i])
    # print prob/means.shape[0]

    return prob/means.shape[0]

def main(speakerIndex=0):
    y_test = []
    y_pred = []
    speakerIndex = 0
    numMixtures = 8

    import cPickle

    results = {}

    for emotion in emotions:
        filename = "../SpeechMCMC/{}-{}.txt".format(emotion, speakers[speakerIndex])
        print filename

        results[emotion] = {}

        with open(filename) as f:
            MCMCmeans, MCMCcovs, MCMCweights = cPickle.load(f)

        for testEmotion in emotions:
            testCorpus = getIndiviudalData(testEmotion, speakers[speakerIndex])

            print "Actual Emotion: {}".format(testEmotion)

            emotRes = np.zeros(len(testCorpus))
            i = 0

            for utterance in testCorpus:
                ll = -BayesProb(utterance, 8, MCMCmeans, MCMCcovs, MCMCweights)
                emotRes[i] = ll
                i+=1

            results[emotion][testEmotion] = emotRes

    #Search for max

    for actualEmotion in emotions:
        valList = []
        for k in results.keys():
            lls = results[k][actualEmotion]
            valList.append(lls.reshape(len(lls),1))

        valList = np.hstack(valList)
        print valList

        assert (valList.shape[1] ==len(emotions))

        emotIndex = valList.argmax(1)

        classifiedEmotions =  [emotions[i] for i in emotIndex]

        TrueEmotes = [actualEmotion] * valList.shape[0]

        y_test.extend(TrueEmotes)
        y_pred.extend(classifiedEmotions)

    #some Measure of inference

    print y_test
    print y_pred






if __name__ == '__main__':
    main(0)