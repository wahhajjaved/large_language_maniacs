# -*- coding: utf-8 -*-

def ReadCfgToOptions(cfgFile = "Options.ini"):
    """
    Read Options.ini file located in the ./cfg/ directory, and return an
    immutable object with fields representing the content of the ini file. The
    fields are: ['nPlayers','playerNames', 'startScores', 'qPoints1',
        'qPoints2' ,'qFileName', 'totalSpins', 'dailyDouble','timeLimit1',
        'timeLimit2', 'enableSound', 'enableAnimation']

    @type	cfgFile: string
    @param	cfgFile: path to the Options.ini

    @rtype	namedTuple
    @return	parsed INI file

    @author: J Wu, johnwuy@gmail.com
    """
    import ConfigParser, os
    from collections import namedtuple as ntp  # use nametuple since immutable

    cfgFile = os.path.join(os.getcwd(), "cfg", cfgFile)
    cp = ConfigParser.RawConfigParser() # configParser
    tmpName = cp.read(cfgFile) # read in config file
    if not tmpName: # if file is not found
        raise IOError('Config file "%s" not found.' % cfgFile)

    # Parse [players] section
    sec = 'players'
    nPlayers = cp.getint(sec, 'numPlayers')
    playerNames = [None for x in range(nPlayers)] # pre-allocate
    startScores = [None for x in range(nPlayers)]
    for n in range(nPlayers):
        playerNames[n] = cp.get(sec, 'name'+str(n+1) )
        startScores[n] = cp.get(sec, 'startScore'+str(n+1))

    # Parse [board] section
    sec = 'board'
    dailyDouble = cp.getboolean(sec, 'dailyDoubleOn')
    qPoints1 = [int(x) for x in cp.get(sec, 'roundOnePoints').split()]
    qPoints2 = [int(x) for x in cp.get(sec, 'roundTwoPoints').split()]
    qFileName = cp.get(sec, 'questionFile')

    # Parse [game] section
    sec = 'game'
    totalSpins = cp.getint(sec, 'totalSpinsPerRound')
    enableSound = cp.getboolean(sec, 'enableSound')
    enableAnimation = cp.getboolean(sec, 'enableAnimation')
    timeLimit1 = cp.getint(sec, 'round1AnswerTimeLimitInSeconds')
    timeLimit2 = cp.getint(sec, 'round2AnswerTimeLimitInSeconds')

    # make the namedtuple
    optionsList = ['nPlayers', 'playerNames', 'startScores', 'qPoints1',
        'qPoints2' ,'qFileName', 'totalSpins', 'dailyDouble','timeLimit1' ,
        'timeLimit2', 'enableSound', 'enableAnimation']
    Options = ntp('Options', optionsList) # Make class
    wojOpt = Options._make([nPlayers, playerNames, startScores, qPoints1,
        qPoints2, qFileName, totalSpins, dailyDouble, timeLimit1, timeLimit2,
        enableSound, enableAnimation]) # instantiate

    return wojOpt
