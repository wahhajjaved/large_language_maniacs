#
# An action plugin for hypnotoad to create panasas links.
#


import datetime
import errno
import json
import logging
import os
import pprint
import shlex
import subprocess

from hypnotoad import plugin
from hypnotoad import hypnofs

LOG = logging.getLogger('root')
HYPNOFS = hypnofs.hypnofs()

class panlinks_plugin(plugin.action_plugin):
    def setup(self, config, model_version):
        """Called before the plugin is asked to do anything."""
        if config.getboolean('Action Options', 'panlinks_plugin_enabled'):
            self.plugin_enabled = True
            LOG.debug("Panasas Links plugin enabled")

            self.state_dir = config.get('Basic Options', 'state_dir') + "/panlinks"
            self.new_dir_perms = config.get('Action Options', 'panlinks_new_dir_perms')

            self.root_mount_point = config.get('Action Options', 'panlinks_mount_point')

            self.skip_bad_realms = config.getboolean('Action Options', 'panlinks_skip_bad_realms')
            self.max_diff_count = config.getint('Action Options', 'panlinks_max_diff_count')
            self.max_skip_bad_vols = config.getint('Action Options', 'panlinks_max_skip_bad_vols')
            self.max_skip_bad_realms = config.getint('Action Options', 'panlinks_max_skip_bad_realms')
            self.command_timeout = config.getint('Action Options', 'panlinks_subprocess_timeout')

            self.realms_to_skip = shlex.shlex(config.get('Action Options', 'panlinks_skip_realms'))
            self.realms_to_skip.whitespace += ','
            self.realms_to_skip.whitespace_split = True

            self.create_pristine = config.getboolean('Action Options', 'panlinks_pristine_dir_create')
            self.pristine_mount_dir = config.get('Action Options', 'panlinks_pristine_mount_dir')
            self.pristine_subdir = config.get('Action Options', 'panlinks_pristine_subdir')

            self.config = config
            self.model_version = model_version

            self.volume_failures = {}
            self.realm_failures = {}
        else:
            self.plugin_enabled = False

    def teardown(self):
        """Called to allow the plugin to free anything."""
        if self.plugin_enabled:
            LOG.debug("Got to Panasas Links plugin teardown")

    def append_model(self, models):
        """Handled a model appended to this output."""
        if self.plugin_enabled:
            LOG.debug("Got to Panasas Links plugin append_model.")

            self.cache_check_and_update(models)

            all_usernames = self.collect_users_from_models(models)
            self.ensure_user_directories_exist(all_usernames)

    def ensure_user_directories_exist(self, all_usernames):
        """
        Check to make sure each user has a directory located on a single
        volume on each realm. Then, ensure that a symlink exists for each
        realm.
        """
        mounted_panfs_list = self.get_current_panfs_mounts()

        users_with_orig_dirs, where_user_orig_dir_is = self.get_user_original_directory_info(mounted_panfs_list, all_usernames)
        users_without_orig_dirs = set(all_usernames) - set(users_with_orig_dirs)

        LOG.debug("Users without directories: " + str(users_without_orig_dirs))
        if len(users_without_orig_dirs) > self.max_diff_count:
            LOG.debug("Too many missing users. We have " + len(all_usernames) + " total users, but only " + len(users_with_orig_dirs) + " have existing directories.")
            raise UserError

        """Create intial directories and symlinks for new users."""
        for user in users_without_orig_dirs:
            create_initial_directories_for(user, mounted_panfs_list)

        """Just verify symlinks for users with existing directories."""
        for u in users_with_orig_dirs:
            user_realm = where_user_orig_dir_is[u]['realm']
            user_volume = where_user_orig_dir_is[u]['volume']
            self.ensure_symlink_for_user(u, user_realm, user_volume, "/")

        """Go back and create a pristine directory if necessary."""
        if self.create_pristine:
            pristine_users, pristine_where = self.get_user_original_directory_info(mounted_panfs_list, all_usernames)
            for u in pristine_users:
                realm = pristine_where[u]['realm']
                volume = pristine_where[u]['volume']
                if HYPNOFS.ismount(self.pristine_mount_dir, self.command_timeout):
                    pristine_path = self.pristine_mount_dir + "/" + self.pristine_subdir
                    self.ensure_symlink_for_user(u, realm, volume, pristine_path)
                else:
                    LOG.debug("Pristine base path was not mounted.")
                    raise UserError

    def check_realm_failure_counters():
        """
        Check to see if the number of failures are still within the limits
        defined by the configuration.
        """
        LOG.debug("Checking realm and volume failures. Failure is likely in progress.")

        for realm, fail_count in volume_failures:
            if fail_count > self.max_skip_bad_vols:
                LOG.debug("Too many volumes have failed on '" + realm + "'. Realm is now considered in a failed state.")
                if self.realm_failures[realm] is None:
                    self.realm_failures[realm] = 1
                else:
                    self.realm_failures[realm] = self.realm_failures[realm] + 1

        for realm, fail_count in realm_failures:
            if fail_count > self.max_skip_bad_realms:
                LOG.debug("Too many realms have failed. We're giving up.")
                sys.exit("Exceeded number of allowed realm failures.")

    def create_initial_directories_for(self, username, realms):
        """Create a new directory on each realm for the specified user."""
        for realm in realms:
            try:
                vol_name = self.get_volume_with_least_users(realm)
            except IOError, exc:
                if exc.errno == errno.EWOULDBLOCK:
                    if self.volume_failures[realm] is None:
                        self.volume_failures[realm] = 1
                    else:
                        LOG.debug("Encountered a failure on '" + realm + "'. Attempting to continue.")

                        self.volume_failures[realm] = self.volume_failures[realm] + 1
                        self.check_realm_failure_counters()

                        return
                    pass
                else:
                    raise

            user_dir_path = self.root_mount_point + "/" + realm + "/" + vol_name + "/" + username

            LOG.debug('Creating initial user directory "' + user_dir_path + '" for user "' + username)
            self.ensure_dir(user_dir_path)

            LOG.debug('Creating new symlink for user "' + username + '" on realm "' + realm + '".')
            self.ensure_symlink_for_user(username, realm, vol_name, self.root_mount_point)

    def ensure_symlink_for_user(self, username, realm_name, volume_name, base):
        """
        Ensure that a symlink exists for the user in the specified location.
        """
        user_symlink_dst_path = base + "/" + realm_name + "/" + username
        user_symlink_src_path = self.root_mount_point + "/" + realm_name + "/" + volume_name + "/" + username
        
        try:
            if not HYPNOFS.path_exists(user_symlink_dst_path, self.command_timeout):
                LOG.debug('Creating missing symlink from "' + user_symlink_src_path + '" to "' + user_symlink_dst_path)
                HYPNOFS.symlink(user_symlink_src_path, user_symlink_dst_path, self.command_timeout)
                if not HYPNOFS.islink(user_symlink_dst_path, self.command_timeout):
                    LOG.debug('Failed to create a symlink at: "' + user_symlink_dst_path + '".')
        except IOError, exc:
            if exc.errno == errno.EWOULDBLOCK:
                if self.volume_failures[realm_name] is None:
                    self.volume_failures[realm_name] = 1
                else:
                    LOG.debug("Encountered a failure on '" + realm_name + "'. Attempting to continue.")

                    self.volume_failures[realm_name] = self.volume_failures[realm_name] + 1
                    self.check_realm_failure_counters()

                    return
                pass
            else:
                raise

    def collect_users_from_models(self, models):
        """ Merge all hypnotoad models into a single list of user names."""
        userlist = []
        for plug_model in models:
            for m in plug_model:
                if 'user_entry' in m.keys():
                    user = m['user_entry']
                    userlist.append(user['short_name_string'].strip())
        return userlist

    def get_volume_with_least_users(self, realm):
        """
        Determines the volume in a realm with the least number of users and
        returns the name.
        """
        volume_with_least_users = None
        current_least_count = None
        realm_path = self.root_mount_point + "/" + realm

        if not HYPNOFS.isdir(realm_path, self.command_timeout):
            LOG.debug('The specified realm path "' + realm_path + '" does not exist.')
            raise UserError

        for volume_dir in HYPNOFS.listdir(realm_path, self.command_timeout):
            if not HYPNOFS.isdir(volume_dir, self.command_timeout):
                LOG.debug('Found a volume that is not a directory (' + volume_dir + ').')
                raise UserError
            users_in_this_volume = len(HYPNOFS.listdir(volume_dir, self.command_timeout))
            if current_least_count is None or users_in_this_volume < current_least_count:
                volume_with_least_users = volume_dir
                current_top_count = users_in_this_volume

        if volume_with_least_users is None:
            LOG.debug("Could not find a volume with the least number of users.")
            raise UserError

        LOG.debug("Found the volume with the least number of users: " + volume_with_least_users)
        return volume_with_least_users

    def get_user_original_directory_info(self, mounts, all_users):
        """
        Find valid users which already have directories created, as well as
        what volume users have directories on.
        """
        users_on_realm_vols = {}
        users_with_dirs = []

        for mount_dir in mounts:
            if not HYPNOFS.isdir(mount_dir, self.command_timeout):
                LOG.debug('Mount directory "' + mount_dir + '" is invalid.')
                raise UserError
            for volume_dir in HYPNOFS.listdir(mount_dir, self.command_timeout):
                if not volume_dir.startswith("vol"):
                    continue
                volume_path = mount_dir + "/" + volume_dir
                if not HYPNOFS.isdir(volume_path, self.command_timeout):
                    LOG.debug('Volume directory "' + volume_path + '" is invalid.')
                    raise UserError
                for user_dir in HYPNOFS.listdir(volume_path, self.command_timeout):
                    user_pth = volume_path + "/" + user_dir
                    if not HYPNOFS.isdir(user_path, self.command_timeout):
                        LOG.debug('User directory "' + user_path + '" is invalid.')
                        raise UserError
                    users_on_realm_vols[user_dir] = {
                        "volume": volume_dir,
                        "realm": os.path.basename(mount_dir)
                    }
                    users_with_dirs.append(user_dir)

        intersection = set(all_users) & set(users_with_dirs)
        return intersection, users_on_realm_vols

    def cache_check_and_update(self, models):
        """
        If a cache exists, check differences and update the cache if the
        differences are not too great. Otherwise quietly create a cache if one
        does not exist already.
        """
        cache_file_name = self.state_dir + "/" + "model.json"
        self.ensure_dir(self.state_dir)

        def save_as_json(obj, dest_file_name):
            """Serializes obj to json and saves to a file at dest."""
            LOG.debug("Saving to json at: " + dest_file_name)
            j = json.dumps(obj)
            f = open(dest_file_name, 'w')
            f.write(j + "\n")
            f.close()

        def json_to_models(json_file_name):
            LOG.debug("Reading in json file at: " + json_file_name)
            f = open(json_file_name)
            return json.load(f)

        if self.isfile(cache_file_name):
            old_models = json_to_models(cache_file_name)

            old_userlist, new_userlist = map(self.collect_users_from_models, [old_models, models])
            model_diff_count = len(list(set(old_userlist) - set(new_userlist)))

            if model_diff_count > self.max_diff_count:
                LOG.error("Model too different with " + model_diff_count + " changes.")
                raise UserWarning
            else:
                # Overwrite the old cache.
                save_as_json(models, cache_file_name)
        else:
            # Create a new cache if one does not exist.
            save_as_json(models, cache_file_name)

    def ensure_dir(self, path):
        """Create directory at path if it doesn't exist."""
        LOG.debug("Ensure dir at '" + path + "' with perms '" + str(int(self.new_dir_perms, 8)) + "'.")
        try:
            HYPNOFS.makedirs(path, self.command_timeout)
            HYPNOFS.chmod(path, int(self.new_dir_perms, 8), self.command_timeout)
        except OSError, exc:
            if exc.errno == errno.EEXIST:
                pass
            else:
                raise

    def get_current_panfs_mounts(self):
        """
        Check if all panfs mounts specified in fstab are mounted. Display a
        warning if not. Return mounted panfs mount points.
        """
        def tab_check(f):
            m = []
            for l in f.readlines():
                i = l.find('#')
                if i != -1:
                    l = l[:i]
                    l = l.rstrip()
                if l.find('panfs') != -1:
                    m.append(l.split()[1])
            return set(m)

        fstab_mounts, mtab_mounts = map(tab_check, [open('/etc/fstab'), open('/etc/mtab')])
        if len(fstab_mounts & mtab_mounts) == len(fstab_mounts):
            LOG.debug('All detected PanFS mounts are mounted.')
        else:
            LOG.warn('There are panfs mounts that are NOT mounted.')
            raise UserWarning

        skips = list(self.realms_to_skip)
        for s in skips:
            LOG.debug("Not using realm '" + str(s) + "' due to configuration.")
            mtab_mounts.discard(s)

        LOG.debug("Using realms: " + str(mtab_mounts))
        return mtab_mounts

# EOF
