from random import randint
import traceback

class Player:
    VERSION = "8"


    def firstBetIndex(self, ourHoleCards, bet_index, current_buy_in):
        if bet_index == 0:
            if (ourHoleCards[0]["rank"]) == (ourHoleCards[1]["rank"]):
                 return 10000
            else:
                return self.checkIfGotHighCards(ourHoleCard, current_buy_in)


    def checkIfGotHighCards(self, ourHoleCards, current_buy_in):

        if ("A" in ourHoleCards.values()) or ("K" in ourHoleCards.values()) or ("Q" in ourHoleCards.values()) or ("J" in ourHoleCards.values()):
            return 10000
        else:
            return 0

    
    def betRequest(self, game_state): 
        try:
            betIndex = game_state["bet_index"]
            players = game_state["players"]
            communityCards = game_state["community_cards"]
            dealer = game_state["dealer"]
            current_buy_in = game_state["current_buy_in"]
            
           
            for player in players:
                if player["name"] == "Spookers": 
                    ourHoleCards = player["hole_cards"]
                    if (player["id"] == (dealer+1) % (len(players))) or (player["id"] == (dealer+2) % (len(players))):
                        if betIndex == 0:
                            if current_buy_in > player["bet"]:
                                if (self.firstBetIndex(ourHoleCards, betIndex, current_buy_in)) > 0:
                                    return ((current_buy_in) - (player["bet"]))
                    else:
                        return self.firstBetIndex(ourHoleCards, betIndex, current_buy_in)


        except Exception, e:
            print("--------------------------------------------------- E R R O R ---------------------------------------------------")
            print(str(e))
            print(traceback.print_exc())
            return randint(500,1000)
        
        return 100
            

    def showdown(self, game_state):
        pass


    def checkFromSecondBet(self, communityCards, ourHoleCards):
        if ourHoleCards[0]["rank"] == ourHoleCards[1]["rank"]:
                for card in community_cards:
                    if (card["rank"] == ourHoleCards[0]["rank"]) or (card["rank"] == ourHoleCards[1]["rank"]):
                        return 10000
                    else:
                        return self.checkIfGotHighCards(ourHoleCards)
        return self.checkIfGotHighCards(ourHoleCards)