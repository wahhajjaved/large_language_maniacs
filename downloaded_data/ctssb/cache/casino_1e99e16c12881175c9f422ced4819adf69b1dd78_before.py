import random # Подключаем библиотеки

cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 'B', 'D', 'K', 'A'] # Колода карт
money = 100 # Начальный баланс игрока

# Вывод разданных карт
def getStatus():
    print('Player:', player, ' Dealer: ', dealer)

# Подсчитывание очков
def getSum(hand):
    sum = 0
    for card in hand:
        if card != 'A':
            if card == 'B' or card == 'D' or card == 'K':
                sum += 10
            else:
                sum += card
    for card in hand:
        if card == 'A':
            if sum > 10:
                sum += 1
            else:
                sum += 11
    return sum

# Раздача карт игроку
def playPlayer():
    while True:
        print(getStatus())
        answer = input(' Want another card? 1 - YES, otherwise - NO: ')
        if answer == '1':
            player.append(random.choice(cards))
            if getSum(player) >= 21:
                break
        else:
            break

# Раздачка карт дилеру
def playDealer():
    while getSum(dealer) < 17:
        dealer.append(random.choice(cards))
    getStatus()

# Определение победителя
def getResult():
    if getSum(dealer) == 21:
        print('Dealer have Black Jack :(')
        return(False)
    elif getSum(player) == 21:
        print('You have Black Jack *_*')
        return(True)
    elif getSum(player) > 21:
        print('You bust :::(')
        return(False)
    elif getSum(dealer) > 21:
        print('Dealer bust T_T')
        return(True)
    elif getSum(player) > getSum(dealer):
        print('You Win!')
        return(True)
    else:
        print('You lost!')
        return(False)

# Алгоритм одной раздачи
def game():
    global player
    global dealer
    player = [random.choice(cards), random.choice(cards)]
    dealer = [random.choice(cards)]
    playPlayer()
    playDealer()
    return getResult()

# Ставка игрока
def betPlayer():
    bet = int(input('Choose your bet: '))
    while bet > money:
        bet = int(input('You don\'t have so much money. Try again: '))
    return bet

# Игра
print("Welcome to our casino!")
while True:
    if money > 0:
        if input('Want to play? 1 - YES, otherwise - NO: ') == '1':
            bet = betPlayer()
            if game() == True:
                money += bet * 0.5
            else:
                money -= bet
            print('Your balance:', money)
        else:
            print('I\'ll see you next time. Your winnings:', money - 100)
            break
    else:
        print('Game Over! Your balance: 0 :(')
        break
