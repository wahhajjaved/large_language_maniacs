import core
import random


class CardGenerator(object):
    '''Generates creature-type card objects'''
    nameList = []
    abilityList = []

    def __init__(self, maxPower, maxDefence, balancer, cardCount):
        self.InitNames()
        self.InitAbilities()
        self.maxPower = maxPower
        self.maxDefence = maxDefence
        self.balancer = balancer
        self.cardCount = cardCount
        self.Generate()

    def Generate(self):
        workDeck = []
        print("Starting card generation...")
        for i in self.cardCount:
            workName = self.nameList[randint(len(self.nameList))]
            workAbility = self.abilityList[randint(len(self.abilityList))]
            workPower = randint(1, self.maxPower)
            workDefence = randint(1, self.maxDefence)
            workID = randint(1, (self.cardCount * 100))
            workCost = int(((workPower + workDefence) / self.balancer) +
                           (workAbility.cost / self.balancer))
            workID = core.cCards.Creature(workname, workCost, workPower,
                                          workDefence, workAbility)
            workDeck.append(workID)
        print("Card generation complete. /n Saving card list...")
        self.Save(workDeck)

    def Save(self, deck):
        with open('CardGenerator\cardList.csv', 'a') as file:
            for card in deck:
                file.write(card + "\n")

    def InitNames(self):
        print("Initialising namelist...")
        with open('CardGenerator\nameList.csv', 'rt') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
            for row in spamreader:
                name = ""
                for word in row:
                    name = word
                self.nameList.append(name)
        print("Namelist initialised.")

    def InitAbilities(self):
        print("Initialising abilitylist...")
        with open('CardGenerator\abilityList.csv', 'rt') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
            for row in spamreader:
                name = ""
                cost = 0
                cache = 0
                for word in row:
                    if cache == 0:
                        name = word
                        cache += 1
                    elif cache == 1:
                        cost = word
                name = core.cAbility.Ability(name, cost)
                abilityList.append(name)
        print("Abilitylist initialised.")
