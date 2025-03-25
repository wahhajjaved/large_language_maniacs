from __future__ import print_function

def menu():
    print()
    print ("Welcome to Connect 4")
    print ("Choose versus are computer")
    print("1: Computer")
    print("2: Versus")
    print()

def createArray(size):
    return [None] * size

def createBoard():
    m = createArray(6)
    for r in range(0,6,1):
        m[r] = createArray(7)
    for r in range(0,6):
        for c in range(0,7):
            m[r][c] = '[O]'
    return m

def printBoard(m):
    for r in range(0,6):
        for c in range(0,7):
            print(m[r][c],end="")
        print()
    print(' 0  1  2  3  4  5  6')
    return



#def versus():

def choice1(colNum,board):
    rowNum = 5
    while rowNum >= 0:
        if board[rowNum][colNum] == '[O]':
            board[rowNum][colNum] = '[R]'
            return board
        rowNum = rowNum - 1
    return board

def choice2(colNum,board):
    rowNum = 5
    while rowNum >= 0:
        if board[rowNum][colNum] == '[O]':
            board[rowNum][colNum] = '[B]'
            return board
        rowNum = rowNum - 1
    return board

def checkDiagnol(board):
    winner = False

    return winner

def checkVertical(board):
    winner = False

    return winner

def checkHorizontal(board):
    winner = False
    
    return winner

def isGameOver(board):
    winner = False
    if checkDiagnol(board):
        return True
    if checkVertical(board):
        return True
    if checkHorizontal(board):
        return True

def main():
    play = True
    menu()
    choice = int(input("Which choice? "))
    print()
    m = createBoard()
    printBoard(m)
    while play == True:
        print()
        colNum = int(input("Player 1 choose a row "))
        if colNum > 6:
            print ("Out of range choose number from 0-6")
            colNum = int(input("Which row? "))
        m = choice1(colNum,m)
        printBoard(m)
        print()
        colNum = int(input("Player 2 choose a row "))
        if colNum > 6:
            print ("Out of range choose number from 0-6")
            colNum = int(input("Which row? "))
        m = choice2(colNum,m)
        printBoard(m)

main()
