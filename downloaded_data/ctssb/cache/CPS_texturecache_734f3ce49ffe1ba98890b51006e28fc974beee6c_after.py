from subprocess import Popen, check_output, check_call, PIPE, STDOUT, CalledProcessError
import traceback
import os
import time
import codecs

from couchpotato.core.logger import CPLog
from couchpotato.core.event import addEvent, fireEvent
from couchpotato.core.plugins.base import Plugin
from couchpotato.core.helpers.variable import splitString, getTitle
from couchpotato.environment import Env

log = CPLog(__name__)


class Texturecache(Plugin):

    def __init__(self):

        # only load plugin if it is enabled on configs
        if self.conf('enabled'):
            # check if development setting is enabled to load new code and trigger renamer automatically
            if Env.get('dev'):
                def test():
                    fireEvent('renamer.scan')
                addEvent('app.load', test)

            addEvent('renamer.after', self.texturecache, priority=110)

    def texturecache(self, message = None, group = None):
        if not group: group = {}

        # group['destination_dir'] ex: E:\Movies\Avatar.(2009)
        # group['identifier'] ex: tt0089218
        # group['filename'] ex: Avatar.(2009)
        # group['renamed_files'] ex: [u'E:\Movies\Avatar.(2009)\Avatar.(2009).DVD-Rip.cd1.avi', u'E:\Movies\Avatar.(2009)\Avatar.(2009).DVD-Rip.cd2.avi']
        
        # Movie name
        self.movie_name = getTitle(group)

        # Max Retries to retrive information
        self.MAX_RETRIES = 3
        self.RETRIES = 0

        log.debug("TextureCache script user configurations:")
        # TextureCache.py script path
        self.texturecache_path = os.path.join(self.conf('texturecache_path'), 'texturecache.py')
        log.debug("texturecache.py script path: %s", self.texturecache_path)
        # Configurations file path
        self.config_path = os.path.join(self.conf('config_file'), 'texturecache.cfg')
        self.config_file = '@config=' + self.config_path
        log.debug("Configurations file: %s", self.config_path)
        # Log file path
        self.log_path = os.path.join(self.conf('log_file'), 'tc.log')
        self.log_file = '@logfile=' + self.log_path
        log.debug("Log file: %s", self.log_path)
        # Mklocal.py script path
        self.mklocal_path = os.path.join(self.conf('mklocal_path'), 'mklocal.py')
        log.debug("mklocal.py script path: %s", self.mklocal_path)
        # Artwork local path
        self.local_path = self.conf('local_path')
        log.debug("Artwork local path: %s", self.local_path)
        # Artwork prefix path
        self.prefix_path = self.conf('prefix_path')
        log.debug("Artwork prefix path: %s", self.prefix_path)
        # Don't download remote artwork
        self.readonly = self.conf('readonly')
        if self.readonly:
            set_readonly = True
        else:
            set_readonly = False
        log.debug("Don't download remote artwork: %s", set_readonly)
        # Don't keep media library artwork if local files no longer exist
        self.nokeep = self.conf('nokeep')
        if self.nokeep:
            set_nokeep = True
        else:
            set_nokeep = False
        log.debug("Don't keep media library artwork : %s", set_nokeep)

        # Custom artwork || 'default': 'poster fanart clearlogo:logo clearart discart:disc banner landscape',
        self.custom_artwork = splitString(self.conf('custom_artwork'), ' ')

        self.movie_input = os.path.join(os.path.dirname(__file__), 'movie.input')
        self.movie_local = os.path.join(os.path.dirname(__file__), 'movie.local')

        # Fallback to default parameters if empty
        if len(self.custom_artwork) == 0:
            self.custom_artwork.append('poster')
            self.custom_artwork.append('fanart')
            self.custom_artwork.append('clearlogo:logo')
            self.custom_artwork.append('clearart')
            self.custom_artwork.append('discart:disc')
            self.custom_artwork.append('banner')
            self.custom_artwork.append('landscape')

        log.debug("IMDB identifier: %s", group['identifier'])
        log.debug("Movie name: %s", self.movie_name)
        log.debug("Downloaded Movie directory: %s", group['parentdir'])
        log.debug("Renamed Movie Files: %s", group['renamed_files'])

        try:
            # Ember Media Manager already updates kodi library while scraping!
            #log.info("Updating Kodi library with movie %s", self.movie_name)
            #if self.update_kodi(group):

            # Let's make sure we have texturecache.py script downloaded and path is correct
            if self.verify_tc_script():
                log.info("Setting and caching local artwork for movie %s", self.movie_name)
                self.process()
        except:
            log.error("There was a problem setting and/or caching local artwork for movie %s: %s", (self.movie_name, (traceback.format_exc())))
            return False

    def verify_tc_script(self):

        log.info('Verifying texturecache.py script')
        try:
            command = []
            command = ['python', self.texturecache_path, 'version', self.config_file, self.log_file]
            p = Popen(command, stdout=PIPE, stderr=STDOUT)
            response = p.communicate()[0]
            response = response[:-1] if response.endswith("\n") else response
            log.debug('verify_tc_script response: %s', response)
            if response.find('Current Version:') != -1:
                log.debug('Found texturecache script. Proceeding...')
                return True
            else:
                log.error('texturecache.py path is invalid! Please make sure path is correct or install script from https://github.com/MilhouseVH/texturecache.py')
                return False
        except:
            log.error("There was a problem verifying texturecache.py script: %s" % traceback.format_exc())
            return False

    def remove_file(self, filepath):

        try:
            os.remove(os.path.realpath(filepath))
            log.debug("Permanently removed file %s!", filepath)
        except:
            log.error("There was a problem removing file: %s!", filepath)
            pass

    def update_kodi(self, group):

        log.info("Sending JSON-RPC update command to Kodi")

        try:
            remote_moviepath = os.path.join(self.prefix_path, os.path.basename(os.path.normpath(group['destination_dir'])))

            log.debug("Sending JSON VideoLibrary.Scan to scan new movie: %s", remote_moviepath)
            command = []
            command = ['python', self.texturecache_path, 'vscan', self.prefix_path, self.config_file, self.log_file]
            p = Popen(command, stdout=PIPE, stderr=STDOUT)
            response = p.communicate()[0]
            response = response[:-1] if response.endswith("\n") else response
            log.debug('update_kodi response: %s', response)
            if response.find('Updating Library: New movieid') != -1:
                log.info("Successfully updated Kodi library with movie: %s", self.movie_name)
                # wait for Kodi to update database
                time.sleep(20)
                return True
            else:
                log.info("No response from Kodi! Disconnected?")
                return False
        except:
            log.error("There was a problem updating Kodi library with movie %s: %s", (self.movie_name, (traceback.format_exc())))
            return False

    def process(self):

        # starting texturecache steps:
        log.debug("First step: Query Kodi library")
        # Query Kodi library
        if self.get_json():
            log.debug("Second step: Local artwork references")
            # Local artwork references
            if self.mklocal():
                log.debug("Third step: Set artwork")
                # Set artwork
                if self.set_artwork():
                    log.debug("Fourth step: Cache artwork")
                    # Cache local artwork
                    if self.cache_artwork():
                        # Clean temp files
                        self.remove_file(self.movie_input)
                        self.remove_file(self.movie_local)
                        return True
        return False

    def empty_file(self, filename):
        try:
            if os.stat(filename).st_size > 0:
                log.debug("File exists... Processing...")
                return False
            else:
                log.debug("Empty file! Trying again...")
                return True
        except OSError:
            log.debug("File not found! Trying again...")
            return True

    def get_json(self):

        try:
            # get Kodi library movie json data
            command = []
            command = ['python', self.texturecache_path, 'jd', 'movies', '@filter.operator=is', self.movie_name, self.config_file, self.log_file]
            log.debug("Retrieving Kodi Media library json data for movie %s with command: %s", (self.movie_name, command))

            try:
                response = check_output(command, stderr=PIPE).decode("utf-8")
                response = response[:-1] if response.endswith("\n") else response
                log.debug('get_json() response: %s', response)
                if not (response.find('libMovies.ERROR') != -1):
                    f = codecs.open(self.movie_input, "wb", encoding="utf-8")
                    f.write(response)
                    f.close()
            except:
                log.debug("There was a problem creating file with Kodi json data for movie %s: %s", (self.movie_name, (traceback.format_exc())))
                return False

            # test file and proceed only if not empty!
            if self.empty_file(self.movie_input):
                self.RETRIES += 1
                if (self.RETRIES <= self.MAX_RETRIES):
                    log.debug("Retry number %s of %s", (self.RETRIES, self.MAX_RETRIES))
                    log.debug("Sleeping for 60 seconds and then trying again...")
                    time.sleep(60)
                    self.get_json()
                else:
                    log.info("There was a problem creating file with Kodi json data for movie %s! Reached maximum number of retries!", self.movie_name)
                    return False
            else:
                log.info("Successfully generated json data for movie %s", self.movie_name)
                self.RETRIES = 0
                return True
        except:
            log.error("There was a problem retrieving json data for movie %s: %s", (self.movie_name, (traceback.format_exc())))
            return False

    def mklocal(self):

        try:
            # mklocal command
            command = []
            command = command + ['python', self.mklocal_path, '-i', self.movie_input, '-l', self.local_path, '-p', self.prefix_path, '-a']
            for artwork in self.custom_artwork:
                command.append(artwork)
            if self.readonly:
                command.append('-r')
            if self.nokeep:
                command.append('-nk')
            command.append('-o')

            log.debug("Creating local artwork references for movie %s with command: %s", (self.movie_name, command))

            try:
                response = check_output(command, stderr=PIPE).decode("utf-8")
                log.debug('mklocal() response: %s', response)
                if response:
                    f = codecs.open(self.movie_local, "wb", encoding="utf-8")
                    f.write(response)
                    f.close()
            except:
                log.debug("There was a problem creating file with local artwork references for movie %s: %s", (self.movie_name, (traceback.format_exc())))
                return False

            # test file and proceed only if not empty!
            if self.empty_file(self.movie_local):
                self.RETRIES += 1
                if (self.RETRIES <= self.MAX_RETRIES):
                    log.debug("Retry number %s of %s", (self.RETRIES, self.MAX_RETRIES))
                    log.debug("Sleeping for 60 seconds and then trying again...")
                    time.sleep(60)
                    self.mklocal()
                else:
                    log.info("There was a problem creating file with local artwork references for movie %s! Reached maximum number of retries!", self.movie_name)
                    return False
            else:
                log.info("Successfully created json local artwork references for movie: %s", self.movie_name)
                self.RETRIES = 0
                return True
        except:
            log.error("Failed to create local artwork references for movie %s: %s", (self.movie_name, (traceback.format_exc())))
            return False

    def set_artwork(self):

        try:
            command = []
            command = ['python', self.texturecache_path, 'set', self.config_file, self.log_file]
            log.debug("Setting media library artwork with command: %s", command)
            myinput = codecs.open(self.movie_local, "rb", encoding="utf-8")
            log.debug(myinput)
            ret = check_call(command, stdin=myinput, stderr=PIPE)
            myinput.close()
            log.debug('set_artwork() return code: %s', ret)
            if ret == 0:
                log.info("Successfully set %s local artwork to Kodi Media library!: ", self.movie_name)
                self.RETRIES = 0
                return True
            else:
                self.RETRIES += 1
                if (self.RETRIES <= self.MAX_RETRIES):
                    log.debug("Retry number %s of %s", (self.RETRIES, self.MAX_RETRIES))
                    log.debug("Sleeping for 60 seconds and then trying again...")
                    time.sleep(60)
                    self.set_artwork()
                else:
                    log.info("There was a problem setting artwork for movie %s! Reached maximum number of retries!", self.movie_name)
                    return False
        except:
            log.error("There was a problem updating %s local artwork on Kodi Media library: %s", (self.movie_name, (traceback.format_exc())))
            return False

    def cache_artwork(self):

        try:
            command = []
            command = ['python', self.texturecache_path, 'C', 'movies', self.movie_name, self.config_file, self.log_file]
            log.debug("Caching movie artwork with command: %s", command)
            response = check_output(command, stderr=STDOUT).decode("utf-8")
            response = response[:-1] if response.endswith("\n") else response
            log.debug('cache_artwork() response: %s', response)
            if not (response.find("TOTAL RUNTIME:") != -1):
                self.RETRIES += 1
                if (self.RETRIES <= self.MAX_RETRIES):
                    log.debug("Retry number %s of %s", (self.RETRIES, self.MAX_RETRIES))
                    log.debug("Sleeping for 60 seconds and then trying again...")
                    time.sleep(60)
                    self.cache_artwork()
                else:
                    log.info("There was a problem caching movie %s! Reached maximum number of retries!", self.movie_name)
                    return False
            else:
                log.info("Successfully cached %s local artwork!", self.movie_name)
                self.RETRIES = 0
                return True
        except CalledProcessError as e:
            log.debug('CalledProcessError exited with: %s', e.output)
        except:
            log.error("There was a problem caching %s local artwork: %s", (self.movie_name, (traceback.format_exc())))
            return False
