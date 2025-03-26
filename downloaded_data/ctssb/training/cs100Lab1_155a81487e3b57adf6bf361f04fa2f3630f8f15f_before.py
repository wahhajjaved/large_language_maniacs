# -*- coding: utf-8 -*-
"""
Created on Tue Oct 10 11:26:00 2017

Holds the code for the UI

@author: Isaac Galang
"""

from tkinter import *

class Interface:
    def __init__(self, onClick, gameLogic):
        '''
        onClick is a function of 4 variables, the x and y coordinates of the clicked cell, the gameLogic state, and the Interface (self)
        '''
        self.frame = Frame(Tk())
        self.frame.pack()
        self.board = [[' ' for _ in range(3)] for _ in range(3)]
        self.buttonGrid = [[Button(self.frame,
                                   text=' ',
                                   width=3,
                                   height=2,
                                   font=("Courier", 44),
                                   command=lambda i=i, j=j: onClick(i, j, self, gameLogic)).grid(row=i, column=j) for i in range(3)] for j in range(3)]
        self.frame.mainloop()
    
    def updateState(self, newBoard):
        self.board = newBoard
        for r in range(3):
            for c in range(3):
                self.buttonGrid[r][c].config(text=newBoard[r][c])

def testFunc(x, y):
    print(str(x)+str(y))
if __name__ == '__main__':
    Interface(testFunc)