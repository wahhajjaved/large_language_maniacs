# pylint: disable=E1101, E0611
"""Installer module"""
import os
import sys
import yaml
import time
import shutil
import urllib2
import platform
import subprocess
import webbrowser

from gi.repository import Gtk, Gdk

from lutris import pga, settings
from lutris.util import extract, devices, system
from lutris.util.fileio import EvilConfigParser, MultiOrderedDict
from lutris.util.jobs import async_call
from lutris.util.log import logger
from lutris.util.strings import add_url_tags

from lutris.game import Game
from lutris.config import LutrisConfig
from lutris.gui.config_dialogs import AddGameDialog
from lutris.gui.dialogs import ErrorDialog, NoInstallerDialog
from lutris.gui.widgets import DownloadProgressBox, FileChooserEntry
from lutris.runners import wine, winesteam, steam, import_task, import_runner


class ScriptingError(Exception):
    """ Custom exception for scripting errors, can be caught by modifying
    excepthook """
    def __init__(self, message, faulty_data=None):
        self.message = message
        self.faulty_data = faulty_data
        logger.error(self.message + repr(self.faulty_data))
        super(ScriptingError, self).__init__()

    def __str__(self):
        return self.message + "\n" + repr(self.faulty_data)

    def __repr__(self):
        return self.message

_excepthook = sys.excepthook


def error_handler(error_type, value, traceback):
    if error_type == ScriptingError:
        message = value.message
        if value.faulty_data:
            message += "\n<b>" + str(value.faulty_data) + "</b>"
        ErrorDialog(message)
    else:
        _excepthook(error_type, value, traceback)
sys.excepthook = error_handler


def fetch_script(window, game_ref):
    """Downloads install script(s) for matching game_ref"""
    request = urllib2.Request(url=settings.INSTALLER_URL % game_ref)
    try:
        request = urllib2.urlopen(request)
        script_contents = request.read()
    except IOError:
        dlg = NoInstallerDialog(window)
        if dlg.result == 1:
            game = Game(game_ref)
            game_dialog = AddGameDialog(window, game)
            game_dialog.run()
            if game_dialog.installed:
                window.notify_install_success()
        elif dlg.result == 2:
            installer_url = settings.SITE_URL + "games/%s/" % game_ref
            webbrowser.open(installer_url)
        return
    # Data should be JSON here, but JSON is also valid YAML.
    # At some point we will be dropping the YAML parser and load installer
    # data with json.loads
    return yaml.safe_load(script_contents)


class ScriptInterpreter(object):
    """ Class that converts raw script data to actions """

    def __init__(self, script, parent):
        self.error = None
        self.errors = []
        self.files = []
        self.target_path = None
        self.parent = parent
        self.game_name = None
        self.game_slug = None
        self.game_files = {}
        self.game_disc = None
        self.user_inputs = []
        self.steam_data = {}
        self.script = script
        if not self.script:
            return
        if not self.is_valid():
            raise ScriptingError("Invalid script", (self.script, self.errors))
        self.game_name = self.script['name']
        self.game_slug = self.script['game_slug']
        self.requires = self.script.get('requires')
        if self.requires:
            self._check_dependecy()
        else:
            self.target_path = self.default_target

    @property
    def default_target(self):
        lutris_config = LutrisConfig(runner=self.script['runner'])
        games_dir = lutris_config.get_path() or os.path.expanduser('~')
        return os.path.join(games_dir, self.game_slug)

    @property
    def download_cache_path(self):
        return os.path.join(settings.CACHE_DIR,
                            "installer/%s" % self.game_slug)

    @property
    def should_create_target(self):
        return (not os.path.exists(self.target_path)
                and 'nocreatedir' not in self.script)

    def _check_dependecy(self):
        # XXX Maybe handle this with Game instead of hitting directly the PGA?
        game = pga.get_game_by_slug(self.requires)
        if not game or not game['directory']:
            raise ScriptingError(
                "You need to install {} before".format(self.requires)
            )
        self.target_path = game['directory']

    def is_valid(self):
        """ Return True if script is usable """
        required_fields = ('runner', 'name', 'game_slug')
        for field in required_fields:
            if not self.script.get(field):
                self.errors.append("Missing field '%s'" % field)

        self.files = self.script.get('files', [])
        return not bool(self.errors)

    def iter_game_files(self):
        if self.files:
            # Create cache dir if needed
            if not os.path.exists(self.download_cache_path):
                os.mkdir(self.download_cache_path)

            if self.should_create_target:
                os.makedirs(self.target_path)

        if len(self.game_files) < len(self.files):
            logger.info(
                "Downloading file %d of %d",
                len(self.game_files) + 1, len(self.script["files"])
            )
            file_index = len(self.game_files)
            try:
                current_file = self.script["files"][file_index]
            except KeyError:
                raise ScriptingError("Error getting file %d in %s",
                                     file_index, self.script['files'])
            self._download_file(current_file)
        else:
            self.current_command = 0
            self._prepare_commands()

    def _download_file(self, game_file):
        """Download a file referenced in the installer script

           Game files can be either a string, containing the location of the
           file to fetch or a dict with the following keys:
           - url : location of file, if not present, filename will be used
                   this should be the case for local files
           - filename : force destination filename when url is present or path
                        of local file
        """
        # Setup file_id, file_uri and local filename
        file_id = game_file.keys()[0]
        if isinstance(game_file[file_id], dict):
            filename = game_file[file_id]['filename']
            file_uri = game_file[file_id]['url']
        else:
            file_uri = game_file[file_id]
            filename = os.path.basename(file_uri)
        if file_uri.startswith("/"):
            file_uri = "file://" + file_uri
        elif file_uri.startswith(("$WINESTEAM", "$STEAM")):
            # Download Steam data
            try:
                parts = file_uri.split(":", 2)
                steam_rel_path = parts[2].strip()
            except IndexError:
                raise ScriptingError("Malformed steam path: %s" % file_uri)
            if steam_rel_path == "/":
                steam_rel_path = "."
            self.steam_data = {
                'appid': parts[1],
                'steam_rel_path': steam_rel_path,
                'file_id': file_id
            }
            if parts[0] == '$WINESTEAM':
                appid = self.steam_data['appid']
                logger.debug("Getting Wine Steam data for appid %s" % appid)
                self.parent.set_status('Getting Wine Steam game data')
                self.steam_data['platform'] = "windows"
                # Check that wine is installed
                wine_runner = wine.wine()
                if not wine_runner.is_installed():
                    wine_runner.install()
                # Getting data from Wine Steam
                steam_runner = winesteam.winesteam()
                if not steam_runner.is_installed():
                    winesteam.download_steam(
                        downloader=self.parent.start_download,
                        callback=self.parent.on_steam_downloaded
                    )
                else:
                    self.install_steam_game(winesteam.winesteam)
                return
            else:
                # Getting data from Linux Steam
                self.parent.set_status('Getting Steam game data')
                self.steam_data['platform'] = "linux"
                self.install_steam_game(steam.steam)
                return
        logger.debug("Fetching [%s]: %s" % (file_id, file_uri))

        # Check for file availability in PGA
        pga_uri = pga.check_for_file(self.game_slug, file_id)
        if pga_uri:
            file_uri = pga_uri

        # Setup destination path
        dest_file = os.path.join(self.download_cache_path, filename)

        if file_uri.startswith("N/A"):
            # Ask the user where is the file located
            parts = file_uri.split(":", 1)
            if len(parts) == 2:
                message = parts[1]
            else:
                message = "Please select file '%s'" % file_id
            self.current_file_id = file_id
            self.parent.ask_user_for_file(message)
            return

        if os.path.exists(dest_file):
            logger.debug("Destination file exists")
            if settings.KEEP_CACHED_ASSETS:
                self.game_files[file_id] = dest_file
                self.iter_game_files()
                return
            else:
                os.remove(dest_file)

        # Change parent's status
        self.parent.set_status('Fetching %s' % file_uri)
        self.game_files[file_id] = dest_file
        self.parent.start_download(file_uri, dest_file)

    def file_selected(self, file_path):
        file_id = self.current_file_id
        if not file_path or not os.path.exists(file_path):
            raise ScriptingError(
                "Can't continue installation without file", file_id
            )
        self.game_files[file_id] = file_path
        self.iter_game_files()

    def _prepare_commands(self):
        if os.path.exists(self.target_path):
            os.chdir(self.target_path)
        self._iter_commands()

    def _iter_commands(self, result=None, exception=None):
        if result == 'STOP':
            return

        self.parent.set_status("Installing game data")
        self.parent.add_spinner()
        self.parent.continue_button.hide()

        commands = self.script.get('installer', [])
        if exception:
            self.parent.on_install_error(repr(exception))
        elif self.current_command < len(commands):
            command = commands[self.current_command]
            self.current_command += 1
            method, params = self._map_command(command)
            if isinstance(params, dict):
                status_text = params.pop("description", None)
            else:
                status_text = None
            if status_text:
                self.parent.set_status(status_text)
            async_call(method, self._iter_commands, params)
        else:
            self._finish_install()

    def _finish_install(self):
        self.parent.set_status("Writing configuration")
        self._write_config()
        self.parent.set_status("Installation finished !")
        self.parent.on_install_finished()

    def _install_error(self, message):
        self.parent.set_status(message)

    def cleanup(self):
        if os.path.exists(self.download_cache_path):
            shutil.rmtree(self.download_cache_path)

    def _substitute_config(self, script_config):
        """ Substitutes values such as $GAMEDIR in a config dict """
        config = {}
        for key in script_config:
            if not isinstance(key, basestring):
                raise ScriptingError("Game config key must be a string", key)
            value = script_config[key]
            if isinstance(value, list):
                config[key] = [self._substitute(i) for i in value]
            else:
                config[key] = self._substitute(value)
        return config

    def _write_config(self):
        """Write the game configuration as a Lutris launcher."""
        runner_name = self.script['runner']

        # Get existing config
        config_filename = os.path.join(settings.CONFIG_DIR,
                                       "games/%s.yml" % self.game_slug)
        if self.requires and os.path.exists(config_filename):
            # The installer is patching an existing game, update its config
            # XXX Maybe drop the self.requires condition and always update
            #     the existing config?
            lutris_config = LutrisConfig(game=self.game_slug)
            config = lutris_config.game_config
        else:
            config = {
                'game': {},
            }

        # DB update
        pga.add_or_update(self.script['name'], runner_name,
                          slug=self.game_slug,
                          directory=self.target_path,
                          installed=1,
                          installer_slug=self.script.get('installer_slug'),
                          year=self.script.get('year'),
                          steamid=self.script.get('steamid'))

        # Config update
        if 'system' in self.script:
            config['system'] = self._substitute_config(self.script['system'])
        if runner_name in self.script:
            config[runner_name] = self._substitute_config(
                self.script[runner_name]
            )
        if 'game' in self.script:
            config['game'].update(self._substitute_config(self.script['game']))

        is_64bit = platform.machine() == "x86_64"
        exe = 'exe64' if 'exe64' in self.script and is_64bit else 'exe'

        for launcher in [exe, 'iso', 'rom', 'disk', 'main_file']:
            if launcher not in self.script:
                continue
            launcher_description = self.script[launcher]
            if launcher == "exe64":
                launcher = "exe"
            if type(launcher_description) == list:
                game_files = []
                for game_file in launcher_description:
                    if game_file in self.game_files:
                        game_files.append(self.game_files[game_file])
                    else:
                        game_files.append(game_file)
                config['game'][launcher] = game_files
            else:
                if launcher_description in self.game_files:
                    launcher_description = self.game_files[launcher_description]
                elif os.path.exists(os.path.join(self.target_path,
                                                 launcher_description)):
                    launcher_description = os.path.join(self.target_path,
                                                        launcher_description)
                else:
                    launcher_description = launcher_description
                config['game'][launcher] = launcher_description

        yaml_config = yaml.safe_dump(config, default_flow_style=False)
        logger.debug(yaml_config)
        with open(config_filename, "w") as config_file:
            config_file.write(yaml_config)

    def _map_command(self, command_data):
        """ Converts a line from the installer directive an internal method """
        if isinstance(command_data, dict):
            command_name = command_data.keys()[0]
            command_params = command_data[command_name]
        else:
            command_name = command_data
            command_params = {}
        command_name = command_name.replace("-", "_")
        command_name = command_name.strip("_")
        if not hasattr(self, command_name):
            raise ScriptingError("The command %s does not exists"
                                 % command_name)
        return getattr(self, command_name), command_params

    def _substitute(self, template_string):
        """ Replace path aliases with real paths """
        replacements = {
            "GAMEDIR": self.target_path,
            "CACHE": settings.CACHE_DIR,
            "HOME": os.path.expanduser("~"),
            "DISC": self.game_disc,
            "USER": os.getenv('USER'),
            "INPUT": self._get_last_user_input(),
        }
        # Add 'INPUT_<id>' replacements for user inputs with an id
        for input_data in self.user_inputs:
            alias = input_data['alias']
            if alias:
                replacements[alias] = input_data['value']

        replacements.update(self.game_files)
        return system.substitute(template_string, replacements)

    def _get_last_user_input(self):
        return self.user_inputs[-1]['value'] if self.user_inputs else ''

    def _get_move_paths(self, params):
        """ Validate and converts raw data passed to 'move' """
        for required_param in ('dst', 'src'):
            if required_param not in params:
                raise ScriptingError(
                    "The '%s' parameter is required for 'move'"
                    % required_param, params
                )
        src_ref = params['src']
        src = (self.game_files.get(src_ref) or self._substitute(src_ref))
        if not src:
            raise ScriptingError("Wrong value for 'src' param", src_ref)
        dst_ref = params['dst']
        dst = self._substitute(dst_ref)
        if not dst:
            raise ScriptingError("Wrong value for 'dst' param", dst_ref)
        return (src, dst)

    def _get_file(self, fileid):
        return self.game_files.get(fileid)

    def chmodx(self, filename):
        filename = self._substitute(filename)
        os.popen('chmod +x "%s"' % filename)

    def execute(self, data):
        """Run an executable file"""
        if isinstance(data, dict):
            file_ref = data['file']
            args = [self._substitute(arg)
                    for arg in data.get('args', '').split()]
        else:
            file_ref = data
            args = []
        # Determine whether 'file' value is a file id or a path
        exec_path = self._get_file(file_ref) or self._substitute(file_ref)
        if not exec_path:
            raise ScriptingError("Unable to find file %s" % file_ref,
                                 file_ref)
        if not os.path.exists(exec_path):
            raise ScriptingError("Unable to find required executable",
                                 exec_path)
        else:
            self.chmodx(exec_path)
            logger.debug("Executing %s %s" % (exec_path, args))
            subprocess.call([exec_path] + args)

    def check_md5(self, data):
        filename = self._get_file(data['file'])
        _hash = system.get_md5_hash(filename)
        if _hash != data['value']:
            raise ScriptingError("MD5 checksum mismatch", data)

    def input_menu(self, data):
        """Display an input request as a dropdown menu with options."""
        identifier = data.get('id')
        alias = 'INPUT_%s' % identifier if identifier else None
        has_entry = data.get('entry')
        options = data.get('options')
        preselect = self._substitute(data.get('preselect', ''))
        self.parent.input_menu(alias, options, preselect, has_entry,
                               self._on_input_menu_validated)
        return 'STOP'

    def _on_input_menu_validated(self, widget, *args):
        alias = args[0]
        menu = args[1]
        choosen_option = menu.get_active_id()
        if choosen_option:
            self.user_inputs.append({'alias': alias,
                                     'value': choosen_option})
            self.parent.continue_button.hide()
            self._iter_commands()

    def insert_disc(self, data):
        requires = data.get('requires')
        message = data.get(
            'message',
            "Insert game disc or mount disk image and click OK."
        )
        message += (
            "\n\nLutris is looking for a mounted disk drive or image \n"
            "containing the following file or folder:\n"
            "<i>%s</i>" % requires
        )
        if not requires:
            raise ScriptingError("The installer's `insert_disc` command is "
                                 "missing the `requires` parameter." * 2)
        self.parent.wait_for_user_action(message, self._find_matching_disc,
                                         requires)
        return 'STOP'

    def _find_matching_disc(self, widget, requires):
        drives = devices.get_mounted_discs()
        for drive in drives:
            mount_point = drive.get_root().get_path()
            required_abspath = os.path.join(mount_point, requires)
            required_abspath = system.fix_path_case(required_abspath)
            if required_abspath:
                logger.debug("Found %s on cdrom %s" % (requires, mount_point))
                self.game_disc = mount_point
                self._iter_commands()
                break

    def mkdir(self, directory):
        directory = self._substitute(directory)
        try:
            os.makedirs(directory)
        except OSError:
            logger.debug("Directory %s already exists" % directory)
        else:
            logger.debug("Created directory %s" % directory)

    def merge(self, params):
        src, dst = self._get_move_paths(params)
        logger.debug("Merging %s into %s" % (src, dst))
        if not os.path.exists(src):
            raise ScriptingError("Source does not exist: %s" % src, params)
        if not os.path.exists(dst):
            os.makedirs(dst)
        if os.path.isfile(src):
            # If single file, copy it and change reference in game file so it
            # can be used as executable. Skip copying if the source is the same
            # as destination.
            if os.path.dirname(src) != dst:
                shutil.copy(src, dst)
            if params['src'] in self.game_files.keys():
                self.game_files[params['src']] = os.path.join(
                    dst, os.path.basename(src)
                )
            return
        system.merge_folders(src, dst)

    def move(self, params):
        """ Move a file or directory """
        src, dst = self._get_move_paths(params)
        logger.debug("Moving %s to %s" % (src, dst))
        if not os.path.exists(src):
            raise ScriptingError("I can't move %s, it does not exist" % src)
        if os.path.isfile(src):
            src_filename = os.path.basename(src)
            src_dir = os.path.dirname(src)
            dst_path = os.path.join(dst, src_filename)
            if src_dir == dst:
                logger.info("Source file is the same as destination, skipping")
            elif os.path.exists(dst_path):
                # May not be the best choice, but it's the safest.
                # Maybe should display confirmation dialog (Overwrite / Skip) ?
                logger.info("Destination file exists, skipping")
            else:
                shutil.move(src, dst)
        else:
            try:
                shutil.move(src, dst)
            except shutil.Error:
                raise ScriptingError("Can't move %s to destination %s"
                                     % (src, dst))
        if os.path.isfile(src) and params['src'] in self.game_files.keys():
            # Change game file reference so it can be used as executable
            self.game_files['src'] = src

    def extract(self, data):
        """ Extracts a file, guessing the compression method """
        if 'file' not in data:
            raise ScriptingError('"file" parameter is mandatory for the '
                                 'extract command', data)
        filename = self._get_file(data['file'])
        if not filename:
            filename = self._substitute(data['file'])

        if not os.path.exists(filename):
            raise ScriptingError("%s does not exists" % filename)
        if 'dst' in data:
            dest_path = self._substitute(data['dst'])
        else:
            dest_path = self.target_path
        msg = "Extracting %s" % os.path.basename(filename)
        logger.debug(msg)
        self.parent.set_status(msg)
        merge_single = 'nomerge' not in data
        extractor = data.get('format')
        logger.debug("extracting file %s to %s", filename, dest_path)
        extract.extract_archive(filename, dest_path, merge_single, extractor)

    def write_config(self, params):
        """Writes a key-value pair into an INI type config file."""
        # Get file
        if 'file' not in params:
            raise ScriptingError('"file" parameter is mandatory for the '
                                 'write_conf command', params)
        config_file = self._get_file(params['file'])
        if not config_file:
            config_file = self._substitute(params['file'])

        # Create it if necessary
        basedir = os.path.dirname(config_file)
        if not os.path.exists(basedir):
            os.makedirs(basedir)

        parser = EvilConfigParser(allow_no_value=True,
                                  dict_type=MultiOrderedDict)
        parser.optionxform = str  # Preserve text case
        parser.read(config_file)

        if not parser.has_section(params['section']):
            parser.add_section(params['section'])
        parser.set(params['section'], params['key'], params['value'])

        with open(config_file, 'wb') as f:
            parser.write(f)

    def _append_steam_data_to_files(self, runner_class):
        steam_runner = runner_class()
        data_path = steam_runner.get_game_path_from_appid(
            self.steam_data['appid'])
        if not data_path or not os.path.exists(data_path):
            raise ScriptingError("Unable to get Steam data for game")
        logger.debug("got data path: %s" % data_path)
        self.game_files[self.steam_data['file_id']] = \
            os.path.join(data_path, self.steam_data['steam_rel_path'])
        self.iter_game_files()

    def task(self, data):
        """ This action triggers a task within a runner.
            The 'name' parameter is mandatory. If 'args' is provided it will be
            passed to the runner task.
        """
        task_name = data.pop('name')
        if not task_name:
            raise ScriptingError("Missing required task name", data)
        if '.' in task_name:
            # Run a task from a different runner than the one for this installer
            runner_name, task_name = task_name.split('.')
        else:
            runner_name = self.script["runner"]
        runner = import_runner(runner_name)()

        # Check/install Wine runner at version specified in the script
        wine_version = None
        wine_arch = None
        if runner_name == 'wine' and self.script.get('wine'):
            wine_version = self.script.get('wine').get('version')
            wine_arch = self.script.get('wine').get('arch')
        if wine_version and task_name == 'wineexec':
            if not wine.is_version_installed(wine_version, wine_arch):
                Gdk.threads_init()
                Gdk.threads_enter()
                runner.install(wine_version, wine_arch)
                Gdk.threads_leave()
            data['wine_path'] = wine.get_wine_version_exe(wine_version,
                                                          wine_arch)
        # Check/install other runner
        elif not runner.is_installed():
            Gdk.threads_init()
            Gdk.threads_enter()
            runner.install()
            Gdk.threads_leave()

        for key in data:
            data[key] = self._substitute(data[key])
        task = import_task(runner_name, task_name)
        task(**data)

    def install_steam_game(self, runner_class):
        steam_runner = runner_class()
        appid = self.steam_data['appid']
        if not steam_runner.get_game_path_from_appid(appid):
            logger.debug("Installing steam game %s" % appid)
            # Here the user must wait for the game to finish installing, a
            # better way to handle this would be to poll StateFlags on the
            # game's config to check if the game has finished installing.
            self.parent.wait_for_user_action(
                "Steam will now download and install game %s, "
                "press Ok when it's finished" % appid,
                self.on_steam_game_installed,
                appid
            )
            steam_runner.appid = appid
            async_call(steam_runner.install_game, None, appid)
        else:
            self._append_steam_data_to_files(runner_class)

    def complete_steam_install(self, dest):
        winesteam_runner = winesteam.winesteam()
        async_call(winesteam_runner.install, self.on_winesteam_installed, dest)

    def on_winesteam_installed(self, *args):
        self.install_steam_game(winesteam.winesteam)

    def on_steam_game_installed(self, *args):
        logger.debug("Steam game installed")
        if self.steam_data['platform'] == 'windows':
            runner_class = winesteam.winesteam
        else:
            runner_class = steam.steam
        self._append_steam_data_to_files(runner_class)


# pylint: disable=R0904
class InstallerDialog(Gtk.Window):
    """ Gtk Dialog used during the install process """
    game_dir = None
    download_progress = None

    def __init__(self, game_ref, parent=None):
        Gtk.Window.__init__(self)
        self.interpreter = None
        self.selected_directory = None  # Latest directory chosen by user
        self.parent = parent
        self.game_ref = game_ref
        # Dialog properties
        self.set_size_request(600, 480)
        self.set_default_size(600, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)

        self.vbox = Gtk.VBox()
        self.add(self.vbox)

        # Default signals
        self.connect('destroy', self.on_destroy)

        # GUI Setup

        # Title label
        self.title_label = Gtk.Label()
        self.vbox.pack_start(self.title_label, False, False, 20)

        self.status_label = Gtk.Label()
        self.status_label.set_max_width_chars(80)
        self.status_label.set_property('wrap', True)
        self.status_label.set_selectable(True)
        self.vbox.pack_start(self.status_label, False, False, 15)

        # Main widget box
        self.widget_box = Gtk.VBox()
        self.widget_box.set_margin_right(25)
        self.widget_box.set_margin_left(25)
        self.vbox.pack_start(self.widget_box, True, True, 15)

        self.location_entry = None

        # Separator
        self.vbox.pack_start(Gtk.HSeparator(), False, False, 0)

        # Buttons
        action_buttons_alignment = Gtk.Alignment.new(0.95, 0, 0.15, 0)
        self.action_buttons = Gtk.HBox()
        action_buttons_alignment.add(self.action_buttons)
        self.vbox.pack_start(action_buttons_alignment, False, True, 20)

        self.install_button = Gtk.Button(label='Install')
        self.install_button.connect('clicked', self.on_install_clicked)
        self.action_buttons.add(self.install_button)

        self.continue_button = Gtk.Button(label='Continue')
        self.continue_button.set_margin_left(20)
        self.continue_handler = None
        self.action_buttons.add(self.continue_button)

        self.play_button = Gtk.Button(label="Launch game")
        self.play_button.set_margin_left(20)
        self.play_button.connect('clicked', self.launch_game)
        self.action_buttons.add(self.play_button)

        self.close_button = Gtk.Button(label="Close")
        self.close_button.set_margin_left(20)
        self.close_button.connect('clicked', self.close)
        self.action_buttons.add(self.close_button)

        if os.path.exists(game_ref):
            # local script
            logger.debug("Opening script: %s", game_ref)
            self.scripts = yaml.safe_load(open(game_ref, 'r').read())
        else:
            self.scripts = fetch_script(self, game_ref)
        if not self.scripts:
            raise ScriptingError("Failed to get installer script")
        if not isinstance(self.scripts, list):
            self.scripts = [self.scripts]
        self.show_all()
        self.close_button.hide()
        self.play_button.hide()
        self.install_button.hide()

        self.choose_installer()

    def launch_install(self, script_index):
        script = self.scripts[script_index]
        self.interpreter = ScriptInterpreter(script, self)
        game_name = self.interpreter.game_name.replace('&', '&amp;')
        self.title_label.set_markup("<b>Installing {}</b>".format(game_name))
        self.continue_install()

    def continue_install(self):
        # Target chooser
        if not self.interpreter.requires and self.interpreter.files:
            self.set_message("Select installation directory")
            default_path = self.interpreter.default_target
            self.set_location_entry(self.on_target_changed, 'folder',
                                    default_path)
            self.non_empty_label = Gtk.Label()
            self.non_empty_label.set_markup(
                "<b>Warning!</b> The selected path "
                "contains files, installation might not work property."
            )
            self.widget_box.pack_start(self.non_empty_label, False, False, 10)
        else:
            self.set_message("Click install to continue")
        if self.continue_handler:
            self.continue_button.disconnect(self.continue_handler)
        self.continue_button.hide()
        self.continue_button.connect('clicked', self.on_file_selected)
        self.install_button.show()

    def choose_installer(self):
        self.title_label.set_markup('<b>Select which version to install</b>')
        self.installer_choice_box = Gtk.VBox()
        self.installer_choice = 0
        radio_group = None

        # Build list
        for index, script in enumerate(self.scripts):
            label = script['version']
            btn = Gtk.RadioButton.new_with_label_from_widget(radio_group, label)
            btn.connect('toggled', self.on_installer_toggled, index)
            self.installer_choice_box.pack_start(btn, False, False, 0)
            if not radio_group:
                radio_group = btn

        self.widget_box.pack_start(self.installer_choice_box, False, False, 10)
        self.installer_choice_box.show_all()

        self.continue_button.show()
        self.continue_handler = self.continue_button.connect(
            'clicked', self.on_installer_selected
        )

    def on_installer_toggled(self, btn, script_index):
        if btn.get_active():
            self.installer_choice = script_index

    def on_installer_selected(self, widget):
        self.launch_install(self.installer_choice)
        self.installer_choice_box.destroy()
        self.show_non_empty_warning()

    def on_destroy(self, widget):
        if self.interpreter:
            self.interpreter.cleanup()
        if self.parent:
            self.destroy()
        else:
            Gtk.main_quit()

    def show_non_empty_warning(self):
        if not self.location_entry:
            return
        path = self.location_entry.get_text()
        if os.path.exists(path) and os.listdir(path):
            self.non_empty_label.show()
        else:
            self.non_empty_label.hide()

    def set_message(self, message):
        label = Gtk.Label()
        label.set_markup('<b>%s</b>' % add_url_tags(message))
        label.set_max_width_chars(80)
        label.set_property('wrap', True)
        label.set_alignment(0, 0)
        label.show()
        self.widget_box.pack_start(label, False, False, 10)

    def set_location_entry(self, callback, action=None, default_path=None):
        if action == 'file':
            action = Gtk.FileChooserAction.OPEN
        elif action == 'folder':
            action = Gtk.FileChooserAction.SELECT_FOLDER

        if self.location_entry:
            self.location_entry.destroy()
        self.location_entry = FileChooserEntry(action, default_path)
        self.location_entry.show_all()
        if callback:
            self.location_entry.entry.connect('changed', callback)
        else:
            self.install_button.set_visible(False)
            self.continue_button.show()
        self.widget_box.pack_start(self.location_entry, False, False, 0)

    def on_target_changed(self, text_entry):
        """ Sets the installation target for the game """
        path = text_entry.get_text()
        self.interpreter.target_path = path
        self.show_non_empty_warning()

    def on_install_clicked(self, button):
        button.hide()
        self.interpreter.iter_game_files()

    def ask_user_for_file(self, message):
        self.clean_widgets()
        self.set_message(message)
        if self.selected_directory:
            path = self.selected_directory
        else:
            path = os.path.expanduser('~')
        self.set_location_entry(None, 'file', default_path=path)

    def on_file_selected(self, widget):
        file_path = self.location_entry.get_text()
        if os.path.isfile(file_path):
            self.selected_directory = os.path.dirname(file_path)
        else:
            return
        self.interpreter.file_selected(file_path)

    def clean_widgets(self):
        for child_widget in self.widget_box.get_children():
            child_widget.destroy()

    def set_status(self, text):
        self.status_label.set_text(text)

    def add_spinner(self):
        self.clean_widgets()
        spinner = Gtk.Spinner()
        self.widget_box.pack_start(spinner, True, False, 10)
        spinner.show()
        spinner.start()

    def start_download(self, file_uri, dest_file, callback=None, data=None):
        self.clean_widgets()
        logger.debug("Downloading %s to %s", file_uri, dest_file)
        self.download_progress = DownloadProgressBox(
            {'url': file_uri, 'dest': dest_file}, cancelable=True
        )
        callback_function = callback or self.download_complete
        self.download_progress.connect('complete', callback_function, data)
        self.widget_box.pack_start(self.download_progress, False, False, 10)
        self.download_progress.show()
        self.download_progress.start()

    def wait_for_user_action(self, message, callback, data=None):
        time.sleep(0.3)
        self.clean_widgets()
        label = Gtk.Label(label=message)
        label.set_use_markup(True)
        self.widget_box.add(label)
        label.show()
        button = Gtk.Button(label='Ok')
        button.connect('clicked', callback, data)
        self.widget_box.add(button)
        button.show()

    def input_menu(self, alias, options, preselect, has_entry, callback):
        """Display an input request as a dropdown menu with options."""
        time.sleep(0.3)
        self.clean_widgets()

        model = Gtk.ListStore(str, str)
        for option in options:
            key, label = option.popitem()
            model.append([key, label])
        combobox = Gtk.ComboBox.new_with_model(model)
        renderer_text = Gtk.CellRendererText()
        combobox.pack_start(renderer_text, True)
        combobox.add_attribute(renderer_text, "text", 1)
        combobox.set_id_column(0)
        combobox.set_active_id(preselect)
        self.widget_box.pack_start(combobox, True, False, 100)

        combobox.connect("changed", self.on_input_menu_changed)
        combobox.show()
        self.continue_handler = self.continue_button.connect(
            'clicked', callback, alias, combobox)
        if not preselect:
            self.continue_button.set_sensitive(False)
        self.continue_button.show()

    def on_input_menu_changed(self, widget):
        if widget.get_active_id():
            self.continue_button.set_sensitive(True)

    def download_complete(self, widget, data, more_data=None):
        """Action called on a completed download"""
        self.interpreter.iter_game_files()

    def on_steam_downloaded(self, widget, *args, **kwargs):
        self.interpreter.complete_steam_install(widget.dest)

    def on_install_finished(self):
        """Actual game installation"""
        self.status_label.set_text("Installation finished !")
        self.clean_widgets()
        self.notify_install_success()
        self.continue_button.hide()
        self.install_button.hide()
        self.play_button.show()
        self.close_button.show()
        self.set_urgency_hint(True)

    def notify_install_success(self):
        if self.parent:
            self.parent.view.emit('game-installed', self.game_ref)

    def on_install_error(self, message):
        self.status_label.set_text(message)
        self.clean_widgets()
        self.close_button.show()

    def launch_game(self, widget, _data=None):
        """Launch a game after it's been installed"""
        widget.set_sensitive(False)
        game = Game(self.interpreter.game_slug)
        game.play()
        self.close(widget)

    def close(self, _widget):
        self.destroy()
