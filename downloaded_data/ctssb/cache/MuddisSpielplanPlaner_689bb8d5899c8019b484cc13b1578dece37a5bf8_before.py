import unittest

from DataAPI import DataAPI
from GameState import GameState
from TournamentDescriptionClasses import Slot, MatchUp, Result, Game, Team, Location 
import time

divisionId_Swissdraw = 8
def minutesToTime(minutes: int):
    hour = int(minutes / 60)
    restMinutes = int(minutes % 60)
    return hour, restMinutes


class TestConnectionHandling(unittest.TestCase):
    @classmethod
    def setUp(self):
        print("Set Up Test")
        self.instance = DataAPI()

    def test_getListOfSlots(self):
        print("Testing getting list of upcoming slots of swiss draw division")
        slots = self.instance.getListOfUpcomingSlots(divisionId_Swissdraw)
        for slot in slots:
            start = minutesToTime(slot.start)
            end = minutesToTime(slot.end)
            location = slot.locationId
            print(str(start[0]) + ":" + str(start[1]) + " - " + str(end[0]) + ":" + str(end[1]) + " ; " + str(location))
        self.assertGreater(len(slots),0)     
        
    def test_getListOfSlotsAll(self):
        print("Testing getting list of upcoming slots of all division")
        slots = self.instance.getListOfUpcomingSlots(divisionId_Swissdraw,)
        for slot in slots:
            start = minutesToTime(slot.start)
            end = minutesToTime(slot.end)
            location = slot.locationId
            print(str(slot.start) + ":" + str(start[1]) + " - " + str((slot.end)) + ":" + str(end[1]) + " ; " + str(location))
        self.assertGreater(len(slots),0)  
       
        
    def test_getListOfAllTeams(self):
        print("testing getting list of all teams")
        teams = self.instance.getListOfAllTeams(divisionId_Swissdraw)
        for team in teams:
            print(team.name + ", " + team.acronym + ", " + str(team.teamId))
        self.assertGreater(len(teams),0)

    def test_getListOfGames(self):
        print("testing gettingListOfPlayedGames")
        gameStates = [GameState.COMPLETED, GameState.RUNNING]
        self.instance.getListOfGames(divisionId_Swissdraw,8,gameStates)
        print("#####################################################################")

    def test_getGames(self):
        print("testing running game")
        self.instance.getListOfGames(1, GameState.RUNNING)

    def test_getRunningGamesInLocationFromDatabase(self):
        print("testing running game with getting location from db")
        locations = self.instance.getListOfLocations()
        location = locations[0].locationId
        print( location )
        games = self.instance.getListOfGames(GameState.RUNNING, location)
        for game in games:
            print(game.toString())

    def test_getLocations(self):
        print("testing getting Locations")
        locations = self.instance.getListOfLocations()
        for location in locations:
            print(location.toString())

    def test_getScoreboardTexts(self):
        print("testing getting ScoreboardTexts")
        getScoreboardTexts = self.instance.getScoreboardTexts()
        for getScoreboardText in getScoreboardTexts:
            print(getScoreboardText.toString())

    def test_getSwissDrawDivision(self):
        print("testing getting SwissDrawDivisions")
        getSwissDrwawDivisions = self.instance.getSwissDrawDivisions()
        for getSwissDrwawDivision in getSwissDrwawDivisions:
            print(getSwissDrwawDivision.divisionId)

    def test_getFinalizedGameTime(self):
        print("testing getting finalizedGameTime")
        finalizedGameTime = self.instance.getFinalizeGameTime()
        print(finalizedGameTime)


    def test_insertGame(self):
        print("########## testing inserting next games ############")
        teams = self.instance.getListOfAllTeams(divisionId_Swissdraw) # get a list of teams
        result = Result(-1,0,0,0,0)   # set a result
        slots = self.instance.getListOfUpcomingSlots(divisionId_Swissdraw) # get upcompiung slots
        if(len(slots) != 0):
            matchup = MatchUp(teams[0], teams[1])   #set up matchups with 2 (random, the first 2) teams from all teams
            game:Game = Game(matchup,result,slots[0]) #set up game with matchup, result, and the first slot
            self.instance.insertNextGame(game,GameState.PREDICTION,1) # insert nextgames in debug mode (no real insertion in db). don' use second parameter for productive system
        print("no available Slots found")
    @classmethod    
    def tearDownClass(self):
        print("Destruct test")


if __name__ == '__main__':
    unittest.sortTestMethodsUsing = None
    try: unittest.main()
    except SystemExit: pass
