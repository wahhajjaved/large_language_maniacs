class Character:
    def __init__(self):
        self.dexterity = self.ability()
        self.wisdom = self.ability()
        self.constitution = self.ability()
        self.strength = self.ability()
        self.intelligence = self.ability()
        self.charisma = self.ability()
        self.hitpoints = (10- modifier(self.constitution))
    #find sum top 3 dice
    def ability(self):
        import random
        #generate list of 4 random dice numbers
        randnums = [random.randint(1,6) for i in range(4)]
        #find the min of those 4 numbers
        minrand = int(min(randnums))
        #sum the dice and subtract the min value to give sum of top 3 dice
        sumrandnums = int(sum(randnums) - minrand)
        return(sumrandnums)
    
def round_down(n, decimals=0):
    import math
    multiplier = 10 ** decimals
    return math.floor(n * multiplier) / multiplier

def modifier(c):    
    modified = round_down((c - 10)/2)
    return modified









