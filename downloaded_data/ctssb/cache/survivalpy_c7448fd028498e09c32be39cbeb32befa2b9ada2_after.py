__author__ = 'Leo'

from time import sleep
from random import randint

from event import (GameEnd, FireWentOut, BulletsUsed, MonsterAttack,
                   RadioRepairResult, RadioRepairProgress)
from character import Soldier, Dog, Psychiatrist, Scientist
from util import roll

class Game(object):
    def __init__(self):
        self.days = 30
        self.radio_repair_progress = 0
        self.bullets = 0
        self.food_rations = 0
        self.vaccines = 0
        self.characters = []
        self.skill_commands = {}
        self.turn_action_points = 0
        self.fire = 0
        self.infected_someone_today = False

    def update(self):
        self.infected_someone_today = False
        events = []
        self.days -= 1
        if self.days == 0:
            if self.radio_repair_progress >= 50:
                events.append(RadioRepairResult(True))
                events.append(GameEnd(True))
            else:
                events.append(RadioRepairResult(False))
                events.append(GameEnd(False))
            return events

        self.fire -= 1
        if self.fire <= 0:
            events.append(FireWentOut())
            events.append(GameEnd(False))
            return events

        for character in self.characters:
            cevt = character.update()
            for e in cevt:
                events.append(e)

        self.characters = [c for c in self.characters if c.is_alive]
        if len(self.characters) == 0:
            events.append(GameEnd(False))

        if roll(30 - self.days):
            food_stolen = randint(1, min(8, self.food_rations))
            self.food_rations -= food_stolen
            events.append(MonsterAttack(food_stolen))
            if self.bullets > 0:
                bullets_used = randint(1, min(8, self.bullets))
                self.bullets -= bullets_used
                events.append(BulletsUsed(bullets_used))
            else:
                events.append(GameEnd(False))

        return events

def recount_events(events):
    if events is not None:
        for e in events:
            print e
            if isinstance(e, GameEnd):
                exit(0)
            sleep(0.5)

def main():
    game = Game()
    soldier = Soldier(game)
    dog = Dog(game)
    shrink = Psychiatrist(game)
    spook = Scientist(game)

    while True:
        print ("")
        print ("============================================")
        print ("Day %d" % game.days)
        print ("============================================")
        for character in game.characters:
            print ("%s (INS: %d, INF: %s) ['%s']" % (character.name,
                                              character.insanity,
                                              character.is_infected,
                                              character.skill_command))
        print ("")
        print ("Fire strength: %d" % game.fire)
        print ("Radio repair: %d%%" % game.radio_repair_progress)
        print ("You have %d food rations" % game.food_rations)
        print ("You have %d bullets" % game.bullets)
        print ("You have %d vaccines" % game.vaccines)
        print ("You have %d action points" % game.turn_action_points)

        print ("")
        if game.turn_action_points > 0:
            cmd = raw_input('What would you like to do? ').lower().split(' ')
            print ("")
            sleep(0.5)
            if cmd[0] in game.skill_commands and game.turn_action_points > 0:
                events = game.skill_commands[cmd[0]]()
                recount_events(events)
            elif cmd[0] == 'fire' and game.turn_action_points > 0:
                game.fire = 3
                game.turn_action_points -= 1
                print ("You put some wood in the fire.")
            elif (cmd[0] == 'soothe' and len(cmd[1]) > 0 and
                          game.turn_action_points > 0):
                for c in game.characters:
                    if c.name.lower() == cmd[1]:
                        events = c.soothe()
                        recount_events(events)
                        break
            elif (cmd[0] == 'cure' and len(cmd[1]) > 0 and
                          game.turn_action_points > 0 and game.vaccines > 0):
                for c in game.characters:
                    if c.name.lower() == cmd[1]:
                        events = c.cure()
                        recount_events(events)
                        break
            elif cmd[0] == 'radio' and game.turn_action_points > 0:
                game.radio_repair_progress += 1
                game.turn_action_points -= 1
                recount_events([RadioRepairProgress()])
            else:
                print ("You may use character skills, 'fire', 'radio', "
                       "'soothe <name>', 'cure <name>'")

        sleep(1)

        if game.turn_action_points == 0:
            events = game.update()
            recount_events(events)
            print ("")
            sleep(1)
            print ("A new day dawns...")
            sleep(1)

if __name__ == '__main__':
    main()