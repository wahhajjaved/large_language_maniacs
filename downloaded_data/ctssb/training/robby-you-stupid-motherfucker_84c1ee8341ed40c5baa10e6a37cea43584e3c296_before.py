import os
from Parameters import *
from MultipleSessions import *
from Robby import *
import random


class Generation:
    robots = []

    def __init__(self, id, robots=None):
        self.id = id
        if robots == None:
            for i in range(POPULATION_SIZE):
                self.robots.append(Robby.getRandomRobby())
        else:
            self.robots = robots

    def getRouletteWheelSelection(self, count):

        # your code goes here ... (TODO #4)
        # return a number between [0, count-1]
        # search for roulette wheel selection on google.

        return 0

    def getScore(self):
        rVal = 0.0
        for i in range(len(self.robots)):
            m = MultipleSessions(self.robots[i])
            rVal = rVal + m.run()
        return rVal / len(self.robots)

    def applyEvolution(self):
        tuples = []
        totalScore = 0.0

        MultipleSessions.refreshGrids()
        for i in range(len(self.robots)):
            m = MultipleSessions(self.robots[i])
            score = m.run()
            totalScore = totalScore + score
            tuples.append( (self.robots[i], score) )

        tuples.sort(key=lambda x: x[1], reverse=True)
        normalizedScore = totalScore / len(self.robots)
        bestScore = tuples[0][1]

        childRobots = []
        # your code goes here ... (TODO #5)
        # fill the childRobots array with POPULATION_SIZE children
        # using getRouletteWheelSelection() and Robby.giveBirth()

        return Generation(self.id + 1, childRobots), normalizedScore, bestScore
