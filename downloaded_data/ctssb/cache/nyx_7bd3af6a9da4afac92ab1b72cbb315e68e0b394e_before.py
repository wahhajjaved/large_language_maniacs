"""
Main interface loop for arm, periodically redrawing the screen and issuing
user input to the proper panels.
"""

import os
import time
import curses
import threading

import cli.menu.menu
import cli.wizard
import cli.popups
import cli.headerPanel
import cli.logPanel
import cli.configPanel
import cli.torrcPanel
import cli.graphing.graphPanel
import cli.graphing.bandwidthStats
import cli.graphing.connStats
import cli.graphing.resourceStats
import cli.connections.connPanel

from TorCtl import TorCtl

from util import connections, conf, enum, log, panel, sysTools, torConfig, torTools

ARM_CONTROLLER = None

CONFIG = {"startup.events": "N3",
          "startup.dataDirectory": "~/.arm",
          "startup.blindModeEnabled": False,
          "features.offerTorShutdownOnQuit": False,
          "features.panels.show.graph": True,
          "features.panels.show.log": True,
          "features.panels.show.connection": True,
          "features.panels.show.config": True,
          "features.panels.show.torrc": True,
          "features.redrawRate": 5,
          "features.confirmQuit": True,
          "features.graph.type": 1,
          "features.graph.bw.prepopulate": True,
          "wizard.default": {},
          "log.startTime": log.INFO,
          "log.torEventTypeUnrecognized": log.NOTICE,
          "log.configEntryUndefined": log.NOTICE,
          "log.unknownTorPid": log.WARN}

GraphStat = enum.Enum("BANDWIDTH", "CONNECTIONS", "SYSTEM_RESOURCES")

# maps 'features.graph.type' config values to the initial types
GRAPH_INIT_STATS = {1: GraphStat.BANDWIDTH, 2: GraphStat.CONNECTIONS, 3: GraphStat.SYSTEM_RESOURCES}

def getController():
  """
  Provides the arm controller instance.
  """
  
  return ARM_CONTROLLER

def initController(stdscr, startTime):
  """
  Spawns the controller, and related panels for it.
  
  Arguments:
    stdscr - curses window
  """
  
  global ARM_CONTROLLER
  config = conf.getConfig("arm")
  
  # initializes the panels
  stickyPanels = [cli.headerPanel.HeaderPanel(stdscr, startTime, config),
                  LabelPanel(stdscr)]
  pagePanels, firstPagePanels = [], []
  
  # first page: graph and log
  if CONFIG["features.panels.show.graph"]:
    firstPagePanels.append(cli.graphing.graphPanel.GraphPanel(stdscr))
  
  if CONFIG["features.panels.show.log"]:
    expandedEvents = cli.logPanel.expandEvents(CONFIG["startup.events"])
    firstPagePanels.append(cli.logPanel.LogPanel(stdscr, expandedEvents, config))
  
  if firstPagePanels: pagePanels.append(firstPagePanels)
  
  # second page: connections
  if not CONFIG["startup.blindModeEnabled"] and CONFIG["features.panels.show.connection"]:
    pagePanels.append([cli.connections.connPanel.ConnectionPanel(stdscr, config)])
  
  # third page: config
  if CONFIG["features.panels.show.config"]:
    pagePanels.append([cli.configPanel.ConfigPanel(stdscr, cli.configPanel.State.TOR, config)])
  
  # fourth page: torrc
  if CONFIG["features.panels.show.torrc"]:
    pagePanels.append([cli.torrcPanel.TorrcPanel(stdscr, cli.torrcPanel.Config.TORRC, config)])
  
  # initializes the controller
  ARM_CONTROLLER = Controller(stdscr, stickyPanels, pagePanels)
  
  # additional configuration for the graph panel
  graphPanel = ARM_CONTROLLER.getPanel("graph")
  
  if graphPanel:
    # statistical monitors for graph
    bwStats = cli.graphing.bandwidthStats.BandwidthStats(config)
    graphPanel.addStats(GraphStat.BANDWIDTH, bwStats)
    graphPanel.addStats(GraphStat.SYSTEM_RESOURCES, cli.graphing.resourceStats.ResourceStats())
    if not CONFIG["startup.blindModeEnabled"]:
      graphPanel.addStats(GraphStat.CONNECTIONS, cli.graphing.connStats.ConnStats())
    
    # sets graph based on config parameter
    try:
      initialStats = GRAPH_INIT_STATS.get(CONFIG["features.graph.type"])
      graphPanel.setStats(initialStats)
    except ValueError: pass # invalid stats, maybe connections when in blind mode
    
    # prepopulates bandwidth values from state file
    if CONFIG["features.graph.bw.prepopulate"] and torTools.getConn().isAlive():
      isSuccessful = bwStats.prepopulateFromState()
      if isSuccessful: graphPanel.updateInterval = 4

class LabelPanel(panel.Panel):
  """
  Panel that just displays a single line of text.
  """
  
  def __init__(self, stdscr):
    panel.Panel.__init__(self, stdscr, "msg", 0, height=1)
    self.msgText = ""
    self.msgAttr = curses.A_NORMAL
  
  def setMessage(self, msg, attr = None):
    """
    Sets the message being displayed by the panel.
    
    Arguments:
      msg  - string to be displayed
      attr - attribute for the label, normal text if undefined
    """
    
    if attr == None: attr = curses.A_NORMAL
    self.msgText = msg
    self.msgAttr = attr
  
  def draw(self, width, height):
    self.addstr(0, 0, self.msgText, self.msgAttr)

class Controller:
  """
  Tracks the global state of the interface
  """
  
  def __init__(self, stdscr, stickyPanels, pagePanels):
    """
    Creates a new controller instance. Panel lists are ordered as they appear,
    top to bottom on the page.
    
    Arguments:
      stdscr       - curses window
      stickyPanels - panels shown at the top of each page
      pagePanels   - list of pages, each being a list of the panels on it
    """
    
    self._screen = stdscr
    self._stickyPanels = stickyPanels
    self._pagePanels = pagePanels
    self._page = 0
    self._isPaused = False
    self._forceRedraw = False
    self._isDone = False
    self._torManager = TorManager(self)
    self.setMsg() # initializes our control message
  
  def getScreen(self):
    """
    Provides our curses window.
    """
    
    return self._screen
  
  def getPageCount(self):
    """
    Provides the number of pages the interface has. This may be zero if all
    page panels have been disabled.
    """
    
    return len(self._pagePanels)
  
  def getPage(self):
    """
    Provides the number belonging to this page. Page numbers start at zero.
    """
    
    return self._page
  
  def setPage(self, pageNumber):
    """
    Sets the selected page, raising a ValueError if the page number is invalid.
    
    Arguments:
      pageNumber - page number to be selected
    """
    
    if pageNumber < 0 or pageNumber >= self.getPageCount():
      raise ValueError("Invalid page number: %i" % pageNumber)
    
    if pageNumber != self._page:
      self._page = pageNumber
      self._forceRedraw = True
      self.setMsg()
  
  def nextPage(self):
    """
    Increments the page number.
    """
    
    self.setPage((self._page + 1) % len(self._pagePanels))
  
  def prevPage(self):
    """
    Decrements the page number.
    """
    
    self.setPage((self._page - 1) % len(self._pagePanels))
  
  def isPaused(self):
    """
    True if the interface is paused, false otherwise.
    """
    
    return self._isPaused
  
  def setPaused(self, isPause):
    """
    Sets the interface to be paused or unpaused.
    """
    
    if isPause != self._isPaused:
      self._isPaused = isPause
      self._forceRedraw = True
      self.setMsg()
      
      for panelImpl in self.getAllPanels():
        panelImpl.setPaused(isPause)
  
  def getPanel(self, name):
    """
    Provides the panel with the given identifier. This returns None if no such
    panel exists.
    
    Arguments:
      name - name of the panel to be fetched
    """
    
    for panelImpl in self.getAllPanels():
      if panelImpl.getName() == name:
        return panelImpl
    
    return None
  
  def getStickyPanels(self):
    """
    Provides the panels visibile at the top of every page.
    """
    
    return list(self._stickyPanels)
  
  def getDisplayPanels(self, pageNumber = None, includeSticky = True):
    """
    Provides all panels belonging to a page and sticky content above it. This
    is ordered they way they are presented (top to bottom) on the page.
    
    Arguments:
      pageNumber    - page number of the panels to be returned, the current
                      page if None
      includeSticky - includes sticky panels in the results if true
    """
    
    returnPage = self._page if pageNumber == None else pageNumber
    
    if self._pagePanels:
      if includeSticky:
        return self._stickyPanels + self._pagePanels[returnPage]
      else: return list(self._pagePanels[returnPage])
    else: return self._stickyPanels if includeSticky else []
  
  def getDaemonPanels(self):
    """
    Provides thread panels.
    """
    
    threadPanels = []
    for panelImpl in self.getAllPanels():
      if isinstance(panelImpl, threading.Thread):
        threadPanels.append(panelImpl)
    
    return threadPanels
  
  def getAllPanels(self):
    """
    Provides all panels in the interface.
    """
    
    allPanels = list(self._stickyPanels)
    
    for page in self._pagePanels:
      allPanels += list(page)
    
    return allPanels
  
  def requestRedraw(self, immediate = False):
    """
    Requests that all content is redrawn when the interface is next rendered.
    
    Arguments:
      immediate - redraws now if true, otherwise waits for when next normally
                  drawn
    """
    
    if immediate:
      displayPanels = self.getDisplayPanels()
      
      occupiedContent = 0
      for panelImpl in displayPanels:
        panelImpl.setTop(occupiedContent)
        occupiedContent += panelImpl.getHeight()
      
      for panelImpl in displayPanels:
        panelImpl.redraw(True)
    else:
      self._forceRedraw = True
  
  def isRedrawRequested(self, clearFlag = False):
    """
    True if a full redraw has been requested, false otherwise.
    
    Arguments:
      clearFlag - request clears the flag if true
    """
    
    returnValue = self._forceRedraw
    if clearFlag: self._forceRedraw = False
    return returnValue
  
  def setMsg(self, msg = None, attr = None, redraw = False):
    """
    Sets the message displayed in the interfaces control panel. This uses our
    default prompt if no arguments are provided.
    
    Arguments:
      msg    - string to be displayed
      attr   - attribute for the label, normal text if undefined
      redraw - redraws right away if true, otherwise redraws when display
               content is next normally drawn
    """
    
    if msg == None:
      msg = ""
      
      if attr == None:
        if not self._isPaused:
          msg = "page %i / %i - m: menu, p: pause, h: page help, q: quit" % (self._page + 1, len(self._pagePanels))
          attr = curses.A_NORMAL
        else:
          msg = "Paused"
          attr = curses.A_STANDOUT
    
    controlPanel = self.getPanel("msg")
    controlPanel.setMessage(msg, attr)
    
    if redraw: controlPanel.redraw(True)
    else: self._forceRedraw = True
  
  def getDataDirectory(self):
    """
    Provides the path where arm's resources are being placed. The path ends
    with a slash and is created if it doesn't already exist.
    """
    
    dataDir = CONFIG["startup.dataDirectory"]
    if not dataDir.endswith("/"): dataDir += "/"
    if not os.path.exists(dataDir): os.makedirs(dataDir)
    return os.path.expanduser(dataDir)
  
  def getTorManager(self):
    """
    Provides management utils for an arm managed tor instance.
    """
    
    return self._torManager
  
  def isDone(self):
    """
    True if arm should be terminated, false otherwise.
    """
    
    return self._isDone
  
  def quit(self):
    """
    Terminates arm after the input is processed. Optionally if we're connected
    to a arm generated tor instance then this may check if that should be shut
    down too.
    """
    
    self._isDone = True
    
    if CONFIG["features.offerTorShutdownOnQuit"]:
      conn = torTools.getConn()
      
      if self.getTorManager().isManaged(conn):
        while True:
          msg = "Shut down the Tor instance arm started (y/n)?"
          confirmationKey = cli.popups.showMsg(msg, attr = curses.A_BOLD)
          
          if confirmationKey in (ord('y'), ord('Y')):
            # attempts a graceful shutdown of tor, showing the issue if
            # unsuccessful then continuing the shutdown
            try: conn.shutdown()
            except IOError, exc: cli.popups.showMsg(str(exc), 3, curses.A_BOLD)
            
            break
          elif confirmationKey in (ord('n'), ord('N')):
            break

class TorManager:
  """
  Bundle of utils for starting and manipulating an arm generated tor instance.
  """
  
  def __init__(self, controller):
    self._controller = controller
  
  def getTorrcPath(self):
    """
    Provides the path to a wizard generated torrc.
    """
    
    return self._controller.getDataDirectory() + "torrc"
  
  def isTorrcAvailable(self):
    """
    True if a wizard generated torrc exists, false otherwise.
    """
    
    return os.path.exists(self.getTorrcPath())
  
  def isManaged(self, conn):
    """
    Returns true if the given tor instance is managed by us, false otherwise.
    
    Arguments:
      conn - controller instance to be checked
    """
    
    return conn.getInfo("config-file") == self.getTorrcPath()
  
  def startManagedInstance(self):
    """
    Starts a managed instance of tor, raising an IOError if unsuccessful.
    """
    
    os.system("tor --quiet -f %s&" % self.getTorrcPath())
    startTime = time.time()
    
    # attempts to connect for five seconds (tor might or might not be
    # immediately available)
    torctlConn, authType, authValue, raisedExc = None, None, None, None
    while not torctlConn and time.time() - startTime < 5:
      try:
        torctlConn, authType, authValue = TorCtl.preauth_connect(controlPort = int(CONFIG["wizard.default"]["Control"]))
      except IOError, exc:
        raisedExc == exc
        time.sleep(0.5)
    
    if not torctlConn: raise raisedExc
    
    if authType == TorCtl.AUTH_TYPE.COOKIE:
      torctlConn.authenticate(authValue)
      torTools.getConn().init(torctlConn)
    else:
      raise IOError("unexpected authentication type '%s'" % authType)

def shutdownDaemons():
  """
  Stops and joins on worker threads.
  """
  
  # prevents further worker threads from being spawned
  torTools.NO_SPAWN = True
  
  # stops panel daemons
  control = getController()
  for panelImpl in control.getDaemonPanels(): panelImpl.stop()
  for panelImpl in control.getDaemonPanels(): panelImpl.join()
  
  # joins on TorCtl event thread
  torTools.getConn().close()
  
  # joins on utility daemon threads - this might take a moment since the
  # internal threadpools being joined might be sleeping
  resourceTrackers = sysTools.RESOURCE_TRACKERS.values()
  resolver = connections.getResolver("tor") if connections.isResolverAlive("tor") else None
  for tracker in resourceTrackers: tracker.stop()
  if resolver: resolver.stop()  # sets halt flag (returning immediately)
  for tracker in resourceTrackers: tracker.join()
  if resolver: resolver.join()  # joins on halted resolver

def heartbeatCheck(isUnresponsive):
  """
  Logs if its been ten seconds since the last BW event.
  
  Arguments:
    isUnresponsive - flag for if we've indicated to be responsive or not
  """
  
  conn = torTools.getConn()
  lastHeartbeat = conn.getHeartbeat()
  if conn.isAlive() and "BW" in conn.getControllerEvents():
    if not isUnresponsive and (time.time() - lastHeartbeat) >= 10:
      isUnresponsive = True
      log.log(log.NOTICE, "Relay unresponsive (last heartbeat: %s)" % time.ctime(lastHeartbeat))
    elif isUnresponsive and (time.time() - lastHeartbeat) < 10:
      # really shouldn't happen (meant Tor froze for a bit)
      isUnresponsive = False
      log.log(log.NOTICE, "Relay resumed")
  
  return isUnresponsive

def connResetListener(conn, eventType):
  """
  Pauses connection resolution when tor's shut down, and resumes with the new
  pid if started again.
  """
  
  if connections.isResolverAlive("tor"):
    resolver = connections.getResolver("tor")
    resolver.setPaused(eventType == torTools.State.CLOSED)
    
    if eventType in (torTools.State.INIT, torTools.State.RESET):
      torPid = conn.getMyPid()
      
      if torPid and torPid != resolver.getPid():
        resolver.setPid(torPid)

def startTorMonitor(startTime):
  """
  Initializes the interface and starts the main draw loop.
  
  Arguments:
    startTime - unix time for when arm was started
  """
  
  # initializes interface configs
  config = conf.getConfig("arm")
  config.update(CONFIG)
  
  cli.graphing.graphPanel.loadConfig(config)
  cli.connections.connEntry.loadConfig(config)
  cli.wizard.loadConfig(config)
  
  # attempts to fetch the tor pid, warning if unsuccessful (this is needed for
  # checking its resource usage, among other things)
  conn = torTools.getConn()
  torPid = conn.getMyPid()
  
  if not torPid and conn.isAlive():
    msg = "Unable to determine Tor's pid. Some information, like its resource usage will be unavailable."
    log.log(CONFIG["log.unknownTorPid"], msg)
  
  # adds events needed for arm functionality to the torTools REQ_EVENTS
  # mapping (they're then included with any setControllerEvents call, and log
  # a more helpful error if unavailable)
  
  torTools.REQ_EVENTS["BW"] = "bandwidth graph won't function"
  
  if not CONFIG["startup.blindModeEnabled"]:
    torTools.REQ_EVENTS["CIRC"] = "may cause issues in identifying client connections"
    
    # Configures connection resoultions. This is paused/unpaused according to
    # if Tor's connected or not.
    conn.addStatusListener(connResetListener)
    
    if torPid:
      # use the tor pid to help narrow connection results
      torCmdName = sysTools.getProcessName(torPid, "tor")
      connections.getResolver(torCmdName, torPid, "tor")
    else:
      # constructs singleton resolver and, if tor isn't connected, initizes
      # it to be paused
      connections.getResolver("tor").setPaused(not conn.isAlive())
    
    # hack to display a better (arm specific) notice if all resolvers fail
    connections.RESOLVER_FINAL_FAILURE_MSG += " (connection related portions of the monitor won't function)"
  
  # provides a notice about any event types tor supports but arm doesn't
  missingEventTypes = cli.logPanel.getMissingEventTypes()
  
  if missingEventTypes:
    pluralLabel = "s" if len(missingEventTypes) > 1 else ""
    log.log(CONFIG["log.torEventTypeUnrecognized"], "arm doesn't recognize the following event type%s: %s (log 'UNKNOWN' events to see them)" % (pluralLabel, ", ".join(missingEventTypes)))
  
  try:
    curses.wrapper(drawTorMonitor, startTime)
  except KeyboardInterrupt:
    pass # skip printing stack trace in case of keyboard interrupt
  finally: shutdownDaemons()

def drawTorMonitor(stdscr, startTime):
  """
  Main draw loop context.
  
  Arguments:
    stdscr    - curses window
    startTime - unix time for when arm was started
  """
  
  initController(stdscr, startTime)
  control = getController()
  
  # provides notice about any unused config keys
  for key in conf.getConfig("arm").getUnusedKeys():
    log.log(CONFIG["log.configEntryUndefined"], "Unused configuration entry: %s" % key)
  
  # tells daemon panels to start
  for panelImpl in control.getDaemonPanels(): panelImpl.start()
  
  # allows for background transparency
  try: curses.use_default_colors()
  except curses.error: pass
  
  # makes the cursor invisible
  try: curses.curs_set(0)
  except curses.error: pass
  
  # logs the initialization time
  msg = "arm started (initialization took %0.3f seconds)" % (time.time() - startTime)
  log.log(CONFIG["log.startTime"], msg)
  
  # main draw loop
  overrideKey = None     # uses this rather than waiting on user input
  isUnresponsive = False # flag for heartbeat responsiveness check
  if not torTools.getConn().isAlive(): overrideKey = ord('w') # shows wizard
  
  while not control.isDone():
    displayPanels = control.getDisplayPanels()
    isUnresponsive = heartbeatCheck(isUnresponsive)
    
    # sets panel visability
    for panelImpl in control.getAllPanels():
      panelImpl.setVisible(panelImpl in displayPanels)
    
    # panel placement
    occupiedContent = 0
    for panelImpl in displayPanels:
      panelImpl.setTop(occupiedContent)
      occupiedContent += panelImpl.getHeight()
    
    # redraws visible content
    forceRedraw = control.isRedrawRequested(True)
    for panelImpl in displayPanels:
      panelImpl.redraw(forceRedraw)
    
    stdscr.refresh()
    
    # wait for user keyboard input until timeout, unless an override was set
    if overrideKey:
      key, overrideKey = overrideKey, None
    else:
      curses.halfdelay(CONFIG["features.redrawRate"] * 10)
      key = stdscr.getch()
    
    if key == curses.KEY_RIGHT:
      control.nextPage()
    elif key == curses.KEY_LEFT:
      control.prevPage()
    elif key == ord('p') or key == ord('P'):
      control.setPaused(not control.isPaused())
    elif key == ord('m') or key == ord('M'):
      cli.menu.menu.showMenu()
    elif key == ord('q') or key == ord('Q'):
      # provides prompt to confirm that arm should exit
      if CONFIG["features.confirmQuit"]:
        msg = "Are you sure (q again to confirm)?"
        confirmationKey = cli.popups.showMsg(msg, attr = curses.A_BOLD)
        quitConfirmed = confirmationKey in (ord('q'), ord('Q'))
      else: quitConfirmed = True
      
      if quitConfirmed: control.quit()
    elif key == ord('x') or key == ord('X'):
      # provides prompt to confirm that arm should issue a sighup
      msg = "This will reset Tor's internal state. Are you sure (x again to confirm)?"
      confirmationKey = cli.popups.showMsg(msg, attr = curses.A_BOLD)
      
      if confirmationKey in (ord('x'), ord('X')):
        try: torTools.getConn().reload()
        except IOError, exc:
          log.log(log.ERR, "Error detected when reloading tor: %s" % sysTools.getFileErrorMsg(exc))
    elif key == ord('h') or key == ord('H'):
      overrideKey = cli.popups.showHelpPopup()
    elif key == ord('w') or key == ord('W'):
      cli.wizard.showWizard()
    else:
      for panelImpl in displayPanels:
        isKeystrokeConsumed = panelImpl.handleKey(key)
        if isKeystrokeConsumed: break

