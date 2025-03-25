import unittest
import sqlite3
from pandemicgame import startinggame
from pandemicgame import inaturn

class T( unittest.TestCase ):

# This checks the players have been put in the right starting locations
	def test_setup_sginfect (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.startinglocals (3)
		with sqlite3.connect('pandemic.db') as conn:
                        cursor = conn.cursor()
                        tobedone = """SELECT rstation,player1,player2,player4 FROM boardTBL WHERE name is 'Atlanta'; """
                        cursor.execute( tobedone)
                        answerX = cursor.fetchone ( )
                self.assertEqual(answerX,(1, 1, 1, 0),'Something wrong with research station and player placement')

# This def tests if a table containing a list of countries is created and populated.
	def test_setup_BoardTBL (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name, colour, connect, co1, co5, rcube, bcube, rstation FROM BoardTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
			answer2 = answerX [2]
			answer3 = answerX [3]
			answer4 = answerX [4]
			answer5 = answerX [5]
			answer6 = answerX [6]
			answer7 = answerX [7]
		self.assertEqual(answer0,'Atlanta','The table for countries has no name column.')
		self.assertEqual(answer1,'u','The table for countries has no colour column.')
		self.assertEqual(answer2,2,'The table for countries has no connect column.')
		self.assertEqual(answer3,'Chicago','The table for countries has no co1 column.')
		self.assertEqual(answer4,0,'The table for countries has no co5 column.')
		self.assertEqual(answer5,0,'The table for countries has no rcube column.')
		self.assertEqual(answer6,0,'The table for countries has no bcube column.')
		self.assertEqual(answer7,0,'The table for countries has no rstation column.')

# This def tests that the table with the player deck cards in has been set up
	def test_setup_pdTBL (self):
		sg = startinggame ()
		sg.pdTBL ()
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name,pos FROM pdTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
		self.assertEqual(answer0,'Atlanta','The table for the player deck has no name column.')
		self.assertEqual(answer1,0,'The table for the player deck has no position in the deck column.')

# This def tests that the table with the player deck cards are discarded into has been set up
	def test_setup_pddTBL (self):
		sg = startinggame ()
		sg.pddTBL ('testboard.txt')
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name FROM pddTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
		self.assertEqual(answerX,None,'The table for discarded player cards has no name column.')

# This def tests that the table with the infection deck has been setup.
	def test_setup_idTBL (self):
		sg = startinggame ()
		sg.idTBL('testboard.txt' )
		sg.shufid ( )
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name,pos FROM shufid WHERE pos > 10;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
			tobedone = """SELECT count (*) FROM shufid;"""
			cursor.execute (tobedone)
			answerY = cursor.fetchone ( )
			answer2 = answerY [0]
		self.assertNotEqual(answer0,None,'The table for the infection deck has no name column.')
                self.assertGreater(answer1,0,'The pos of the cards in the infection deck is not right')
                self.assertLess(answer1,501,'The pos of the cards in the infection deck is not right')
		self.assertLess(answer2,55,'There are too many cards in the infection deck')

# This def tests that the table with the infection deck discard pile has been setup.
	def test_setup_iddTBL (self):
		sg = startinggame ()
		sg.iddTBL( )
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name FROM iddTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
		self.assertEqual(answerX,None,'The table for the infection cards to be discarded into has no name column.')

# This def tests the event deck has been setup
	def test_setup_edTBL (self):
		sg = startinggame ()
		sg.edTBL('testevent.txt' )
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name,pos FROM edTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
		self.assertNotEqual(answer0,None,'The table for the event cards has no name column.')
		self.assertNotEqual(answer1,None,'The table for the event cards deck has no position in the deck column.')

# This checks the character cards table has been set up.
	def test_setup_cTBL (self):
		sg = startinggame ()
		sg.cTBL('testcharacter.txt' )
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name FROM cTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
		self.assertEqual(answer0,'Dispatcher','The table for the characters cards has no name column.')

# This checks the set up of the table for the number of cubes of each colour.
	def test_setup_cubesTBL (self):
		sg = startinggame ()
		sg.cubesTBL( )
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT redr,yellowy,blueu,blackb,purplep FROM cubesTBL;'

			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
			answer2 = answerX [2]
			answer3 = answerX [3]
			answer4 = answerX [4]
		self.assertEqual(answer0,24,'The table for cubes has the wrong number of cubes in the red column.')
		self.assertEqual(answer1,24,'The table for cubes has the wrong number of cubes in the yellow column.')
		self.assertEqual(answer2,24,'The table for cubes has the wrong number of cubes in the blue column.')
		self.assertEqual(answer3,24,'The table for cubes has the wrong number of cubes in the black column.')
		self.assertEqual(answer4,24,'The table for cubes has the wrong number of cubes in the purple column.')


# This checks the set up of the table for player2's hand
	def test_setup_player2TBL (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.pddTBL ('testboard.txt')
		sg.edTBL('testevent.txt' )
		sg.shufpd(2)
		sg.player2TBL(2)
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT * FROM player2TBL;'
			cursor.execute(tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			tobedone = 'SELECT * FROM shufpd ORDER BY pos ASC;'
			cursor.execute( tobedone)
			answerY = cursor.fetchone ( )
			answer1 = answerY [0]
		self.assertNotEqual(answer0,None,"""Nothing found in the hand""")
		self.assertNotEqual(answer0,answer1,"""Player 1's hand has cards still in the player deck.""")



# This checks the set up of the table for player3's hand
	def test_setup_player3TBL (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.pddTBL ('testboard.txt')
		sg.edTBL('testevent.txt' )
		sg.shufpd(3)
		sg.player3TBL(3)
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT * FROM player3TBL;'
			cursor.execute(tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			tobedone = 'SELECT * FROM shufpd ORDER BY pos ASC;'
			cursor.execute( tobedone)
			answerY = cursor.fetchone ( )
			answer1 = answerY [0]
		self.assertNotEqual(answer0,None,"""Nothing found in the hand""")
		self.assertNotEqual(answer0,answer1,"""Player 4's hand has cards still in the player deck.""")

# This checks the set up of the table for player4's hand
	def test_setup_player4TBL (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.pddTBL ('testboard.txt')
		sg.edTBL('testevent.txt' )
		sg.shufpd(4)
		sg.player4TBL(4)
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT * FROM player4TBL;'
			cursor.execute(tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			tobedone = 'SELECT * FROM shufpd ORDER BY pos ASC;'
			cursor.execute( tobedone)
			answerY = cursor.fetchone ( )
			answer1 = answerY [0]
		self.assertNotEqual(answer0,None,"""Nothing found in the hand""")
		self.assertNotEqual(answer0,answer1,"""Player 4's hand has cards still in the player deck.""")


# This checks the set up of the table for player1's hand
	def test_setup_player1TBL (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.pddTBL ('testboard.txt')
		sg.edTBL('testevent.txt' )
		sg.shufpd(1)
		sg.player1TBL(1)
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT * FROM player1TBL;'
			cursor.execute(tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			tobedone = 'SELECT * FROM shufpd ORDER BY pos ASC;'
			cursor.execute( tobedone)
			answerY = cursor.fetchone ( )
			answer1 = answerY [0]
		self.assertNotEqual(answer0,None,"""Nothing found in the hand""")
		self.assertNotEqual(answer0,answer1,"""Player 1's hand has cards still in the player deck.""")


	
# This checks the player deck has been shuffled, without epidemic cards included.
	def test_setup_shufpd (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.pddTBL ('testboard.txt')
		sg.edTBL('testevent.txt' )
		sg.shufpd(3)
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT pos FROM shufpd;'
			cursor.execute( tobedone)
			answerX = cursor.fetchall ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
		self.assertNotEqual(answer0,0,'The deck has not shufpdfled correctly.')
		self.assertNotEqual(answer1,0,'The deck has not shufpdfled correctly.')

# This def tests that the table with the game state has been setup.
	def test_setup_gsTBL (self):
		sg = startinggame ()
		sg.gsTBL(3)
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT ir,oc,players FROM gsTBL;'
			cursor.execute( tobedone)
			answerX = cursor.fetchone ( )
			answer0 = answerX [0]
			answer1 = answerX [1]
			answer2 = answerX [2]
		self.assertEqual(answer0,2,'The infection rate is not two. It should be at the start of the game.')
                self.assertEqual(answer1,0,'The number of outbreaks is not 0. It should be.')
                self.assertEqual(answer2,3,'The number of players is not 3. It should be.')

# This def tests the infection of the first 9 cities works right.
	def test_setup_sginfect (self):
		sg = startinggame ()
		sg.BoardTBL ('testboard.txt')
		sg.idTBL('testboard.txt' )
		sg.iddTBL ( )
		sg.shufid ( )
		sg.sginfect ( )
		with sqlite3.connect('pandemic.db') as conn:
			cursor = conn.cursor()
			tobedone = 'SELECT name FROM BoardTBL WHERE rcube = 1 or bcube = 1 or ycube = 1 or pcube = 1 or ucube = 1;'
			cursor.execute( tobedone)
			answerX = cursor.fetchall ( )
			answer1 = answerX [2]
			tobedone = 'SELECT name FROM BoardTBL WHERE rcube = 2 or bcube = 2 or ycube = 2 or pcube = 2 or ucube = 2;'
			cursor.execute( tobedone)
			answerY = cursor.fetchall ( )
			answer2 = answerY [2]
			tobedone = 'SELECT name FROM BoardTBL WHERE rcube = 3 or bcube = 3 or ycube = 3 or pcube = 3 or ucube = 3;'
			cursor.execute( tobedone)
			answerZ = cursor.fetchall ( )
			answer3 = answerZ [2]
		self.assertNotEqual(answer3,None,'3 countries with 3 cubes not found')
                self.assertNotEqual(answer1,None,'3 countries with 1 cubes not found')
                self.assertNotEqual(answer2,None,'3 countries with 2 cubes not found')



# This def tests the infect cities def.
        def test_inaturn_infectcities (self):
                it = inaturn ()
                sg = startinggame ()
                sg.BoardTBL ('testboard.txt')
                sg.idTBL('testboard.txt' )
		sg.iddTBL ()
                sg.shufid ( )
                it.infectcities (2)
                with sqlite3.connect('pandemic.db') as conn:
                        cursor = conn.cursor()
                        tobedone = """SELECT * FROM boardTBL WHERE rcube >= 1 or bcube >= 1 or ycube >= 1 or pcube >= 1 or ucube >= 1; """
                        cursor.execute( tobedone)
                        answerX = cursor.fetchall ( )
                        tobedone = """SELECT * FROM iddTBL; """
                        cursor.execute( tobedone)
                        answerY = cursor.fetchone ( )
                        answer2 = answerY [0]
                        tobedone = """SELECT rcube,bcube,ycube,ucube,pcube FROM boardTBL WHERE name is '%s';""" % (answer2)
                        cursor.execute( tobedone)
                        answerZ = cursor.fetchone ( )
			answer4a = answerZ [0]
			answer4b = answerZ [1]
			answer4c = answerZ [2]
			answer4d = answerZ [3]
			answer4e = answerZ [4]
			answer4 = answer4a + answer4b + answer4c + answer4d + answer4e
                self.assertNotEqual(answerX,None,'Something wrong')
                self.assertEqual(answer4,1,'A city card in the infection discard pile has no infection cubes on')


# This checks the infection deck has been set up
        def test_setup_epTBL (self):
                sg = startinggame ()
                sg.BoardTBL ('testboard.txt')
                sg.pddTBL ('testboard.txt')
                sg.edTBL('testevent.txt' )
		sg.pdTBL ()
                sg.shufpd(3)
                sg.epTBL(5)
                with sqlite3.connect('pandemic.db') as conn:
                        cursor = conn.cursor()
                        tobedone = '''SELECT * FROM shufpd WHERE name = 'Ep2';'''
                        cursor.execute( tobedone)
                        answerX = cursor.fetchone ( )
                        answer1 = answerX [0]
                        answer2 = answerX [1]
		ranswer2 = int(answer2)
                self.assertEqual(answer1,'Ep2','The second epidemic card cannot be found')
                self.assertLess(ranswer2,501,'The pos of the second epidemic card is not right')
