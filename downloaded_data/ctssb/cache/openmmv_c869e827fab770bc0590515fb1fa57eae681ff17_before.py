# Note: "keep value" self.f we use to men the portion of the total amount given
# by a single supporter.  In usual STV keep value means the portion of a ballot's
# support given by a single supporter.  These are obviously related by quota.
# In our case, using portion of share would mean that keep values would change
# when adding a new funding level.  For example: suppose each of 25 supporters gives
# $4 to get a project to $100.  Then the keep value is 4%.  That percentage also
# works at $50 (each supporter give 4%, that is $2).  However, portion of ballot
# changes: if a share is $8, each supporter gives 50% of the ballot to get the
# project to $100; but 25% to get it to 50 and 25% to get it from 50 to 100.

# TODO: epsilons & fudge factors
# TODO: ballot priors
# TODO: ties

import itertools

from projectBallots import *
from STV import *

class ProjectElection(RecursiveSTV):

    def __init__(self, b):
        self.method = "MMV"
        RecursiveSTV.__init__(self, b)
        self.setOptions(threshName=("Hare", "Static", "Fractional"))

###

    def setOptions(self, debug=None, strongTieBreakMethod=None, prec=None,
                 threshName=None):
        """Called by user before start of election to set options."""
        if threshName != None:
            assert threshName[0]=="Hare"
        RecursiveSTV.setOptions(self,debug,strongTieBreakMethod,prec,threshName)

###

    def initialize(self):
        """Called at start of election."""
        RecursiveSTV.initialize(self)
        self.meek = False
        self.share = self.p * self.b.nResources / self.b.nBallots
        self.supportLimit = self.p
        if self.b.supportObligation!=None and self.b.supportObligation>0:
            self.supportLimit = self.p * 100 / self.b.nBallots / self.b.supportObligation + 1
        self.minimum = [self.p*self.b.minimum[c] for c in xrange(self.b.nProj)]
        self.maximum = [self.p*self.b.maximum[c] for c in xrange(self.b.nProj)]
        self.winAmount = []
        self.eliminatedAbove = []
        self.resourcesWanted = []
        self.eliminableResources = []
        self.resourcesWantedOfLeastNonLoser = None
        self.totalCount = []

###

    def checkMinRequirements(self):
        """Called from Election.initialize to abort silly elections.
        MMV removes most requirements.
        """
        if self.b.nResources < 1:
            raise RuntimeError, "Not enough resources to run an election."

###

    def allocateRound(self):
        """Called each iteration to set up data structures for the coming round (self.R)."""
        RecursiveSTV.allocateRound(self)
        self.count[self.R] = [0] * self.b.nProj
        self.totalCount.append([0] * self.b.nProj) # just used for printing results
        for c in xrange(self.b.nProj):
            self.count[self.R][c] = {}
            self.f[self.R][c] = {}
        if self.R == 0:
            self.winAmount = [[0] * self.b.nProj]
            self.eliminatedAbove = [[self.maximum[p] for p in xrange(self.b.nProj)]]
        else:
            self.winAmount.append(self.winAmount[self.R-1][:])
            self.eliminatedAbove.append(self.eliminatedAbove[self.R-1][:])
        self.resourcesWanted.append([0] * self.b.nProj)
        self.eliminableResources.append([0] * self.b.nProj)

###

    def initializeTreeAndKeepValues(self):
        """Called at start of election to set up tree of ballots and keep values self.f."""
        RecursiveSTV.initializeTreeAndKeepValues(self)
        self.tree["bi"] = []
        self.tree["i"] = []
        for c in xrange(self.b.nProj):
            self.f[0][c] = {}

###

    def updateCount(self):
        """Called at end of each iteration to set count, exhausted, thresh, surplus."""

        # temporary round-to-round track of largest values given to funding levles
        self.maxKeep = [0] * self.b.nProj
        for c in xrange(self.b.nProj):
            self.maxKeep[c] = {}
        self.treeCount(self.tree, self.share)

        # compute thresh and surplus
        # Note: MMV doesn't actually use exhausted or thresh.
        self.exhausted[self.R] = self.p*self.b.nResources 
        for c in self.winners + self.purgatory:
		for v in self.count[self.R][c].values():
                   self.exhausted[self.R] -= v
        self.updateThresh()
        for c in self.winners + self.purgatory:
            prior = 0
            for amount in sorted(self.count[self.R][c].keys()):
                if self.count[self.R][c][amount] >= amount - prior:
                    self.surplus[self.R] += self.count[self.R][c][amount] - (amount - prior)
                prior = amount

    	return ""

###

    def updateWinners(self):
        """Called after updateCount to set winners and losers.
        MMV adds winAmount, eliminatedAbove, resourcesWanted, and eliminableResources.
        """
        winners = []
        desc = ""
        for c in self.purgatory:
            prior = 0
            for amount in sorted(self.count[self.R][c].keys()):
                if amount <= self.eliminatedAbove[self.R][c]:
                    if self.count[self.R][c][amount] >= amount - prior:
                        self.winAmount[self.R][c] = amount
                    else:
                        self.resourcesWanted[self.R][c] += amount - prior - self.count[self.R][c][amount]
                        self.eliminableResources[self.R][c] += self.count[self.R][c][amount]
                else:
                    break
                prior = amount
                
            if self.winAmount[self.R][c] == self.eliminatedAbove[self.R][c]:
                winners.append(c)
                        
        desc = self.newWinners(winners)
        if len(winners)>0:
            desc += "Winning amounts: " + self.joinList([str(int((self.winAmount[self.R][c]+self.p-1)/self.p)) for c in winners], convert="none") + ". "
        return desc

###

    def electionOver(self):
        """Called before each iteration."""

        if len(self.purgatory) <= 0:
            desc = "The election is over since all projects have won or been eliminated.  "
            return (True, desc)

        # possible shortcut...?
        spent = 0
        for amount in self.winAmount[self.R]:
            spent += amount
        if spent == self.b.nResources:
            desc = "The election is over since all resources are spent. "
            return (True, desc)

        # Not done yet.
        return (False, "")

###

    def getLosers(self, ppp = None):
        """Called at start of each iteration, via RecursiveSTV.chooseCandidatesToEliminate.
        Returns sure losers.
        MMV also sets resourcesWantedOfLeastNonLoser, in order to determine
        correct funding level at which to eliminate greatest loser.
        In MMV we eliminate first the projects which need the most resources;
        unlike OpenSTV this isn't the same as projects with the least count.
        """
        if ppp == None: ppp = self.purgatory
        R = self.R - 1
        ppp.sort(key=lambda a: -self.resourcesWanted[R][a])
        losers = []

        s = 0
        self.resourcesWantedOfLeastNonLoser = 0
        for i in xrange(len(ppp)):
            c = ppp[i]
            if i<len(ppp)-1:
                nextResourcesWanted = self.resourcesWanted[R][ppp[i+1]]
            else:
                nextResourcesWanted = 0 # TODO: make this some epsilon---in case we're willing to elect "close enough" projects
            # If you gave c all eliminable resources from even worse projects (s),
            # and all of the surplus, would it still want more than the next project?
            # If so c and all worse projects are sure losers.
            if self.resourcesWanted[R][c] - s - self.surplus[R] > nextResourcesWanted:
                losers = ppp[:i+1]
                self.resourcesWantedOfLeastNonLoser = nextResourcesWanted
            s += self.eliminableResources[R][c]

        return losers

###

    def breakWeakTie(self, R, cList, mostfewest, what=""):
        """If there are no sure losers, we'll need to pick somebody.
        We do this by looking at prior rounds to see which one was doing worse recently,
        if any.  If that doesn't work we call breakStrongTie and choose randomly.
        In order to reuse the OpenSTV code which looks at self.count, we maneuver 
        self.resourcesWanted into self.count and look for the biggest.
        """
        savedcount = self.count
        self.count = self.resourcesWanted
        fewestmost = "most"
        if mostfewest == "most":
            fewestmost = "fewest"
        res = RecursiveSTV.breakWeakTie(self,R,cList,fewestmost,what)
        self.count = savedcount
        # This is important, as res isn't a sure loser, so we should just eliminate
        # a little bit.
        self.resourcesWantedOfLeastNonLoser = None
        return res
        
###

    def eliminateLosers(self, losers):
        """Perform an elimination.
        We have to work a lot harder than OpenSTV in order to figure out and set the
        eliminated funding levels.  The key is resourcesWantedOfLeastNonLoser.
        """
        R = self.R-1
        extraDesc = ""
        if self.resourcesWantedOfLeastNonLoser == None:
            # We chose a loser, who wasn't a sure loser.  Just eliminate a little.
            assert(len(losers)==1)
            amounts = [self.eliminatedAbove[R][losers[0]] - self.p]  # TODO: choose some epsilon
            if amounts[0] < self.minimum[losers[0]]:
                amounts = [0]
        else:
            # All in losers re sure losers; all but the last should be
            # fully eliminated, and the last should eliminate just enough
            # that it can't want less than resourcesWantedOfLeastNonLoser
            amounts = []
            lastLoser = losers[len(losers)-1]
            allButLastEliminated = 0
            for l in losers[:-1]:
                amounts.append(self.winAmount[R][l])
                allButLastEliminated += self.eliminableResources[R][l]
                      
            lastLoserAmount = self.eliminatedAbove[R][lastLoser] - \
                              (self.resourcesWanted[R][lastLoser] - self.surplus[R] - \
                               allButLastEliminated - self.resourcesWantedOfLeastNonLoser)
            if lastLoserAmount < self.minimum[lastLoser] or lastLoserAmount <= self.winAmount[R][lastLoser]:
                lastLoserAmount = self.winAmount[R][lastLoser]
            else:
                extraDesc = ", and " + self.b.names[lastLoser] + " (to " + str(int((lastLoserAmount+self.p-1)/self.p)) + "),"
            amounts.append(lastLoserAmount)

        totalLosers = []
        winners = []
        for c, amount in itertools.izip(losers,amounts):
            self.eliminatedAbove[self.R][c] = amount
            if self.winAmount[self.R][c] == self.eliminatedAbove[self.R][c]:
                if self.winAmount[self.R][c] == 0:
                    totalLosers.append(c)
                else:
                    winners.append(c)

        self.newWinners(winners)
        self.newLosers(totalLosers)
        if len(totalLosers+winners) > 0 :
            desc = "Count after eliminating %s%s and transferring votes. "\
               % (self.joinList(totalLosers+winners), extraDesc)
        return desc

###

    def copyKeepValues(self):
        """Called after an elimination."""
        for c in self.purgatory + self.winners:
            self.f[self.R][c] = self.f[self.R-1][c].copy()
            # only keys for winners, so no need to look at eliminateds

###

    def updateKeepValues(self):
        """Called in a non-eliminating round."""

        if self.winners != []:
            desc = "Keep values of candidates who have exceeded the threshold: "
            list = []
        else:
            desc = ""

        for c in self.purgatory + self.winners:
            prior = 0
            for amount in sorted(self.count[self.R-1][c].keys()):
                if amount > self.winAmount[self.R-1][c]:
                    break
                oldf = self.f[self.R-1][c].get(amount,self.supportLimit)
                if oldf > self.maxKeep[c].get(amount,self.p):
                    oldf = self.maxKeep[c][amount]
                f, r = divmod(oldf * (amount - prior),
                      self.count[self.R-1][c][amount])
                if r > 0: f += 1
                self.f[self.R][c][amount] = f
                prior = amount
                list.append("%s(%s), %s" % (self.b.names[c], str(int((amount+self.p-1)/self.p)),
                                  self.displayValue(f)))

        if list != []:
            desc += self.joinList(list, convert="none") + ". "
        else:
            desc += "None (shouldn't happen?) "
        return desc

###
      
    def addBallotToTree(self, tree, ballotIndex, start=0):
        """Part of tree counting.  Adds one ballot to this tree."""

        ballot = self.b.packed[ballotIndex][start:]
        amounts = self.b.packedAmounts[ballotIndex][start:]
        weight = self.b.weight[ballotIndex]

        nextStart = start
        for c, amount in itertools.izip(ballot,amounts):
            nextStart += 1
            # TODO: deal with ballot priors (ask Robert)
            if c in self.purgatory + self.winners:
                amount = amount * self.p
                amount = min(amount,self.eliminatedAbove[self.R][c])
                break
        else:
            # This will happen if the ballot contains only winning and losing
            # candidates.  The ballot index will not need to be transferred
            # again so it can be thrown away.
            return

        key = (c,amount)

        # Create space if necessary.
        if not key in tree:
            tree[key] = {}
            tree[key]["n"] = 0
            tree[key]["i"] = [] # for each ballot in bi, which index to start at?
            tree[key]["bi"] = []

        tree[key]["n"] += weight
        tree[key]["bi"].append(ballotIndex) # we lazily instantiate the tree
        tree[key]["i"].append(nextStart)

###

    def updateTree(self, tree):
        """This is called each round before counting to modify the tree to deal with
        new winners and new losers.
        """
        for key in tree.keys():
            if key == "n": continue
            if key == "i": continue
            if key == "bi": continue

            self.updateTree(tree[key])
            c, bamount = key
            newAmount = self.eliminatedAbove[self.R][c]
            if bamount <= newAmount: continue
            if newAmount < self.minimum[c]:
                treeToMerge = tree[key]
                del tree[key]
                self.mergeTree(treeToMerge,tree)
            else:
                newKey = (c,newAmount)
                if newKey in tree:
                    tree[newKey]["n"] += tree[key]["n"]
                    treeToMerge = tree[key]
                    del tree[key]
                    self.mergeTree(treeToMerge,tree)
                else:
                    tree[newKey] = tree[key]
                    del tree[key]

###

    def mergeTree(self,treeToMerge,tree):
        """Merges two trees.  Doesn't deal with weight n."""
        tree["bi"] += treeToMerge["bi"]
        tree["i"] += treeToMerge["i"]
        for key in treeToMerge.keys():
            if key == "n": continue
            if key == "i": continue
            if key == "bi": continue

            if key in tree:
                tree[key]["n"] += treeToMerge[key]["n"]
                self.mergeTree(tree[key],treeToMerge[key])
            else:
                tree[key] = treeToMerge[key]
            del treeToMerge[key]
    
###

    def treeCount(self, tree, remainder):
        """Called from updateCount to traverse the ballot tree.  Recursive."""
        for bi, i in itertools.izip(tree["bi"],tree["i"]):
            self.addBallotToTree(tree, bi, i)
        tree["bi"] = []
        tree["i"] = []

        # Iterate over the next candidates on the ballots
        for key in tree.keys():
            if key == "n": continue
            if key == "i": continue
            if key == "bi": continue

            c, bamount = key
            if bamount > self.eliminatedAbove[self.R][c]: bamount = self.eliminatedAbove[self.R][c]
            rrr = remainder
            if bamount >= self.minimum[c]: # not fully eliminated
                for amount in sorted(self.f[self.R][c].keys()):
                    if amount == bamount: break
                    if amount > bamount:
                        self.f[self.R][c][bamount] = self.f[self.R][c][amount]
                        break
                if not bamount in self.count[self.R][c]:
                    nextamount = 0
                    prior = 0
                    for nextamount in sorted(self.count[self.R][c].keys()):
                        if nextamount > bamount: break
                        prior = nextamount
                    if nextamount < bamount: self.count[self.R][c][bamount] = 0
                    else:
                        self.count[self.R][c][bamount] = self.count[self.R][c][nextamount] * (bamount - prior) / (nextamount - prior)
                        self.count[self.R][c][nextamount] -= self.count[self.R][c][amount]

                contrib = {}
                contribTot = 0
                prior = 0
                for amount in sorted(self.count[self.R][c].keys()):
                    if amount > bamount:
                        break
                    f = self.f[self.R][c].get(amount, self.supportLimit)
                    contrib[amount] = f * (amount - prior) / self.p
                    contribTot += contrib[amount]
                    prior = amount

                overContrib = False
                # TODO: some rounding issues to fix.
                if self.meek:
                    if contribTot > self.share:
                        shouldContrib = self.share * self.p / contribTot
                        overContrib = True
                else:
                    if contribTot > rrr:
                        shouldContrib = rrr * self.p / contribTot
                        overContrib = True
                prior = 0
                for amount in sorted(contrib.keys()):
                    if overContrib:
                        f = shouldContrib * contrib[amount] / (amount - prior)
                        if f > self.maxKeep[c].get(amount,0):
                            self.maxKeep[c][amount] = f
                        newamount = rrr
                    else:
                        self.maxKeep[c][amount] = self.p
                        newamount = contrib[amount]
                        if self.meek: newamount = newamount * rrr / self.share
                    self.count[self.R][c][amount] += tree[key]["n"] * newamount
                    self.totalCount[self.R][c] += tree[key]["n"] * newamount
                    rrr -= newamount
                    prior = amount

            # If ballot not used up and more candidates, keep going
            if rrr > 0:
                self.treeCount(tree[key], rrr)

###

    def updateStatus(self):
        """Called at end of each election, to eliminate any trailing funding levels.
        Originally was: Update the status of winners who haven't reached the threshold.
        """

        desc = ""
        self.nRounds = self.R+1

        winners = []
        losers = []
        for c in self.purgatory:
            self.eliminatedAbove[self.R][c] = self.winAmount[self.R][c]
            if self.winAmount[self.R][c] > 0:
                winners.append(c)
            else:
                losers.append(c)
        desc += self.newWinners(winners, "under")
        self.newLosers(losers)

        return desc

###

    def generateTextResults(self, maxWidth=80, style="full", round=None):
        """Pretty print results."""
        savedcount = self.count
        self.count = self.totalCount
        res = RecursiveSTV.generateTextResults(self,maxWidth,style,round)
        self.count = savedcount
        return res

###

    def getMaxNumber(self):
        """Find the largest number to be printed in the results."""
        if "count" in dir(self) and self.count != []:
            savedcount = self.count
            self.count = self.totalCount
        res = RecursiveSTV.getMaxNumber(self)
        if "count" in dir(self) and self.count != []:
            self.count = savedcount
        return res

        


#    b = ProjectBallots()
#    b.load("case_x.bltp")
#    e = ProjectElection(b)
#    e.runElection()
#    print e.generateTextResults()
