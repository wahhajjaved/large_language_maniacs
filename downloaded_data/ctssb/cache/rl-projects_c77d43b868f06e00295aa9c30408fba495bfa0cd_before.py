import random
from Action import *
import Print


LAMBDA = 0.9
LEARNING_RATE = 0.8
DISCOUNT_FACTOR = 0.95
EPSILON = 0.1


class SarsaLambdaAgent:

	def __init__(self):
		self.qTable = {}
		self.sarsaTable = {}
	
	def learn(self, state, nextState, action, reward, nextChosenAction):
		nextQValue = self.getQValue(nextChosenAction,nextState)
		previousQValue = self.getQValue(action,state) 
		
		delta = reward + DISCOUNT_FACTOR*(nextQValue) - previousQValue
		self.setSarsaValue(action,state,self.getSarsaValue(action,state)+1)
		for a,s in self.sarsaTable.keys(): #Actualizo los diccionarios Q y Sarsa.
			asvalue = self.getSarsaValue(a,s)
			self.setQValue(a,s,self.getQValue(a,s) + LEARNING_RATE*asvalue*delta)   
			self.setSarsaValue(a,s,LAMBDA * asvalue * DISCOUNT_FACTOR)
		
		
	def nextAction(self,state):
		if self.goRandom(): 
			return random.choice(Action.ACTIONS)
		else: 
			qMax = max([self.getQValue(a,state) for a in Action.ACTIONS])	
			return random.choice([a for a in Action.ACTIONS if self.getQValue(a,state)==qMax])

	def goRandom(self):
		return random.random() < EPSILON

	def getQValue(self,action,state):
		return self.qTable.get((action,int(state))) or 0.0 #float!
		
	def setQValue(self,action,state,value):
 		self.qTable[(action,int(state))] = value

	def getSarsaValue(self,action,state):
		return self.sarsaTable.get((action,int(state))) or 0.0 #float!
		
	def setSarsaValue(self,action,state,value):
 		self.sarsaTable[(action,int(state))] = value


	def inspect(self):
		return Print.prnDict(self.qTable) + Print.prnDict(self.sarsaTable)
