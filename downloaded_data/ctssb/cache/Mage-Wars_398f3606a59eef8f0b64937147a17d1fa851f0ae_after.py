###########################################################################
##########################    v1.12.5.0     #######################################
###########################################################################
import time
import re
import sys
sys.path.append(wd("lib"))
import os
############################################################################
##########################		Constants		##################################
############################################################################

##########################		Markers			##################################

ActionBlue = ("Action", "c980c190-448d-414f-9397-a5f17068ac58" )
ActionBlueUsed = ("Action Used", "5926df42-919d-4c63-babb-5bfedd14f649" )
ActionGreen = ("Action", "9cd83c4b-91b7-4386-9d9a-70719971f949" )
ActionGreenUsed = ("Action Used", "5f20a2e2-cc59-4de7-ab90-cc7d1ced0eee" )
ActionRed = ("Action", "4dd182d2-6e69-499c-b2ad-38701c0fb60d" )
ActionRedUsed = ("Action Used", "2e069a99-1696-4cbe-b6c6-13e1dda29563" )
ActionYellow = ("Action", "2ec4ddea-9596-45cc-a084-23caa32511be" )
ActionYellowUsed = ("Action Used", "7c145c5d-54c3-4f5b-bf66-f4d52f240af6" )
ActionGrey = ("Action", "623f07fb-9cfb-4b4b-a350-6b208f0ef29e" )
ActionGreyUsed = ("Action Used", "99bd454e-fab9-47c6-9f59-54a112eeb2da" )
ActionPurple = ("Action", "edb61e00-a666-480a-81f3-20eb9944b0ea")
ActionPurpleUsed = ("Action Used", "158f738b-6034-4c6d-b4ca-5abcf159ed9f" )
Armor = ("Armor +1", "b3b6b5d3-4bda-4769-9bac-6ed48f7eb0fc" )
Bleed = ("Bleed", "df8e1a68-9fc3-46be-ac4f-7d9c61805cf5" )
BloodReaper = ("BloodReaper","50d83b50-c8b1-47bc-a4a8-8bd6b9b621ce" )
Burn = ("Burn", "f9eb0f3a-63de-49eb-832b-05912fc9ec64" )
Corrode = ("Corrode", "c3de25bf-4845-4d2d-8a28-6c31ad12af46" )
Cripple = ("Cripple", "82df2507-4fba-4c81-a1de-71e70b9a16f5" )
CrushToken = ("Crush Token", "d7472637-7c6d-4593-bc16-5975155c2926" )
Damage = ("Damage", "00000000-0000-0000-0000-000000000004" )
Daze = ("Daze","3ef51126-e2c0-44b3-b781-0b3f8476cb20" )
DeflectR = ("Deflect Ready", "684fcda0-e69d-426e-861c-5a92bc984f55" )
DeflectU = ("Deflect Used", "2c5b85ea-93de-4a99-b64d-da6c48baa205" )
Disable = ("Disable", "f68b3b5b-0755-40f4-84db-bf3197a667cb" )
DissipateToken = ("Dissipate Token","96348698-ae05-4c59-89bb-e79dad50ad1f" )
EternalServant = ("Eternal Servant", "86a71cf6-35ce-4728-a2f8-6701b1e29aa4" )
EggToken = ("Egg Token","874c7fbb-c566-4f17-b14e-ae367716dce5" )
FFToken = ("Forcefield Token", "fc23dce7-d58a-4c7d-a1b2-af9e23f5f29b" )
Growth = ("Growth", "c580e015-96ff-4b8c-8905-28688bcd70e8" )
Guard = ("Guard", "91ed27dc-294d-4732-ab71-37911f4011f2" )
HolyAvenger = ("Holy Avenger", "99381ac8-7d73-4d75-9787-60e6411d3613" )
Ichthellid = ("Ichthellid Larva", "c8bff05e-e43a-4b23-b467-9c4596050f28" )
Invisible = ("Invisible", "8d994fe9-2422-4a9d-963d-3ad10b2b823d" )
LoadToken = ("Load Token","d32267be-f4c5-48c6-8396-83c0db406942" )
Mana = ("Mana", "00000000-0000-0000-0000-000000000002" )
Melee = ("Melee +1", "e96b3791-fbcf-40a2-9c11-106342703db9" )
MistToken = ("Mist Token","fcc2ffeb-6ae6-45c8-930e-8f3521d326eb" )
Pet = ("Pet", "f4a2d3d3-4a95-4b9a-b899-81ea58293167" )
Quick = ("Quick", "11370fe9-41a4-4f05-9249-29a179c0031b" )
QuickBack = ("Quick Back", "a6ce63f9-a3fb-4ab2-8d9f-7d4b0108d7fd" )
Ranged = ("Ranged +1","cfb394b2-8571-439a-8833-476122a9eaa5")
Ready = ("Ready", "aaea8e90-e9c5-4fbc-8de3-4bf651d784a7" )
ReadyII = ("Ready II", "73fffebd-a8f0-43bd-a118-6aebc366ecf6" )
Rot = ("Rot", "81360faf-87d6-42a8-a719-c49386bd2ab5" )
RuneofFortification = ("Rune of Fortification","ae179c85-11ce-4be7-b9c9-352139d0c8f2" )
RuneofPower = ("Rune of Power","b3dd4c8e-35a9-407f-b9c8-a0b0ff1d3f07" )
RuneofPrecision = ("Rune of Precision","c2a265f9-ad97-4976-a83c-78891a224478" )
RuneofReforging = ("Rune of Reforging","d10ada1f-c03b-4077-b6cb-c9667d6b2744" )
RuneofShielding = ("Rune of Shielding","e0bb0e90-4831-43c6-966e-27c8dc2d2eef" )
SecretPassage = ("Secret Passage","a4b3bb92-b597-441e-b2eb-d18ef6b8cc77" )
Slam = ("Slam", "f7379e4e-8120-4f1f-b734-51f1bd9fbab9" )
Sleep = ("Sleep", "ad0e8e3c-c1af-47b7-866d-427f8908dea4" )
SpikedPitTrap = ("Spiked Pit Trap", "8731f61b-2af8-41f7-8474-bb9be0f32926")
StormToken = ("Storm Token", "6383011a-c544-443d-b039-9f7ba8de4c6b")
Stuck = ("Stuck", "a01e836f-0768-4aba-94d8-018982dfc122" )
Stun = ("Stun", "4bbac09e-a46c-42de-9272-422e8074533f" )
Tainted = ("Tainted", "826e81c3-6281-4a43-be30-bac60343c58f" )
Taunt = ("Taunt(Sosroku)", "16f03c44-5656-4e9d-9629-90c4ff1765a7" )
TauntT = ("Taunt(Thorg)", "8b5e3fe0-7cb1-44cd-9e9c-dadadbf04ab7" )
Treebond = ("Treebond", "ced2ce11-5e69-46a9-9fbb-887e96bdf805" )
Turn = ("Turn", "e0a54bea-6e30-409d-82cd-44a944e591dc" )
Used = ("Used", "ab8708ac-9735-4803-ba4d-4932a787540d" )
UsedII = ("Used II", "61bec951-ebb1-48f7-a2ab-0b6364d262e6" )
Veteran = ("Veteran", "72ee460f-adc1-41ab-9231-765001f9e08e" )
Visible = ("Visible", "b9b205a2-a998-44f5-97dc-c7f315afbbe2" )
VoltaricON = ("Voltaric On", "a6e79926-db8d-4095-9aee-e3b46bf24a3f" )
VoltaricOFF = ("Voltaric Off", "d91aabe0-d9cd-4b7e-b994-4e1c7a51c027" )
VTar = ("V'tar", "d01f02e4-392f-409f-95f5-d2fa40f89882" )
Weak = ("Weak", "22ef0c9e-6c0b-4e24-a4fa-e9d83f24fcba" )
WoundedPrey = ("Wounded Prey", "42f6cee3-3de4-4c90-a77c-9fb2c432d78d" )
Zombie = ("Zombie", "de101060-a4b4-4387-a7f8-aab82ecff2c8" )

##########################		Dice-related			########################

Die = [ "DieBlank",
		"DieBlank",
		"Die1",
		"Die2",
		"Die1s",
		"Die2s"]
attackDie = [ ("DieBlank","a1f061ec-efbe-444e-8e06-8d973600696c"),
		("DieBlank","a1f061ec-efbe-444e-8e06-8d973600696c"),
		("Die1","8cc1704a-6f2f-4dbf-a80c-8f79a5a8d165"),
		("Die2","b881f652-9384-43e1-9758-e68b04583b3b"),
		("Die1s","a3d3fff3-bb1c-4469-9a9d-f8dc1f341d39"),
		("Die2s","101976ea-ec22-4496-a762-6fbc0d1a41bb"),
		]
DieBlank = ("DieBlank","a1f061ec-efbe-444e-8e06-8d973600696c")
Die1 = ("Die1","8cc1704a-6f2f-4dbf-a80c-8f79a5a8d165")
Die2 = ("Die2","b881f652-9384-43e1-9758-e68b04583b3b")
Die1s = ("Die1s","a3d3fff3-bb1c-4469-9a9d-f8dc1f341d39")
Die2s = ("Die2s","101976ea-ec22-4496-a762-6fbc0d1a41bb")
DieD12 = ("DieD12","3cdf4231-065d-400e-9c74-d0ae669e852c")
diceBank = []
diceBankD12 = []

##########################		Other			############################

PlayerColor = 	["#de2827", 	# Red 		R=222 G=40  B=39
				"#171e78", 		# Blue		R=23  G=30  B=120
				"#01603e", 		# Green		R=1   G=96  B=62
				"#f7d917", 		# Yellow 	R=247 G=217 B=23
				"#c680b4",		# Purple
				"#c0c0c0"]		# Grey
boardSet = "GameBoard1.png"
debugMode = False
myIniRoll = 0
deckLoaded = False
iniTokenCreated = False
blankSpellbook = False
currentPhase = ""
discountsUsed = [ ]
gameStartTime = ""
gameEndTime = ""
roundTimes = []
gameTurn = 0
gameNum = 1
playerNum = 0
Magebind = ""
mageRevealCost = ""
infostr = ""
passOnClick = ""

############################################################################
############################		Events		##################################
############################################################################

def onTableLoad():
	#log in chat screen what version of the game definiton the player is using
	notify("{} is running v.{} of the Mage Wars module.".format(me, gameVersion))
	#if there's only one player, go into debug mode

def onGameStart():
	mute()
	global playerNum
	global debugMode
	#Set default map
	defineRectangularMap(4,3,250)

	# reset python Global Variables
	for p in players:
		remoteCall(p, "setClearVars",[])

	#create a dictionary of attachments and bound spells and enable autoattachment
	setGlobalVariable("attachDict",str({}))
	setGlobalVariable("bindDict",str({}))
	setSetting("AutoAttach", True)

	#set global event lists for rounds and single actions
	setGlobalVariable("roundEventList",str([]))
	setGlobalVariable("turnEventList",str([]))

	#enable AutoRoll of Initative for now....
	setSetting("AutoRollIni", True)

	# bring up window to point to documentation
	initializeGame()

	#if there's only one player, go into debug mode
	if len(players) == 1:
		debugMode = True
		playerNum = 2
		me.setGlobalVariable("MyColor", PlayerColor[0])
		CreateIniToken()
		#	players[0].setActivePlayer()
		setGlobalVariable("InitiativeDone", "True")
		notify("There is only one player, so there is no need to roll for initative.")
		notify("Enabling debug mode. In debug mode, deck validation is turned off and you can advance to the next phase by yourself.")
	setGlobalVariable("IniAllDone", ("x" if len(players) == 1 else "")) #Needs to be done here, since onTableLoad happens first.

def defineRectangularMap(I,J,tilesize):
	mapDict = createMap(I,J,[[1 for j in range(J)] for i in range(I)],tilesize)
	mapDict.get('zoneArray')[0][0]['startLocation'] = '1'
	mapDict.get('zoneArray')[-1][-1]['startLocation'] = '2'
	setGlobalVariable("Map", str(mapDict))

def setUpDiceAndPhaseCards():
	mute()
	TableSetup = getGlobalVariable("TableSetup")
	if TableSetup == "False" and me.name == Player(1).name:
                card = table.create("a6ce63f9-a3fb-4ab2-8d9f-7d4b0108d7fd",0,0) #dice field
                card.anchor = (True)
                moveCardToDefaultLocation(card)
		setGlobalVariable("TableSetup", True)

def onLoadDeck(player, groups):
	mute()
	global gameNum
	global deckLoaded
	global debugMode
	global playerNum
	global iniTokenCreated
	global blankSpellbook
	if bool(getGlobalVariable('DiceAndPhaseCardsDone')):
                setUpDiceAndPhaseCards()
                setGlobalVariable('DiceAndPhaseCardsDone','True')
	if player == me:
		#if a deck was already loaded, reset the game
		if deckLoaded:
			notify ("{} has attempted to load a second Spellbook, the game will be reset".format(me))
			for p in players:
				remoteCall(p, "setClearVars",[])
			gameNum += 1
			resetGame()
		elif debugMode or blankSpellbook or validateDeck(groups[0]):
			deckLoaded = True
			playerSetup()
			if len(getGlobalVariable("SetupDone")) != len(players) - 1: #we're not the last done with setup
				playerNum = len(getGlobalVariable("SetupDone")) + 1
				setGlobalVariable("P" + str(playerNum) + "Name", me.name)
				setGlobalVariable("SetupDone", getGlobalVariable("SetupDone") + "x")
				if playerNum == 1:
					# set Dice Rolling Area, Initative, and Phase Marker Card location
					AskDiceRollArea()
			else:	#other guy is done too
				playerNum = len(getGlobalVariable("SetupDone")) + 1
				setGlobalVariable("P" + str(playerNum) + "Name", me.name)
				for p in players:
					remoteCall(p, "SetupForIni", [])
				notify("All players have set up. Please roll for initiative.")
		else:
			#notify and delete deck
			notify("Validation of {}'s spellbook FAILED. Please choose another spellbook.".format(me.name))
			for group in groups:
				for card in group:
					if card.controller == me:
						card.delete()

def onMoveCards(player,cards,fromGroups,toGroups,oldIndices,indices,oldXs,oldYs,xs,ys,highlights,markers,faceup):
        mute()
        for i in range(len(cards)):
                card = cards[i]
                if card.controller == me and fromGroups[i]==table:
                        if not (getAttachTarget(card) in cards or getBindTarget(card) in cards): #Only check for detach if the attachtarget was not moved
                                unbind(card)
                                c,t = detach(card)
                                if toGroups[i] == table: card.moveToTable(xs[i],ys[i])#ugly, but fixes a bug that was preventing all but the first detached enchantment from moving.
                                actionType = None
                                if t:
                                        actionType = ['detaches','from']
                                hasAttached = False
                                if len(cards) == 1 and toGroups[i] == table: #Only check for autoattach if this is the only card moved
                                        for a in table:
                                                if (cardX(a)-xs[i])**2 + (cardY(a)-ys[i])**2 < 400 and canBind(card,a):
                                                        c,t = bind(card,a)
                                                        if t:
                                                                actionType = ['binds','to']
                                                                hasAttached = True
                                                                break
                                                elif getSetting('AutoAttach',True) and (cardX(a)-xs[i])**2 + (cardY(a)-ys[i])**2 < 400 and canAttach(card,a):
                                                        if (card.Type == "Enchantment" or card.Name in ["Tanglevine","Stranglevine","Quicksand"]) and not card.isFaceUp and not castSpell(card,a): break
                                                        c,t = attach(card,a)
                                                        if t:
                                                                actionType = ['attaches','to']
                                                                hasAttached = True
                                                                break
                                if (not hasAttached) and (toGroups[i] == table): snapToZone(card)
                                if actionType:
                                        notify("{} {} {} {} {}.".format(me,actionType[0],c,actionType[1],t))
                        if toGroups[i] != table:
                                unbind(card)
                                detach(card)
                                detachAll(card)
                                unbindAll(card)
                        if not ((oldIndices[i] != indices[i] and oldXs[i]==xs[i] and oldYs[i]==ys[i]) or
                                isAttached(card) or
                                getBindTarget(card) or
                                toGroups[i] != table):
                                alignAttachments(card)
                                alignBound(card)#Do not realign if it is  only the index that is changing. Prevents recursions.

def onTargetCardArrow(player,fromCard,toCard,isTargeted):#Expect this function to become SEVERELY overworked in Q2... :)
        if player == me == fromCard.controller and isTargeted:
                if getSetting("DeclareAttackWithArrow",True) and getSetting('BattleCalculator',True) and canDeclareAttack(fromCard) and toCard.type in ['Creature','Conjuration','Conjuration-Wall','Mage']:
                        attacker,defender = fromCard,toCard #Should probably make an attack declaration function. Eventually.
                        aTraitDict = computeTraits(attacker)
                        dTraitDict = computeTraits(defender)
                        attack = diceRollMenu(attacker,defender)
                        #Pay costs for spells
                        if attack.get('Cost'):
                                originalSource = Card(attack.get('OriginalSourceID'))
                                if not originalSource.isFaceUp: flipcard(originalSource)
                                if originalSource.type == 'Attack': castSpell(originalSource)
                                else:
                                        cost = attack.get('Cost')
                                        realCost = askInteger('Enter amount to pay for {}'.format(attack.get('Name')),cost)
                                        if realCost <= me.Mana: me.Mana -= realCost
                                        else:
                                                notify('{} has insufficient mana for {}. Cancelling attack.'.format(me,attack.get('Name')))
                                                return
                        if attack and attack.get('SourceID')==attacker._id:
                                remoteCall(defender.controller,'initializeAttackSequence',[aTraitDict,attack,dTraitDict])
                                attacker.arrow(defender,False)
                        elif attack.get("Dice"): rollDice(attack.get("Dice"))
                else:
                        if fromCard.Type == "Enchantment" and not fromCard.isFaceUp and castSpell(fromCard,toCard):
                                attach(fromCard,toCard)
                                fromCard.arrow(toCard,False)
                        elif fromCard.Type !="Enchantment":
                                castSpell(fromCard,toCard) #Assume that player wants to cast card on target
                                fromCard.arrow(toCard,False)

def setClearVars():
	global deckLoaded
	global iniTokenCreated
	global gameNum
	if gameNum == 1: return
	deckLoaded = False
	iniTokenCreated = False

def SetupForIni():
	mute()
	global myIniRoll
	global playerNum

	if getSetting("AutoRollIni", False):
		effect = 0
		for i in range(playerNum * 2):
			effect = rnd(1, 12)
		notify("Automatically rolling initiative for {}...".format(me))
		setGlobalVariable("InitiativeDone", "True")
		iniRoll(effect)

def iniRoll(effect):
	global playerNum
	global myIniRoll

	myIniRoll = effect
	notify("{} rolled a {} for initiative".format(me, effect))
	myRollStr = (str(playerNum) + ":" + str(effect) + ";")
	setGlobalVariable("OppIniRoll", getGlobalVariable("OppIniRoll") + myRollStr)

	if getGlobalVariable("OppIniRoll").count(";") == len(players):
		#all initiatives rolled, see who had highest
		rollString = getGlobalVariable("OppIniRoll")
		rollStringList = rollString.split(";")
		max = 0
		timesMaxRolled = 0
		victoriousPlayerNum = 0
		for roll in rollStringList:
			if roll == "":
				continue
			temp = roll.split(":")
			if int(temp[1]) > max:
				max = int(temp[1])
				timesMaxRolled = 1
				victoriousPlayerNum = int(temp[0])
			elif int(temp[1]) == max:
				timesMaxRolled += 1

		if timesMaxRolled > 1:
			# we got a tie in there somewhere. determine winner randomly from high rollers
			notify("High roll tied! Randomly determining initiative...")
			highRollerPlayerNums = []
			for roll in rollStringList:
				if roll == "":
					continue
				temp = roll.split(":")
				if int(temp[1]) == max:
					highRollerPlayerNums.append(int(temp[0]))
			victoriousPlayerNum = highRollerPlayerNums[rnd(0, len(highRollerPlayerNums) - 1)]
			debug(str(victoriousPlayerNum))

		for p in players:
			remoteCall(p, "AskInitiative", [victoriousPlayerNum])

############################################################################
######################		Group Actions			########################
############################################################################

def playerDone(group, x=0, y=0):
	notify("{} is done".format(me.name))
	mageStatus()

def useUntargetedAbility(attacker, x=0, y=0):
        mute()
        pass

def genericAttack(group, x=0, y=0):
	target = [cards for cards in table if cards.targetedBy==me]
	defender = (target[0] if len(target) == 1 else None)
        dice = diceRollMenu(None,defender).get('Dice',-1)
        if dice >=0: rollDice(dice)

def flipCoin(group, x = 0, y = 0):
    mute()
    n = rnd(1, 2)
    if n == 1:
        notify("{} flips heads.".format(me))
    else:
        notify("{} flips tails.".format(me))

def playerSetup():
	mute()

	# Players select their color
	choiceList = ["Red", "Blue", "Green", "Yellow", "Purple", "Grey"]
	if not debugMode or len(players) > 1:
		while (True):
			choice = askChoice("Pick a color:", choiceList, PlayerColor) - 1
			colorsChosen = getGlobalVariable("ColorsChosen")
			if colorsChosen == "":	#we're the first to pick
				setGlobalVariable("ColorsChosen", str(choice))
				me.setGlobalVariable("MyColor", PlayerColor[choice])
				break
			elif str(choice) not in colorsChosen:	#not first to pick but no one else has taken this yet
				setGlobalVariable("ColorsChosen", colorsChosen + str(choice))
				me.setGlobalVariable("MyColor", PlayerColor[choice])
				break
			else:	#someone else took our choice
				askChoice("Someone else took that color. Choose a different one.", ["OK"], ["#FF0000"])

	#set initial health and channeling values
	global blankSpellbook
	if blankSpellbook: return
	for c in me.hand:
		if c.Type == "Mage":
			stats = c.Stats.split(",")
			break
	for stat in stats:
		debug("stat {}".format(stat))

		statval = stat.split("=")
		if "Channeling" in statval[0]:
			me.Channeling = int(statval[1])
			me.Mana = 10+me.Channeling
			whisper("Channeling set to {} and Mana to {}".format(me.Channeling,me.Mana))
		elif "Life" in statval[0]:
			me.Life = int(statval[1])
			whisper("Life set to {}".format(me.Life))

def createVineMarker(group, x=0, y=0):
	table.create("ed8ec185-6cb2-424f-a46e-7fd7be2bc1e0", 450, -40 )

def createCompassRose(group, x=0, y=0):
	table.create("7ff8ed79-159c-46e5-9e87-649b3269a931", 450, -40 )

def createAltBoardCard(group, x=0, y=0):
	table.create("af14ca09-a83d-4185-afa0-bc38a31dbf82", 450, -40 )

def setNoGameBoard(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard0.png"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard1(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard1.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard2(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard2.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard3(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard3.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard4(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard4.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard5(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard5.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard6(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard6.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard9(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard9.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard10(group, x=0, y=0):
	global boardSet
	boardSet = "GameBoard10.jpg"
	mute()
	for p in players:
		remoteCall(p, "setGameBoard", [boardSet])

def setGameBoard(bset):
	mute()
	global boardSet
	boardSet = bset
	table.setBoardImage("GameBoards\\{}".format(boardSet))

def AskInitiative(pNum):
	global playerNum
	if playerNum != pNum:
		return
	mute()
	notify("{} is choosing whether or not to go first.".format(me))
	choiceList = ['Yes', 'No']
	colorsList = ['#FF0000', '#0000FF']
	choice = askChoice("You have won initiative! Would you like to go first?", choiceList, colorsList)
	if choice == 1:
		notify("{} has elected to go first!".format(me))
		CreateIniToken()
		players[0].setActivePlayer()
	else:
		#randomly determine who else should go first (in a 2 player game, this will always choose the other player)
		pNum = rnd(1, len(players) - 1)
		notify("{} has elected NOT to go first! {} has first initiative.".format(me, players[pNum]))
		remoteCall(players[pNum], "CreateIniToken", [])
		players[pNum].setActivePlayer()

def AskDiceRollArea():
	mute()
	notify("{} is choosing where the Dice Roll Area will be placed.".format(me))
	choiceList = ['Side', 'Bottom']
	colorsList = ['#FF0000', '#0000FF']
	choice = askChoice("Would you like to place the Dice Roll Area, Initative Marker, and Phase Marker to the Side or Bottom of the Gameboard?", choiceList, colorsList)
	if choice == 0 or choice == 1:
		notify("{} has elected to place the Dice Roll Area to the Side.".format(me))
	else:
		notify("{} has elected to place the Dice Roll Area to the Bottom.".format(me))
                setGlobalVariable("DiceRollAreaPlacement", "Bottom")
	#setDRAIP(choice)
	#for p in players:
		#remoteCall(p, "setDRAIP", [choice])

def CreateIniToken():
	global gameStartTime
	global iniTokenCreated
	global currentPhase
	myColor = me.getGlobalVariable("MyColor")
	mute()
	dieCardX = -570
	dieCardY = -40
	if not iniTokenCreated:
		iniTokenCreated = True
		init = table.create("8ad1880e-afee-49fe-a9ef-b0c17aefac3f", (dieCardX + 5) , (dieCardY - 75 ) ) #initiative token # Obsolete dieCard definitions, not high priority.
		init.anchor = (True)
		init.switchTo({
                        PlayerColor[0]:"",
                        PlayerColor[1]:"B",
                        PlayerColor[2]:"C",
                        PlayerColor[3]:"D",
                        PlayerColor[4]:"E",
                        PlayerColor[5]:"F"
                        }[myColor])
		setGlobalVariable("IniAllDone", "x")
		setGlobalVariable("RoundNumber", "1")
		setGlobalVariable("PlayerWithIni", str(playerNum))
		gameStartTime = time.time()
		currentPhase = "Planning"
                card = table.create("6a71e6e9-83fa-4604-9ff7-23c14bf75d48",0,0) #Phase token/Next Phase Button
                card.switchTo("Planning") #skips upkeep for first turn
                card.anchor = (True)
		for c in table:
                        remoteCall(c.controller,'moveCardToDefaultLocation',[c])
		notify("Setup is complete!")

def nextPhase(group, x=-360, y=-150):
        mute()
	global roundTimes
	global gameTurn
	gameIsOver = getGlobalVariable("GameIsOver")
	if gameIsOver:	#don't advance phase once the game is done
		notify("Game is Over!")
		return
	if getGlobalVariable("IniAllDone") == "": # Player setup is not done yet.
		return
	mageStatus()
	card = None
	for c in table: #find phase card
		if c.model == "6a71e6e9-83fa-4604-9ff7-23c14bf75d48":
			card = c
			break
	if not card:
                whisper("You must roll initiative first!")
                return
	if card.alternate == "":
		switchPhase(card,"Planning","Planning Phase")
	elif card.alternate == "Planning":
		switchPhase(card,"Deploy","Deployment Phase")
	elif card.alternate == "Deploy":
		switchPhase(card,"Quick","First Quickcast Phase")
	elif card.alternate == "Quick":
		switchPhase(card,"Actions","Actions Phase")
	elif card.alternate == "Actions":
		switchPhase(card,"Quick2","Final Quickcast Phase")
	elif card.alternate == "Quick2":
		if switchPhase(card,"","Upkeep Phase") == True: # "New Round" begins time to perform the Intiative, Reset, Channeling and Upkeep Phases
			setEventList('Round',[])
			setEventList('Turn',[])#Clear event list for new round
			gTurn = getGlobalVariable("RoundNumber")
			gameTurn = int(gTurn) + 1
			setGlobalVariable("RoundNumber", str(gameTurn))
			rTime = time.time()
			roundTimes.append(rTime)
			notify("Round {} Start Time: {}".format(str(gameTurn),time.ctime(roundTimes[-1])))
			notify("Ready Stage for Round #" + str(gameTurn) + ":  Performing Initiative, Reset, and Channeling Phases")
			init = [card for card in table if card.model == "8ad1880e-afee-49fe-a9ef-b0c17aefac3f"][0]
			if init.controller == me:
				flipcard(init)
			else:
				remoteCall(init.controller, "flipcard", [init])

			#resolve other automated items
			for p in players:
				remoteCall(p,"resetDiscounts",[])
				remoteCall(p, "resetMarkers", [])
				remoteCall(p, "resolveChanneling", [p])
				remoteCall(p, "resolveBurns", [])
				remoteCall(p, "resolveRot", [])
				remoteCall(p, "resolveBleed", [])
				remoteCall(p, "resolveDissipate", [])
				remoteCall(p, "resolveLoadTokens", [])
				remoteCall(p, "resolveStormTokens", [])
				remoteCall(p, "resolveUpkeep", [])


	update() #attempt to resolve phase indicator sometimes not switching

def resetDiscounts():
	#reset discounts used
	for tup in discountsUsed:
		discountsUsed.remove(tup)
		discountsUsed.append((tup[0],tup[1],0))

def advanceTurn():
	mute()
	nextPlayer = getNextPlayerNum()
	nextPlayerName = getGlobalVariable("P" + str(nextPlayer) + "Name")
	for p in players:
		if p.name == nextPlayerName:
			for p2 in players:
				remoteCall(p2, "setActiveP", [p])

def setActiveP(p):
	p.setActivePlayer()

def resetMarkers():
	mute()
	for c in table:
		if c.targetedBy == me:
			c.target(False)
		if c.controller == me and c.isFaceUp: #don't waste time on facedown cards and only reset the markers on my cards.
			mDict = {ActionRedUsed : ActionRed,
		                ActionBlueUsed : ActionBlue,
		                ActionGreenUsed : ActionGreen,
		                ActionYellowUsed : ActionYellow,
		                ActionPurpleUsed : ActionPurple,
		                ActionGreyUsed : ActionGrey,
		                QuickBack : Quick,
		                Used : Ready,
		                UsedII : ReadyII,
		                VoltaricON : VoltaricOFF,
		                DeflectU : DeflectR,
		                Visible : Invisible}
			for key in mDict:
		                if c.markers[key] == 1:
		                        c.markers[key] = 0
		                        c.markers[mDict[key]] = 1
	notify("{} resets all Action, Ability, Quickcast, and Ready Markers on the Mages cards by flipping them to their active side.".format(me.name))
	debug("card,stats,subtype {} {} {}".format(c.name,c.Stats,c.Subtype))

def resolveBurns():
	mute()

	#is the setting on?
	if not getSetting("AutoResolveBurns", True):
		return
	cardsWithBurn = [c for c in table if c.markers[Burn] and c.controller == me]
	if len(cardsWithBurn) > 0:
		notify("Resolving Burns for {}...".format(me))	#found at least one
		for card in cardsWithBurn:
			numMarkers = card.markers[Burn]
			burnDamage = 0
			burnsRemoved = 0
			for i in range(0, numMarkers):
				roll = rnd(0, 2)
				if roll == 0:
					card.markers[Burn] -= 1
					burnsRemoved += 1
				burnDamage += roll
			#apply damage
			if card.Type == "Mage":
				card.controller.Damage += burnDamage
			elif card.Type == "Creature" or "Conjuration" in card.Type:
				card.markers[Damage] += burnDamage
			notify("{} damage added to {}. {} Burns removed.".format(burnDamage, card.Name, burnsRemoved))
		notify("Finished auto-resolving Burns for {}.".format(me))

def resolveRot():
	mute()

	#is the setting on?
	if not getSetting("AutoResolveRot", True):
		return
	cardsWithRot = [c for c in table if c.markers[Rot] and c.controller == me]
	if len(cardsWithRot) > 0:
		notify("Resolving Rot for {}...".format(me))	#found at least one
		for card in cardsWithRot:
			rotDamage = (card.markers[Rot])
			 #apply damage
			if card.Type == "Mage":
				card.controller.Damage += rotDamage
			elif card.Type == "Creature" or "Conjuration" in card.Type:
				card.markers[Damage] += rotDamage
			notify("{} damage added to {}.".format(rotDamage, card.Name))
		notify("Finished auto-resolving Rot for {}.".format(me))

def resolveBleed():
	mute()

	#is the setting on?
	if not getSetting("AutoResolveBleed", True):
		return
	cardsWithBleed = [c for c in table if c.markers[Bleed] and c.controller == me]
	if len(cardsWithBleed) > 0:
		notify("Resolving Bleed for {}...".format(me))	#found at least one
		for card in cardsWithBleed:
			bleedDamage = (card.markers[Bleed])
			 #apply damage
			if card.Type == "Mage":
				card.controller.Damage += bleedDamage
			elif card.Type == "Creature" or "Conjuration" in card.Type:
				card.markers[Damage] += bleedDamage
			notify("{} damage added to {}.".format(bleedDamage, card.Name))
		notify("Finished auto-resolving Bleed for {}.".format(me))

def resolveDissipate():
	mute()

#is the setting on?
	if not getSetting("AutoResolveDissipate", True):
		return

	cardsWithDissipate = [c for c in table if c.markers[DissipateToken] and c.controller == me]
	if len(cardsWithDissipate) > 0:
		notify("Resolving Dissipate for {}...".format(me))	#found at least one
		for card in cardsWithDissipate:
			notify("Removing 1 Dissipate Token from {}...".format(card.Name))
			card.markers[DissipateToken] -= 1 # Remove Token
			if card.markers[DissipateToken] == 0 and card.Name == "Rolling Fog": # Only discard Rolling Fog for now
				notify("{} discards {} as it no longer has any Dissipate Tokens".format(me, card.Name))
				card.moveTo(me.piles['Discard'])
			notify("Finished auto-resolving Dissipate for {}.".format(me))

	#use the logic for Dissipate for Disable Markers
	cardsWithDisable = [c for c in table if c.markers[Disable] and c.controller == me]
	if len(cardsWithDisable) > 0:
		notify("Resolving Disable Markers for {}...".format(me))	#found at least one
		for card in cardsWithDisable:
			notify("{} removes a Disable Marker from '{}'".format(me, c.name))	#found at least one
			card.markers[Disable] -= 1 # Remove Marker
			notify("Finished auto-resolving Disable Markers for {}.".format(me))

def resolveLoadTokens():
	mute()
	loadTokenCards = [card for card in table if card.Name in ["Ballista", "Akiro's Hammer"] and card.controller == me and card.isFaceUp ]
	for card in loadTokenCards:
		notify("Resolving Load Tokens for {}...".format(me))	#found at least one
		if card.markers[LoadToken] == 0:
			notify("Placing the First Load Token on {}...".format(card.Name)) #found no load token on card
			card.markers[LoadToken] = 1
		elif card.markers[LoadToken] == 1:
			notify("Placing the Second Load Token on {}...".format(card.Name)) #found one load token on card
			card.markers[LoadToken] = 2
		notify("Finished adding Load Tokens for {}.".format(me))

def resolveStormTokens():
	mute()
	stormTokenCards = [card for card in table if card.Name in ["Staff of Storms"] and card.controller == me and card.isFaceUp ]
	for card in stormTokenCards:
		if card.markers[StormToken] ==4:
			return
		notify("Resolving Storm Tokens for {}...".format(me))	#found at least one
		if card.markers[StormToken] == 0 or card.markers[StormToken] < 4:
			notify("Placing a Storm Token on the '{}'...".format(card.Name)) #Card needs a load token
			card.markers[StormToken] += 1
		notify("Finished adding Storm Tokens for {}.".format(me))

def resolveChanneling(p):
	mute()
	for c in table:
                if c.controller==me and c.isFaceUp:
                        if c.Stats != None and c.Type != "Mage":
                                if "Channeling=" in c.Stats: #let's add mana for spawnpoints etc.
                                        channel = getStat(c.Stats,"Channeling")
                                        channelBoost = len([k for k in table if k.isFaceUp and k.name == "Harmonize" and c == getAttachTarget(k)]) #Well, you can't really attach more than 1 harmonize anyway. But if there were another spell that boosted channeling, we could add it to this list.
                                        debug("Found Channeling stat {} in card {}".format(channel,c.name))
                                        for x in range(channel+channelBoost):
                                                addMana(c)
                        if c.name == "Barracks": #has the channeling=X stat
                                debug("Found Barracks")
                                x = 0
                                for c2 in table:
                                        if c2.isFaceUp and c2.Subtype != "" and c2.Subtype != None:
                                                #debug("owners {} {}".format(c.owner,c2.owner))
                                                if "Outpost" in c2.Subtype and c.owner == c2.owner:
                                                        debug("Found Outpost")
                                                        addMana(c)
                                                        x += 1
                                        if x == 3: #max 3 outpost count.
                                                break
	if p == me:
		me.Mana += me.Channeling
		notify("{} channels {} mana.".format(me.name,me.Channeling))

def resolveUpkeep():
	mute()
	#is the setting on?
	if not getSetting("AutoResolveUpkeep", True):
		return
	Upkeep = "Upkeep"
	MordoksObeliskInPlay = 0
	HarshforgeMonolithInPlay = 0
	ManaPrismInPlay = 0
	PsiOrbDisc = 0
	upKeepIgnoreList = ["Essence Drain","Mind Control","Stranglevine","Mordok's Obelisk","Harshforge Monolith","Psi-Orb", "Mana Prism"]
	for card in table:
		if card.Name == "Mordok's Obelisk" and card.isFaceUp:
			MordoksObeliskInPlay = 1
			MordoksObelisk = card
		if card.Name == "Harshforge Monolith" and card.isFaceUp:
			HarshforgeMonolithInPlay = 1
			HarshforgeMonolith = card
		if card.name == "Mana Prism" and card.isFaceUp and card.controller == me:
			ManaPrismInPlay = 1
			ManaPrism = card
		if card.Name == "Psi-Orb" and card.isFaceUp and card.controller == me: # if the player has Psi-Orb in play set Discount to 3
		 	PsiOrbDisc = 3
		 	if PsiOrbDisc == 3: notify("{}".format(PsiOrbDisc))

	for card in table:
		upKeepCost = 0
		obeliskUpKeepCost = 0
		monolithUpKeepCost = 0
		# Process Upkeep for Harshforge Monolith
		if card.Type == "Enchantment" and card.controller == me and HarshforgeMonolithInPlay == 1:
			monolithUpKeepCost = 1
			aZone = getZoneContaining(card)
			bZone = getZoneContaining(HarshforgeMonolith)
			distance = zoneGetDistance(aZone,bZone)
			if card.isFaceUp:
				notifystr = "Do you wish to pay the Upkeep +1 cost for your Face Up {} from Harshforge Monolith's effect?".format(card.Name)
			else:
				notifystr = "Do you wish to pay the Upkeep +1 cost for your Face Down {} from Harshforge Monolith's effect?".format(card.Name)
			if distance < 2:
				processUpKeep(monolithUpKeepCost, card.Name, HarshforgeMonolith, notifystr)
				if ManaPrismInPlay == 1:
					addToken(ManaPrism, Mana)
		# Process Upkeep for Mordok's Obelisk's
		if card.Type == "Creature" and card.controller == me and MordoksObeliskInPlay == 1 and card.isFaceUp:
			obeliskUpKeepCost = 1
			notifystr = "Do you wish to pay the Upkeep +1 cost for {} from Mordok's Obelisk's effect?".format(card.Name)
			processUpKeep(obeliskUpKeepCost, card, MordoksObelisk, notifystr)
			if ManaPrismInPlay == 1:
				addToken(ManaPrism, Mana)
		 # Process Upkeep for Cards with the Upkeep Card Trait
		if not card.Name in upKeepIgnoreList and "Upkeep" in card.Traits and card.controller == me and card.isFaceUp:
			upKeepCost = getTraitValue(card, "Upkeep")
			if PsiOrbDisc > 0 and "Mind" in card.school:
				PsiOrbDisc, notifystr, upKeepCost = processPsiOrb(card, PsiOrbDisc, upKeepCost)
			else:
				if isAttached(card) == True:
					attatchedTo = getAttachTarget(card)
					notifystr = "Do you wish to pay the Upkeep +{} cost for {} attached to {}?".format(upKeepCost, card.Name, attatchedTo.Name)
				else:
					notifystr = "Do you wish to pay the Upkeep +{} cost for {}?".format(upKeepCost, card.Name)
		# Process Upkeep for Cards with the Upkeep Trait in the Card Text that is attached to Objects (Creatures)
		elif not card.Name in upKeepIgnoreList and "[Upkeep" in card.Text and card.controller == me and card.isFaceUp and isAttached(card) == True:
			attatchedTo = getAttachTarget(card)
			upKeepCost = getTextTraitValue(card, "Upkeep")
			if PsiOrbDisc > 0 and "Mind" in card.school:
				PsiOrbDisc, notifystr, upKeepCost = processPsiOrb(card, PsiOrbDisc, upKeepCost)
			else:
				notifystr = "Do you wish to pay the Upkeep +{} cost for {}?".format(upKeepCost, card.Name, attatchedTo.Name)
		# Process Upkeep for Essence Drain
		elif card.Name == "Essence Drain" and card.controller != me and card.isFaceUp:
			upKeepCost = getTextTraitValue(card, "Upkeep")
			if PsiOrbDisc > 0 and "Mind" in card.school:
				PsiOrbDisc, notifystr, upKeepCost = processPsiOrb(card, PsiOrbDisc, upKeepCost)
			else:
				notifystr = "Do you wish to pay the Upkeep +{} cost for {}?".format(upKeepCost, card.Name)
				processUpKeep(upKeepCost, card, Upkeep, notifystr)
				if ManaPrismInPlay == 1:
					addToken(ManaPrism, Mana)
				upKeepCost = 0
		# Process Upkeep for Mind Control
		elif card.Name == "Mind Control" and card.controller == me and card.isFaceUp and isAttached(card) == True:
			attatchedTo = getAttachTarget(card)
			upKeepCost = int(attatchedTo.level)
			if PsiOrbDisc > 0 and "Mind" in card.school:
				PsiOrbDisc, notifystr, upKeepCost = processPsiOrb(card, PsiOrbDisc, upKeepCost)
			else:
				notifystr = "Do you wish to pay the Upkeep +{} cost for the {} attached to {}?".format(upKeepCost, card.Name, attatchedTo.Name)
		# Process Upkeep for Stranglevine
		else:
			if card.Name == "Stranglevine" and card.controller == me and card.isFaceUp and isAttached(card) == True:
				attatchedTo = getAttachTarget(card)
				notify("{} has a Stranglevine attached to it adding a Crush token...".format(attatchedTo.name))
				card.markers[CrushToken] += 1
				upKeepCost = card.markers[CrushToken]
				notifystr = "Do you wish to pay the Upkeep +{} cost for {} attached to {}?".format(upKeepCost, card.Name, attatchedTo.Name)

		if upKeepCost >= 1:
			processUpKeep(upKeepCost, card, Upkeep, notifystr)

def processPsiOrb(card, PsiOrbDisc, upKeepCost):
	mute()
	debug("Psi-Orb Discount: {} and Card Name: {} Card School: {}".format(str(PsiOrbDisc),card.name, card.school))
	PsiOrbDisc -= 1
	notify("{} uses the Psi-Orb to pay 1 less Upkeep for '{}', there are {} remaining Upkeep discounts left for this Round.".format(me,card.name,PsiOrbDisc))
	upKeepCost = upKeepCost - 1
	notifystr = "Do you wish to pay the Upkeep +{} cost for {} after the 1 Mana Discount from the Psi-Orb?".format(upKeepCost, card.Name)
	return PsiOrbDisc, notifystr, upKeepCost

def processUpKeep(upKeepCost, card1, card2, notifystr):
	mute()
	upKeepCost = upKeepCost
	card1 = card1
	card2 = card2
	notifystr = notifystr

	if me.Mana < upKeepCost:
		card1.moveTo(me.piles['Discard'])
		notify("{} was unable to pay Upkeep cost for {} from {} effect and has placed {} in the discard pile.".format(me, card1, card2, card1))
		return
	else:
		choiceList = ['Yes', 'No']
		colorsList = ['#0000FF', '#FF0000']
		choice = askChoice("{}".format(notifystr), choiceList, colorsList)#Bookmark
		#whisper("{} {}".format(me, notifystr))
		if choice == 1 and card1.isFaceUp:
			me.Mana -= upKeepCost
			notify("{} pays the Upkeep cost of {} for {}".format(me, upKeepCost, card1, card2))
			if card1.Name == "Stranglevine" and card1.controller == me and card1.isFaceUp and isAttached(card1) == True:
				attatchedTo = getAttachTarget(card1)
				damage = card1.markers[CrushToken]
				remoteCall(attatchedTo.controller,"stranglevineReceiptPrompt",[attatchedTo,damage])
			return
		if choice == 1 and not card1.isFaceUp:
			me.Mana -= upKeepCost
			notify("{} pays the Upkeep cost of {} for the mage's Face Down Enchantment".format(me, upKeepCost, card1))
			return
		else:
			card1.moveTo(me.piles['Discard'])
			notify("{} has chosen not to pay the Upkeep cost for {} effect on {} and has placed {} in the discard pile.".format(me, card2, card1, card1))
			return

def stranglevineReceiptPrompt(card,damage):#I suppose this would really be better done as a generic damage receipt prompt but...Q2.
        mute()
        if askChoice("Apply {} damage to {} from Stranglevine?".format(str(damage),card.Name.split(",")[0]),["Yes","No"],["#01603e","#de2827"])==1:
                if card.Type == "Mage": card.controller.damage += damage
                else: card.markers[Damage] += damage
                strangleMessages=["Stranglevine tightens its hold on {}! ({} damage)",
                                  "As Stranglevine grows, its hold on {} tightens! ({} damage)",
                                  "{} is constricted by Stranglevine! ({} damage)",
                                  "Stranglevine crushes {}! ({} damage)",
                                  "Stranglevine writhes and constricts {}! ({} damage)"]
                message=rnd(0,len(strangleMessages)-1)
                notify(strangleMessages[message].format(card,str(damage)))
                traitsDict = computeTraits(card)
                if getRemainingLife(traitsDict) == 0: deathPrompt(traitsDict)

def getTraitValue(card, TraitName):
	listofTraits = ""
	debug("{} has the {} trait".format(card.name, TraitName))
	listofTraits = card.Traits.split(", ")
	debug("List of Traits: {} ".format(listofTraits))
	if not len(listofTraits) > 1:
		strTraits = ''.join(listofTraits)
	else:
		for traits in listofTraits:
			if TraitName in traits:
				strTraits = ''.join(traits)
	STraitCost = strTraits.split("+")
	if STraitCost[1].strip('[]') == "X":
		infostr = "The spell {} has an Upkeep value of 'X' what is the value of X?".format(card.Name)
		TraitCost = askInteger(infostr, 3)
	else:
		TraitCost = int(STraitCost[1].strip('[]'))
	return (TraitCost)

def getTextTraitValue(card, TraitName):
	listofTraits = ""
	debug("{} has the {} trait in its card text.".format(card.name, TraitName))
	cardText = card.Text.split("\r\n")
	strofTraits = cardText[1]
	debug("{}".format(strofTraits))
	if "] [" in strofTraits:
			listofTraits = strofTraits.split("] [")
			for traits in listofTraits:
					if TraitName in traits:
							strTrait = ''.join(traits)
	else:
			strTrait = strofTraits
	STraitCost = strTrait.split("+")
	if STraitCost[1].strip('[]') == "X":
		TraitCost = 0
	else:
		TraitCost = int(STraitCost[1].strip('[]'))
	return (TraitCost)

def mageStatus():
	mute()
	if not me.Damage >= me.Life:
		return
	for c in table:
		if c.Type == "Mage" and c.controller == me:
			c.orientation = 1
	#	playSoundFX('Winner')
	for p in players:
		remoteCall(p, "reportDeath",[me])
	#reportGame('MageDeath')

def reportDeath(deadmage):
	setGlobalVariable("GameIsOver", True)
	setGlobalVariable("GameEndTime", str(time.ctime()))
	choiceList = ['OK']
	colorsList = ['#de2827']
	whisper("'{}' has fallen in the arena! At {} after {} Rounds.".format(deadmage, getGlobalVariable("GameEndTime"), getGlobalVariable("RoundNumber")))
	choice = askChoice("{} has fallen in the arena! At {} after {} Rounds.".format(deadmage, getGlobalVariable("GameEndTime"), getGlobalVariable("RoundNumber")), choiceList, colorsList)
	if choice == 0 or choice == 1:
		return

def checkMageDeath(player, counter, oldvalue):
	global currentPhase
	if getGlobalVariable("IniAllDone") == "x" and (counter.name == "Damage" or counter.name == "Life"):
		if me.Damage >= me.Life and currentPhase == "Actions":
			if not confirm("                       Your Mage has fallen in the Arena! \n\nDo you wish to continue playing until the end of the current creatures Action Phase?"):
				mageStatus()

def concede(group=table, x = 0, y = 0):
	global gameTurn
	mute()
	if confirm("Are you sure you want to concede this game?"):
		setGlobalVariable("GameIsOver", True)
		for c in table:
			if c.Type == "Mage" and c.controller == me:
				c.orientation = 1
		setGlobalVariable("GameEndTime", str(time.time()))
#		reportGame('Conceded')
		notify("'{}' has conceded the game".format(me))
	else:
		notify("'{}' was about to concede the game, but thought better of it...".format(me))

"""
Format:
[function name, setting name, message, default]
"""

fGenToggleSettingsList = [['ResolveBurns','AutoResolveBurns',"You have {} automatic resolution of Burn tokens on your cards.",True],
                          ['SoundFX','AutoConfigSoundFX',"You have {} Sound Effects.",True],
                          ["ResolveRot","AutoResolveRot","You have {} automatic resolution of Rot tokens on your cards.",True],
                          ["FFTokens","AutoResolveFFTokens","You have {} automatic resolution of Forcefield tokens on your cards.",True],
                          ["ResolveBleed","AutoResolveBleed","You have {} automatic resolution of Bleed markers on your cards.",True],
                          ["ResolveDissipate","AutoResolveDissipate","You have {} automatic resolution of Dissipate tokens on your cards.",True],
                          ["EnchantRevealPrompt","EnchantPromptReveal","You have {} the enchantment reveal prompt.",False],
                          ["AutoRollInitiative","AutoRollIni","You have {} automatically rolling initiative.",False],
                          ["AutoResolveUpkeep","ResolveUpkeep","You have {} automatically caculating Upkeep costs.",False],
                          ["AutoAttach","AutoAttach","You have {} automatically attaching cards.",True],
                          ["ComputeProbabilities","AutoConfigProbabilities","You have {} battle computations on targeted cards.",True],
                          ["DiceButtons","AutoConfigDiceButtons","You have {} dice selection buttons.",True],
                          ["BattleCalculator","BattleCalculator","You have {} the battle calculator.",True],
                          ["DeclareAttackWithArrow","DeclareAttackWithArrow","You have {} declaring attacks with the targeting arrow.",True]]

for fGen in fGenToggleSettingsList:
        exec(
'def toggle'+fGen[0]+'(group,x=0,y=0):\n\t'+
        'state=getSetting("'+fGen[1]+'",'+str(fGen[3])+')\n\t'+
        'setSetting("'+fGen[1]+'", not state)\n\t'+
        'if state:\n\t\twhisper("'+fGen[2].format('disabled')+'")\n\t'+
        'else:\n\t\twhisper(":'+fGen[2].format('enabled')+'")')

def toggleDebug(group, x=0, y=0):
	global debugMode
	debugMode = not debugMode
	if debugMode:
		notify("{} turns on debug".format(me))
	else:
		notify("{} turns off debug".format(me))


############################################################################
######################		Chat Actions			################################
############################################################################
def sayYes(group, x=0, y=0):
	notify("{} says Yes".format(me.name))

def sayNo(group, x=0, y=0):
	notify("{} says No".format(me.name))

def sayPass(group, x=0, y=0):
	notify("{} says Pass".format(me.name))

def sayThinking(group, x=0, y=0):
	notify("{} says I am thinking....".format(me.name))

def askThinking(group, x=0, y=0):
	notify("{} asks are you thinking?".format(me.name))

def askYourTurn(group, x=0, y=0):
	notify("{} asks is it your turn?".format(me.name))

def askMyTurn(group, x=0, y=0):
	notify("{} asks is it my turn?".format(me.name))

def askRevealEnchant(group, x=0, y=0):
	notify("{} asks do you wish to Reveal your Enchantment?".format(me.name))

############################################################################
######################		Card Actions			################################
############################################################################

##########################     Add/Subtract Tokens     ##############################

tokenList=['Armor',
           'Bleed',
           'Burn',
           'Cripple',
           'Corrode',
           'Disable',
           'Daze',
           'Growth',
           'Mana',
           'Melee',
           'Ranged',
           'Rot',
           'Slam',
           'Stun',
           'Stuck',
           'Sleep',
           'Tainted',
           'Veteran',
           'Weak',
           'Zombie'
           ]

for token in tokenList:
        exec('def add'+token+'(card, x = 0, y = 0):\n\taddToken(card,'+token+')')
        exec('def sub'+token+'(card, x = 0, y = 0):\n\tsubToken(card,'+token+')')

def addDamage(card, x = 0, y = 0):
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if "Mage" in card.Type and card.controller == me:
		me.Damage += 1
	else:
		addToken(card, Damage)

def addOther(card, x = 0, y = 0):
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	marker, qty = askMarker()
	if qty == 0:
		return
	card.markers[marker] += qty

def subDamage(card, x = 0, y = 0):
	if "Mage" in card.Type and card.controller == me:
			me.Damage -= 1
	else:
		subToken(card, Damage)

def clearTokens(card, x = 0, y = 0):
	mute()
	for tokenType in card.markers:
		card.markers[tokenType] = 0
	notify("{} removes all tokens from '{}'".format(me, card.Name))

##########################     Toggle Actions/Tokens     ##############################
typeIgnoreList = ['Internal','Phase','DiceRoll']

def toggleAction(card, x=0, y=0):
	mute()
	myColor = me.getGlobalVariable("MyColor")
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if myColor == "#800080":
		whisper("Please perform player setup to initialize player color")
	elif myColor == PlayerColor[0]: # Red
		if card.markers[ActionRedUsed] > 0:
			card.markers[ActionRed] = 1
			card.markers[ActionRedUsed] = 0
			notify("'{}' readies Action Marker".format(card.Name))
		else:
			card.markers[ActionRed] = 0
			card.markers[ActionRedUsed] = 1
			notify("'{}' spends Action Marker".format(card.Name))
	elif myColor == PlayerColor[1]: # Blue
		if card.markers[ActionBlueUsed] > 0:
			card.markers[ActionBlue] = 1
			card.markers[ActionBlueUsed] = 0
			notify("'{}' readies Action Marker".format(card.Name))
		else:
			card.markers[ActionBlue] = 0
			card.markers[ActionBlueUsed] = 1
			notify("'{}' spends Action Marker".format(card.Name))
	elif myColor == PlayerColor[2]: #Green
		if card.markers[ActionGreenUsed] > 0:
			card.markers[ActionGreen] = 1
			card.markers[ActionGreenUsed] = 0
			notify("'{}' readies Action Marker".format(card.Name))
		else:
			card.markers[ActionGreen] = 0
			card.markers[ActionGreenUsed] = 1
			notify("'{}' spends Action Marker".format(card.Name))
	elif myColor == PlayerColor[3]: #Yellow
		if card.markers[ActionYellowUsed] > 0:
			card.markers[ActionYellow] = 1
			card.markers[ActionYellowUsed] = 0
			notify("'{}' readies Action Marker".format(card.Name))
		else:
			card.markers[ActionYellow] = 0
			card.markers[ActionYellowUsed] = 1
			notify("'{}' spends Action Marker".format(card.Name))
	elif myColor == PlayerColor[4]: #Purple
		if card.markers[ActionPurpleUsed] > 0:
			card.markers[ActionPurple] = 1
			card.markers[ActionPurpleUsed] = 0
			notify("'{}' readies Action Marker".format(card.Name))
		else:
			card.markers[ActionPurple] = 0
			card.markers[ActionPurpleUsed] = 1
			notify("'{}' spends Action Marker".format(card.Name))
	elif myColor == PlayerColor[5]: #Grey
		if card.markers[ActionGreyUsed] > 0:
			card.markers[ActionGrey] = 1
			card.markers[ActionGreyUsed] = 0
			notify("'{}' readies Action Marker".format(card.Name))
		else:
			card.markers[ActionGrey] = 0
			card.markers[ActionGreyUsed] = 1
			notify("'{}' spends Action Marker".format(card.Name))

def toggleDeflect(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if card.markers[DeflectR] > 0:
		card.markers[DeflectR] = 0
		card.markers[DeflectU] = 1
		notify("'{}' uses deflect".format(card.Name))
	else:
		card.markers[DeflectR] = 1
		card.markers[DeflectU] = 0
		notify("'{}' readies deflect".format(card.Name))

def toggleGuard(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	toggleToken(card, Guard)

def toggleInvisible(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if card.markers[Invisible] > 0:
		card.markers[Invisible] = 0
		card.markers[Visible] = 1
		notify("'{}' becomes visible".format(card.Name))
	else:
		card.markers[Invisible] = 1
		card.markers[Visible] = 0
		notify("'{}' becomes invisible".format(card.Name))

def toggleReady(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if card.markers[Ready] > 0:
		card.markers[Ready] = 0
		card.markers[Used] = 1
		notify("'{}' spends the Ready Marker on '{}'".format(me, card.Name))
	else:
		card.markers[Ready] = 1
		card.markers[Used] = 0
		notify("'{}' readies the Ready Marker on '{}'".format(me, card.Name))

def toggleReadyII(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if card.markers[ReadyII] > 0:
		card.markers[ReadyII] = 0
		card.markers[UsedII] = 1
		notify("'{}' spends the Ready Marker II on '{}'".format(me, card.Name))
	else:
		card.markers[ReadyII] = 1
		card.markers[UsedII] = 0
		notify("'{}' readies the Ready Marker II on '{}'".format(me, card.Name))

def toggleQuick(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if card.markers[Quick] > 0:
		card.markers[Quick] = 0
		card.markers[QuickBack] = 1
		notify("'{}' spends Quick Cast action".format(card.Name))
	else:
		card.markers[Quick] = 1
		card.markers[QuickBack] = 0
		notify("'{}' readies Quick Cast action".format(card.Name))

def toggleVoltaric(card, x=0, y=0):
	mute()
	if card.Type in typeIgnoreList or not card.isFaceUp: return
	if card.markers[VoltaricON] > 0:
		card.markers[VoltaricON] = 0
		card.markers[VoltaricOFF] = 1
		notify("'{}' disables Voltaric shield".format(card.Name))
	else:
		card.markers[VoltaricON] = 1
		card.markers[VoltaricOFF] = 0
		notify("'{}' enables Voltaric shield".format(card.Name))

############################################################################
######################		Other  Actions		################################
############################################################################
typeChannelingList = ['Mana Flower','Mana Crystal','Moonglow Amulet']

def rotateCard(card, x = 0, y = 0):
	# Rot90, Rot180, etc. are just aliases for the numbers 0-3
	mute()
	if card.controller == me:
		card.orientation = (card.orientation + 1) % 4
		if card.isFaceUp:
			notify("{} Rotates '{}'".format(me, card.Name))
		else:
			notify("{} Rotates a card".format(me))

def flipcard(card, x = 0, y = 0):
	mute()
	# markers that are cards in game that have two sides
	if "Vine Marker" in card.Name and card.controller == me:
		if card.alternate == "B":
			card.switchTo("")
		else:
			card.switchTo("B")
		notify("{} Flips Vine Marker.".format(me))
	elif "Alt Zone" in card.Name and card.controller == me:
		if card.alternate == "B":
			card.switchTo("")
		else:
			card.switchTo("B")
		notify("{} Flips Zone Marker.".format(me))
	elif "1st Player Token" in card.Name:
		nextPlayer = getNextPlayerNum()
		setGlobalVariable("PlayerWithIni", str(nextPlayer))
		for p in players:
			remoteCall(p, "changeIniColor", [card])

	# do not place markers/tokens on table objects like Initative, Phase, and Vine Markers
	if card.Type in typeIgnoreList: return
	# normal card flipping processing starts here
	if card.isFaceUp == False:
		card.isFaceUp = True
		if card.Type != "Enchantment"  and "Conjuration" not in card.Type: #leaves the highlight around Enchantments and Conjurations
			card.highlight = None
		if card.Type == "Mage" or card.Type == "Creature": #places action marker on card
			toggleAction(card)
		if card.Type == "Mage": #once more to flip action to active side
			toggleAction(card)
			toggleQuick(card)
			if "Wizard" in card.Name:
					card.markers[VoltaricOFF] = 1
			if "Forcemaster" == card.Name:
					card.markers[DeflectR] = 1
			if "Beastmaster" == card.Name:
					card.markers[Pet] = 1
			if "Johktari Beastmaster" == card.Name:
					card.markers[WoundedPrey] = 1
			if "Priest" == card.Name:
					card.markers[HolyAvenger] = 1
			if "Druid" == card.Name:
					card.markers[Treebond] = 1
			if "Necromancer" == card.Name:
					card.markers[EternalServant] = 1
			if "Warlock" == card.Name:
					card.markers[BloodReaper] = 1
		if "Anvil Throne Warlord Stats" == card.Name:
					card.markers[RuneofFortification] = 1
					card.markers[RuneofPower] = 1
					card.markers[RuneofPrecision] = 1
					card.markers[RuneofReforging] = 1
					card.markers[RuneofShielding] = 1
		if card.Name in typeChannelingList and card.controller == me and card.isFaceUp == True:
			notify("{} increases the Channeling stat by 1 as a result of '{}' being revealed".format(me, card))
			me.Channeling += 1
		if "Harmonize" == card.Name and card.controller == me and isAttached(card) and card.isFaceUp == True:
			magecard = getAttachTarget(card)
			if magecard.Type == "Mage":
				notify("{} increases the Channeling stat by 1 as a result of '{}' being revealed".format(me, card))
				me.Channeling += 1
		if card.Type == "Creature":
			if "Invisible Stalker" == card.Name:
					card.markers[Invisible] = 1
			if "Thorg, Chief Bodyguard" == card.Name:
					card.markers[TauntT] = 1
			if "Sosruko, Ferret Companion" == card.Name:
					card.markers[Taunt] = 1
			if "Ichthellid" == card.Name:
					card.markers[EggToken] = 1
			if "Talos" == card.Name:
					toggleAction(card)
			if "Orb Guardian" in card.name:
					card.markers[Guard] = 1
		if card.Type == "Conjuration":
			if "Ballista" == card.Name:
  				card.markers[LoadToken] = 1
			if "Akiro's Hammer" == card.Name:
  				card.markers[LoadToken] = 1
			if "Corrosive Orchid" == card.Name:
  				card.markers[MistToken] = 1
			if "Nightshade Lotus" == card.Name:
  				card.markers[MistToken] = 1
			if "Rolling Fog" == card.Name:
  				card.markers[DissipateToken] = 3
		if "Defense" in card.Stats and not card.Name=="Forcemaster":
			if "1x" in card.Stats:
				card.markers[Ready] = 1
			if "2x" in card.Stats:
				card.markers[Ready] = 1
				card.markers[ReadyII] = 1
		if "Forcefield" == card.Name:
			card.markers[FFToken] = 3
		if "[ReadyMarker]" in card.Text:
			card.markers[Ready] = 1
	elif card.isFaceUp:
		notify("{} turns '{}' face down.".format(me, card.Name))
		card.isFaceUp = False
		card.peek()

def getNextPlayerNum():
	activePlayer = int(getGlobalVariable("PlayerWithIni"))
	nextPlayer = activePlayer + 1
	if nextPlayer > len(players):
		nextPlayer = 1
	return nextPlayer

def changeIniColor(card):
	mute()
	myColor = me.getGlobalVariable("MyColor")

	if playerNum == int(getGlobalVariable("PlayerWithIni")):
		if myColor == PlayerColor[0]:
			if card.controller == me:
				card.switchTo("")
			else:
				remoteCall(card.controller, "remoteSwitchPhase", [card, "", ""])
		elif myColor == PlayerColor[1]:
			if card.controller == me:
				card.switchTo("B")
			else:
				remoteCall(card.controller, "remoteSwitchPhase", [card, "B", ""])
		elif myColor == PlayerColor[2]:
			if card.controller == me:
				card.switchTo("C")
			else:
				remoteCall(card.controller, "remoteSwitchPhase", [card, "C", ""])
		elif myColor == PlayerColor[3]:
			if card.controller == me:
				card.switchTo("D")
			else:
				remoteCall(card.controller, "remoteSwitchPhase", [card, "D", ""])
		elif myColor == PlayerColor[4]:
			if card.controller == me:
				card.switchTo("E")
			else:
				remoteCall(card.controller, "remoteSwitchPhase", [card, "E", ""])
		elif myColor == PlayerColor[5]:
			if card.controller == me:
				card.switchTo("F")
			else:
				remoteCall(card.controller, "remoteSwitchPhase", [card, "F", ""])

def discard(card, x=0, y=0):
	mute()
	if card.controller != me:
		whisper("{} does not control '{}' - discard cancelled".format(me, card))
		return
	if card.Name in typeChannelingList and card.controller == me and card.isFaceUp == True:
			notify("{} decreases the Channeling stat by 1 because '{}' is being discarded".format(me, card))
			me.Channeling -= 1
	elif "Harmonize" == card.Name and card.controller == me:
		discardedCard = getAttachTarget(card)
		if magecard.Type == "Mage":
			notify("{} decreases the Channeling stat by 1 because '{}' is being discarded".format(me, card))
			me.Channeling -= 1
	else:
			notify("{} discards '{}'".format(me, card))
	card.isFaceUp = True
	detach(card)
	card.moveTo(me.piles['Discard'])

def obliterate(card, x=0, y=0):
	mute()
	if card.controller != me:
		whisper("{} does not control '{}' - card obliteration cancelled".format(me, card))
		return
	if card.Name in typeChannelingList and card.controller == me and card.isFaceUp == True:
			notify("{} decreases the Channeling stat by 1 because '{}' has been obliterated".format(me, card))
			me.Channeling -= 1
	elif "Harmonize" == card.Name and card.controller == me:
		discardedCard = getAttachTarget(card)
		if magecard.Type == "Mage":
			notify("{} decreases the Channeling stat by 1 because '{}' has been obliterated".format(me, card))
			me.Channeling -= 1
	else:
			notify("{} obliterates '{}'".format(me, card))
	card.isFaceUp = True
	detach(card)
	card.moveTo(me.piles['Obliterate Pile'])

def OnCardDoubleClick(card, mouseButton, keysDown):
	mute()
	if card.type == "DiceRoll":
		genericAttack(0)

	if card.type =="Phase":
		nextPhase(table)

def defaultAction(card,x=0,y=0):
	mute()
	if card.controller == me:
		if not card.isFaceUp:
			#is this a face-down enchantment? if so, prompt before revealing
                        payForAttack = not (getSetting('BattleCalculator',True) and card.Type=='Attack')
			if "Mage" in card.Type or not payForAttack: #Attack spells will now be paid for through the battlecalculator
				flipcard(card, x, y)

				if not getSetting('attackChangeNotified',False) and not payForAttack:
                                        whisper('Note: Mana for {} will be paid when you declare an attack using the Battle Calculator, or if you double-click on {} again.'.format(card,card))
                                        setSetting('attackChangeNotified',True)
			elif card.Type == "Enchantment": revealEnchantment(card)
			else: castSpell(card)

		else:
			if card.Type == "Incantation" or card.Type == "Attack": castSpell(card) #They can cancel in the castSpell prompt; no need to add another menu

############################################################################
######################		Utility Functions		########################
############################################################################

def addToken(card, tokenType):
	mute()
	if card.Type in typeIgnoreList: return  # do not place markers/tokens on table objects like Initative, Phase, and Vine Markers
	card.markers[tokenType] += 1
	if card.isFaceUp:
		notify("{} added to '{}'".format(tokenType[0], card.Name))
	else:
		notify("{} added to face-down card.".format(tokenType[0]))

def subToken(card, tokenType):
	mute()
	if card.Type in typeIgnoreList: return  # do not place markers/tokens on table objects like Initative, Phase, and Vine Markers
	if card.markers[tokenType] > 0:
		card.markers[tokenType] -= 1
		if card.isFaceUp:
			notify("{} removed from '{}'".format(tokenType[0], card.Name))
		else:
			notify("{} removed from face-down card.".format(tokenType[0]))

def toggleToken(card, tokenType):
	mute()
	if card.Type in typeIgnoreList: return  # do not place markers/tokens on table objects like Initative, Phase, and Vine Markers
	if card.markers[tokenType] > 0:
		card.markers[tokenType] = 0
		if card.isFaceUp:
			notify("{} removes a {} from '{}'".format(me, tokenType[0], card.Name))
		else:
			notify("{} removed from face-down card.".format(tokenType[0]))
	else:
		card.markers[tokenType] = 1
		if card.isFaceUp:
			notify("{} adds a {} to '{}'".format(me, tokenType[0], card.Name))
		else:
			notify("{} added to face-down card.".format(tokenType[0]))

def playCardFaceDown(card, x=0, y=0):
        mute()
	myColor = me.getGlobalVariable("MyColor")
	moveCardToDefaultLocation(card)
	card.peek()
	card.highlight = myColor
	notify("{} prepares a Spell from their Spellbook by placing a card face down on the table.".format(me))

def moveCardToDefaultLocation(card,returning=False):#Returning if you want it to go to the returning zone
        mute()
        mapDict = eval(getGlobalVariable('Map'))
        x,y = 0,0
        if mapDict:
                zoneArray = mapDict.get('zoneArray')
                cardType = card.type
                if cardType == 'Internal': return
                cardW,cardH = card.width(),card.height()
                mapX,mapW = mapDict.get('x'),mapDict.get('X')
                if cardType == 'DiceRoll':
                        diceBoxSetup = getGlobalVariable("DiceRollAreaPlacement")
                        zone = ([z for z in zoneArray[0] if z and not z.get('startLocation')] if diceBoxSetup == 'Side' else
                                [z[-1] for z in zoneArray if z[-1] and not z[-1].get('startLocation')])[0]
                        zoneX,zoneY,zoneS = zone.get('x'),zone.get('y'),zone.get('size')
                        x=zoneX-(cardW if diceBoxSetup=='Side' else 0)
                        y=zoneY+zoneS-(cardH if diceBoxSetup=='Side' else 0)
                        card.moveToTable(x,y,True)
                        mapDict['DiceBoxLocation'] = (x,y)
                        setGlobalVariable("Map",str(mapDict))
                        #except: notify('Error! Maps must be at least 2 zones tall!')
                        return
                if cardType == 'Phase':
                        diceBoxSetup = getGlobalVariable("DiceRollAreaPlacement")
                        zone = ([z for z in zoneArray[0] if z and not z.get('startLocation')] if diceBoxSetup == 'Side' else
                                [z[-1] for z in zoneArray if z[-1] and not z[-1].get('startLocation')])[0]
                        zoneX,zoneY,zoneS = zone.get('x'),zone.get('y'),zone.get('size')
                        x=zoneX-(130 if diceBoxSetup=='Side' else 0)
                        y=zoneY+zoneS-(80 if diceBoxSetup=='Side' else 0)
                        if '1st Player Token' in card.name:
                                x-=(18  if diceBoxSetup=='Side' else -105-cardH)
                                y+=(-75 if diceBoxSetup=='Side' else 80-cardH)
                        elif cardType=='Phase' and 'Phase' in card.name:
                                x+=(39 if diceBoxSetup=='Side' else 155-cardH)
                                y+=(-63 if diceBoxSetup=='Side' else 23-cardH)
                        card.moveToTable(x,y,True)
                        return
                for i in range(len(zoneArray)):
                        for j in range(len(zoneArray[0])):
                                zone = zoneArray[i][j]
                                if zone and zone.get('startLocation') == str(playerNum):
                                        zoneX,zoneY,zoneS = zone.get('x'),zone.get('y'),zone.get('size')
                                        if cardType == 'Mage':
                                                x = (zoneX if i < mapDict.get('I')/2 else mapX + mapW - cardW)
                                                y = (zoneY if j < mapDict.get('J')/2 else zoneY+zoneS-cardH)
                                        elif cardType == 'Magestats':
                                                x = (zoneX - cardW if i < mapDict.get('I')/2 else mapX + mapW)
                                                y = (zoneY if j < mapDict.get('J')/2 else zoneY+zoneS-cardH)
                                        else:
                                                x = (zoneX - cardW if i < mapDict.get('I')/2 else mapX + mapW)
                                                y = (zoneY+cardH+cardH*int(returning) if j < mapDict.get('J')/2 else zoneY+zoneS-2*cardH-cardH*int(returning))
                                                xOffset = 0
                                                while True:
                                                        occupied = False
                                                        for c in table:
                                                                if c.controller == me:
                                                                        posx, posy = c.position
                                                                        #debug("c.position {}".format(c.position))
                                                                        if posx == x+xOffset and posy == y:
                                                                                occupied = True
                                                                                break
                                                        if occupied:
                                                                xOffset += cardW*(-1 if i < mapDict.get('I')/2 else 1)
                                                        else: break
                                                x += xOffset
        card.moveToTable(x,y,True)
        #setUpDiceAndPhaseCards,CreateIniToken
def debug(str):
	global debugMode
	if debugMode:
		whisper("Debug Msg: {}".format(str))

def createCard(group,x=0,y=0):
        mute()
        cardName = askString("Create which card?","Enter card name here")
        guid,quantity = askCard({'Name':cardName},title="Select card version and quantity")
        if guid and quantity:
                cards = ([table.create(guid,0,0,1,True)] if quantity == 1 else table.create(guid,0,0,quantity,True))
                for card in cards:
                        card.moveTo(me.hand)
                        notify("{} created a card. Card placed in {}'s spellbook.".format(me,me))

def moveCard(model, x, y):
	for c in table:
		if c.model == model:
			c.moveToTable(x, y)
			return c
	return table.create(model, x, y)

#Check see if a card at x1,y1 overlaps a card at x2,y2
#Both have size w, h
def overlaps(x1, y1, x2, y2, w, h):
	#Four checks, one for each corner
	if x1 >= x2 and x1 <= x2 + w and y1 >= y2 and y1 <= y2 + h: return True
	if x1 + w >= x2 and x1 <= x2 and y1 >= y2 and y1 <= y2 + h: return True
	if x1 >= x2 and x1 <= x2 + w and y1 + h >= y2 and y1 <= y2: return True
	if x1 + w >= x2 and x1 <= x2 and y1 + h >= y2 and y1 <= y2: return True
	return False

def cardHere(x, y, stat=""):
	for c in table:
		if c.controller == me:
			cx, cy = c.position
			#if overlaps(x, y, cx, cy, c.width(), c.height()):
			if x >= cx and x <= cx+c.width() and y >= cy and y <= cy+c.height() and stat in c.Stats:
				return c
	return None

def cardX(card):
	x, y = card.position
	return x

def cardY(card):
	x, y = card.position
	return y

def findCard(group, model):
	for c in group:
		if c.model == model:
			return c
	return None

def showAltCard(card, x = 0, y = 0):
	mute()
	alt = card.alternates
	if 'B' in alt:
		if card.alternate == '':
			notify("{} flips {} to the alternate version of the card.".format(me, card))
			card.switchTo("B")
		else:
			notify("{} flips {} to the standard version of the card.".format(me, card))
			card.switchTo()

#------------------------------------------------------------
# Global variable manipulations function
#------------------------------------------------------------

#---------------------------------------------------------------------------
# Workflow routines
#---------------------------------------------------------------------------

def playSoundFX(sound):
	mute()

	#is the setting on?
	if not getSetting("AutoConfigSoundFX", True):
		return
	else:
		playSound(sound)

def initializeGame():
    mute()
    #### LOAD UPDATES
    v1, v2, v3, v4 = gameVersion.split('.')  ## split apart the game's version number
    v1 = int(v1) * 1000000
    v2 = int(v2) * 10000
    v3 = int(v3) * 100
    v4 = int(v4)
    currentVersion = v1 + v2 + v3 + v4  ## An integer interpretation of the version number, for comparisons later
    lastVersion = getSetting("lastVersion", convertToString(currentVersion - 1))  ## -1 is for players experiencing the system for the first time
    lastVersion = int(lastVersion)
    for log in sorted(changelog):  ## Sort the dictionary numerically
        if lastVersion < log:  ## Trigger a changelog for each update they haven't seen yet.
            stringVersion, date, text = changelog[log]
            updates = '\n-'.join(text)
            confirm("Documentation available in v.{} ({}):\n-{}".format(stringVersion, date, updates))
    setSetting("lastVersion", convertToString(currentVersion))  ## Store's the current version to a setting

#---------------------------------------------------------------------------
# Table group actions
#---------------------------------------------------------------------------

def getStat(stats, stat): #searches stats string for stat and extract value
	statlist = stats.split(", ")
	for statitem in statlist:
		statval = statitem.split("=")
		if statval[0] == stat:
                        try: return int(statval[1])
                        except: return 0
	return 0

def switchPhase(card, phase, phrase):
	myColor = me.getGlobalVariable("MyColor")
	global playerNum
	global currentPhase
	mute()
	currentPhase = phase
	if debugMode:	#debuggin'
		card.switchTo(phase)
		notify("Phase changed to the {}".format(phrase))
		return True
	else:
		doneWithPhase = getGlobalVariable("DoneWithPhase")
		if str(playerNum) in doneWithPhase:
			return

		doneWithPhase += str(playerNum)
		if len(doneWithPhase) != len(players):
			setGlobalVariable("DoneWithPhase", doneWithPhase)
			if card.controller == me:
				card.highlight = myColor
			else:
				remoteCall(card.controller, "remoteHighlight", [card, myColor])
			notify("{} is done with the {}".format(me.name,card.Name))
			return False
		else:
			setGlobalVariable("DoneWithPhase", "")
			if card.controller == me:
				card.highlight = None
				card.switchTo(phase)
			else:
				remoteCall(card.controller, "remoteHighlight", [card, None])
				remoteCall(card.controller, "remoteSwitchPhase", [card, phase, phrase])
			notify("Phase changed to the {}".format(phrase))

			return True

def remoteHighlight(card, color):
	card.highlight = color

def remoteSwitchPhase(card, phase, phrase):
	card.switchTo(phase)

#---------------------------------------------------------------------------
# Table card actions
#---------------------------------------------------------------------------

def castSpell(card,target=None):
        #Figure out who is casting the spell
        binder = getBindTarget(card)
        caster = getBindTarget(card)
        if not caster or not ("Familiar" in caster.Traits or "Spawnpoint" in caster.Traits):
                casters = [d for d in table if d.Type == "Mage" and d.isFaceUp and d.controller == me]
                if casters: caster = casters[0]
                else:
                        whisper("And just who do you expect to cast that? You need to play a mage first.")
                        return
        costStr = card.Cost
        if not target and card.Target not in ['Zone','Zone Border','Arena'] and card.Type in ["Incantation","Conjuration"]:
                targets = [c for c in table if c.targetedBy==me]
                if targets and len(targets) == 1: target = targets[0]
                else: whisper("No single target for {} detected. Cost calculation is more effective if you select a target.".format(card))
        if card.Type == "Enchantment" and not canAttach(card,target): return
        #Long term, invalid targets will result in spell cancellation. Won't enforce that for now, though.
	if costStr:
                cardType = card.Type
                #First, determine the base cost
                cost = computeCastCost(card,target)
                if cost == None:
                        costQuery = askInteger("Non-standard cost detected. Please enter base cost of this spell.\n(Close this menu to cancel)",0)
                        if costQuery!=None: cost = costQuery
                        else: return
                casterMana = caster.markers[Mana]
                ownerMana = me.Mana
                discountList = filter(lambda d: d[1]>0, map(lambda c: (c,getCastDiscount(c,card,target)),table)) #Find all discounts. It would be better to pass a list, but this isn't a bottleneck, so we'll make do for now.
                #Reduce printed cost by sum of discounts
                usedDiscounts = []
                discountAppend = usedDiscounts.append
                for c,d in discountList:
                        if cost > 0: #Right now, all discounts are for 1 (except construction yard). If there is ever a 2-mana discount, we will need to adjust this to optimize discount use. Come to think of it, some discounts overlap, and we might want to optimize for those...well, we can cross that bridge when we reach it.
                                discAmt = min(cost,d)
                                cost -= discAmt
                                discountAppend((c,discAmt)) #Keep track of which discounts we are applying, and how much of each was applied
                        else: break #Stop if the cost of the spell reaches 0; we don't need any more discounts.
                #Ask the player how much mana they want to pay
                discountSourceNames = '\n'.join(map(lambda t: "{} (-{})".format(t[0].Name,str(t[1])),usedDiscounts))
                discountString = "The following discounts were applied: \n{}\n\n".format(discountSourceNames) if discountSourceNames else ""
                pronoun = {"Male":"he","Female":"she"}.get(getGender(caster),"it")
                casterString = "{} will pay what {} can. You will pay the rest.\n\n".format(caster.Name.split(",")[0],pronoun) if (caster.Type != "Mage" and caster.markers[Mana]) else ""
                cost = askInteger("We think this spell costs {} mana.\n\n".format(str(cost))+
                                     discountString+
                                     casterString+
                                     "How much mana would you like to pay?",cost)
                if cost == None: return
                if cost > casterMana + ownerMana:
                        whisper('You do not have enough mana to cast {}!'.format(card.Name))
                        return
                casterCost = min(casterMana,cost)
                caster.markers[Mana] -= casterCost #Hmmm... is casterMana mutable? Will need to experiment; not high priority
                if casterCost: notify("{} pays {} mana.".format(caster,str(casterCost)))
                cost -= casterCost
                if cost:
                        me.Mana = max(me.Mana-cost,0)
                        notify("{} pays {} mana.".format(me,str(cost)))
                for c,d in usedDiscounts: #track discount usage
                        if c.Name=="Construction Yard": c.markers[Mana] -= d
                        rememberAbilityUse(c)
                if card.Type == "Enchantment": notify("{} enchants {}!".format(caster,target.Name) if target else "{} casts an enchantment!".format(caster))
                elif card.Type == "Creature": notify("{} summons {}!".format(caster,card.Name))
                elif "Conjuration" in card.Type: notify("{} conjures {}!".format(caster,card.Name))
                else: notify("{} casts {}!".format(caster,card.Name))
                if card.Type != "Enchantment" and not card.isFaceUp: flipcard(card)
                if not binder or not "Spellbind" in binder.Traits:
                        unbind(card) #If it is not bound, unbind it from its card
                        if card.Type in ["Attack","Incantation"]: moveCardToDefaultLocation(card,True)
                        else: card.sendToFront()
                return True

def revealEnchantment(card):
	if card.Type == "Enchantment" and not card.isFaceUp:
                cardType = card.Type
                target = getAttachTarget(card)
                if target and [True for c in getAttachments(target) if c.Name == card.Name and c.isFaceUp]:
                        whisper("There is already a copy of {} attached to {}!".format(card.Name, target.Name))
                        return
                if not target and card.Target not in ['Zone','Zone Border','Arena'] and not confirm("This enchantment is not attached to anything. Are you sure you want to reveal it?"): return
                #First, determine the base cost
                cost = computeRevealCost(card)
                if cost == None:
                        costQuery = askInteger("Non-standard cost detected. Please enter the base cost of revealing this enchantment.",0)
                        if costQuery!=None: cost = costQuery
                        else: return
                ownerMana = me.Mana
                discountList = filter(lambda d: d[1]>0, map(lambda c: (c,getRevealDiscount(c,card)),table)) #Find all discounts. It would be better to pass a list, but this isn't a bottleneck, so we'll make do for now.
                #Reduce printed cost by sum of discounts
                usedDiscounts = []
                discountAppend = usedDiscounts.append
                for c,d in discountList:
                        if cost > 0: #Right now, all discounts are for 1. If there is ever a 2-mana discount, we will need to adjust this to optimize discount use. Come to think of it, some discounts overlap, and we might want to optimize for those...well, we can cross that bridge when we reach it.
                                cost = max(cost-d,0)
                                discountAppend((c,d)) #Keep track of which discounts we are applying
                        else: break #Stop if the cost of the spell reaches 0; we don't need any more discounts.
                #Ask the player how much mana they want to pay
                discountSourceNames = '\n'.join(map(lambda t: t[0].Name,usedDiscounts))
                discountString = "The following discounts were applied: \n{}\n\n".format(discountSourceNames) if discountSourceNames else ""
                cost = askInteger("We think this enchantment costs {} mana to reveal.\n\n".format(str(cost))+
                                     discountString+
                                     "How much mana would you like to pay?",cost)
                if cost == None: return
                #Do we have enough mana?
                if cost > ownerMana:
                        whisper('You do not have enough mana to reveal {}!'.format(card.Name))
                        return
                if cost:
                        me.Mana = max(me.Mana-cost,0)
                        notify("{} pays {} mana.".format(me,str(cost)))
                for c,d in usedDiscounts: #track discount usage
                        rememberAbilityUse(c)
                notify("{} reveals {}!".format(me,card.Name))
                flipcard(card)
                return True

def getCastDiscount(card,spell,target=None): #Discount granted by <card> to <spell> given <target>. NOT for revealing enchantments.
        if card.controller != spell.controller or not card.isFaceUp or card==spell: return 0 #No discounts from other players' cards or facedown cards!
        caster = getBindTarget(spell)
        mageCast = not(caster and ("Familiar" in caster.Traits or "Spawnpoint" in caster.Traits))
        spawnpointCast = (caster and "Spawnpoint" in caster.Traits)
        cName = card.Name
        sSubtype = spell.Subtype
        sType = spell.Type
        sName = spell.Name
        sSchool = spell.School
        timesUsed = timesHasUsedAbility(card)
        if timesUsed < 1: #Once-per-round discounts
                #Discounts that only apply when your mage casts the spell
                if (mageCast and
                    ((cName == "Arcane Ring" and sType != "Enchantment" and (("Metamagic" in sSubtype) or ("Mana" in sSubtype))) or
                     (cName == "Enchanter's Ring" and target and target.controller == card.controller and sType == "Enchantment") or
                     (cName == "Ring of Asyra" and ("Holy" in sSchool) and sType == "Incantation") or
                     (cName == "Ring of Beasts" and sType == "Creature" and ("Animal" in sSubtype)) or
                     (cName == "Ring of Curses" and sType != "Enchantment" and ("Curse" in sSubtype)) or
                     (cName == "Druid's Leaf Ring" and sType != "Enchantment" and ("Plant" in sSubtype)) or
                     (cName == "Force Ring" and sType != "Enchantment" and ("Force" in sSubtype)) or
                     (cName == "Ring of Command" and sType != "Enchantment" and ("Command" in sSubtype)))):
                        return 1
                #Discounts that apply no matter who casts the spell
                if ((cName == "General's Signet Ring" and ("Soldier" in sSubtype)) or
                    (cName == "Eisenach's Forge Hammer" and (sType == "Equipment"))):
                        return 1
                #Construction yard will be treated as a once-per-round discount.
                if (cName == "Construction Yard" and
                    ((not "Incorporeal" in spell.Traits and "War" in sSchool and "Conjuration" in sType) or ("Earth" in sSchool and sType=="Conjuration-Wall"))):
                        return card.markers[Mana]
        if timesUsed <2: #Twice-per-round discounts
                if cName == "Death Ring" and (mageCast or spawnpointCast) and sType != "Enchantment" and ("Necro" in sSubtype or "Undead" in sSubtype):
                        return 1
        return 0
        #Returns discount as integer (0, if no discount)

def getRevealDiscount(card,spell): #Discount granted by <card> to <spell>. ONLY used for revealing enchantments (don't call for casting spells!)
        if card.controller != spell.controller or not card.isFaceUp or card==spell: return 0 #No discounts from other players' cards or facedown cards, or from itself!
        target = getAttachTarget(spell)
        cName = card.Name
        sSubtype = spell.Subtype
        sType = spell.Type
        sName = spell.Name
        sSchool = spell.School
        timesUsed = timesHasUsedAbility(card)
        if timesUsed < 1 and ((cName == "Arcane Ring" and (("Metamagic" in sSubtype) or ("Mana" in sSubtype))) or
                              (cName == "Ring of Asyra" and ("Holy" in sSchool)) or
                              (cName == "Ring of Curses" and ("Curse" in sSubtype)) or
                              (cName == "Druid's Leaf Ring" and ("Plant" in sSubtype)) or
                              (cName == "Force Ring" and ("Force" in sSubtype)) or
                              (cName == "Ring of Command" and ("Command" in sSubtype))): return 1
        if timesUsed <2 and cName == "Death Ring" and ("Necro" in sSubtype or "Undead" in sSubtype): return 1
        return 0
        #Returns discount as integer (0, if no discount)

def computeRevealCost(card): #For enchantment reveals
        target = getAttachTarget(card) #To what is it attached?
        cost = None
        try: cost = int(card.Cost.split('+')[1])
        except: pass
        if not target: return cost
        #Exceptions
        name = card.Name
        tLevel = 6 if target.Type == "Mage" else int(sum(map(lambda x: int(x), target.Level.split('+')))) #And...this is why mages NEED to have a level field in the XML file.
        if name == "Mind Control":
                cost = 2*tLevel
        elif name in ["Charm","Fumble"]:
                cost = tLevel-1
        if cost == None: return #If it doesn't fit an exception, the player will have to handle it.
        traits = computeTraits(card)
        if target.Type=="Mage":
                cost += traits.get("Magebind",0)
        return cost

def computeCastCost(card,target=None): #Does NOT take discounts into consideration. Just computes base casting cost of the card. NOT reveal cost.
        cost = 2 if card.Type == 'Enchantment' else None
        try: cost = int(card.Cost)
        except: pass
        if target: #Compute exact cost based on target. For now, cards like dissolve will have to target the spell they want to destroy. Does not check for target legality.
                name = card.Name
                tLevel = 6 if target.Type == "Mage" else (int(target.Level.split("/")[0]) if "/" in target.Level else int(sum(map(lambda x: int(x), target.Level.split('+')))))
                if name in ["Dissolve", "Conquer"]:
                        cost = int(target.Cost)
                elif name in ["Dispel","Steal Enchantment"]:
                        revealCost = computeRevealCost(target)
                        if revealCost!=None: cost = 2 + revealCost
                elif name in ["Steal Equipment"]:
                        cost = 2*int(target.Cost)
                elif name in ["Rouse the Beast","Disarm"]:
                        cost = tLevel
                elif name in ["Quicksand"]:
                        cost = 2*tLevel
                elif name == "Explode":
                        cost = 6+int(target.Cost)
                elif name == "Shift Enchantment":
                        if not card.isFaceUp: cost = 1
                        else: cost = tLevel
                elif name == "Sleep":
                        cost = {1:4,2:5,3:6}.get(tLevel,2*tLevel)
                elif name == "Defend":
                        cost = {1:1,2:1,3:2,4:2}.get(tLevel,3)
                #For now, we won't consider things like harshforge plate. We could, but it is not necessary at the moment. We will add that when we implement the 3 stages of casting a spell. (Q2)
        return cost

def inspectCard(card, x = 0, y = 0):
    whisper("{}".format(card))
    for k in card.properties:
        if len(card.properties[k]) > 0:
            whisper("{}: {}".format(k, card.properties[k]))

def validateDeck(deck):
	for c in deck:
		if c.Type == "Mage":
			stats = c.Stats.split(",")
			schoolcosts = c.MageSchoolCost.split(",")
			break

	debug("Stats {}".format(stats))
	spellbook = {"Dark":2,"Holy":2,"Nature":2,"Mind":2,"Arcane":2,"War":2,"Earth":2,"Water":2,"Air":2,"Fire":2,"Creature":0}

	#get spellbook point limit
	for stat in stats:
		debug("stat {}".format(stat))
		statval = stat.split("=")
		if "Spellbook" in statval[0]:
			spellbook["spellpoints"] = int(statval[1])
			break

	#get school costs
	for schoolcost in schoolcosts:
		debug("schoolcost {}".format(schoolcost))
		costval = schoolcost.split("=")
		if "Spellbook" in costval[0]:
			spellbook["spellpoints"] = int(costval[1])
		elif "Dark" in costval[0]:
			spellbook["Dark"] = int(costval[1])
		elif "Holy" in costval[0]:
			spellbook["Holy"] = int(costval[1])
		elif "Nature" in costval[0]:
			spellbook["Nature"] = int(costval[1])
		elif "Mind" in costval[0]:
			spellbook["Mind"] = int(costval[1])
		elif "Arcane" in costval[0]:
			spellbook["Arcane"] = int(costval[1])
		elif "War" in costval[0]:
			spellbook["War"] = int(costval[1])
		elif "Earth" in costval[0]:
			spellbook["Earth"] = int(costval[1])
		elif "Water" in costval[0] and c.name != "Druid":
			spellbook["Water"] = int(costval[1])
		elif "Air" in costval[0]:
			spellbook["Air"] = int(costval[1])
		elif "Fire" in costval[0]:
			spellbook["Fire"] = int(costval[1])
	debug("Spellbook {}".format(spellbook))
	#spellbook["Dark"] = sumLevel("Dark")
	levels = {}
	booktotal = 0
	epics = ["", "three"]
	cardCounts = { }
	for card in deck: #run through deck adding levels
		if "Novice" in card.Traits: #Novice cards cost 1 spellpoint
			debug("novice {}".format(card))
			booktotal += 1
		elif "Talos" in card.Name: #Talos costs nothing
			debug("Talos")
		elif "+" in card.School: #and clause
			debug("and {}".format(card))
			schools = card.School.split("+")
			level = card.Level.split("+")
			i = 0
			for s in schools:
				try:
					levels[s] += int(level[i])
				except:
					levels[s] = int(level[i])
				i += 1
		elif "/" in card.School: #or clause
			debug("or {}".format(card))
			schools = card.School.split("/")
			level = card.Level.split("/")
			i = -1
			s_low = schools[0]
			for s in schools:
				i += 1
				if spellbook[s] < spellbook[s_low]: #if trained in one of the schools use that one
					s_low = s
					break
			try:
				levels[s_low] += int(level[i])
			except:
				levels[s_low] = int(level[i])
		elif card.School != "": # only one school
			debug("single {}".format(card))
			try:
				levels[card.School] += int(card.Level)
			except:
				levels[card.School] = int(card.Level)

		if card.Type == "Creature" and c.name == "Forcemaster": #check for the forcemaster rule
			debug("FM creature test")
			if "Mind" not in card.School:
				if "+" in card.School:
					level = card.Level.split("+")
					for l in level:
						booktotal += int(l)
				elif "/" in card.School:
					level = card.Level.split("/")
					booktotal += int(level[0])
				elif card.School != "": # only one school
					booktotal += int(card.Level)

		if "Water" in card.School and c.name == "Druid": #check for the druid rule
			if "1" in card.Level:
				debug("Druid Water test: {}".format(card.Name))
				if "+" in card.School:
					schools = card.School.split("+")
					level = card.Level.split("+")
					i = 0
					for s in schools:
						if s == "Water" and 1 == int(level[i]): #if water level 1 is here only pay 1 spell book point for it.
							levels[s] -= 1
							booktotal += 1
						i += 1
				elif "/" in card.School: #this rule will calculate wrong if water is present as level 1 but wizard is trained in another element of the same spell too
					level = card.Level.split("/")
					levels[card.School] -= 1
					booktotal += 1
				elif card.School != "": # only one school
					levels[card.School] -= 1
					booktotal += 1
				debug("levels {}".format(levels))

		if "Epic" in card.Traits:	#check for multiple epic cards
			if card.Name in epics:
				notify("*** ILLEGAL ***: multiple copies of Epic card {} found in spellbook".format(card.Name))
				return False
			epics.append(card.Name)

		if "Only" in card.Traits:	#check for school/mage restricted cards
			ok = False
			magename = c.Name
			if "Beastmaster" in magename:
				magename = "Beastmaster"
			if "Wizard" in magename:
				magename = "Wizard"
			if "Warlock" in magename:
				magename = "Warlock"
			if "Warlord" in magename:
				magename = "Warlord"
			if "Priestess" in magename:
				magename = "Priestess"
			if magename in card.Traits:	#mage restriction
				ok = True
			for s in [school for school in spellbook if spellbook[school] == 1]:
				if s + " Mage" in card.Traits:
					ok = True
			if not ok:
				notify("*** ILLEGAL ***: the card {} is not legal in a {} deck.".format(card.Name, c.Name))
				return False

		l = 0	#check spell number restrictions
		if card.Level != "":
			if cardCounts.has_key(card.Name):
				cardCounts.update({card.Name:cardCounts.get(card.Name)+1})
			else:
				cardCounts.update({card.Name:1})
			if "+" in card.Level:
				level = card.Level.split("+")
				for s in level:
					l += int(s)
			elif "/" in card.Level:
				level = card.Level.split("/")
				l = int(level[0])
			else:
				l = int(card.Level)
			if (l == 1 and cardCounts.get(card.Name) > 6) or (l >= 2 and cardCounts.get(card.Name) > 4):
				notify("*** ILLEGAL ***: there are too many copies of {} in {}'s deck.".format(card.Name, me))
				return False

	debug("levels {}".format(levels))
	for level in levels:
		debug("booktotal {}, level {}".format(booktotal,level))
		booktotal += spellbook[level]*levels[level]
	notify("Spellbook of {} calculated to {} points".format(me,booktotal))

	if (booktotal > spellbook["spellpoints"]):
		return False

	#all good!
	return True

############################################################################
############################	   Map Construction     ####################
############################################################################

def importArray(filename):
        """Takes a txt character array and outputs a dictionary of arrays (sets of columns). To get an entry from an array, use array[x][y]"""
        #Open the file
        directory = os.path.split(os.path.dirname(__file__))[0]+'\{}'.format('maps')
        try: raw = open('{}\{}{}'.format(directory,filename,'.txt'),'r')
        except: return #Bad practice, I know. I'll try to find a better way later.
        #Create an empty array.
        #Because of the order in which data are read, we will need to transpose it.
        transposeArray = []
        #Fill up the transposed array, as a set of rows.
        scenarioDict = {}
        dictKey = None
        for line in raw:
                if line == '\n': pass #ignore blank lines
                elif line[0] != '#':
                        row = []
                        for char in range(len(line)):
                            if line[char] != '\n':
                                row.append(line[char])
                        transposeArray.append(row)
                else:
                        dictKey = line.replace('\n','').strip('#')
                        X0 = len(transposeArray[0])
                        X1 = len(transposeArray)
                        array = [[transposeArray[x1][x0] for x1 in range(X1)] for x0 in range(X0)]
                        transposeArray = []
                        scenarioDict[dictKey] = array
        return scenarioDict

def loadMapFile(group, x=0, y=0):
        mute()
        notify("This feature coming to your Mage Wars game here soon!")
        return
        directory = os.path.split(os.path.dirname(__file__))[0]+'\{}'.format('maps')
        fileList = [f.split('.')[0] for f in os.listdir(directory) if (os.path.isfile(os.path.join(directory,f)) and f.split('.')[1]=='txt')]
        choices = fileList+['Cancel']
        colors = ['#6600CC' for f in fileList] + ['#FF0000']
        choice = askChoice('Load which map?',choices,colors)
        if choice == 0 or choice == len(choices): return
        notify('{} loads {}.'.format(me,fileList[choice-1]))

        mapArray = scenario.get('Map',False)
        objectsArray = scenario.get('Objects',False)
        creaturesArray= scenario.get('Creatures',False)

        for c in table:
                if c.type == "Internal": c.delete()# or
                   # card.name in ["Sslak, Orb Guardian","Usslak, Greater Orb Guardian"]): card.delete() #We need a way to distinguish between scenario guardians and those in spellbooks
	setNoGameBoard(table)

        #iterate over elements, top to bottom then left to right.
        I,J = len(mapArray),len(mapArray[0])
        X,Y = I*mapTileSize,J*mapTileSize
        x,y = (-X/2,-Y/2) #Do we want 0,0 to be the center, or the upper corner? Currently set as center.

        zoneArray = mapArray

        for i in range(I):
                for j in range(J): #Might as well add support for non-rectangular maps now. Though this won't help with the rows.
                        if mapArray:
                                tile = mapTileDict.get(mapArray[i][j],None)
                                SPT = (True if tile == "c3e970f7-1eeb-432b-ac3f-7dbcd4f45492" else False) #Spiked Pit Trap
                                zoneArray[i][j] = (1 if tile else 0)
                                if tile:
                                        tile = table.create(tile,x,y)
                                        tile.anchor = True
                                        if SPT: table.create("a4b3bb92-b597-441e-b2eb-d18ef6b8cc77",x+mapTileSize/2,y+mapTileSize/2) #Add trap marker
                        y += mapTileSize
                x += mapTileSize
                y = -Y/2
        x = -X/2

        mapDict = createMap(I,J,zoneArray,mapTileSize)

        for i in range(I): #For some reason, I can't get the map tiles to be sent to the back successfully. So we'll do this in two parts.
                for j in range(J):
                        if objectsArray:
                                obj = mapObjectsDict.get(objectsArray[i][j],None)
                                if obj:
                                        duplicate = objectsArray[i][j].istitle()
                                        table.create(obj,
                                                     x+mapObjectOffset,
                                                     y+mapObjectOffset)
                                        if duplicate:
                                                table.create(obj,
                                                                   x+mapObjectOffset+mapMultipleObjectOffset,
                                                                   y+mapObjectOffset)
                        if creaturesArray:
                                if creaturesArray[i][j] in ['1','2','3','4','5','6']: mapDict.get('zoneArray')[i][j]['startLocation'] = creaturesArray[i][j]
                                cre = mapCreaturesDict.get(creaturesArray[i][j],None)
                                if cre:
                                        duplicate = creaturesArray[i][j].istitle()
                                        table.create(cre,
                                                     x+mapCreatureOffset,
                                                     y+mapCreatureOffset)
                                        if duplicate: table.create(cre,
                                                                   x+mapCreatureOffset+mapMultipleCreatureOffset,
                                                                   y+mapCreatureOffset)
                        y += mapTileSize
                x += mapTileSize
                y = -Y/2

        setGlobalVariable("Map",str(mapDict))
        for c in table:
                remoteCall(c.controller,'moveCardToDefaultLocation',[c,True])

### Map Definitions ###

mapTileSize = 250
mapObjectOffset = 175
mapMultipleObjectOffset = -100
mapCreatureOffset = 0
mapMultipleCreatureOffset = 62


mapTileDict = {
                "1" : "5fbc16dd-f861-42c2-ad0f-3f8aaf0ccb64", #V'Torrak
                "2" : "6136ff26-d2d9-44d2-b972-1e26214675b5", #Corrosive Pool
                "3" : "8972d2d1-348c-4c4b-8c9d-a1d235fe482e", #Altar of Oblivion
                "4" : "a47fa32e-ac83-4ced-8f6a-23906ee38880", #Septagram
                "5" : "bf833552-8ee4-4c62-abd2-83da233da4ce", #Molten Rock
                "6" : "c3e970f7-1eeb-432b-ac3f-7dbcd4f45492", #Spiked Pit
                "7" : "edca7d45-53e0-468d-83a5-7a446c81f070", #Samandriel's Circle
                "8" : "f8d70e09-2734-4de8-8351-66fa98ae0171", #Ethereal Mist
                "." : "4f1b033d-7923-4e0e-8c3d-b92ae19fbad1"} #Generic Tile

mapObjectsDict = {
                "Orb" : "3d339a9d-8804-4afa-9bd5-1cabb1bebc9f",
                "Sslak" : "bf217fd3-18c0-4b61-a33a-117167533f3d",
                "Usslak" : "54e67290-5e6a-4d8a-8bf0-bbb8fddf7ddd",
                "SecretPassage" : "a4b3bb92-b597-441e-b2eb-d18ef6b8cc77"}
