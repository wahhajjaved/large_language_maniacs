from random import shuffle

class Game(object):
	STATE_JUDGING = 0
	STATE_WAITING_FOR_RED_APPLES = 1
	STATE_FINISHED_ROUND = 2

	def __init__(self, name, red_apples, green_apples):
		self.name = name
		self.red_apples = red_apples[:]
		self.green_apples = green_apples[:]
		self.active_green_apple = None
		self.players = []
		self.master = None
		self.judge = 0
		self.in_progress = False
		self.state = 2

		shuffle(self.red_apples)
		shuffle(self.green_apples)

		print "Game created with {rap} red apples and {gap} green apples".format(rap=len(self.red_apples), gap=len(self.green_apples))

	def start(self):
		self.in_progress = True

	def dealCards(self):
		cards_per_player = 1
		for player in self.players:
			deficit = cards_per_player - len(player.red_apples)
			if deficit > 0:
				for i in xrange(1, deficit):
					player.red_apples.append(self.red_apples.pop())

	def drawGreenCard(self):
		if len(self.green_apples) > 0:
			self.active_green_apple = self.green_apples.pop()
			self.state = Game.STATE_WAITING_FOR_RED_APPLES
			for player in self.players:
				player.active_red_apple = None

	def isReadyToJudge(self):
		ready_players = 0
		for player in self.players:
			if player is self.players[self.judge]:
				continue
			if player.active_red_apple != None:
				ready_players = ready_players + 1
		if ready_players == len(self.players) - 1:
			self.state = Game.STATE_JUDGING
		return self.state

	def startNewRound(self):
		self.in_progress = True
		self.dealCards()
		self.drawGreenCard()
		self.judge = self.judge + 1
		if self.judge >= len(self.players):
			self.judge = 0