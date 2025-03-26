from ticTacToe import TicTacToeBoard
from neuralNetwork import neuralNetwork

class AITrainer:
    def __init__(self, numberOfAIs):
        self.AIList = []
        self.numberOfAIs = numberOfAIs
        self.numberOfSurvivingAIs = max(2.0,self.numberOfAIs/5)
        for i in range (0,self.numberOfAIs):
            self.AIList.append(self.initializeAI)

    def crank(self):
        newAIList = []
        winner = 0
        for k in range(0,len(self.AIList)):
            for i in range (0,len(self.AIList)-1):
                winner = self.findWinner(self.AIList[i],self.AIList[i+1])
                if winner==2:
                    self.AIList[i],self.AIList[i+1] = self.AIList[i+1],self.AIList[i]

        for i in range (0, self.numberOfSurvivingAIs):
            for j in range (i, self.numberOfSurvivingAIs):
                newAI=self.initializeAI()
                newAI.generateWeightsMatrixFromParents(self.AIList[i],self.AIList[j])
                newAIList.append(newAI)

        self.AIList = newAIList
        self.numberOfSurvivingAIs = max(2, self.numberOfAIs / 5)

    def initializeAI(self):
        newAI = neuralNetwork(9,5,9,9,[])
        return newAI

    def findWinner(self, ai1, ai2):
        gameWinner = 0
        turn = 1
        answer = 0
        gameBoardReturnString = ""
        gameBoard = TicTacToeBoard()
        while not gameWinner:
            aiInput = gameBoard.returnInputForAi()
            self.transformInput(aiInput, turn)
            if turn==1:
                answer=ai1.answer(aiInput)
            else:
                answer=ai2.answer(aiInput)
            gameBoardReturnString=gameBoard.move(answer/3+1,answer%3+1)
            if gameBoardReturnString == "Player 1 won":
                gameWinner=1
            elif gameBoardReturnString == "Player 2 won":
                gameWinner=2
            elif gameBoardReturnString == "Invalid move":
                if turn == 1:
                    gameWinner = 2
                elif turn == 2:
                    gameWinner = 1
            turn=turn^3
        return gameWinner

    def transformInput(self, input, gameState):
        if gameState == 2:
            gameState = -1
        for i in range (0, len(input)):
            if input[i]=="X":
                input[i]=10000*gameState
            elif input[i]=="O":
                input[i]=-10000*gameState