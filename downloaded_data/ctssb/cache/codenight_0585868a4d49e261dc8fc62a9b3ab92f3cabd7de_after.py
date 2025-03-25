#!/usr/bin/env python
import random

#print rules. def RULES

def MENU():
    print('''
    (1) Deposit $1,000 to your account
    (2) Start playing!
    (3) Print game rules
    (4) Exit game
    ''')

#draw board.
def drawBoard(results, bet):
    a = bet
    print('''...PLAYER HAND...||...BANKER HAND...
.................||.................
''', results[0], '||', results[1], '''
.................||.................
''')

#strings calling out the winner
WIN = ['Player wins!',
'Banker wins!',
'TIE! Pays 9:1!',
'DRAGON! bankers push, dragon pays 40:1!!!',
'PANDA! panda 25:1 and players win!!!']

#current money total
def availMon(totMon, wages):
    aMon = totMon - wages
    return aMon

#add money
def dep(amt, acct):
    acct += amt
    return acct

#check if no more money
def lose(totMon):
    if totMon <= 0:
        print('You are out of money, please deposit more.')
        MENU()

#create shuffled shoe, n is number of decks
def shoe(n):
    decks = []
    for i in range(n):
        for j in 'A23456789TJQK':
            for k in 'shcd':
                decks.append(j+k)
    random.shuffle(decks)
    return decks

#burn first card
def burn(shoe):
    c = dealC(shoe)
    if c[0] in 'JQKA':
        for i in range(4):
            dealC(shoe)
    elif c[0] in '23456789':
        for j in range(int(c[0]) - 1):
            dealC(shoe)
    else:
        for k in range(9):
            dealC(shoe)
    #print(c, len(shoe))
    return c, len(shoe)

#check valid bets, either True for valid or False for invalid:
def placeBet(mon):
    betValid = False
    while(betValid == False):
        b = int(input())
        #what if not a number? error
        if (b % 5 == 0 and 0 <= b and b <= mon):
            betValid = True
            break
        else:
            print('enter a valid number')
    mon -= b
    return (mon, b)

#ask for player bets.bet is [0 = player, 1 = banker, 2 = tie, 3 = dragon, 4 = panda8]
def wager(totMon):
    spots = ['PLAYER','BANKER','TIE','DRAGON','PANDA']
    bet = [0,0,0,0,0]
    a = 'x'
    while(a not in 'PpBb'):
        print('Do you want to bet on PLAYER(p) or BANKER(b)?')
        a = input()
    print('Place a valid bet, increments of $5')
    if(a in 'Pp'):
        print('How much will you bet on PLAYER?', end=' ')
        printMoneyRemaining(totMon, True)
        (totMon, bet[0]) = placeBet(totMon)
        print(bet[0], 'on PLAYER')
    else:
        print('How much will you bet on BANKER?', end=' ')
        printMoneyRemaining(totMon, True)
        (totMon, bet[1]) = placeBet(totMon)
        print(bet[1], 'on BANKER')
    for i in range(2,5):
        if (totMon == 0):
            break
        print('You may place a', spots[i], 'bet', end='; ')
        printMoneyRemaining(totMon, False)
        (totMon, bet[i]) = placeBet(totMon)
        print(bet[i], 'on', spots[i])
    wages = sum(bet)
    return [bet, wages]

def printMoneyRemaining(m, isCap):
    if isCap:
        print('Y', end='')
    else:
        print('y', end='')
    print('ou have $', m, 'remaining.')

#draw one card
def dealC(aShoe):
    tempC = aShoe[0]
    del aShoe[0]
    return tempC

#check for burn card at end of shoe, burn at 50 cards left
def lastHand(shoe):
    bc = False
    if len(shoe) == 50:
        bc = True

#deal the 2 hands
def dealHand(shoe):
    playerH = []
    bankerH = []
    #cards hit per side
    numP = 0
    numB = 0
    #natural hand?
    nat = False

    for i in range(4):
        if i == 0 or i == 2:
            playerH.append(dealC(shoe))
            numP += 1
        else:
            bankerH.append(dealC(shoe))
            numB += 1
    p = value(playerH)
    b = value(bankerH)
    if(p in [8, 9]) or (b in [8, 9]):
        nat = True
        #print('natural', p, 'to', b)
        #print(numP, numB)
    #not natural keep hitting
    if (nat == False):
    #player house way
        if p < 6:
            playerH.append(dealC(shoe))
            numP += 1
        #bankers third card, if no player hit, then house way
        if (numP == 2 and b < 6):
            bankerH.append(dealC(shoe))
            numB += 1
            #print('house way')
        elif (numP == 3 and b < 7):
            #print(b, playerH[2])
            numB += 1
            if (b in [0,1,2]):
                bankerH.append(dealC(shoe))
                #print('always hit')
            elif (b == 3 and playerH[2][0] != '8'):
                bankerH.append(dealC(shoe))
                #print('stay on 8')
            elif (b == 4 and playerH[2][0] in '234567'):
                bankerH.append(dealC(shoe))
                #print('hit 2-7')
            elif (b == 5 and playerH[2][0] in '4567'):
                bankerH.append(dealC(shoe))
                #print('hit 4-7')
            elif (b == 6 and playerH[2][0] in '67'):
                bankerH.append(dealC(shoe))
                #print('hit 6,7')
            else:
                numB -= 1
                #print('stay')
    p = value(playerH)
    b = value(bankerH)
    return [playerH, bankerH, numP, numB, p, b]

#add hand values
def value(hand):
    handVal = 0
    for i in hand:
        if i[0] in '23456789':
            j = int(i[0])
            handVal += j
        elif i[0] in 'A':
            handVal += 1
    hV1 = handVal % 10
    return hV1



#determine win/lose, arguments from def dealHand numPlayerCards, numBankerCards, valPlayer, valBanker
def detWinLose(numP, numB, p, b):
    #who wins, 0 = player, 1 = banker, 2 = tie, 3 = dragon, 4 = player/panda
    whoWins = 0
    if (p == 8) and (p > b) and (numP == 3):
        whoWins = 4
        print(WIN[4])
    elif (b == 7) and (b > p) and (numB == 3):
        whoWins = 3
        print(WIN[3])
    elif p == b:
        whoWins = 2
        print(WIN[2])
    elif p > b:
        whoWins = 0
        print(WIN[0])
    elif b > p:
        whoWins = 1
        print(WIN[1])
    return whoWins

#determine money won or lost, bet = [player, bank, tie, dragon, panda]
def moneyBack(bet, whoWins, availMon):
    #chips = total money returned INCLUDING original bets
    chips = 0
    if whoWins == 4:
        chips += ((26 * bet[4]) + (2 * bet[0]))
    elif whoWins == 3:
        chips += ((41 * bet[3]) + bet[1])
    elif whoWins == 2:
        chips += ((10 * bet[2]) + bet[0] + bet[1])
    elif whoWins == 1:
        chips += (2 * bet[1])
    elif whoWins == 0:
        chips += (2 * bet[0])
    totMon = availMon + chips
    return totMon

if __name__ == "__main__":
    #start money is 0
    totMon = 0

    totMon = dep(20, totMon)
    print('You have $', totMon, 'in chips.')

    p = wager(totMon)
    print(p)
    a = availMon(totMon, p[1])
    print(a)

    newShoe = shoe(8)
    burn(newShoe)
    results = dealHand(newShoe)

    print(results)
    w = detWinLose(results[2], results[3], results[4], results[5])
    totMon = moneyBack(p[0], w, a)
    print(totMon)
