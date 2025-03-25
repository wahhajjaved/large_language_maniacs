__author__ = 'Leo'

from random import randint
from util import roll
from event import (FoodHuntResult, BulletsUsed, VaccinesMade,
    CharacterSoothedResult, CharacterCureResult, CharacterDeath)

class Character(object):
    def __init__(self, name, game, skill_command):
        self.game = game
        self.name = name
        self.insanity = 0
        self.days_infected = 0
        self.is_infected = False
        self.is_alive = True
        self.skill_command = skill_command
        self.game.skill_commands[skill_command] = self.skill
        self.game.food_rations += 2
        self.game.characters.append(self)
        self.game.turn_action_points += 1

    def update(self):
        if roll(25):
            self.insanity += 1

        if self.is_infected:
            self.days_infected += 1
            if self.days_infected == 3:
                self.is_alive = False
        else:
            if roll(25):
                self.is_infected = True
                self.days_infected = 1

        if self.insanity == 5:
            self.is_alive = False

        if self.game.food_rations > 0:
            self.game.food_rations -= 1
        else:
            self.is_alive = False

        if self.is_alive:
            if not self.is_infected:
                self.game.turn_action_points += 1
        else:
            del self.game.skill_commands[self.skill_command]
            return (CharacterDeath(self),)

    def soothe(self):
        self.game.turn_action_points -= 1
        if roll(90):
            self.insanity -= 1
            return (CharacterSoothedResult(self, True),)
        else:
            return (CharacterSoothedResult(self, False),)

    def cure(self):
        self.game.turn_action_points -= 1
        self.game.vaccines -= 1
        self.is_infected = False
        return (CharacterCureResult(self, True),)

    def skill(self):
        raise Exception("skill called on Character base class!")

class Soldier(Character):
    def __init__(self, game):
        super(Soldier, self).__init__("Soldier", game, 'hunt')
        self.game.bullets += 20

    def skill(self):
        self.game.turn_action_points -= 1
        added_food = 0
        bullets_used = 0
        if roll(90) and self.game.bullets > 0:
            bullets_used = randint(1, min(6, self.game.bullets))
            added_food = randint(5, 10)
            self.game.food_rations += added_food
            self.game.bullets -= bullets_used
        return (FoodHuntResult(added_food), BulletsUsed(bullets_used))

class Dog(Character):
    def __init__(self, game):
        super(Dog, self).__init__("Fido", game, 'scavenge')

    def skill(self):
        self.game.turn_action_points -= 1
        added_food = 0
        if roll(60):
            added_food = randint(5, 10)
            self.game.food_rations += added_food
        return (FoodHuntResult(added_food),)

class Psychiatrist(Character):
    def __init__(self, game):
        super(Psychiatrist, self).__init__("Psychiatrist", game, 'therapy')

    def skill(self):
        for i in xrange(self.game.turn_action_points):
            self.game.characters[i].insanity = 0
            self.game.turn_action_points -= 1

class Scientist(Character):
    def __init__(self, game):
        super(Scientist, self).__init__("Scientist", game, 'vaccines')

    def skill(self):
        self.game.turn_action_points -= 1
        vaccines_added = randint(1, 3)
        self.game.vaccines += vaccines_added
        return (VaccinesMade(vaccines_added),)