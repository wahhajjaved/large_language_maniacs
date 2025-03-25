#!/usr/bin/env python
#@+leo-ver=4
#@+node:@file refbot.py
#@@first
"""
An IRC bot for exchanging noderefs with peer freenet users
"""
#@+others
#@+node:imports
import StringIO
import base64
import os
import random
import select
import socket
import string
import sys
import threading
import time
import traceback
import urllib2

import fcp
from minibot import log, MiniBot, PrivateChat, my_exit

have_plugin_module = False;
try:
  import botplugin;
  have_plugin_module = True;
except Exception, msg:
  pass;

#@-node:imports
#@+node:globals
progname = sys.argv[0]
args = sys.argv[1:]
nargs = len(args)

ident = 'FreenetRefBot'

current_config_version = 3

obscenities = ["fuck", "cunt", "shit", "asshole", "fscking", "wank"]
reactToObscenities = False

#@-node:globals
#@+node:exceptions
class NotOwner(Exception):
    """
    peer is telling us to do something only owners can tell us to
    """

#@-node:exceptions
#@+node:class FreenetNodeRefBot
class FreenetNodeRefBot(MiniBot):
    """
    A simple IRC bot
    """

    svnLongRevision = "$Revision$"
    svnRevision = svnLongRevision[ 11 : -2 ]
    minimumNodeBuild = 998;

    #@    @+others
    #@+node:__init__
    def __init__(self, cfgFile=None):
        """
        Takes one optional argument - alternative pathname
        """

        self.bots = {}
        self.botIdentities = {}
        
        log("Starting refbot with the following file versions: refbot.py: r%s  minibot.py: r%s  fcp/node.py: r%s" % (FreenetNodeRefBot.svnRevision, MiniBot.svnRevision, fcp.FCPNode.svnRevision))
        
        # check that we've got an updated fcp/node.py
        try:
            fcpnodepy_revision = fcp.FCPNode.svnRevision;
        except:
            print "This version of the refbot requires a newer version of fcp/node.py.  Please from https://emu.freenetproject.org/svn/trunk/apps/pyFreenet/fcp/node.py and try again.";
            my_exit( 1 );
        
        # determine a config file path
        if not cfgFile:
            cfgFile = os.path.join(os.path.expanduser("~"), ".freenet_ref_bot")
        confpath = self.confpath = cfgFile
    
        # load, or create, a config
        if os.path.isfile(confpath):
            try:
                opts = self.load()
            except Exception, msg:
                print "ERROR loading configuration file:  %s" % ( msg );
                print "ERROR: Failed to load configuration file.  Perhaps it is corrupted?";
                my_exit( 1 );
            needToSave = False
            if( len( opts['usernick'] ) > 12 ):
              print "The node's name used by the bot cannot be any longer than 12 characters because the bot's IRC nickname cannot be any longer than 16 characters and the bot IRC nickname will be this value with '_bot' added to the end.  Try again."
              self.setup_usernick( opts )
              needToSave = True
            elif( opts['usernick'][ -4: ].lower() == "_bot" ):
              print "The node's name used by the bot should not end in \"_bot\" because the bot IRC nickname will use the this node's name with '_bot' added to the end.  Try again."
              self.setup_usernick( opts )
              needToSave = True
            elif( ' ' in opts['usernick'] ):
              print "The node's name used by the bot should not contain spaces because the bot IRC nickname cannot contain spaces.  Try again."
              self.setup_usernick( opts )
              needToSave = True
            elif( '.' in opts['usernick'] ):
              print "The node's name used by the bot should not contain periods because the bot IRC nickname cannot contain periods.  Try again."
              self.setup_usernick( opts )
              needToSave = True
        else:
            opts = self.setup()
            needToSave = True

        if(not opts.has_key('config_version')):
            opts['config_version'] = 0
            needToSave = True
        try:
            self.config_version = int( opts['config_version'] )
        except:
            self.config_version = 0
            needToSave = True

        self.max_cpeers = 30
        self.max_tpeers = 50
        self.cpeers = None
        self.tpeers = None
    
        # now, gotta map from config file to constructor keyword
        kw = {}
    
        # set up keywords from config
        kw['host'] = opts['irchost']
        kw['port'] = opts['ircport']
        if(opts.has_key('ownerircnick')):
            kw['owner'] = opts['ownerircnick']
        else:
            kw['owner'] = opts['usernick']
            needToSave = True
        kw['nodenick'] = opts['usernick']
        kw['password'] = opts['password']
        if(opts.has_key('ircchannel')):
            kw['channel'] = opts['ircchannel']
        else:
            kw['channel'] = "#freenet-refs"
            needToSave = True
    
        # set up non-config keywords
        kw['nick'] = kw['nodenick'] + "_bot"
        kw['peerclass'] = RefBotConversation
        kw['realname'] = "%s's Freenet NodeRef Bot" % kw['nick']
    
        # get local attribs
        self.nodenick = opts['usernick']
        self.refs = opts['refs']
        if(self.config_version < 1 and (not opts.has_key('bot2bot') or (opts.has_key('bot2bot') and opts['bot2bot'] == 'y'))):
            self.setup_bot2bot( opts )
        if(opts.has_key('bot2bot')):
            if( opts['bot2bot'] == 'y' ):
                self.bot2bot_enabled = True
            else:
                self.bot2bot_enabled = False
        else:
            self.bot2bot_enabled = True
            needToSave = True
        # Not implemented yet - **FIXME**
        # **FIXME** Needs config_version check and old config_version upgrading
        #if(opts.has_key('bot2bot_announces')):
        #    if( opts['bot2bot_announce'] == 'y' ):
        #        self.bot2bot_announces_enabled = True
        #    else:
        #        self.bot2bot_announces_enabled = False
        #else:
        #    self.bot2bot_announces_enabled = False
        #    needToSave = True
        if(self.config_version < 1 and (not opts.has_key('bot2bot_trades') or (opts.has_key('bot2bot_trades') and opts['bot2bot_trades'] == 'n'))):
            self.setup_bot2bot_trades( opts )
        if(opts.has_key('bot2bot_trades')):
            if( opts['bot2bot_trades'] == 'y' ):
                self.bot2bot_trades_enabled = True
            else:
                self.bot2bot_trades_enabled = False
        else:
            self.bot2bot_trades_enabled = True
            needToSave = True
        if(self.config_version < 2 and (not opts.has_key('bot2bot_trades_only') or (opts.has_key('bot2bot_trades_only') and opts['bot2bot_trades_only'] == 'n'))):
            self.setup_bot2bot_trades_only( opts )
        if(opts.has_key('bot2bot_trades_only')):
            if( opts['bot2bot_trades_only'] == 'y' ):
                self.bot2bot_trades_only_enabled = True
            else:
                self.bot2bot_trades_only_enabled = False
        else:
            self.bot2bot_trades_only_enabled = False
            needToSave = True
        if(not self.bot2bot_enabled and self.bot2bot_trades_only_enabled):
            print "bot2bot communication is disabled, but trading with other bots only is enabled.  This does not make sense.  Quitting."
            my_exit( 1 );
        if(not self.bot2bot_trades_enabled and self.bot2bot_trades_only_enabled):
            print "bot2bot ref trading is disabled, but trading with other bots only is enabled.  This does not make sense.  Quitting."
            my_exit( 1 );
        if(self.config_version < 3 and (not opts.has_key('privmsg_only') or (opts.has_key('privmsg_only') and opts['privmsg_only'] == 'y'))):
            self.setup_privmsg_only( opts )
        self.refurl = opts['refurl']
        if('' == self.refurl and not self.bot2bot_trades_only_enabled):
            print "configured to trade with humans using a noderef url, but we don't know a noderef url.  This does not make sense.  Quitting."
            my_exit( 1 );
        if(opts.has_key('privmsg_only')):
            if( opts['privmsg_only'] == 'y' ):
                self.privmsg_only_enabled = True
            else:
                self.privmsg_only_enabled = False
        else:
            self.privmsg_only_enabled = True
            needToSave = True
        if(opts.has_key('ircchannel')):
            self.chan = opts['ircchannel']
        else:
            self.chan = "#freenet-refs"
            needToSave = True
        if(opts.has_key('fcp_host')):
            self.fcp_host = opts['fcp_host']
        else:
            self.fcp_host = "127.0.0.1";
            needToSave = True
        if(opts.has_key('fcp_port')):
            self.fcp_port = opts['fcp_port']
        else:
            self.fcp_port = 9481;
            needToSave = True
        if(opts.has_key('greetinterval')):
            try:
                self.greet_interval = int( opts['greetinterval'] )
            except:
                print "Seems you've a bogus value for greetinterval in your config file.  Bailing."
                my_exit( 1 );
        else:
            self.greet_interval = 1800
            needToSave = True
        if(opts.has_key('spaminterval')):
            try:
                self.spam_interval = int( opts['spaminterval'] )
            except:
                print "Seems you've a bogus value for spaminterval in your config file.  Bailing."
                my_exit( 1 );
        else:
            self.spam_interval = 7200
            needToSave = True
        if(opts.has_key('refsperrun')):
            try:
                self.number_of_refs_to_collect = int( opts['refsperrun'] )
            except:
                print "Seems you've a bogus value for refsperrun in your config file.  Bailing."
                my_exit( 1 );
        else:
            self.number_of_refs_to_collect = 10
            needToSave = True
        if(self.number_of_refs_to_collect <= 0):
            print "refsperrun is at or below zero.  Nothing to do.  Quitting."
            my_exit( 1 );
        if(self.number_of_refs_to_collect > 20):
            self.number_of_refs_to_collect = 20
            needToSave = True
        if(opts.has_key('telnethost')):
            self.tmci_host = opts['telnethost']
            needToSave = True
        else:
            if(opts.has_key('tmci_host')):
                self.tmci_host = opts['tmci_host']
            else:
                self.tmci_host = "127.0.0.1";
                needToSave = True
        if(opts.has_key('telnetport')):
            self.tmci_port = opts['telnetport']
            needToSave = True
        else:
            if(opts.has_key('tmci_port')):
                self.tmci_port = opts['tmci_port']
            else:
                self.tmci_port = 2323;
                needToSave = True
        
        # for internal use shadow of MiniBot configs
        self.irc_host = kw[ 'host' ]
        self.irc_port = kw[ 'port' ]
    
        # finally construct the parent
        MiniBot.__init__(self, **kw)
    
        if( self.config_version < current_config_version ):
            self.config_version = current_config_version
            needToSave = True
        if needToSave:
            self.save()

        self.nodeRef = {};
        log("Verifying node build version....")
        try:
          f = fcp.FCPNode( host = self.fcp_host, port = self.fcp_port )
          if( f.nodeBuild < self.minimumNodeBuild ):
            log("ERROR: This version of the refbot requires your node be running build %d or higher.  Please upgrade your Freenet node and try again." % ( self.minimumNodeBuild ))
            f.shutdown()
            my_exit( 1 )
          try:
            noderef = f.refstats();
            if( type( noderef ) == type( [] )):
              noderef = noderef[ 0 ];
            self.nodeIdentity = noderef[ "identity" ];
          except Exception, msg:
            log("ERROR: Failed to get the node's identity via FCP.  This is an odd error this refbot developer is not sure of a reason for.");
            f.shutdown()
            my_exit( 1 )
        except Exception, msg:
          log("ERROR: Failed to connect to node via FCP (%s:%d).  Check your fcp host and port settings on both the node and the bot config." % ( self.fcp_host, self.fcp_port ));
          f.shutdown()
          my_exit( 1 )
        del noderef[ "header" ];
        self.nodeRef = noderef;
    
        while( 'y' != opts['bot2bot_trades_only'] ):
            log("Getting advertised ref from URL...");
            try:
                openurl = urllib2.urlopen(opts['refurl'])
                refbuf = openurl.read(20*1024)  # read up to 20 KiB
                openurl.close()
                refmemfile = StringIO.StringIO(refbuf)
                reflines = refmemfile.readlines()
                refmemfile.close();
            except Exception, msg:
                log("ERROR: Failed to get advertised ref from URL.");
                self.setup_refurl( opts );
                continue;
            log("Checking syntax of advertised ref...");
            ref_fieldset = {};
            end_found = False
            for refline in reflines:
                refline = refline.strip();
                if("" == refline):
                    continue;
                if("end" == refline.lower()):
                    end_found = True
                    break;
                reflinefields = refline.split("=", 1)
                if(2 != len(reflinefields)):
                    continue;
                if(not ref_fieldset.has_key(reflinefields[ 0 ])):
                    ref_fieldset[ reflinefields[ 0 ]] = reflinefields[ 1 ]
            ref_has_syntax_problem = False;
            if(not end_found):
                log("ERROR: Advertised ref does not contain an \"End\" line.");
                ref_has_syntax_problem = True;
            required_ref_fields = [ "dsaGroup.g", "dsaGroup.p", "dsaGroup.q", "dsaPubKey.y", "identity", "location", "myName", "sig" ];
            for require_ref_field in required_ref_fields:
                if(not ref_fieldset.has_key(require_ref_field)):
                    log("ERROR: No %s field in ref" % ( require_ref_field ));
                    ref_has_syntax_problem = True;
            if(ref_has_syntax_problem):
                self.setup_refurl( opts );
                continue;
            if( ref_fieldset[ "identity" ] != self.nodeIdentity ):
                log("ERROR: The advertised ref's identity does not match the node's identity; perhaps your FCP host/port setting is wrong?");
                self.setup_refurl( opts );
                continue;
            log("Test adding advertised ref...");
            try:
                addpeer_result = f.addpeer( kwdict = ref_fieldset )
            except fcp.node.FCPException, msg:
                if( 21 == msg.info[ 'Code' ] ):
                    log("ERROR: The node had trouble parsing the advertised ref");
                    self.setup_refurl( opts );
                    continue;
                elif( 27 == msg.info[ 'Code' ] ):
                    log("ERROR: The node could not verify the signature of the advertised ref");
                    self.setup_refurl( opts );
                    continue;
                elif( 28 == msg.info[ 'Code' ] ):
                    log("The advertised ref appears to be good");
                    break;
                elif( 29 == msg.info[ 'Code' ] ):
                    log("ERROR: The node has a peer with the advertised ref; perhaps your FCP host/port setting is wrong?");
                    f.shutdown()
                    my_exit( 1 )
                log("ERROR: The node had trouble test-adding the advertised ref and gave us an unexpected error; perhaps you need to run updater.py");
                f.shutdown()
                my_exit( 1 )
            except Exception, msg:
                log("ERROR: caught generic exception adding peer: %s" % ( msg ));
                f.shutdown()
                my_exit( 1 )
            try:
                f.removepeer(ref_fieldset[ "identity" ] );
            except Exception, msg:
                pass;
            break;
        f.shutdown()

        self.nrefs = 0
        
        log("Getting Peer Update...")
        temp_cpeers = None;
        temp_dpeers = None;
        peerUpdateCallResult = getPeerUpdateHelper( self.fcp_host, self.fcp_port )
        if( peerUpdateCallResult.has_key( "cpeers" )):
            temp_cpeers = peerUpdateCallResult[ "cpeers" ];
        if( peerUpdateCallResult.has_key( "tpeers" )):
            temp_tpeers = peerUpdateCallResult[ "tpeers" ];
        if( temp_cpeers != None and temp_tpeers != None ):
            while(self.number_of_refs_to_collect > 0 and (self.number_of_refs_to_collect - self.nrefs) > 0 and ((temp_cpeers + (self.number_of_refs_to_collect - self.nrefs)) > self.max_cpeers)):
                self.number_of_refs_to_collect -= 1;
            while(self.number_of_refs_to_collect > 0 and (self.number_of_refs_to_collect - self.nrefs) > 0 and ((temp_tpeers + (self.number_of_refs_to_collect - self.nrefs)) > self.max_tpeers)):
                self.number_of_refs_to_collect -= 1;
            if(self.number_of_refs_to_collect <= 0):
                log("Don't need any more refs, now terminating!")
                my_exit( 1 )
            self.cpeers = temp_cpeers
            self.tpeers = temp_tpeers
    
        self.timeLastChanGreeting = time.time()
        self.haveSentDownloadLink = False
    
        self.lastSendTime = time.time()
        self.sendlock = threading.Lock()
    
        self.adderThreads = []
        self.identityCheckerThreads = []
        self.peerUpdaterThreads = []
        self.peer_update_interval = 60
        self.api_options = []
        if(self.bot2bot_enabled):
            self.api_options.append( "bot2bot" );
            # Not implemented yet - **FIXME**
            #if(self.bot2bot_announces_enabled):
            #    self.api_options.append( "bot2bot_announces" );
            if(self.bot2bot_trades_enabled):
                self.api_options.append( "bot2bot_trades" );
            if(self.bot2bot_trades_only_enabled):
                self.api_options.append( "bot2bot_trades_only" );
            if(self.privmsg_only_enabled):
                self.api_options.append( "privmsg_only" );
    
    #@-node:__init__
    #@+node:setup
    def setup(self):
        """
        """
    
        opts = {}
    
        opts['config_version'] = current_config_version
            
        print
        print "** You will need to be sure to register your IRC nick with freenode"
        print "** so that someone else can't /msg your bot and shut it down"
        print "** while you're away.  Use /msg nickserv register <password>"
        opts['ownerircnick'] = self.prompt("Enter your usual freenode.net IRC nick")
        opts['usernick'] = opts['ownerircnick']
        print
        self.setup_usernick( opts )
        print
        print "** You need to choose a new password, since this bot will"
        print "** register this password with freenode 'nickserv', and"
        print "** on subsequent runs, will identify with this password"
        opts['password'] = self.prompt("Enter a new password")
        opts['ircchannel'] = self.prompt("IRC channel to join", "#freenet-refs")
        opts['irchost'] = self.prompt("Hostname of IRC server", "irc.freenode.net")
    
        while 1:
            opts['ircport'] = self.prompt("IRC Server Port", "6667")
            try:
                opts['ircport'] = int(opts['ircport'])
                break
            except:
                print "Invalid port '%s'.  Try again." % opts['ircport']
    
        opts['tmci_host'] = self.prompt("Node TMCI (telnet) hostname", "127.0.0.1")
    
        while 1:
            opts['tmci_port'] = self.prompt("Node TMCI (telnet) port", "2323")
            try:
                opts['tmci_port'] = int(opts['tmci_port'])
                break
            except:
                print "Invalid port '%s'.  Try again." % opts['tmci_port']
    
        opts['fcp_host'] = self.prompt("Node FCP hostname", "127.0.0.1")
    
        while 1:
            opts['fcp_port'] = self.prompt("Node FCP port", "9481")
            try:
                opts['fcp_port'] = int(opts['fcp_port'])
                break
            except:
                print "Invalid port '%s'.  Try again." % opts['fcp_port']
    
        self.setup_bot2bot( opts )
        #self.setup_bot2bot_announce( opts )  **FIXME** Not implemented yet
        self.setup_bot2bot_trades( opts )
        self.setup_bot2bot_trades_only( opts )
        opts['refurl'] = '';
        self.setup_refurl( opts );
        self.setup_privmsg_only( opts )

        opts['greetinterval'] = 1800
        opts['spaminterval'] = 7200
        opts['refsperrun'] = 10
        opts['refs'] = []
    
        return opts
    
    #@-node:setup
    #@+node:setup_bot2bot
    def setup_bot2bot(self, opts):
        """
        """
        while 1:
            opts['bot2bot'] = self.prompt("Enable bot-2-bot communication (required for bot-2-bot ref trading)", "y")
            opts['bot2bot'] = opts['bot2bot'].lower();
            if( opts['bot2bot'] in [ 'y', 'n' ] ):
                break;
            print "Invalid option '%s' - must be 'y' for yes or 'n' for no" % opts['bot2bot']
    
    #@-node:setup_bot2bot
    #@+node:setup_bot2bot_announces
    def setup_bot2bot_announces(self, opts):
        """
        """
        if( 'y' == opts['bot2bot'] ):
            while 1:
                opts['bot2bot_announces'] = self.prompt("Enable cooperative bot announcements (requires bot-2-bot communication to be enabled)", "n")
                opts['bot2bot_announces'] = opts['bot2bot_announces'].lower();
                if( opts['bot2bot_announces'] in [ 'y', 'n' ] ):
                    break;
                print "Invalid option '%s' - must be 'y' for yes or 'n' for no" % opts['bot2bot_announces']

    
    #@-node:setup_bot2bot_announces
    #@+node:setup_bot2bot_trades
    def setup_bot2bot_trades(self, opts):
        """
        """
        if( 'y' == opts['bot2bot'] ):
            while 1:
                opts['bot2bot_trades'] = self.prompt("Enable bot-2-bot ref trades (requires bot-2-bot communication to be enabled)", "y")
                opts['bot2bot_trades'] = opts['bot2bot_trades'].lower();
                if( opts['bot2bot_trades'] in [ 'y', 'n' ] ):
                    break;
                print "Invalid option '%s' - must be 'y' for yes or 'n' for no" % opts['bot2bot_trades']
        else:
            opts['bot2bot_trades'] = 'n';
    
    #@-node:setup_bot2bot_trades
    #@+node:setup_bot2bot_trades_only
    def setup_bot2bot_trades_only(self, opts):
        """
        """
        if( 'y' == opts['bot2bot_trades'] ):
            while 1:
                opts['bot2bot_trades_only'] = self.prompt("Trade refs via bot-2-bot ref trades only (Don't share a URL or fetch URLs)", "n")
                opts['bot2bot_trades_only'] = opts['bot2bot_trades_only'].lower();
                if( opts['bot2bot_trades_only'] in [ 'y', 'n' ] ):
                    break;
                print "Invalid option '%s' - must be 'y' for yes or 'n' for no" % opts['bot2bot_trades_only']
        else:
            opts['bot2bot_trades_only'] = 'n';
    
    #@-node:setup_bot2bot_trades_only
    #@+node:setup_privmsg_only
    def setup_privmsg_only(self, opts):
        """
        """
        if( 'y' != opts['bot2bot_trades_only'] ):
            while 1:
                opts['privmsg_only'] = self.prompt("Should we only allow ref trades by private message?", "y")
                opts['privmsg_only'] = opts['privmsg_only'].lower();
                if( opts['privmsg_only'] in [ 'y', 'n' ] ):
                    break;
                print "Invalid option '%s' - must be 'y' for yes or 'n' for no" % opts['privmsg_only']
        else:
            opts['privmsg_only'] = 'y';
    
    #@-node:setup_privmsg_only
    #@+node:setup_refurl
    def setup_refurl(self, opts):
        """
        """
        if( 'y' != opts['bot2bot_trades_only'] ):
            opts['refurl'] = self.prompt("URL of your noderef")
        else:
            opts['refurl'] = '';
    
    #@-node:setup_refurl
    #@+node:setup_usernick
    def setup_usernick(self, opts):
        """
        """
        print "** Give a short 12 character or less version of your node's name; The bot will tack \"_bot\" onto the end of it to form it's IRC nick"
        while( 1 ):
            opts['usernick'] = self.prompt("Enter your node's name", opts['usernick'])
            if( len( opts['usernick'] ) > 12 ):
              print "The node's name used by the bot cannot be any longer than 12 characters because the bot's IRC nickname cannot be any longer than 16 characters and the bot IRC nickname will be this value with '_bot' added to the end.  Try again."
            elif( opts['usernick'][ -4: ].lower() == "_bot" ):
              print "The node's name used by the bot should not end in \"_bot\" because the bot IRC nickname will use the this node's name with '_bot' added to the end.  Try again."
            elif( ' ' in opts['usernick'] ):
              print "The node's name used by the bot should not contain spaces because the bot IRC nickname cannot contain spaces.  Try again."
            elif( '.' in opts['usernick'] ):
              print "The node's name used by the bot should not contain periods because the bot IRC nickname cannot contain periods.  Try again."
            else:
              break
    
    #@-node:setup_usernick
    #@+node:save
    def save(self):
    
        f = file(self.confpath, "w")
    
        fmt = "%s = %s\n"
        f.write(fmt % ("config_version", repr(self.config_version)))
        f.write(fmt % ("ownerircnick", repr(self.owner)))
        f.write(fmt % ("ircchannel", repr(self.chan)))
        f.write(fmt % ("usernick", repr(self.nodenick)))
        f.write(fmt % ("irchost", repr(self.host)))
        f.write(fmt % ("ircport", repr(self.port)))
        f.write(fmt % ("tmci_host", repr(self.tmci_host)))
        f.write(fmt % ("tmci_port", repr(self.tmci_port)))
        f.write(fmt % ("fcp_host", repr(self.fcp_host)))
        f.write(fmt % ("fcp_port", repr(self.fcp_port)))
        f.write(fmt % ("refurl", repr(self.refurl)))
        f.write(fmt % ("password", repr(self.password)))
        f.write(fmt % ("greetinterval", repr(self.greet_interval)))
        f.write(fmt % ("spaminterval", repr(self.spam_interval)))
        f.write(fmt % ("refsperrun", repr(self.number_of_refs_to_collect)))
        f.write(fmt % ("refs", repr(self.refs)))
        if(self.bot2bot_enabled):
            f.write(fmt % ("bot2bot", repr('y')))
        else:
            f.write(fmt % ("bot2bot", repr('n')))
        # Not implemented yet - **FIXME**
        #if(self.bot2bot_announces_enabled):
        #    f.write(fmt % ("bot2bot_announces", repr('y')))
        #else:
        #    f.write(fmt % ("bot2bot_announces", repr('n')))
        if(self.bot2bot_trades_enabled):
            f.write(fmt % ("bot2bot_trades", repr('y')))
        else:
            f.write(fmt % ("bot2bot_trades", repr('n')))
        if(self.bot2bot_trades_only_enabled):
            f.write(fmt % ("bot2bot_trades_only", repr('y')))
        else:
            f.write(fmt % ("bot2bot_trades_only", repr('n')))
        if(self.privmsg_only_enabled):
            f.write(fmt % ("privmsg_only", repr('y')))
        else:
            f.write(fmt % ("privmsg_only", repr('n')))
    
        f.close()
    
        log("Saved configuration to %s" % self.confpath)
    
    #@-node:save
    #@+node:load
    def load(self):
    
        opts = {}
        exec file(self.confpath).read() in opts
        log("Read configuration from %s" % self.confpath)
        return opts
    
    #@-node:load
    #@+node:events
    # handle events
    #@+node:on_chanmsg
    def on_chanmsg(self, sender, target, msg):
        """
        Handles a message on the channel, not addressed to the bot
        """
        log("** chanmsg: %s => %s: %s" % (sender, target, repr(msg)))
    
        if reactToObscenities:
            m = msg.lower()
            for o in obscenities:
                if o in m:
                    self.action(self.channel, "blushes")
                    break
        if(self.bot2bot_enabled and -1 != msg.find("bot2bot") and "_bot" == sender[ -4: ]):
            if(not self.bots.has_key(sender)):
                bot_data = {}
                self.bots[ sender ] = bot_data
                log("** bots: %s" % ( self.bots.keys() ))
                self.after(random.randint(7, 20), self.sendBotHello, sender)  # Introduce ourselves after 7-20 seconds
    
    #@-node:on_chanmsg
    #@+node:on_ready
    def on_ready(self):
        """
        Invoked when bot is fully signed in, on channel and ready to play
        """
        if self._restarted:
            self.action(self.channel, "restarted because the server was ignoring it")
        else:
            self.getPeerUpdate()
            self.greetChannel()
        
        self.after(10, self.spamChannel)
        self.after(1, self.process_any_identities_checked)
        self.after(0.5, self.process_any_refs_added)
        self.after(1, self.process_peer_updates)
    
        log("****** on_ready")
    
    #@-node:on_ready
    #@+node:post_on_join
    def post_on_join(self, sender, target):
        """
        When another user (or us) have joined (post processing by inheriting class)
        """
        # We don't know if it's a bot at this point
        pass
        
    #@-node:post_on_join
    #@+node:post_on_nick
    def post_on_nick(self, sender, target):
        """
        When another user (or us) have changed nicks (post processing by inheriting class)
        """
        if(self.bots.has_key( sender )):
          bot_data = self.bots[ sender ]
          del self.bots[ sender ]
          self.bots[ target ] = bot_data
          log("** bots: %s" % ( self.bots.keys() ))
    
    #@-node:post_on_nick
    #@+node:post_on_part
    def post_on_part(self, sender, target, msg):
        """
        When another user (or us) have left a channel (post processing by inheriting class)
        """
        if(self.bots.has_key( sender )):
          del self.bots[ sender ]
          log("** bots: %s" % ( self.bots.keys() ))
    
    #@-node:post_on_part
    #@+node:post_on_quit
    def post_on_quit(self, sender, msg):
        """
        When another user (or us) have quit a server (post processing by inheriting class)
        """
        if(self.bots.has_key( sender )):
            if( self.bots[ sender ].has_key( "identity" )):
                identity = self.bots[ sender ][ "identity" ]
                if( self.botIdentities.has_key( identity )):
                    del self.botIdentities[ identity ]
            del self.bots[ sender ]
            log("** bots: %s" % ( self.bots.keys() ))
    
    #@-node:post_on_quit
    #@-node:events
    #@+node:actions
    # action methods
    
    #@+others
    #@+node:addBotIdentity
    def addBotIdentity(self, botNick, botIdentity ):
    
        if( self.botIdentities.has_key( botIdentity )):
            return False;
        if( not self.bots.has_key( botNick )):
            return False;
        if( self.bots[ botNick ].has_key( "identity" )):
            return False;
        self.bots[ botNick ][ "identity" ] = botIdentity;
        self.botIdentities[ botIdentity ] = botNick;
        return True;
    
    #@-node:addBotIdentity
    #@+node:getPeerUpdate
    def getPeerUpdate(self):
    
        peerUpdaterThread = GetPeerUpdate(self.fcp_host, self.fcp_port)
        self.peerUpdaterThreads.append(peerUpdaterThread)
        peerUpdaterThread.start()
        if(self.peer_update_interval > 0):
            self.after(self.peer_update_interval, self.getPeerUpdate)
    
    #@-node:getPeerUpdate
    #@+node:greetChannel
    def greetChannel(self):
    
        if(self.tpeers == None):
            self.after(0.25, self.greetChannel);
            return;
        if( self.number_of_refs_to_collect <= 0 ):
            return
        refs_to_go = self.number_of_refs_to_collect - self.nrefs
        refs_plural_str = ''
        if( refs_to_go > 1 ):
            refs_plural_str = "s"
        if( self.bot2bot_trades_only_enabled ):
            self.privmsg(
                self.channel,
                "Hi, I'm %s's noderef swap bot.  I'm configured to only trade with other bots.  Send me the \"help\" command to learn how to run your own ref swapping bot.  (%d ref%s to go)" \
                % ( self.nodenick, refs_to_go, refs_plural_str )
            )
        elif( self.privmsg_only_enabled ):
            self.privmsg(
                self.channel,
                "Hi, I'm %s's noderef swap bot.  I'm configured to only trade refs with humans via private message (requires registering with nickserv, i.e. /ns register <password>).  To swap a ref with me, /msg me with your ref url  (%d ref%s to go)" \
                % ( self.nodenick, refs_to_go, refs_plural_str )
            )
        else:
            self.privmsg(
                self.channel,
                "Hi, I'm %s's noderef swap bot.  To swap a ref with me, /msg me or say %s: your_ref_url  (%d ref%s to go)" \
                % ( self.nodenick, self.nick, refs_to_go, refs_plural_str )
            )
        if(self.greet_interval > 0 and not self.bot2bot_trades_only_enabled):
            self.after(self.greet_interval, self.greetChannel)
    
    #@-node:greetChannel
    #@+node:sendBotHello
    def sendBotHello(self, target):
        """
        Introduce ourselves to a just connected bot
        """
        self.privmsg( target, "bothello" )
    
    #@-node:sendBotHello
    #@+node:sendDoRefSwapAllow
    def sendDoRefSwapAllow(self, target):
        """
        Tell the bot with the target IRC nick that we agree to swap refs with them as negotiated
        """
        self.privmsg( target, "dorefswapallow" )
    
    #@-node:sendDoRefSwapAllow
    #@+node:sendDoRefSwapCompleted
    def sendDoRefSwapCompleted(self, target):
        """
        Tell the bot with the target IRC nick that we have completed the negotiated ref swap with them
        """
        self.privmsg( target, "dorefswapcompleted" )
    
    #@-node:sendDoRefSwapCompleted
    #@+node:sendDoRefSwapDeny
    def sendDoRefSwapDeny(self, target):
        """
        Tell the bot with the target IRC nick that we are denying their request to swap refs with us as negotiated
        """
        self.privmsg( target, "dorefswapdeny" )
    
    #@-node:sendDoRefSwapDeny
    #@+node:sendDoRefSwapFailed
    def sendDoRefSwapFailed(self, target):
        """
        Tell the bot with the target IRC nick that we have failed to complete the negotiated ref swap with them
        """
        self.privmsg( target, "dorefswapfailed" )
    
    #@-node:sendDoRefSwapFailed
    #@+node:sendDoRefSwapRequest
    def sendDoRefSwapRequest(self, target):
        """
        Ask the bot with the target IRC nick to swap refs with us
        """
        self.privmsg( target, "dorefswaprequest" )
    
    #@-node:sendDoRefSwapRequest
    #@+node:sendGetIdentity
    def sendGetIdentity(self, target):
        """
        Ask for a bot's identity and send them ours
        """
        if(self.bots.has_key( target ) and not self.bots[ target ].has_key( "identity" )):
            self.privmsg( target, "getidentity %s" % ( self.nodeIdentity ))
    
    #@-node:sendGetIdentity
    #@+node:sendGetOptions
    def sendGetOptions(self, target):
        """
        Ask for a bot's options and send them ours
        """
        if(self.bots.has_key( target ) and not self.bots[ target ].has_key( "options" )):
            self.privmsg( target, "getoptions %s" % ( self.api_options ))
    
    #@-node:sendGetOptions
    #@+node:sendGetRefDirect
    def sendGetRefDirect(self, target):
        """
        Give them our identity
        """
        if(self.bots.has_key( target ) and not self.bots[ target ].has_key( "ref" )):
            self.privmsg( target, "getrefdirect" )
    
    #@-node:sendGetRefDirect
    #@+node:sendMyIdentity
    def sendMyIdentity(self, target):
        """
        Give them our identity
        """
        self.privmsg( target, "myidentity %s" % ( self.nodeIdentity ))
    
    #@-node:sendMyIdentity
    #@+node:sendMyOptions
    def sendMyOptions(self, target):
        """
        Give them our options
        """
        self.privmsg( target, "myoptions %s" % ( self.api_options ))
    
    #@-node:sendMyOptions
    #@+node:setPeerBotOptions
    def setPeerBotOptions(self, botNick, botOptions ):

        if(self.bots.has_key( botNick )):
            try:
                options = eval( botOptions )
            except:
                return
            self.bots[ botNick ][ "options" ] = options;

    #@-node:setPeerBotOptions
    #@+node:spamChannel
    def spamChannel(self):
        """
        Periodic plugs
        """

        if(self.tpeers == None):
            self.after(5, self.spamChannel);
            return
        if( self.number_of_refs_to_collect <= 0 ):
            return
        bot2bot_string = '';
        if( self.bot2bot_enabled ):
            bot2bot_string = "(bot2bot)";
        self.action(
            self.channel,
            "is a Freenet NodeRef Swap-bot owned by %s (install pyfcp as detailed at http://wiki.freenetproject.org/Refbot then run refbot.py; run updater.py periodically)(r%s/r%s)%s" % ( self.owner, FreenetNodeRefBot.svnRevision, MiniBot.svnRevision, bot2bot_string )
            )
        if(self.spam_interval > 0 and not self.bot2bot_trades_only_enabled):
            self.after(self.spam_interval, self.spamChannel)
    
    #@-node:spamChannel
    #@+node:thankChannel
    def thankChannelThenDie(self):
    
        if( self.nrefs > 0 ):
            if( self.number_of_refs_to_collect > 0 ):
                refs_plural_str = ''
                if( self.number_of_refs_to_collect > 1 ):
                    refs_plural_str = "s"
                self.privmsg(
                    self.channel,
                    "OK, I've got my %d noderef%s.  Thanks all." \
                    % ( self.number_of_refs_to_collect, refs_plural_str )
                    )
            else:
                self.privmsg(
                    self.channel,
                    "OK, I've got all the noderefs I need.  Thanks all."
                    )
            self.privmsg(
                self.channel,
                "Bye"
                )
        self.after(4, self.die)
    
    #@-node:thankChannelThenDie
    #@+node:addref
    def addref(self, url, replyfunc, sender_irc_nick, peerRef = None, botAddType = None):
    
        log("** adding ref: %s" % url)
        adderThread = AddRef(self.tmci_host, self.tmci_port, self.fcp_host, self.fcp_port, url, replyfunc, sender_irc_nick, self.irc_host, self.nodeIdentity, self.nodeRef, peerRef, botAddType)
        self.adderThreads.append(adderThread)
        adderThread.start()
    
    #@-node:addref
    #@+node:check_bot_peer_has_option
    def check_bot_peer_has_option( self, botNick, option ):

        if( not self.bots.has_key( botNick )):
            return False;
        if( self.bots[ botNick ].has_key( "options" ) and option in self.bots[ botNick ][ "options" ] ):
            return True;
        return False;
    
    #@-node:check_bot_peer_has_option
    #@+node:check_bot_peer_is_connected
    def check_bot_peer_is_connected( self, botNick ):

        if( not self.bots.has_key( botNick )):
            return False;
        if( self.bots[ botNick ].has_key( "connected" ) and self.bots[ botNick ][ "connected" ] ):
            return True;
        return False;
    
    #@-node:check_bot_peer_is_connected
    #@+node:check_identity_with_node
    def check_identity_with_node(self, botIdentity):
    
        log("** checking identity with node: %s" % ( botIdentity ))
        identityCheckerThread = CheckIdentityWithNode(self.fcp_host, self.fcp_port, botIdentity)
        self.identityCheckerThreads.append(identityCheckerThread)
        identityCheckerThread.start()
    
    #@-node:check_identity_with_node
    #@+node:check_ref_from_bot_and_act
    def check_ref_from_bot_and_act(self, botNick ):

        if( not self.bots.has_key( botNick )):
            log("** can't check a ref from a bot using a nick (%s) we don't have a bots entry for.  They must have disconnected." % ( botNick ));
            return
        if( not self.bots[ botNick ].has_key( "identity" )):
            log("** can't check a ref from a bot using a nick (%s) we don't know the identity of." % ( botNick ));
            return
        botIdentity = self.bots[ botNick ][ "identity" ];
        if( not self.botIdentities.has_key( botIdentity )):
            log("** don't want to check a ref from a bot with an identity (%s) we don't have a botIdentities entry for." % ( botIdentity ));
            return
        if( not self.bots[ botNick ].has_key( "ref" )):
            log("** can't check a ref from a bot using a nick (%s) we don't have any ref lines for." % ( botNick ));
            return
        if( not self.bots[ botNick ].has_key( "ref_terminated" )):
            log("** can't check a ref from a bot using a nick (%s) we don't have all the ref lines for." % ( botNick ));
            return
        if( self.bots[ botNick ].has_key( "ref_is_good" )):
            log("** don't want to check a ref from a bot using a nick (%s) we already think is good." % ( botNick ));
            return
        reflines = self.bots[ botNick ][ "ref" ]
        ref_fieldset = {};
        end_found = False
        for refline in reflines:
            refline = refline.strip();
            if("" == refline):
                continue;
            if("end" == refline.lower()):
                end_found = True
                break;
            reflinefields = refline.split("=", 1)
            if(2 != len(reflinefields)):
                continue;
            if(not ref_fieldset.has_key(reflinefields[ 0 ])):
                ref_fieldset[ reflinefields[ 0 ]] = reflinefields[ 1 ]
        required_ref_fields = [ "dsaGroup.g", "dsaGroup.p", "dsaGroup.q", "dsaPubKey.y", "identity", "location", "myName", "sig" ];
        for require_ref_field in required_ref_fields:
            if(not ref_fieldset.has_key(require_ref_field)):
                log("** bot using nick '%s' gave us a ref missing the required '%d' field." % ( botNick, require_ref_field ));
                del self.bots[ botNick ][ "ref" ]
                del self.bots[ botNick ][ "ref_terminated" ]
                return
        if( ref_fieldset[ "identity" ] == self.nodeIdentity ):
            log("** bot using nick '%s' gave us our own node's ref." % ( botNick ));
            del self.bots[ botNick ][ "ref" ]
            del self.bots[ botNick ][ "ref_terminated" ]
            return
        if( ref_fieldset[ "identity" ] != botIdentity ):
            log("** bot using nick '%s' gave us a ref that doesn't match the identity they claimed they have: %s" % ( botNick, botIdentity ));
            del self.bots[ botNick ][ "ref" ]
            del self.bots[ botNick ][ "ref_terminated" ]
            return
        self.bots[ botNick ][ "ref_is_good" ] = True
        self.privmsg( botNick, "haveref" );

    #@-node:check_ref_from_bot_and_act
    #@+node:check_ref_url_and_complain
    def check_ref_url_and_complain(self, url, replyfunc):
    
        if( "http://code.bulix.org/" == url[ :22 ].lower() and "?raw" != url[ -4: ].lower() ):
            replyfunc("When sharing a code.bulix.org ref url, please include a \"?raw\" at the end (i.e. %s?raw).  Ref not added." % ( url ))
            return False
        if( "http://dark-code.bulix.org/" == url[ :27 ].lower() and "?raw" != url[ -4: ].lower() ):
            replyfunc("When sharing a dark-code.bulix.org ref url, please include a \"?raw\" at the end (i.e. %s?raw).  Ref not added." % ( url ))
            return False
        if( "http://pastebin.ca/" == url[ :19 ].lower() and "raw/" != url[ 19:23 ].lower() ):
            replyfunc("When sharing a pastebin.ca ref url, please use the \"Raw Content Download\" link.  Ref not added.")
            return False
        if( "http://rafb.net/paste/results/" == url[ :30 ].lower() and ".txt" != url[ -4: ].lower() ):
            replyfunc("When sharing a rafb.net ref url, please use the \"Download as Text\" link.  Ref not added.")
            return False
        if( "http://www.rafb.net/paste/results/" == url[ :34 ].lower() and ".txt" != url[ -4: ].lower() ):
            replyfunc("When sharing a www.rafb.net ref url, please use the \"Download as Text\" link.  Ref not added.")
            return False
        return True
    
    #@-node:check_ref_url_and_complain
    #@+node:has_ref
    def has_ref(self, url):
        """
        Checks to see if we've already got the given ref
        """
        if url in self.refs:
            return True
        return False
    #@-node:has_ref
    #@+node:maybe_add_ref
    def maybe_add_ref(self, url, replyfunc, sender_irc_nick):
        """
        Checks, adds and replies to a ref add request
        """
        if( self.check_ref_url_and_complain(url, replyfunc)):
           self.addref(url, replyfunc, sender_irc_nick)
    #@-node:maybe_add_ref
    #@+node:process_any_identities_checked
    def process_any_identities_checked(self):
        if(len(self.identityCheckerThreads) != 0):
            for identityCheckerThread in self.identityCheckerThreads:
                if(not identityCheckerThread.isAlive()):
                    identityCheckerThread.join()
                    log("identityCheckerThread has status: %s  identity: %s  status_msg: %s" % (identityCheckerThread.status, identityCheckerThread.identity, identityCheckerThread.status_msg))
                    self.identityCheckerThreads.remove(identityCheckerThread)
                    status = identityCheckerThread.status
                    botIdentity = identityCheckerThread.identity;
                    if( not self.botIdentities.has_key( botIdentity )):
                        log("** checked bot identity (%s) we don't have a bot nickname for.  They must have disconnected." % ( botIdentity ));
                        continue
                    botNick = self.botIdentities[ botIdentity ];
                    if( not self.bots.has_key( botNick )):
                        log("** checked bot nick (%s) we don't have a bots entry for.  They must have disconnected." % ( botNick ));
                        continue
                    if( self.check_bot_peer_is_connected( botNick )):
                        continue
                    if(1 == status):
                        self.privmsg( botNick, "havepeer" );
                        self.bots[ botNick ][ "connected" ] = True;
                    elif( 0 == status ):
                        if( self.bots[ botNick ].has_key( "ref" ) and self.bots[ botNick ].has_key( "ref_terminated" ) and self.bots[ botNick ].has_key( "ref_is_good" )):
                            self.privmsg( botNick, "haveref" );
                        elif( self.bots[ botNick ].has_key( "ref" )):
                            pass;  # Assume it's currently being sent
                        else:
                            if( self.bot2bot_enabled and self.bot2bot_trades_enabled ):
                                if( self.check_bot_peer_has_option( botNick, "bot2bot_trades" )):
                                    self.after(random.randint(15, 90), self.sendGetRefDirect, botNick)  # Ask for their ref to be sent directly after 15-90 seconds
                    else:
                        log("** error checking bot identity (%s): %s" % ( botIdentity, identityCheckerThread.status_msg ));
        self.after(1, self.process_any_identities_checked)
    
    #@-node:process_any_identities_checked
    #@+node:process_any_refs_added
    def process_any_refs_added(self):
        if(len(self.adderThreads) != 0):
            for adderThread in self.adderThreads:
                if(not adderThread.isAlive()):
                    adderThread.join()
                    log("adderThread has status: %s  url: %s  error_msg: %s" % (adderThread.status, adderThread.url, adderThread.error_msg))
                    self.adderThreads.remove(adderThread)
                    if(0 < adderThread.status):
                        if( adderThread.peerRef != None ):
                            if( adderThread.botAddType == "request" ):
                                self.after(random.randint(7, 20), self.sendDoRefSwapAllow, adderThread.sender_irc_nick)  # After 7-20 seconds, agree to swap refs with them
                            else:
                                self.after(random.randint(7, 20), self.sendDoRefSwapCompleted, adderThread.sender_irc_nick)  # After 7-20 seconds, agree to swap refs with them
                                self.nrefs += 1
                                refs_to_go = self.number_of_refs_to_collect - self.nrefs
                                refs_plural_str = ''
                                if( refs_to_go > 1 ):
                                    refs_plural_str = "s"
                                log("** Added ref via bot2bot trade with %s (%d ref%s to go)" % ( adderThread.sender_irc_nick, refs_to_go, refs_plural_str ))
                                if self.nrefs >= self.number_of_refs_to_collect:
                                    log("Got our %d refs, now terminating!" % ( self.number_of_refs_to_collect ))
                                    self.after(3, self.thankChannelThenDie)
                        elif( self.bot2bot_trades_only_enabled ):
                            log("** Somehow we got in the post-add phase of things, but not from a bot2bot trade when we're doing bot2bot trades only")
                        else:
                            self.refs.append(adderThread.url)
                            self.save()
                            self.nrefs += 1
                            log("** added ref: %s" % adderThread.url)
                            refs_to_go = self.number_of_refs_to_collect - self.nrefs
                            refs_to_go_str = ''
                            if refs_to_go > 0:
                                refs_plural_str = ''
                                if( refs_to_go > 1 ):
                                    refs_plural_str = "s"
                                refs_to_go_str = " (%d ref%s to go)" % ( refs_to_go, refs_plural_str )
                            if(2 == adderThread.status):
                                adderThread.replyfunc("while adding your ref, I noticed that it does not have a physical.udp line.  Once you get a connection and that line is added to your ref, renew the URL you share with people (and bots)")
                            adderThread.replyfunc("added your ref.  Now please add mine <%s> to create a peer connection.%s" % (self.refurl, refs_to_go_str))
                            if self.nrefs >= self.number_of_refs_to_collect:
                                log("Got our %d refs, now terminating!" % ( self.number_of_refs_to_collect ))
                                self.after(3, self.thankChannelThenDie)
                    else:
                        if( adderThread.peerRef != None ):
                            if( adderThread.botAddType == "request" ):
                                self.after(random.randint(7, 20), self.sendDoRefSwapDeny, adderThread.sender_irc_nick)  # After 7-20 seconds, agree to swap refs with them
                            else:
                                self.after(random.randint(7, 20), self.sendDoRefSwapFailed, adderThread.sender_irc_nick)  # After 7-20 seconds, agree to swap refs with them
                        else:
                            error_str = "there was some unknown problem while trying to add your ref.  Try again and/or try again later."
                            if(0 == adderThread.status):
                                error_str = "there was a general error while trying to add your ref.  Try again and/or try again later."
                            elif(-1 == adderThread.status):
                                error_str = "the URL does not contain a valid ref (%s).  Please correct the ref at the URL or the URL itself <%s> and try again." % (adderThread.error_msg, adderThread.url)
                            elif(-2 == adderThread.status):
                                known_pastebin_result = self.url_is_known_pastebin( adderThread.url );
                                if( None == known_pastebin_result ):
                                    error_str = "there was a problem fetching the given URL.  Please correct the URL <%s> and try again or try again later/try a different server if you suspect server troubles." % (adderThread.url)
                                else:
                                    error_str = "there was a problem fetching the given URL.  Please correct the URL <%s> and try again, try again later or perhaps try a different pastebin such as %s" % (adderThread.url, known_pastebin_result)
                            elif(-3 == adderThread.status):
                                error_str = "there was a problem talking to the node.  Please try again later."
                            elif(-4 == adderThread.status):
                                error_str = "the node reports that it already has a peer with that identity.  Ref not re-added."
                            elif(-5 == adderThread.status):
                                error_str = "the node reports that it already has a ref with its own identity.  Ref not added."
                            elif(-6 == adderThread.status):
                                error_str = adderThread.error_msg
                            elif(-7 == adderThread.status):
                                error_str = "the node could not add your peer for some reason.  Gave it a corrupted ref maybe?  It cannot be edited nor \"word wrapped\".  Check your ref and try again.  Ref not added."
                            refs_to_go = self.number_of_refs_to_collect - self.nrefs
                            refs_to_go_str = ''
                            if refs_to_go > 0:
                                refs_plural_str = ''
                                if( refs_to_go > 1 ):
                                    refs_plural_str = "s"
                                refs_to_go_str = " (%d ref%s to go)" % ( refs_to_go, refs_plural_str )
                            adderThread.replyfunc("%s%s" % (error_str, refs_to_go_str))
        self.after(0.5, self.process_any_refs_added)
    
    #@-node:process_any_refs_added
    #@+node:process_peer_updates
    def process_peer_updates(self):
        if(len(self.peerUpdaterThreads) != 0):
            for peerUpdaterThread in self.peerUpdaterThreads:
                if(not peerUpdaterThread.isAlive()):
                    peerUpdaterThread.join()
                    self.peerUpdaterThreads.remove(peerUpdaterThread)
                    if(peerUpdaterThread.cpeers == None):
                        continue
                    if(peerUpdaterThread.tpeers == None):
                        continue
                    while(self.number_of_refs_to_collect > 0 and (self.number_of_refs_to_collect - self.nrefs) > 0 and ((peerUpdaterThread.cpeers + (self.number_of_refs_to_collect - self.nrefs)) > self.max_cpeers)):
                        self.number_of_refs_to_collect -= 1;
                    while(self.number_of_refs_to_collect > 0 and (self.number_of_refs_to_collect - self.nrefs) > 0 and ((peerUpdaterThread.tpeers + (self.number_of_refs_to_collect - self.nrefs)) > self.max_tpeers)):
                        self.number_of_refs_to_collect -= 1;
                    if(self.number_of_refs_to_collect <= 0):
                        log("Don't need any more refs, now terminating!")
                        self.after(3, self.thankChannelThenDie)
                        break
                    self.cpeers = peerUpdaterThread.cpeers
                    self.tpeers = peerUpdaterThread.tpeers
        self.after(1, self.process_peer_updates)
    
    #@-node:process_peer_updates
    #@+node:prompt
    def prompt(self, msg, dflt=None):
        if dflt:
            return raw_input(msg + " [%s]: " % dflt) or dflt
        else:
            while 1:
                resp = raw_input(msg + ": ")
                if resp:
                    return resp

    #@-node:prompt
    #@+node:url_is_known_pastebin
    def url_is_known_pastebin(self, url):
    
        if( "http://code.bulix.org/" == url[ :22 ].lower() ):
            return "pastebin.ca or rafb.net/paste/"
        if( "http://dark-code.bulix.org/" == url[ :27 ].lower() ):
            return "pastebin.ca or rafb.net/paste/"
        if( "http://pastebin.ca/" == url[ :19 ].lower() ):
            return "dark-code.bulix.org or rafb.net/paste/"
        if( "http://rafb.net/paste/results/" == url[ :30 ].lower() ):
            return "dark-code.bulix.org or pastebin.ca"
        if( "http://www.rafb.net/paste/results/" == url[ :34 ].lower() ):
            return "dark-code.bulix.org or pastebin.ca"
        return None
    
    #@-node:url_is_known_pastebin
    #@-others
    
    #@-node:actions
    #@+node:low level
    # low level methods
    
    #@+others
    #@+node:thrd
    def thrd(self):
    
        while 1:
            time.sleep(10)
            self.sendline("PING")
    
            now = time.time()
            t = now - self.timeLastChanGreeting
            if(self.greet_interval > 0 and t > self.greet_interval and not self.bot2bot_trades_only_enabled):
                self.greetChannel()
    
    #@-node:thrd
    #@-others
    
    #@-node:low level
    #@-others

#@-node:class FreenetNodeRefBot
#@+node:class RefBotConversation
class RefBotConversation(PrivateChat):
    """
    Encapsulates a private chat with a peer
    """
    #@    @+others
    #@+node:events
    # event handling methods
    
    #@+others
    #@+node:on_unknownCommand
    def on_unknownCommand(self, replyfunc, is_from_privmsg, cmd, msg):
        """
        Pick up possible URLs
        """
        if(cmd.startswith("http://")):
            if( self.bot.bot2bot_trades_only_enabled ):
                replyfunc("Sorry, I'm configured to only trade refs with other bots.  Send me the \"help\" command to learn how to run your own ref swapping bot.")
                return True
            if( self.bot.privmsg_only_enabled and not is_from_privmsg ):
                replyfunc = self.privmsg
            if(cmd == self.bot.refurl):
                self.privmsg("error - already have my own ref <%s>" % (cmd))
                return True
            if(not self.bot.has_ref(cmd)):
                self.bot.maybe_add_ref(cmd.strip(), replyfunc, self.peernick)
            else:
                self.privmsg("error - already have your ref <%s>" % (cmd))
            return True
    
    #@-node:on_unknownCommand
    #@-others
    
    #@-node:events
    #@+node:actions
    # action methods
    
    #@+others
    #@-others
    
    #@-node:actions
    #@+node:command handlers
    # command handlers
    
    #@+others
    #@+node:cmd_addref
    def cmd_addref(self, replyfunc, is_from_privmsg, args):
    
        if( self.bot.bot2bot_trades_only_enabled ):
            replyfunc("Sorry, I'm configured to only trade refs with other bots.  Send me the \"help\" command to learn how to run your own ref swapping bot.")
            return
        if( self.bot.privmsg_only_enabled and not is_from_privmsg ):
            replyfunc = self.privmsg
        if len(args) != 1:
            self.privmsg(
                "Invalid argument count",
                "Syntax: addref <url>"
                )
            return
        
        url = args[0]
        if(url == self.bot.refurl):
            self.privmsg("error - already have my own ref <%s>" % (url))
            return
        if(not self.bot.has_ref(url)):
            self.bot.maybe_add_ref(url.strip(), replyfunc, self.peernick)
        else:
            self.privmsg("error - already have your ref <%s>"% (url))
    
    #@-node:cmd_addref
    #@+node:cmd_bothello
    def cmd_bothello( self, replyfunc, is_from_privmsg, args ):
        if( self.bot.bot2bot_enabled ):
            if(not self.bot.bots.has_key( self.peernick )):
                bot_data = {}
                self.bot.bots[ self.peernick ] = bot_data
                log("** bots: %s" % ( self.bot.bots.keys() ))
            if(self.bot.bots.has_key( self.peernick ) and not self.bot.bots[ self.peernick ].has_key( "options" )):
                self.after(random.randint(7, 20), self.bot.sendGetOptions, self.peernick)  # Ask for their options after 7-20 seconds
    
    #@-node:cmd_bothello
    #@+node:cmd_dorefswapallow
    def cmd_dorefswapallow(self, replyfunc, is_from_privmsg, args):
        # NOTE: We'll not have asked if from our perspective we didn't want to swap, but we don't want to add a ref for a bot we don't think we can respond to (because they disconnected or something)
        # NOTE: Also, we don't want anybody to try to "cheat" the "negotiation" scheme
        if( self.bot.bot2bot_enabled and self.bot.bot2bot_trades_enabled ):
            if( self.bot.check_bot_peer_has_option( self.peernick, "bot2bot_trades" )):
                if( self.bot.bots[ self.peernick ].has_key( "ref" ) and self.bot.bots[ self.peernick ].has_key( "ref_terminated" ) and self.bot.bots[ self.peernick ].has_key( "ref_is_good" )):
                    self.bot.addref( "(from bot: %s)" % ( self.peernick ), replyfunc, self.peernick, self.bot.bots[ self.peernick ][ "ref" ], "allow" )
    
    #@-node:cmd_dorefswapallow
    #@+node:cmd_dorefswapcompleted
    def cmd_dorefswapcompleted(self, replyfunc, is_from_privmsg, args):
        self.bot.nrefs += 1
        refs_to_go = self.bot.number_of_refs_to_collect - self.bot.nrefs
        refs_plural_str = ''
        if( refs_to_go > 1 ):
            refs_plural_str = "s"
        log("** Added ref via bot2bot trade with adderThread.sender_irc_nick (%d ref%s to go)" % ( refs_to_go, refs_plural_str ))
        if self.bot.nrefs >= self.bot.number_of_refs_to_collect:
            log("Got our %d refs, now terminating!" % ( self.bot.number_of_refs_to_collect ))
            self.after(3, self.bot.thankChannelThenDie)
    
    #@-node:cmd_dorefswapcompleted
    #@+node:cmd_dorefswapdeny
    def cmd_dorefswapdeny(self, replyfunc, is_from_privmsg, args):
        pass  # So nothing is going to continue from here in the current "state machine"

    #@-node:cmd_dorefswapdeny
    #@+node:cmd_dorefswapfailed
    def cmd_dorefswapfailed(self, replyfunc, is_from_privmsg, args):
        pass  # So nothing is going to continue from here in the current "state machine"

    #@-node:cmd_dorefswapfailed
    #@+node:cmd_dorefswaprequest
    def cmd_dorefswaprequest(self, replyfunc, is_from_privmsg, args):
        if( self.bot.bot2bot_enabled and self.bot.bot2bot_trades_enabled ):
            if( self.bot.check_bot_peer_has_option( self.peernick, "bot2bot_trades" )):
                if( self.bot.bots[ self.peernick ].has_key( "ref" ) and self.bot.bots[ self.peernick ].has_key( "ref_terminated" ) and self.bot.bots[ self.peernick ].has_key( "ref_is_good" )):
                    # NOTE: Later we may have some criterion for rejecting the request other than we don't have their ref and we don't trade refs or we don't do bot2bot at all
                    self.bot.addref( "(from bot: %s)" % ( self.peernick ), replyfunc, self.peernick, self.bot.bots[ self.peernick ][ "ref" ], "request" )
                    return
        self.after(random.randint(7, 20), self.bot.sendDoRefSwapDeny, self.peernick)  # After 7-20 seconds, deny their request to swap refs
    
    #@-node:cmd_dorefswaprequest
    #@+node:cmd_error
    def cmd_error(self, replyfunc, is_from_privmsg, args):
        pass
    
    #@-node:cmd_error
    #@+node:cmd_getidentity
    def cmd_getidentity(self, replyfunc, is_from_privmsg, args):
        
        self.bot.sendMyIdentity( self.peernick )
        if( 1 == len( args ) and self.bot.bots.has_key( self.peernick )):
            peerIdentity = args[ 0 ];
            if( not self.bot.botIdentities.has_key( peerIdentity )):
                self.bot.addBotIdentity( self.peernick, peerIdentity );
                log("** botIdentities: %s" % ( self.bot.botIdentities.keys() ))
                if( not self.bot.check_bot_peer_is_connected( self.peernick )):
                    if( self.bot.bot2bot_enabled and self.bot.bot2bot_trades_enabled ):
                        if( self.bot.check_bot_peer_has_option( self.peernick, "bot2bot_trades" )):
                            self.bot.check_identity_with_node( peerIdentity )
    
    #@-node:cmd_getidentity
    #@+node:cmd_getoptions
    def cmd_getoptions(self, replyfunc, is_from_privmsg, args):
        
        args = string.join( args, " " );
        self.bot.sendMyOptions( self.peernick )
        if( self.bot.bots.has_key( self.peernick )):
            self.bot.setPeerBotOptions( self.peernick, args );
    
    #@-node:cmd_getoptions
    #@+node:cmd_getref
    def cmd_getref(self, replyfunc, is_from_privmsg, args):
        
        if( self.bot.bot2bot_trades_only_enabled ):
            replyfunc("Sorry, I'm configured to only trade refs with other bots.  Send me the \"help\" command to learn how to run your own ref swapping bot.")
            return
        if( self.bot.privmsg_only_enabled and not is_from_privmsg ):
            replyfunc("Sorry, I'm configured to only trade refs using private messages.  Use the /msg command to send me a private message, after registering with nickserv if needed (i.e. /ns register <password>).")
            return
        replyfunc("My ref is at %s" % self.bot.refurl)
    
    #@-node:cmd_getref
    #@+node:cmd_getrefdirect
    def cmd_getrefdirect(self, replyfunc, is_from_privmsg, args):
        
        if( self.bot.bot2bot_trades_only_enabled and not self.bot.bots.has_key( self.peernick )):
            replyfunc("Sorry, I'm configured to only trade refs with other bots.  Send me the \"help\" command to learn how to run your own ref swapping bot.")
            return
        if( self.bot.privmsg_only_enabled and not is_from_privmsg ):
            replyfunc("Sorry, I'm configured to only trade refs using private messages.  Use the /msg command to send me a private message, after registering with nickserv if needed (i.e. /ns register <password>).")
            return
        nodeRefKeys = self.bot.nodeRef.keys()
        nodeRefKeys.sort()
        # Spread out the lines of the ref so we don't trigger the babbler detector of a receiving refbot
        nextWhen = 0;
        for nodeRefKey in nodeRefKeys:
            self.after( nextWhen, self.privmsg, "refdirect %s=%s" % ( nodeRefKey, self.bot.nodeRef[ nodeRefKey ] ))
            nextWhen += random.randint(7,14)  # 7-14 seconds between each line
        self.after( nextWhen, self.privmsg, "refdirect End" )
    
    #@-node:cmd_getrefdirect
    #@+node:cmd_havepeer
    def cmd_havepeer(self, replyfunc, is_from_privmsg, args):
        if( 1 == len( args ) and self.bot.bots.has_key( self.peernick )):
            self.bot.bots[ self.peernick ][ "connected" ] = True;
    
    #@-node:cmd_havepeer
    #@+node:cmd_haveref
    def cmd_haveref(self, replyfunc, is_from_privmsg, args):
        if( self.bot.bot2bot_enabled and self.bot.bot2bot_trades_enabled ):
            if( self.bot.check_bot_peer_has_option( self.peernick, "bot2bot_trades" )):
                if( self.bot.bots[ self.peernick ].has_key( "ref" ) and self.bot.bots[ self.peernick ].has_key( "ref_terminated" ) and self.bot.bots[ self.peernick ].has_key( "ref_is_good" )):
                    self.after(random.randint(7, 20), self.bot.sendDoRefSwapRequest, self.peernick)  # Ask to swap refs with them after 7-20 seconds
    
    #@-node:cmd_haveref
    #@+node:cmd_help
    def cmd_help(self, replyfunc, is_from_privmsg, args):
    
        self.privmsg(
            "I am a bot for exchanging freenet noderefs",
            "I am part of pyfcp.  To run your own copy of me, install pyfcp as detailed at http://wiki.freenetproject.org/Refbot and then run refbot.py",
            "If you do run your own copy of me, you'll want to run my updater.py script periodically to make sure you have my latest features and bug fixes.",
            "My version numbers are refbot.py at r%s and minibot.py at r%s" % (FreenetNodeRefBot.svnRevision, MiniBot.svnRevision),
            "Available commands:",
            "  help        - display this help",
            "  version     - display the above version information",
            "  die         - terminate me (PM from owner only)"
        )
        if( not self.bot.bot2bot_trades_only_enabled ):
            self.privmsg(
                "  addref <URL> - add ref at <URL> to my node",
                "  getref      - print out my own ref so you can add me"
            )
        self.privmsg(
            "** (end of help listing) **"
        )
    
    #@-node:cmd_help
    #@+node:cmd_hi
    def cmd_hi(self, replyfunc, is_from_privmsg, args):
    
        log("cmd_hi: %s" % str(args))
    
        self.action("waits for a bit")
    
        self.privmsg("Hi - type 'help' for help")
    
    #@-node:cmd_hi
    #@+node:cmd_identity
    def cmd_identity(self, replyfunc, is_from_privmsg, args):
    
        self.privmsg(
            "identity: %s" % (self.bot.nodeIdentity),
            )
    
    #@-node:cmd_identity
    #@+node:cmd_myidentity
    def cmd_myidentity(self, replyfunc, is_from_privmsg, args):
        
        if( 1 == len( args ) and self.bot.bots.has_key( self.peernick )):
            peerIdentity = args[ 0 ];
            if( not self.bot.botIdentities.has_key( peerIdentity )):
                self.bot.addBotIdentity( self.peernick, peerIdentity )
                log("** botIdentities: %s" % ( self.bot.botIdentities.keys() ))
                if( self.bot.bot2bot_enabled and self.bot.bot2bot_trades_enabled ):
                    if( self.bot.check_bot_peer_has_option( self.peernick, "bot2bot_trades" )):
                        self.bot.check_identity_with_node( peerIdentity )
    
    #@-node:cmd_myidentity
    #@+node:cmd_myoptions
    def cmd_myoptions(self, replyfunc, is_from_privmsg, args):
        
        args = string.join( args, " " );
        if( self.bot.bots.has_key( self.peernick )):
            self.bot.setPeerBotOptions( self.peernick, args );
            if(self.bot.bots.has_key( self.peernick ) and not self.bot.bots[ self.peernick ].has_key( "identity" )):
                self.after(random.randint(7, 20), self.bot.sendGetIdentity, self.peernick)  # Ask for their identity after 7-20 seconds
    
    #@-node:cmd_myoptions
    #@+node:cmd_options
    def cmd_options(self, replyfunc, is_from_privmsg, args):
    
        self.privmsg(
            "options: %s" % (self.bot.api_options),
            )
    
    #@-node:cmd_options
    #@+node:cmd_refdirect
    def cmd_refdirect(self, replyfunc, is_from_privmsg, args):

        args = string.join( args, " " );
        if( self.bot.bots.has_key( self.peernick )):
            peerRefLine = args;
            if( not self.bot.bots[ self.peernick ].has_key( "ref" )):
                self.bot.bots[ self.peernick ][ "ref" ] = []
            self.bot.bots[ self.peernick ][ "ref" ].append( peerRefLine )
            if("end" == peerRefLine.lower()):
                self.bot.bots[ self.peernick ][ "ref_terminated" ] = True
                self.bot.check_ref_from_bot_and_act( self.peernick )
    
    #@-node:cmd_refdirect
    #@+node:cmd_version
    def cmd_version(self, replyfunc, is_from_privmsg, args):
    
        self.privmsg(
            "version: refbot.py: r%s  minibot.py: r%s  fcp/node.py: r%s" % (FreenetNodeRefBot.svnRevision, MiniBot.svnRevision, fcp.FCPNode.svnRevision),
            )
    
    #@-node:cmd_version
    #@-others
    
    #@-node:command handlers
    #@-others

#@-node:class RefBotConversation
#@+node:class AddRef
class AddRef(threading.Thread):

    minimumFCPAddNodeBuild = 1008;

    def __init__(self, tmci_host, tmci_port, fcp_host, fcp_port, url, replyfunc, sender_irc_nick, irc_host, nodeIdentity, nodeRef, peerRef, botAddType):
        threading.Thread.__init__(self)
        self.tmci_host = tmci_host
        self.tmci_port = tmci_port
        self.fcp_host = fcp_host
        self.fcp_port = fcp_port
        self.url = url
        self.replyfunc = replyfunc
        self.sender_irc_nick = sender_irc_nick
        self.irc_host = irc_host
        self.nodeIdentity = nodeIdentity
        self.nodeRef = nodeRef
        self.peerRef = peerRef
        self.botAddType = botAddType
        self.status = 0
        self.error_msg = None
        self.plugin_args = { "fcp_module" : fcp, "tmci_host" : self.tmci_host, "tmci_port" : self.tmci_port, "fcp_host" : self.fcp_host, "fcp_port" : self.fcp_port, "sender_irc_nick" : self.sender_irc_nick, "irc_host" : self.irc_host, "log_function" : log, "reply_function" : self.replyfunc, "nodeIdentity" : self.nodeIdentity, "nodeRef" : self.nodeRef, "botAddType" : self.botAddType };

    def run(self):
        if( self.peerRef == None ):
          try:
            openurl = urllib2.urlopen(self.url)
            refbuf = openurl.read(20*1024)  # read up to 20 KiB
            openurl.close()
            refmemfile = StringIO.StringIO(refbuf)
            reflines = refmemfile.readlines()
            refmemfile.close();
          except Exception, msg:
            self.status = -2
            self.error_msg = msg
            return
        else:
          reflines = self.peerRef
        ref_fieldset = {};
        end_found = False
        for refline in reflines:
            refline = refline.strip();
            if("" == refline):
                continue;
            if("end" == refline.lower()):
                end_found = True
                break;
            reflinefields = refline.split("=", 1)
            if(2 != len(reflinefields)):
                continue;
            if(not ref_fieldset.has_key(reflinefields[ 0 ])):
                ref_fieldset[ reflinefields[ 0 ]] = reflinefields[ 1 ]
        required_ref_fields = [ "dsaGroup.g", "dsaGroup.p", "dsaGroup.q", "dsaPubKey.y", "identity", "location", "myName", "sig" ];
        for require_ref_field in required_ref_fields:
            if(not ref_fieldset.has_key(require_ref_field)):
                self.status = -1  # invalid ref found at URL
                self.error_msg = "No %s field in ref" % ( require_ref_field );
                return
        if( ref_fieldset[ "identity" ] == self.nodeIdentity ):
            self.status = -5
            self.error_msg = "Node already has a ref with its own identity"
            f.shutdown();
            return

        try:
          f = fcp.FCPNode( host = self.fcp_host, port = self.fcp_port )
          if( have_plugin_module ):
            try:
              self.plugin_args[ "fcpNode" ] = f;
              self.plugin_args[ "ref" ] = ref_fieldset;
              plugin_result = botplugin.pre_add( self.plugin_args );
              if( plugin_result != None ):
                self.status = -6
                self.error_msg = plugin_result
                f.shutdown();
                return
            except Exception, msg:
              log("Got exception calling botplugin.pre_add(): %s" % ( msg ));
          returned_peer = f.modifypeer( NodeIdentifier = ref_fieldset[ "identity" ] )
          if( type( returned_peer ) == type( [] )):
              returned_peer = returned_peer[ 0 ];
          if( returned_peer[ "header" ] == "Peer" ):
              self.status = -4
              self.error_msg = "Node already has a peer with that identity"
              f.shutdown();
              return
          if( f.nodeBuild < self.minimumFCPAddNodeBuild ):
              sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
              sock.connect((self.tmci_host, self.tmci_port))
              
              # wait for something to come in
              sock.recv(1)
              time.sleep(0.1)
              
              # wait till node stops sending
              while len(select.select([sock], [], [], 0.1)[0]) > 0:
                  sock.recv(1024)
                  
              sock.send("ADDPEER:\r\n")
              for refline in reflines:
                  refline = refline.strip()
                  sock.send("%s\r\n" % (refline))
              
              # wait for something to come in
              sock.recv(1)
              time.sleep(0.1)
              
              # wait till node stops sending
              while len(select.select([sock], [], [], 0.1)[0]) > 0:
                  buf = sock.recv(1024)
                  sys.stdout.write(buf)
                  sys.stdout.flush()
              print
              
              sock.close()
          else:
              addpeer_result = f.addpeer( kwdict = ref_fieldset )
        except Exception, msg:
          self.status = -3
          self.error_msg = msg
          if(f != None):
            f.shutdown();
          return  

        try:
          returned_peer = f.modifypeer( NodeIdentifier = ref_fieldset[ "identity" ] )
          if( type( returned_peer ) == type( [] )):
            returned_peer = returned_peer[ 0 ];
          if( returned_peer[ "header" ] == "UnknownNodeIdentifier" ):
              self.status = -7
              self.error_msg = "Node couldn't add peer for some reason."
              f.shutdown();
              return
        except Exception, msg:
          # We'll let this part fail open for now
          pass
        if( have_plugin_module ):
          try:
            plugin_result = botplugin.post_add( self.plugin_args );
          except Exception, msg:
            log("Got exception calling botplugin.post_add(): %s" % ( msg ));
        try:
          if( self.peerRef == None ):
            note_text = "%s added via refbot.py from %s@%s at %s" % ( ref_fieldset[ "myName" ], self.sender_irc_nick, self.irc_host, time.strftime( "%Y%m%d-%H%M%S", time.localtime() ) )
          else:
            note_text = "%s bot2bot traded via refbot.py with %s@%s at %s" % ( ref_fieldset[ "myName" ], self.sender_irc_nick, self.irc_host, time.strftime( "%Y%m%d-%H%M%S", time.localtime() ) )
          encoded_note_text = base64.encodestring( note_text ).replace( "\r", "" ).replace( "\n", "" );
          f.modifypeernote( NodeIdentifier = ref_fieldset[ "identity" ], PeerNoteType = fcp.node.PEER_NOTE_PRIVATE_DARKNET_COMMENT, NoteText = encoded_note_text )
        except Exception, msg:
          # We'll just not have added a private peer note if we get an exception here
          pass
        f.shutdown();

        if(not ref_fieldset.has_key("physical.udp")):
            self.status = 2
            self.error_msg = "No physical.udp field in ref"
            return
        self.status = 1

#@-node:class AddRef
#@+node:class CheckIdentityWithNode
class CheckIdentityWithNode(threading.Thread):
    def __init__(self, fcp_host, fcp_port, identity):
        threading.Thread.__init__(self)
        self.fcp_host = fcp_host
        self.fcp_port = fcp_port
        self.identity = identity
        self.status = -1
        self.status_msg = None

    def run(self):
        try:
          f = fcp.FCPNode( host = self.fcp_host, port = self.fcp_port )
          returned_peer = f.modifypeer( NodeIdentifier = self.identity )
          if( type( returned_peer ) == type( [] )):
            returned_peer = returned_peer[ 0 ];
          if( returned_peer[ "header" ] == "Peer" ):
              self.status = 1
              self.status_msg = "Node already has a peer with that identity"
              f.shutdown();
              return
          self.status = 0
          self.status_msg = "Node does not yet have a peer with that identity"
          f.shutdown();
          return
        except Exception, msg:
          self.status = -1
          self.status_msg = msg
          if(f != None):
            f.shutdown();
          return  

#@-node:class CheckIdentityWithNode
#@+node:class GetPeerUpdate
class GetPeerUpdate(threading.Thread):
    def __init__(self, fcp_host, fcp_port):
        threading.Thread.__init__(self)
        self.fcp_host = fcp_host
        self.fcp_port = fcp_port
        self.status = -1
        self.status_msg = None
        self.cpeers = None
        self.tpeers = None

    def run(self):
        peerUpdateCallResult = getPeerUpdateHelper( self.fcp_host, self.fcp_port )
        if( peerUpdateCallResult.has_key( "status" )):
            self.status = peerUpdateCallResult[ "status" ];
        if( peerUpdateCallResult.has_key( "status_msg" )):
            self.status_msg = peerUpdateCallResult[ "status_msg" ];
        if( peerUpdateCallResult.has_key( "cpeers" )):
            self.cpeers = peerUpdateCallResult[ "cpeers" ];
        if( peerUpdateCallResult.has_key( "tpeers" )):
            self.tpeers = peerUpdateCallResult[ "tpeers" ];

#@-node:class GetPeerUpdateHelper
#@+node:getPeerUpdateHelper
def getPeerUpdateHelper( fcp_host, fcp_port ):
    cpeers = 0
    tpeers = 0
    f = None;
    try:
      f = fcp.FCPNode( host = fcp_host, port = fcp_port )
      returned_peerlist = f.listpeers( WithVolatile = True )
    except Exception, msg:
      if(f != None):
        f.shutdown()
      return { "status" : -1, "status_msg" : msg, "cpeers" : None, "tpeers" : None }
    try:
      f.shutdown();
    except Exception, msg:
      pass  # Ignore a failure to end the FCP session as we've got what we want now
    if( type( returned_peerlist ) != type( [] )):
      returned_peerlist = [ returned_peerlist ];
    for peer in returned_peerlist:
      if( peer[ "header" ] != "Peer" ):
        break
      if( not peer.has_key( "volatile.status" )):
        continue;
      if( peer[ "volatile.status" ] == "CONNECTED" or peer[ "volatile.status" ] == "BACKED OFF" ):
        cpeers += 1
      tpeers += 1
    return { "status" : 0, "status_msg" : "getPeerUpdateHelper completed normally", "cpeers" : cpeers, "tpeers" : tpeers }

#@-node:getPeerUpdateHelper
#@+node:main
def main():

    if nargs > 0:
        cfgFile = args[0]
    else:
        cfgFile = None
    bot = FreenetNodeRefBot(cfgFile)
    bot.run()

#@-node:main
#@+node:mainline
if __name__ == '__main__':
    main()

#@-node:mainline
#@-others
#@-node:@file refbot.py
#@-leo
