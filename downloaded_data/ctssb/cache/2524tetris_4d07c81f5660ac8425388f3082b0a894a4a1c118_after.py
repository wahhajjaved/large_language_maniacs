#!/usr/bin/python2
# ece2524 final project - Tetris
# controller class 

import Shape
import Matrix
from Tkinter import *

class Application(Frame):
	_Shapes = []
	_row = 15
	_col = 10
	def __init__(self, master=None):
		self._Matrix = Matrix.Matrix()
		self.master = master	
		Frame.__init__(self, master)
		self.boardHeight = 420
		self.boardWidth = 250
		self.difficulty = 1600
		self.sqSize = 25
		self.voidmove = 0
		self.score_count = 0
		self.increaseDiff = 1
		self.paused = 0
		#print("In init")
		master.minsize(height = self.boardHeight+5, width = self.boardWidth+5)
		master.maxsize(height = self.boardHeight+5, width = self.boardWidth+5)
		master.title("Tetris!")
		self.pack()
		self.menu()
		self._CurShape = Shape.Shape()
		self.scoreText = StringVar()
		
	
	def bindEvents(self):
		self.bind_L_funcID = self.master.bind_all("<Left>", lambda event, arg = -1: self.moveLateral(event, arg))
		self.bind_R_funcID = self.master.bind_all("<Right>", lambda event, arg = 1: self.moveLateral(event, arg))
		self.bind_Up_funcID = self.master.bind_all("<Up>", lambda event, arg = 0: self.moveLateral(event, arg))
		self.bind_r_funcID = self.master.bind_all('r', lambda event, arg = 0: self.moveLateral(event, arg))
		self.bind_D_funcID = self.master.bind_all('<Down>', self.moveDown)
		self.bind_space_funcID = self.master.bind_all('<space>', self.moveBottom)
		self.bind_p_funcID = self.master.bind_all('p', self.pause)
		self._job = self.after(self.difficulty, self.moveDown, 1)
		
		
	def initDraw(self, init = 1):
		if init == 1:
			self.board = Canvas(self, bg = 'gray', height = self.boardHeight, width = self.boardWidth, bd = 0)
			self.scoreBox = Label(self,state=NORMAL, justify=CENTER, textvariable=self.scoreText, fg = 'black')
			self.quitButton = Button(self, text = "Quit", bg = 'black', fg = 'white', command = self.quit)
			self.quitButton.pack(side = BOTTOM)
			self.scoreBox.pack(side = BOTTOM)
		self.scoreText.set("Score: " + str(self.score_count))
		for row in range(self._row):
			for col in range(self._col):
				x1 = col*self.sqSize
				y1 = row*self.sqSize
				x2 = x1+self.sqSize
				y2 = y1 + self.sqSize
				self.board.create_rectangle(x1,y1,x2,y2, fill='orange')

		self.board.pack()
		
	def moveDown(self, timer):
		if self._job is not None:
			self.after_cancel(self._job)
			self._job = None
		self._job = self.after(self.difficulty, self.moveDown, 1)
		if self.voidmove == 1:
                        self._Shapes.append(self._CurShape)
                        self.turnOver()
			ret = 0
		else:
			ret = 1	

		self.removeCurrent()
		self._CurShape.moveDown()
		self.redrawAfter()
		#print self.difficulty
#If setDone is true, add the shape to a list so it can not be easily motified and call for a new piece to be generated in its spot
		
		return ret

	def moveLateral(self, event, direction):
		self.removeCurrent()
		if direction == 0:
			self._CurShape.rotateCC()
                grid = self._CurShape.getLayout()
                row = self._CurShape.getRow()
                col = self._CurShape.getCol()


                for y in range(row - 1, row + 3):
                        for x in range(col - 2, col + 2):
                                if grid[y - (row - 1)][x - (col - 2)] == 2:
                                        if (self._Matrix.getValue(y, x + direction) == 1 or x + direction < 0 or x + direction >= 10 or y + direction >= 15):
						if direction == 0:
							self._CurShape.rotateCW()
						self.redrawAfter()
						return 0
		if direction == 1:
			self._CurShape.moveRight()
		elif direction == -1:
			self._CurShape.moveLeft()
                
		self.redrawAfter()
		
	
	def moveBottom(self, event):
		move = self.moveDown(None)
		while(move == 1):
			move = self.moveDown(None)

	def redrawAfter(self):
		
		grid = self._CurShape.getLayout()
		row = self._CurShape.getRow()
		col = self._CurShape.getCol()
		self.voidmove = 0
		#since the refrence point in Shape is at 2,2 on a 0 based grid, we set that to be 0,0. The for loops go through each box in the 4X4 grid
		for y in range(row - 1, row + 3):
			for x in range(col - 2, col + 2):
#since grid is 0 based, we simply do some math. then check if the current coordinate has a 2 in it.
				if grid[y - (row - 1)][x - (col - 2)] == 2:
#if there is a 2 that means that peace will be moved, this next if statement checks if the value below our block is a stationary block or if the block is on the last block in the game field. If either is true, the block can not continue
					self._Matrix.setValue(y, x, 1)
					if (self._Matrix.getValue(y + 1, x) == 1) or y == 14:
						self.voidmove = 1

						

#Next two clear the old blocks and update to the new postion
		self.reDraw()
		
	def reDraw(self):
		self.board.delete("all")
		for row in range(self._row):
			for col in range(self._col):
				x1 = col*self.sqSize
				y1 = row *self.sqSize
				x2 = x1 + self.sqSize
				y2 = y1 + self.sqSize
				if(self._Matrix.getValue(row, col) == 1):
					self.board.create_rectangle(x1,y1,x2,y2, fill = 'blue')
				else:
					self.board.create_rectangle(x1,y1,x2,y2, fill='orange')
	def turnOver(self):
		#print "turn over"
		self.voidmove = 0
		self.checkBoardforScore()

                grid = self._CurShape.getLayout()
                row = self._CurShape.getRow()
                col = self._CurShape.getCol()


                for y in range(row - 1, row + 3):
                        for x in range(col - 2, col + 2):
                                if grid[y - (row - 1)][x - (col - 2)] == 2:
					if self._Matrix.getValue(y, x) == -1:
						#print "\n \n GAME OVER \n \n"
						if self._job is not None:
							self.after_cancel(self._job)
							self._job = None
						self.gameOver(None)
		self._CurShape = Shape.Shape()

	def addNextShape(self):
		#print "addNextShape"
		self.voidmove = 0
				
		self._CurShape = Shape.Shape()




	def checkBoardforScore(self):
		for row in range(self._row):
			col = 0
			while col < self._col and self._Matrix.getValue(row, col) == 1: 
				col = col +1
			if col == self._col and self._Matrix.getValue(row, col-1) == 1:
				self.score(row)

	def gameOver(self, timer):
		if timer is None:
			if self._job is not None:
				self.after_cancel(self._job)
				self._job = None
			for row in range(self._row):
				for col in range(self._col):
					if (self._Matrix.getValue(row, col) == 1):
						self.board.create_rectangle(col*self.sqSize,row*self.sqSize, col*self.sqSize + self.sqSize, col*self.sqSize + self.sqSize, fill='red')
			self.scoreText.set("GAME OVER, Score: " + str(self.score_count))
			self.after(2000, self.gameOver, 1)
		else:
			self._reset = Button(self, text = "reset", command = self.reset, bg = 'black', fg = 'white', anchor=CENTER)
			self._reset.configure(width = 10)
			self._home = Button(self, text= "Home", command = self.home, bg = 'black', fg = 'white', anchor=CENTER)
			self._home.configure(width = 10)
			resetWind = self.board.create_window(125,190, window = self._reset, anchor=CENTER)
			goHome = self.board.create_window(125,220, window = self._home)
			self.board.pack()

	def home(self):
		self.scoreBox.destroy()
		self.quitButton.destroy()
		self._Matrix.clear()
		self._CurShape = Shape.Shape()
		self._Shapes = []
		self.score_count = 0
		self.voidmove = 0
		self.difficulty = 1600
		self.board.delete("all")
		self.board.destroy()
		self.menu()

		
		
	def unbindEvents(self):
		self.master.unbind_all("<Left>")
		self.master.unbind_all("<Right>")
		self.master.unbind_all("<Up>")
		self.master.unbind_all('r')
		self.master.unbind_all('<Down>')
		self.master.unbind_all('<space>')
		self.master.unbind_all('p')
		if self._job is not None:
			self.after_cancel(self._job)
			self._job = None

	def pause(self, event = None):
		
		self.paused = not self.paused
		if(self.paused):
			self.unbindEvents()
			self.bind_p_funcID = self.master.bind_all('p', self.pause)
			self.scoreText.set("Paused, Score: " + str(self.score_count))

		else:
			self.scoreText.set("Score: " + str(self.score_count))
			self.bindEvents()
	
	
	def reset(self, event=None):
		self._Matrix.clear()
		self._CurShape = Shape.Shape()
		self._Shapes = []
		self.score_count = 0
		self.board.delete("all")
		self.initDraw(0)
		self.voidmove = 0
		if(self.increaseDiff):
			self.difficulty = 1600
		self._job = self.after(self.difficulty, self.moveDown, 1) 
		
		
	def score(self, row_score):
		self.score_count = self.score_count + 10
		for row in range(row_score):
			for col in range(self._col):
				if row_score - row == 0:
					self._Matrix.setValue(0, col, 0)
				else:
					temp = self._Matrix.getValue(row_score - (row+1), col)
					self._Matrix.setValue(row_score - row, col, temp)
		
		self.reDraw()		
		self.scoreText.set("Score: " + str(self.score_count))
		self.updateDifficulty()
		
	def updateDifficulty(self):
		if(self.increaseDiff and self.difficulty > 300):
			self.difficulty = int(self.difficulty*.9)
			if(self.difficulty < 300):
				self.difficulty = 300
		



	def removeCurrent(self):
		grid = self._CurShape.getLayout()
		row = self._CurShape.getRow()
		col = self._CurShape.getCol()
		for y in range(row - 1, row + 3):
			for x in range(col - 2, col + 2):
				if grid[y - (row - 1)][x - (col - 2)] == 2:
					self._Matrix.setValue(y, x, 0)
				
		
	def menu(self):
		self.startGameButton = Button(self, text="Start Game", bg = 'black', fg = 'white', command = self.startGame)
		self.helpButton = Button(self, text = "Help", bg = 'black', fg = 'white', command = self.helpScreen)
		self.quitButton = Button(self, text = "Quit", bg = 'black', fg = 'white', command = self.quit)
		self.startGameButton.pack()
		self.quitButton.pack()
		self.helpButton.pack()
		
	def helpScreen(self):
		self.startGameButton.destroy()
		self.helpButton.destroy()
		self.quitButton.destroy()
		
		self.line1 = Label(self,state=NORMAL,text="Move Left / Right:")
		self.line1.pack()				#left and right
		self.line1E = Label(self,state=NORMAL,text="    Left / Right")
		self.line1E.pack()				#l/r extra
		self.line2 = Label(self,state=NORMAL,text="Rotate Piece:")
		self.line2.pack()				#up and r
		self.line2E = Label(self,state=NORMAL,text="    Up / r")
		self.line2E.pack()				#up/r extra
		self.line3 = Label(self,state=NORMAL,text="Drop Piece 1 Space:")
		self.line3.pack()				#down to move faster
		self.line3E = Label(self,state=NORMAL,text="    Down")
		self.line3E.pack()				#down extra
		self.line4 = Label(self,state=NORMAL,text="Drop Piece to Bottom:")
		self.line4.pack()				#space to drop
		self.line4E = Label(self,state=NORMAL,text="    Space")
		self.line4E.pack()				#space extra
		self.line5 = Label(self,state=NORMAL,text="Pause Game:")
		self.line5.pack()				#pause to drop
		self.line5E = Label(self,state=NORMAL,text="    p")
		self.line5E.pack()				#pause extra
		
		self.backFromHelpButton = Button(self, text = "<< Back", bg = 'black', fg = 'white', command = self.backFromHelp)
		self.backFromHelpButton.pack()
		
	def backFromHelp(self):
		self.line1.destroy()
		self.line1E.destroy()
		self.line2.destroy()
		self.line2E.destroy()
		self.line3.destroy()
		self.line3E.destroy()
		self.line4.destroy()
		self.line4E.destroy()
		self.line5.destroy()
		self.line5E.destroy()
		self.backFromHelpButton.destroy()
		self.menu()
		
	
	
	def startGame(self):
		self.startGameButton.destroy()
		self.helpButton.destroy()
		self.quitButton.destroy()
		
		self.regButton = Button(self, text = "Increasing Difficulty", bg = 'black', fg = 'white', command = self.regPlay)
		self.constButton = Button(self, text = "Constant Difficulty", bg = 'black', fg = 'white', command = self.constantPlay)
		self.backToMainButton = Button(self, text = "<< Back", bg = 'black', fg = 'white', command = self.goBackToMain)
		self.regButton.pack()
		self.constButton.pack()
		
	def regPlay(self):
		self.regButton.destroy()
		self.constButton.destroy()
		self.backToMainButton.destroy()
		self.increaseDiff = 1
		self.initDraw()
		self.bindEvents()
		
	def constantPlay(self):
		self.regButton.destroy()
		self.constButton.destroy()
		self.backToMainButton.destroy()
		self.easyButton = Button(self, text = "Easy", bg = 'black', fg = 'white', command = self.setEasyDiff)
		self.medButton = Button(self, text = "Medium", bg = 'black', fg = 'white', command = self.setMedDiff)
		self.hardButton = Button(self, text = "Hard", bg = 'black', fg = 'white', command = self.setHardDiff)
		self.backFromSetDiff = Button(self,text = "<< Back", bg = 'black', fg = 'white', command = self.goBackFromConst)
		self.easyButton.pack()
		self.medButton.pack()
		self.hardButton.pack()
		self.backFromSetDiff.pack()
	
	
	def goBackFromConst(self):
		self.easyButton.destroy()
		self.medButton.destroy()
		self.hardButton.destroy()
		self.backFromSetDiff.destroy()
		
		self.regButton = Button(self, text = "Increasing Difficulty", bg = 'black', fg = 'white', command = self.regPlay)
		self.constButton = Button(self, text = "Constant Difficulty", bg = 'black', fg = 'white', command = self.constantPlay)
		self.backToMainButton = Button(self, text = "<< Back", bg = 'black', fg = 'white', command = self.goBackToMain)
		self.regButton.pack()
		self.constButton.pack()
		self.backToMainButton.pack()
		
	def goBackToMain(self):
		self.regButton.destroy()
		self.constButton.destroy()
		self.backToMainButton.destroy()
		self.menu()
		
	def quit(self):
		self.master.quit()
		
	def setEasyDiff(self):
		self.difficulty = 1600
		self.startConst()
	def setMedDiff(self):
		self.difficulty = 1000
		self.startConst()
	def setHardDiff(self):
		self.difficulty = 300
		self.startConst()
		
	def startConst(self):
		self.easyButton.destroy()
		self.medButton.destroy()
		self.hardButton.destroy()
		self.backFromSetDiff.destroy()
		self.increaseDiff = 0
		self.initDraw()
		self.bindEvents()
def main():
	root = Tk()
	app = Application(master = root)
	app.mainloop()
	return 0
	
if __name__ == "__main__":
	sys.exit(main())									
