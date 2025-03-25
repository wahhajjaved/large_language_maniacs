import unittest
from src.character import Character

class TestCharacter(unittest.TestCase):
    def setUp(self):
        self.character = Character()
        self.character.xp = 250
        self.body = Character.BODY_STAT_NAME

    def test_add_xp(self):
        self.character.addXP(250)
        self.assertEqual(self.character.xp, 500)

    def test_remove_xp(self):
        self.character.removeXP(250)
        self.assertEqual(self.character.xp, 0)

    def test_increase_stat(self):
        self.character.increaseBaseStat(self.body, 5)
        self.assertEqual(self.character.baseStat(self.body), 10)

    def test_decrease_stat(self):
        self.character.decreaseBaseStat(self.body, 5)
        self.assertEqual(self.character.baseStat(self.body), 0)

    def test_buff_stat(self):
        self.character.buffStat(self.body, 5)
        self.assertEqual(self.character.buffsOn(self.body), 5)

    def test_debuff_stat(self):
        self.character.buffStat(self.body, 5)
        self.character.debuffStat(self.body, 3)
        self.assertEqual(self.character.buffsOn(self.body), 2)

    def test_total_stat(self):
        self.character.buffStat(self.body, 5)
        self.character.debuffStat(self.body, 3)
        self.assertEqual(self.character.statValue(self.body), 7)

    def test_max_hp(self):
        self.assertEqual(self.character.maxLife(), 25)

    def test_injure_player(self):
        self.assertEqual(self.character.currentLife, 25)
        self.character.injure(5)
        self.assertEqual(self.character.currentLife, 20)

    def test_heal_player(self):
        self.assertEqual(self.character.currentLife, 25)
        self.character.injure(5)
        self.assertEqual(self.character.currentLife, 20)
        self.character.heal(5)
        self.assertEqual(self.character.currentLife, 25)

    def test_cant_overheal(self):
        self.assertEqual(self.character.currentLife, 25)
        self.character.injure(5)
        self.assertEqual(self.character.currentLife, 20)
        self.character.heal(10)
        self.assertEqual(self.character.currentLife, 25)
