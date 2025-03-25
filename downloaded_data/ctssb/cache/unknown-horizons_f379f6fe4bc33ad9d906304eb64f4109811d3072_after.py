# ###################################################
# Copyright (C) 2011 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

"""This is the main game file, it used to store some global information and to handle
   the main menu, as well as to initialize new gamesessions.
	 <deprecated>horizons.main provides some globals
   that can be used throughout the code just by importing 'horizons.main'. These are the
   globals:</deprecated>.
   * db - the horizons.dbreader instance, used to retrieve data from the database.
   * fife - if a game is running. horizons.fife provides the running engine instance.
   * session - horizons.session instance - check horizons/session.py for more information

   TUTORIAL:
   Continue to horizons.session for further ingame digging.
   """

import os
import os.path
import random
import threading
import thread # for thread.error raised by threading.Lock.release
import shutil

from fife import fife as fife_module

from horizons.util import ActionSetLoader, DifficultySettings, TileSetLoader, Color, parse_port, DbReader
from horizons.util.uhdbaccessor import UhDbAccessor, read_savegame_template
from horizons.savegamemanager import SavegameManager
from horizons.gui import Gui
from horizons.extscheduler import ExtScheduler
from horizons.constants import AI, COLORS, GAME, PATHS, NETWORK, SINGLEPLAYER, GAME_SPEED
from horizons.network.networkinterface import NetworkInterface

# private module pointers of this module
class Modules(object):
	gui = None
	session = None
_modules = Modules()

# used to save a reference to the string previewer to ensure it is not removed by
# garbage collection
__string_previewer = None

def start(command_line_arguments):
	"""Starts the horizons.
	@param command_line_arguments: options object from optparse.OptionParser. see run_uh.py.
	"""
	global fife, db, debug, preloading
	# NOTE: globals are designwise the same thing as singletons. they don't look pretty.
	#       here, we only have globals that are either trivial, or only one instance may ever exist.

	from engine import Fife

	# handle commandline globals
	debug = command_line_arguments.debug

	if command_line_arguments.restore_settings:
		# just delete the file, Settings ctor will create a new one
		os.remove( PATHS.USER_CONFIG_FILE )

	if command_line_arguments.mp_master:
		try:
			mpieces = command_line_arguments.mp_master.partition(':')
			NETWORK.SERVER_ADDRESS = mpieces[0]
			# only change port if port is specified
			if len(mpieces[2]) > 0:
				NETWORK.SERVER_PORT = parse_port(mpieces[2], allow_zero=True)
		except ValueError:
			print _("Error: Invalid syntax in --mp-master commandline option. Port must be a number between 1 and 65535.")
			return False

	# init fife before mp_bind is parsed, since it's needed there
	fife = Fife()

	if command_line_arguments.mp_bind:
		try:
			mpieces = command_line_arguments.mp_bind.partition(':')
			NETWORK.CLIENT_ADDRESS = mpieces[0]
			fife.set_uh_setting("NetworkPort", parse_port(mpieces[2], allow_zero=True))
		except ValueError:
			print _("Error: Invalid syntax in --mp-bind commandline option. Port must be a number between 1 and 65535.")
			return False

	if command_line_arguments.ai_highlights:
		AI.HIGHLIGHT_PLANS = True
	if command_line_arguments.human_ai:
		AI.HUMAN_AI = True

	# set singleplayer natural resource seed
	if command_line_arguments.nature_seed:
		SINGLEPLAYER.SEED = command_line_arguments.nature_seed

	# set MAX_TICKS
	if command_line_arguments.max_ticks:
		GAME.MAX_TICKS = command_line_arguments.max_ticks

	db = _create_db()

	# init game parts

	_init_gettext(fife)

	client_id = fife.get_uh_setting("ClientID")
	if client_id is None or len(client_id) == 0:
		# We need a new client id
		client_id = "".join("-" if c in (8, 13, 18, 23) else \
		                    random.choice("0123456789abcdef") for c in xrange(0, 36))
		from engine import UH_MODULE
		fife.settings.set(UH_MODULE, "ClientID", client_id)
		fife.settings.saveSettings()

	ExtScheduler.create_instance(fife.pump)
	fife.init()
	_modules.gui = Gui()
	SavegameManager.init()

	# for preloading game data while in main screen
	preload_lock = threading.Lock()
	preload_thread = threading.Thread(target=preload_game_data, args=(preload_lock,))
	preloading = (preload_thread, preload_lock)

	# start something according to commandline parameters
	startup_worked = True
	if command_line_arguments.start_dev_map:
		startup_worked = _start_dev_map(command_line_arguments.ai_players, command_line_arguments.human_ai)
	elif command_line_arguments.start_random_map:
		startup_worked = _start_random_map(command_line_arguments.ai_players, command_line_arguments.human_ai)
	elif command_line_arguments.start_specific_random_map is not None:
		startup_worked = _start_random_map(command_line_arguments.ai_players, command_line_arguments.human_ai, \
			seed=command_line_arguments.start_specific_random_map)
	elif command_line_arguments.start_map is not None:
		startup_worked = _start_map(command_line_arguments.start_map, command_line_arguments.ai_players, \
			command_line_arguments.human_ai)
	elif command_line_arguments.start_scenario is not None:
		startup_worked = _start_map(command_line_arguments.start_scenario, 0, False, True)
	elif command_line_arguments.start_campaign is not None:
		startup_worked = _start_campaign(command_line_arguments.start_campaign)
	elif command_line_arguments.load_map is not None:
		startup_worked = _load_map(command_line_arguments.load_map, command_line_arguments.ai_players, \
			command_line_arguments.human_ai)
	elif command_line_arguments.load_quicksave is not None:
		startup_worked = _load_last_quicksave()
	elif command_line_arguments.stringpreview:
		first_map = SavegameManager.get_maps()[0][0]
		startup_worked = _start_map(first_map, ai_players=0, human_ai=False, trader_enabled=False, pirate_enabled=False)
		from development.stringpreviewwidget import StringPreviewWidget
		__string_previewer = StringPreviewWidget(_modules.session)
		__string_previewer.show()
	else: # no commandline parameter, show main screen
		_modules.gui.show_main()
		if not command_line_arguments.nopreload:
			preloading[0].start()

	if not startup_worked:
		# don't start main loop if startup failed
		return False

	if command_line_arguments.gamespeed is not None:
		_modules.session.speed_set(GAME_SPEED.TICKS_PER_SECOND*command_line_arguments.gamespeed)

	fife.run()

def quit():
	"""Quits the game"""
	global fife
	if _modules.session is not None and _modules.session.is_alive:
		_modules.session.end()
	preload_game_join(preloading)
	ExtScheduler.destroy_instance()
	fife.quit()

def start_singleplayer(map_file, playername = "Player", playercolor = None, is_scenario = False, \
		campaign = None, ai_players = 0, human_ai = False, trader_enabled = True, pirate_enabled = True, \
		natural_resource_multiplier = 1):
	"""Starts a singleplayer game
	@param map_file: path to map file
	@param ai_players: number of AI players to start (excludes possible human AI)
	@param human_ai: whether to start the human player as an AI
	"""
	global fife, preloading, db
	preload_game_join(preloading)

	if playercolor is None: # this can't be a default parameter because of circular imports
		playercolor = Color[1]

	# remove cursor while loading
	fife.cursor.set(fife_module.CURSOR_NONE)
	fife.engine.pump()
	fife.set_cursor_image('default')

	# hide whatever is displayed before the game starts
	_modules.gui.hide()

	# destruct old session (right now, without waiting for gc)
	if _modules.session is not None and _modules.session.is_alive:
		_modules.session.end()
	# start new session
	from spsession import SPSession
	_modules.session = SPSession(_modules.gui, db)

	# for now just make it a bit easier for the AI
	difficulty_level = {False: DifficultySettings.DEFAULT_LEVEL, True: DifficultySettings.EASY_LEVEL}
	players = [{ 'id' : 1, 'name' : playername, 'color' : playercolor, 'local' : True, 'ai': human_ai, 'difficulty': difficulty_level[bool(human_ai)]}]

	# add AI players with a distinct color; if none can be found then use black
	for num in xrange(ai_players):
		color = Color[COLORS.BLACK] # if none can be found then be black
		for possible_color in Color:
			if possible_color == Color[COLORS.BLACK]:
				continue # black is used by the trader and the pirate
			available = True
			for player in players:
				if player['color'].to_tuple() == possible_color.to_tuple():
					available = False
					break
			if available:
				color = possible_color
				break
		players.append({'id': num + 2, 'name' : 'AI' + str(num + 1), 'color' : color, 'local' : False, 'ai': True, 'difficulty': difficulty_level[True]})

	from horizons.scenario import InvalidScenarioFileFormat # would create import loop at top
	try:
		_modules.session.load(map_file, players, trader_enabled, pirate_enabled, natural_resource_multiplier, \
			is_scenario = is_scenario, campaign = campaign)
	except InvalidScenarioFileFormat as e:
		raise
	except Exception as e:
		import traceback
		print "Failed to load", map_file
		traceback.print_exc()
		if _modules.session is not None and _modules.session.is_alive:
			_modules.session.end()
		_modules.gui.show_main()
		headline = _(u"Failed to start/load the game")
		descr = _(u"The game you selected couldn't be started.") + u" " +\
			      _("The savegame might be broken or has been saved with an earlier version.")
		_modules.gui.show_error_popup(headline, descr)
		load_game(ai_players, human_ai)


def prepare_multiplayer(game, trader_enabled = True, pirate_enabled = True, natural_resource_multiplier = 1):
	"""Starts a multiplayer game server
	TODO: acctual game data parameter passing
	"""
	global fife, preloading, db

	preload_game_join(preloading)

	# remove cursor while loading
	fife.cursor.set(fife_module.CURSOR_NONE)
	fife.engine.pump()
	fife.set_cursor_image('default')

	# hide whatever is displayed before the game starts
	_modules.gui.hide()

	# destruct old session (right now, without waiting for gc)
	if _modules.session is not None and _modules.session.is_alive:
		_modules.session.end()
	# start new session
	from mpsession import MPSession
	# get random seed for game
	uuid = game.get_uuid()
	random = sum([ int(uuid[i : i + 2], 16) for i in range(0, len(uuid), 2) ])
	_modules.session = MPSession(_modules.gui, db, NetworkInterface(), rng_seed=random)
	# NOTE: this data passing is only temporary, maybe use a player class/struct
	_modules.session.load("content/maps/" + game.get_map_name() + ".sqlite", \
	                      game.get_player_list(), trader_enabled, pirate_enabled, natural_resource_multiplier)

def start_multiplayer(game):
	_modules.session.start()

def load_game(ai_players=0, human_ai=False, savegame=None, is_scenario=False, campaign=None,
              pirate_enabled=True, trader_enabled=True):
	"""Shows select savegame menu if savegame is none, then loads the game"""
	if savegame is None:
		savegame = _modules.gui.show_select_savegame(mode='load')
		if savegame is None:
			return False # user aborted dialog
	_modules.gui.show_loading_screen()
#TODO
	start_singleplayer(savegame, is_scenario = is_scenario, campaign = campaign, \
		ai_players=ai_players, human_ai=human_ai, pirate_enabled=pirate_enabled, trader_enabled=trader_enabled)
	return True


def _init_gettext(fife):
	"""
	Maps _ to the ugettext unicode gettext call. Use: _(string).
	N_ takes care of plural forms for different languages. It masks ungettext
	calls (unicode, plural-aware _() ) to create different translation strings
	depending on the counter value. Not all languages have only two plural forms
	"One" / "Anything else". Use: N_("{n} dungeon", "{n} dungeons", n).format(n=n)
	where n is a counter. N_ is, for some reason, broken. Cf. horizons.i18n.utils
	We will need to make gettext recognise namespaces some time, but hardcoded
	'unknown-horizons' works for now since we currently only use one namespace.
	"""
	from gettext import translation
	namespace_translation = translation('unknown-horizons', 'content/lang', fallback=True)
	_  = namespace_translation.ugettext
	N_ = namespace_translation.ungettext



## GAME START FUNCTIONS

def _start_dev_map(ai_players, human_ai):
	# start the development map (it's the first one)
	first_map = SavegameManager.get_maps()[0][0]
	load_game(ai_players, human_ai, first_map)
	return True

def _start_map(map_name, ai_players, human_ai, is_scenario=False, campaign=None, pirate_enabled=True, trader_enabled=True):
	"""Start a map specified by user
	@param map_name: name of map or path to map
	@return: bool, whether loading succeded"""
	# check for exact/partial matches in map list first
	maps = SavegameManager.get_available_scenarios() if is_scenario else SavegameManager.get_maps()
	map_file = None
	for i in xrange(0, len(maps[1])):
		# exact match
		if maps[1][i] == map_name:
			map_file = maps[0][i]
			break
		# check for partial match
		if maps[1][i].startswith(map_name):
			if map_file is not None:
				# multiple matches, collect all for output
				map_file += u'\n' + maps[0][i]
			else:
				map_file = maps[0][i]
	if map_file is None:
		# not a map name, check for path to file or fail
		if os.path.exists(map_name):
			map_file = map_name
		else:
			#xgettext:python-format
			print _("Error: Cannot find map '{name}'.").format(name=map_name)
			return False
	if len(map_file.splitlines()) > 1:
		print _("Error: Found multiple matches:")
		for match in map_file.splitlines():
			print os.path.basename(match)
		return False
	load_game(ai_players, human_ai, map_file, is_scenario, campaign=campaign,
	          trader_enabled=trader_enabled, pirate_enabled=pirate_enabled)
	return True

def _start_random_map(ai_players, human_ai, seed = None):
	from horizons.util import random_map
	start_singleplayer(random_map.generate_map_from_seed(seed), ai_players=ai_players, human_ai=human_ai)
	return True

def _start_campaign(campaign_name):
	"""Finds the first scenario in this campaign and
	loads it.
	@return: bool, whether loading succeded"""
	if os.path.exists(campaign_name):
		# a file was specified. In order to make sure everything works properly,
		# we need to copy the file over to the UH campaign directory.
		# This is not very clean, but it's safe.

		if not campaign_name.endswith(".yaml"):
			print _("Error: campaign filenames have to end in \".yaml\".")
			return False

		# check if the user specified a file in the UH campaign dir
		campaign_basename = os.path.basename( campaign_name )
		path_in_campaign_dir = os.path.join(SavegameManager.campaigns_dir, campaign_basename)
		if not (os.path.exists(path_in_campaign_dir) and \
		        os.path.samefile(campaign_name, path_in_campaign_dir)):
			#xgettext:python-format
			string = _("Due to technical reasons, the campaign file will be copied to the UH campaign directory ({path}).").format(path=SavegameManager.campaigns_dir)
			string += "\n"
			string += _("This means that changes in the file you specified will not apply to the game directly.")
			#xgettext:python-format
			string += _("To see the changes, either always start UH with the current arguments or edit the file {filename}.").format(filename=path_in_campaign_dir)
			print string

			shutil.copy(campaign_name, SavegameManager.campaigns_dir)
		# use campaign file name below
		campaign_name = os.path.splitext( campaign_basename )[0]
	campaign = SavegameManager.get_campaign_info(name = campaign_name)
	if not campaign:
		#xgettext:python-format
		print _("Error: Cannot find campaign '{name}'.").format(campaign_name)
		return False
	scenarios = [sc.get('level') for sc in campaign.get('scenarios',[])]
	if not scenarios:
		return False
	return _start_map(scenarios[0], 0, False, is_scenario = True, campaign = {'campaign_name': campaign_name, 'scenario_index': 0, 'scenario_name': scenarios[0]})

def _load_map(savegame, ai_players, human_ai):
	"""Load a map specified by user.
	@param savegame: eiter the displayname of a savegame or a path to a savegame
	@return: bool, whether loading succeded"""
	# first check for partial or exact matches in the normal savegame list
	saves = SavegameManager.get_saves()
	map_file = None
	for i in xrange(0, len(saves[1])):
		# exact match
		if saves[1][i] == savegame:
			map_file = saves[0][i]
			break
		# check for partial match
		if saves[1][i].startswith(savegame):
			if map_file is not None:
				# multiple matches, collect all for output
				map_file += u'\n' + saves[0][i]
			else:
				map_file = saves[0][i]
	if map_file is None:
		# not a savegame, check for path to file or fail
		if os.path.exists(savegame):
			map_file = savegame
		else:
			#xgettext:python-format
			print _("Error: Cannot find savegame '{name}'.").format(name=savegame)
			return False
	if len(map_file.splitlines()) > 1:
		print _("Error: Found multiple matches:")
		for match in map_file.splitlines():
			print os.path.basename(match)
		return False
	load_game(savegame=map_file)
	return True

def _load_last_quicksave():
	"""Load last quicksave
	@return: bool, whether loading succeded"""
	save_files = SavegameManager.get_quicksaves()[0]
	if not save_files:
		print _("Error: No quicksave found.")
		return False
	save = max(save_files)
	load_game(savegame=save)
	return True

def _create_db():
	"""Returns a dbreader instance, that is connected to the main game data dbfiles.
	NOTE: This data is read_only, so there are no concurrency issues"""
	_db = UhDbAccessor(':memory:')
	for i in PATHS.DB_FILES:
		f = open(i, "r")
		sql = "BEGIN TRANSACTION;" + f.read() + "COMMIT;"
		_db.execute_script(sql)
	return _db

def preload_game_data(lock):
	"""Preloads game data.
	Keeps releasing and acquiring lock, runs until lock can't be acquired."""
	try:
		import logging
		from horizons.entities import Entities
		from horizons.util import Callback
		log = logging.getLogger("preload")
		mydb = _create_db() # create own db reader instance, since it's not thread-safe
		preload_functions = [ ActionSetLoader.load, \
		                      #TileSetLoader.load, -- this is not needed now, but will be for the new tile system
		                      Callback(Entities.load_grounds, mydb, load_now=True), \
		                      Callback(Entities.load_buildings, mydb, load_now=True), \
		                      Callback(Entities.load_units, load_now=True) ]
		for f in preload_functions:
			if not lock.acquire(False):
				break
			log.debug("Preload: %s", f)
			f()
			log.debug("Preload: %s is done", f)
			lock.release()
		log.debug("Preloading done.")
	except Exception as e:
		log.warning("Exception occured in preloading thread: %s", e)
	finally:
		if lock.locked():
			lock.release()

def preload_game_join(preloading):
	"""Wait for preloading to finish.
	@param preloading: tuple: (Thread, Lock)"""
	# lock preloading
	preloading[1].acquire()
	# wait until it finished its current action
	if preloading[0].isAlive():
		preloading[0].join()
		assert not preloading[0].isAlive()
	else:
		try:
			preloading[1].release()
		except thread.error:
			pass # due to timing issues, the lock might be released already

