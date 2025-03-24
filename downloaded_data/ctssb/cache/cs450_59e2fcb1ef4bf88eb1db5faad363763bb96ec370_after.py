import csv
import matplotlib.pyplot as plt
import numpy as np
import scipy.cluster.hierarchy as hac
from sklearn.cluster import KMeans

class MarMite:
    team1 = ""
    team2 = ""
    lastTeamFound = [0, 0]

    def loadcsv(self, filename):
        f = open(filename)
        lines = csv.reader(f)
        dataset = list(lines)
        f.close()
        return dataset
    #grab the name of the team and shove it into the first entry of the table
    # for each entry of the season, count the wins, the losses
    # send the number of wins and losses into the table for the names entry


    def generateTable(self, csvName):
        namesofTeams = self.loadcsv("teams.csv")
        seasonTable = self.loadcsv(csvName)
        # declare a table, that will hold the name of team, their wins, and their losses
        tableOfWinnersAndLosers = []
        # for each team in the teams csv file
        for row in range(len(namesofTeams)):
            ID = namesofTeams[row][0]
            teamName = namesofTeams[row][1]
            wins = 0
            losses = 0
            for col in range(len(seasonTable)):
                if seasonTable[col][2] == ID:
                    wins += 1
                elif seasonTable[col][4] == ID:
                    losses += 1
            totalPlayed = wins + losses
            if totalPlayed != 0:
                ratio = int(wins / totalPlayed * 100)
            elif wins > 0:
                ratio = 100
            else:
                ratio = 0
            entry = [ID, teamName, wins, losses, totalPlayed, ratio]
            if totalPlayed == 0:
                pass
            else:
                tableOfWinnersAndLosers.append(entry)

        return tableOfWinnersAndLosers

    def getTrend(self, season):
        # build the table for the seasons
        if season == "A" or season == 'a':
            previousSeason = "A"
        elif season != "regular_season_results.csv":
            previousSeason = chr(ord(season) - 1)
        else:
            season = "S"
            previousSeason = "R"
        previousSeasonGood = self.checkSeason([self.team1, self.team2], previousSeason, True)
        # build the tables, then check each one for the data.
        season1Results = []
        season2Results = []
        seasonTable1 = self.generateTable("season " + season + " results.csv")
        seasonTable2 = []
        for row in range(len(seasonTable1)):
            if seasonTable1[row][0] == self.team1:
                season1Results.append(seasonTable1[row])
            if seasonTable1[row][0] == self.team2:
                season1Results.append(seasonTable1[row])
        if previousSeasonGood == False:
            seasonTable2 = self.generateTable("season " + previousSeason + " results.csv")
            for row in range(len(seasonTable2)):
                if seasonTable2[row][0] == self.team1:
                    season2Results.append(seasonTable2[row])
                if seasonTable2[row][0] == self.team2:
                    season2Results.append(seasonTable2[row])
        newTable = []
        for row in range(len(season1Results)):
            if seasonTable2[row][-1]:
                entry = [season1Results[row][0], season1Results[row][1], season1Results[row][-2], season1Results[row][-1], season2Results[row][-1] - season1Results[row][-1]]
            else:
                entry = [season1Results[row][0], season1Results[row][1], season1Results[row][-2], season1Results[row][-1], 0]
            newTable.append(entry)
        return newTable

    def checkTeam(self, teamName, listOfTeams):
        teamsName = ""
        for row in listOfTeams:
            if row[1] == teamName:
                teamsName = row[0]
                break
            elif row[0] == teamName:
                teamsName = row[0]
                break
        return teamsName

    def checkSeason(self, teams, season, prevChecker):
        self.lastTeamFound[0] = 0
        self.lastTeamFound[1] = 0
        answer = True
        if season == "regular_season_results.csv":
            csvName = "regular_season_results.csv"
        else:
            csvName = "season " + season + " results.csv"
        try:
            seasonTable = self.loadcsv(csvName)
        except:
            answer = True
            return answer

        for i in range(len(teams)):
            for row in range(len(seasonTable)):
                if seasonTable[row][2] == teams[i] or seasonTable[row][4] == teams[i]:
                    self.lastTeamFound[i] = 1
                    break

        if prevChecker:
            answer = False
        else:
            if self.lastTeamFound[0] == 1 and self.lastTeamFound[1] == 1:
                answer = False
        return answer

    def tourneyPredictor(self, listOfTeams):
        notFinished = True
        seasonTable = []
        season = ''
        while notFinished:
            accuracy = 0
            quit = input("Press enter to continue making predictions or Type 'quit'")
            if quit == 'quit':
                notFinished = False
            else:
                prompt = True
                while prompt:
                    season = input("Enter a Tournament Season (A-R): ")
                    try:
                        seasonTable = self.loadcsv("tourney " + season + " results.csv")
                        prompt = False
                    except:
                        print("Invalid Season, please try Entering a value as directed")
                        prompt = True
                print("Running predictions...")
                for row in range(len(seasonTable)):
                    self.team1 = seasonTable[row][2]
                    self.team2 = seasonTable[row][4]
                    if (self.team1 == 'wteam'):
                        pass
                    else:
                        trendData = self.getTrend(season)
                        winningID = predictDaWinna(trendData)
                        if self.team1 == winningID:
                            accuracy += 1
                accuracy = int(accuracy / len(seasonTable) * 100)
                print("Over-all Accuracy of Predictions: ", accuracy, "%")

    def getAllTimeStats(self, tableOfGames, teams):
        firstTeamGamesPlayed = 0
        firstwins = 0
        firstTeamRatio = 0
        secondTeamGamesPlayed = 0
        secondwins = 0
        secondTeamRatio = 0
        for i in range(len(teams)):
            for row in range(len(tableOfGames)):
                if tableOfGames[row][2] == teams[i] or tableOfGames[row][4] == teams[i]:
                    if i == 0:
                        firstTeamGamesPlayed += 1
                        if tableOfGames[row][2] == teams[i]:
                            firstwins += 1
                    if i == 1:
                        secondTeamGamesPlayed += 1
                        if tableOfGames[row][2] == teams[i]:
                            secondwins += 1
        firstTeamRatio = int((firstwins / firstTeamGamesPlayed) * 100)
        secondTeamRatio = int((secondwins / secondTeamGamesPlayed) * 100)
        return firstTeamGamesPlayed, firstTeamRatio, secondTeamGamesPlayed, secondTeamRatio

    def collectInput(self, listOfTeams):
        notFinished = True
        season = ""
        while notFinished:
            quit = input("Press enter to continue making predictions or Type 'quit'")
            if quit == 'quit':
                notFinished = False
            else:
                prompt = True
                while prompt:
                    name = input("Team 1: ")
                    goodName = self.checkTeam(name, listOfTeams)
                    if goodName != "":
                        self.team1 = goodName
                        prompt = False
                prompt = True
                while prompt:
                    name = input("Team 2: ")
                    goodName = self.checkTeam(name, listOfTeams)
                    if goodName != "":
                        self.team2 = goodName
                        prompt = False
                prompt = True
                teams = [self.team1, self.team2]
                while prompt:
                    answer = input("Would you like to run against all history(all)? or enter a specific March Madness Season(season)")
                    if answer != "season":
                        season = "regular_season_results.csv"
                    else:
                        season = input("Select a Season between A and S): ")
                    prompt = self.checkSeason(teams, season, False)

                predictionData = self.getTrend(season)
                # correct the ratio for all of time. change [2]# games played and [3] ratio
                if season == "regular_season_results.csv":
                    seasonTable = self.loadcsv(season)
                else:
                    seasonTable = self.loadcsv("season " + season + " results.csv")
                predictionData[0][2], predictionData[0][3], predictionData[1][2], predictionData[1][3] = self.getAllTimeStats(seasonTable, teams)
                predictDaWinna(predictionData)


def predictDaWinna(data):
    daWinna = ""
    #current season ratio
    team1Ratio = data[0][3]
    team2Ratio = data[1][3]
    differenceInGamesPlayed = abs(data[0][2] - data[1][2])
    differenceInRatio = abs(team1Ratio - team2Ratio)
    if differenceInRatio > 5: #clear difference in performance of teams
        if team1Ratio > team2Ratio: # higher performance will most likely win
            daWinna = data[0][0]
            print("Based off of our calculations... " + data[0][1] + " will most likely win.")
        else:
            daWinna = data[1][0]
            print("Based off of our calculations... " + data[1][1] + " will most likely win.")
    else:
        team1Trend = data[0][4]
        team2Trend = data[0][4]
        if team1Trend < team2Trend:  # team 1 has improved more
            if differenceInGamesPlayed > 8:  #
                daWinna = data[0][0]
                print("Based off of our calculations... " + data[0][1] + " will most likely win.")
            else:
                daWinna = data[1][0]
                print("Based off of our calculations... " + data[1][1] + " will most likely win.")
        else:  #team 2 improved more...
            if differenceInGamesPlayed > 8:
                daWinna = data[1][0]
                print("Based off of our calculations... " + data[1][1] + " will most likely win.")
            else:
                daWinna = data[0][0]
                print("Based off of our calculations... " + data[0][1] + " will most likely win.")
    return daWinna

def main(): #TODO: get season from user, teams too.
    MarchMadHatter = MarMite()
    teams = MarchMadHatter.loadcsv("teams.csv")
    ans = input("To predict a games outcome between two teams enter (predict), or to find Tournament accuracy press(enter):")
    if ans == "predict":
        MarchMadHatter.collectInput(teams)
    else:
        MarchMadHatter.tourneyPredictor(teams)
    # table = generateTable(Results)
    # npTable = np.array(table)
    # kmeans = KMeans(init='k-means++', n_clusters=4, n_init=10).fit(table)
################################################################################################################
    # #KMEANS PLOT
    # # Step size of the mesh. Decrease to increase the quality of the VQ.
    # h = .1  # point in the mesh [x_min, x_max]x[y_min, y_max].
    # xmax = table[0][0]
    # xmin = table[0][0]
    # ymax = table[0][1]
    # ymin = table[0][1]
    # for i in range(len(table)):
    #     if table[i][0] > xmax:
    #         xmax = table[i][0]
    #     if table[i][0] < xmin:
    #         xmin = table[i][0]
    #     if table[i][1] > ymax:
    #         ymax = table[i][1]
    #     if table[i][1] < ymin:
    #         ymin = table[i][1]
    #
    # # Plot the decision boundary. For that, we will assign a color to each
    # x_min, x_max = xmin, xmax
    # y_min, y_max = ymin, ymax
    # xx, yy = np.meshgrid(np.arange(x_min, x_max, h), np.arange(y_min, y_max, h))
    #
    # # Obtain labels for each point in mesh. Use last trained model.
    # Z = kmeans.predict(np.c_[xx.ravel(), yy.ravel()])  #hac.linkage(npTable)#
    #
    # # Put the result into a color plot
    # Z = Z.reshape(xx.shape)
    # plt.figure(1)
    # plt.clf()
    # plt.imshow(Z, interpolation='nearest',
    #            extent=(xx.min(), xx.max(), yy.min(), yy.max()),
    #            cmap=plt.cm.Paired,
    #            aspect='auto', origin='lower')
    #
    # for row in range(len(table)):
    #     plt.plot(table[row][0], table[row][1], 'bo', markersize=5)
    # # Plot the centroids as a white X
    # centroids = kmeans.cluster_centers_
    # plt.scatter(centroids[:, 0], centroids[:, 1],
    #             marker='x', s=169, linewidths=5,
    #             color='r', zorder=5)
    # plt.title('Tournament Results 1995 - 2013')
    # plt.show()                                  #KMEANS PLOT
    ###############################################################################################################
    #************************************************************************
    # these were used to construct the csv's, can be uncommented to do so again.
    #************************************************************************
    #seasonResults = loadcsv("regular_season_results.csv")
    #tourneyResults = loadcsv("tourney_results.csv")
    #tableToWrite = buildTableOfWinLoss(seasonResults)
    #anotherTableToWrite = buildTableOfWinLoss((tourneyResults))

    # This code writes the table generated above, to a csv file.
    # The csv was created before using the UI but the content was
    # added with this code.            "a" is for append, w is write, but overwrites csv data
    # with open("tourneyTeamTotals.csv", "a") as textFile: # change this to whatever csv file you want, after you'd added the file to the project
    #     textfileWriter = csv.writer(textFile, lineterminator='\n') #without this lineterminator set, it skips a line between entries.
    #     for row in anotherTableToWrite:
    #         textfileWriter.writerow(row)
    #
    # textFile.close()


main()