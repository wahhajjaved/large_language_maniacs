import unittest

from domain import decide_points, decide_bonus_points, group_players, decide_movement, group_players

class PointSystemTestCase(unittest.TestCase):

    def test_four_player_group(self):
        scores = [4,3,2,1]

        self.assertEqual(3, decide_points(scores, 4))
        self.assertEqual(1, decide_points(scores, 2))
        self.assertEqual(2, decide_points(scores, 3))
        self.assertEqual(0, decide_points(scores, 1))

    def test_three_player_group(self):
        scores = [4,3,2]

        self.assertEqual(3, decide_points(scores, 4))
        self.assertEqual(2, decide_points(scores, 3))
        self.assertEqual(0, decide_points(scores, 2))

    def test_two_player_group(self):
        scores = [4,3]

        self.assertEqual(3, decide_points(scores, 4))
        self.assertEqual(0, decide_points(scores, 3))

class BonusPointSystemTest(unittest.TestCase):
    def test_two_players_bonus_point_to_second_player(self):
        scores = [9,3]

        self.assertEqual(1, decide_bonus_points(scores, 3))
        self.assertEqual(0, decide_bonus_points(scores, 9))

    def test_two_players_bonus_point_to_first_player(self):
        scores = [10,3]

        self.assertEqual(0, decide_bonus_points(scores, 3))
        self.assertEqual(1, decide_bonus_points(scores, 10))

    def test_four_player_two_actual_bonus_points(self):
        scores = [9,3,0,0]

        self.assertEqual(1, decide_bonus_points(scores, 3))
        self.assertEqual(0, decide_bonus_points(scores, 9))
        self.assertEqual(0, decide_bonus_points(scores, 0))

        scores = [10,3,0,0]

        self.assertEqual(0, decide_bonus_points(scores, 3))
        self.assertEqual(1, decide_bonus_points(scores, 10))
        self.assertEqual(0, decide_bonus_points(scores, 0))

    def test_three_players_bonus_point_to_first_player(self):
        scores = [9,5,3]

        self.assertEqual(0, decide_bonus_points(scores, 5))
        self.assertEqual(0, decide_bonus_points(scores, 3))
        self.assertEqual(1, decide_bonus_points(scores, 9))

    def test_three_players_bonus_point_to_last_player(self):
        scores = [9,6,3]

        self.assertEqual(1, decide_bonus_points(scores, 3))
        self.assertEqual(0, decide_bonus_points(scores, 6))
        self.assertEqual(0, decide_bonus_points(scores, 9))

    def test_four_players_three_actualbonus_points(self):
        scores = [9,5,3,0]

        self.assertEqual(0, decide_bonus_points(scores, 5))
        self.assertEqual(0, decide_bonus_points(scores, 3))
        self.assertEqual(1, decide_bonus_points(scores, 9))
        self.assertEqual(0, decide_bonus_points(scores, 0))

        scores = [9,6,3,0]

        self.assertEqual(1, decide_bonus_points(scores, 3))
        self.assertEqual(0, decide_bonus_points(scores, 6))
        self.assertEqual(0, decide_bonus_points(scores, 9))
        self.assertEqual(0, decide_bonus_points(scores, 0))

    def test_four_players_bonus_point_to_first_player(self):
        scores = [9,3,2,1]

        self.assertEqual(1, decide_bonus_points(scores, 9))
        self.assertEqual(0, decide_bonus_points(scores, 3))
        self.assertEqual(0, decide_bonus_points(scores, 2))
        self.assertEqual(1, decide_bonus_points(scores, 1))

    def test_four_players_bonus_point_to_second_player(self):
        scores = [9,6,4,1]

        self.assertEqual(0, decide_bonus_points(scores, 9))
        self.assertEqual(1, decide_bonus_points(scores, 6))
        self.assertEqual(1, decide_bonus_points(scores, 4))
        self.assertEqual(0, decide_bonus_points(scores, 1))
    
    def test_four_players_bonus_point_to_third_player(self):
        scores = [9,6,4,3]

        self.assertEqual(0, decide_bonus_points(scores, 9))
        self.assertEqual(0, decide_bonus_points(scores, 6))
        self.assertEqual(1, decide_bonus_points(scores, 4))
        self.assertEqual(1, decide_bonus_points(scores, 3))

class SetupWeekTestCase(unittest.TestCase):

    def player(self, group, name, points):
        return {'name': name, 'league_points': points, 'total_points': 0}

    def test_decide_movement_in_four_player_group(self):
        players = [self.player(1,'j',10), self.player(1,'k',8), self.player(1,'l',12), self.player(1,'m',6)]

        decide_movement(players)

        self.assertEqual('up', players[0]['direction'])
        self.assertEqual('up', players[2]['direction'])
        self.assertEqual('down', players[1]['direction'])
        self.assertEqual('down', players[3]['direction'])

    def test_decide_movement_in_three_player_group(self):
        players = [self.player(1,'j',10), self.player(1,'k',8), self.player(1,'l',12)]

        decide_movement(players)

        self.assertEqual('same', players[0]['direction'])
        self.assertEqual('down', players[1]['direction'])
        self.assertEqual('up', players[2]['direction'])

    def test_decide_movement_in_two_player_group(self):
        players = [self.player(1,'j',10), self.player(1,'k',8)]

        decide_movement(players)

        self.assertEqual('up', players[0]['direction'])
        self.assertEqual('down', players[1]['direction'])

    def test_decide_groups_three_players(self):
        group1 = [self.player(1,'j',10), self.player(1,'k',8), self.player(1,'l',12)]
        group2 = [self.player(2,'a',10), self.player(2,'b',8), self.player(2,'c',12)]
        groups = {1: group1, 2: group2}
        
        new_group = group_players(groups)

        self.assertEqual(2, len(new_group))
        self.assertItemsEqual(new_group[1]['players'], [group1[0], group1[2], group2[2]])
        self.assertItemsEqual(new_group[2]['players'], [group1[1], group2[0], group2[1]])

    def test_decide_groups_four_players(self):
        group1 = [self.player(1,'j',10), self.player(1,'k',8), self.player(1,'l',12), self.player(1,'m',6)]
        group2 = [self.player(2,'a',10), self.player(2,'b',8), self.player(2,'c',12), self.player(2,'d',6)]
        groups = {1: group1, 2: group2}
        
        new_group = group_players(groups)

        self.assertEqual(2, len(new_group))
        self.assertItemsEqual(new_group[1]['players'], [group1[0], group1[2], group2[0], group2[2]])
        self.assertItemsEqual(new_group[2]['players'], [group1[1], group1[3], group2[1], group2[3]])
