#!/usr/bin/python
#
# Copyright (c) 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

import os
import string
import sys
import time
import urlparse
from datetime import timedelta
from gettext import gettext as _
from itertools import chain
from optparse import OptionGroup

from isodate import ISO8601Error

from pulp.client.admin.plugin import AdminPlugin
from pulp.client.api.consumer import ConsumerAPI
from pulp.client.api.errata import ErrataAPI
from pulp.client.api.file import FileAPI
from pulp.client.api.package import PackageAPI
from pulp.client.api.repository import RepositoryAPI
from pulp.client.api.service import ServiceAPI
from pulp.client.api.task import TaskAPI, task_end, task_succeeded
from pulp.client import constants
from pulp.common.dateutils import (
    parse_iso8601_datetime, parse_iso8601_duration, parse_iso8601_interval,
    format_iso8601_datetime, format_iso8601_duration)
from pulp.client.lib.utils import (
    print_header, parse_interval_schedule)
from pulp.client.lib import utils
from pulp.client.lib.logutil import getLogger
from pulp.client.plugins.repo import RepoAction, Repo, List

log = getLogger(__name__)

# repo command errors ---------------------------------------------------------

class FileError(Exception):
    pass

class SyncError(Exception):
    pass

class CloneError(Exception):
    pass

# base repo action class ------------------------------------------------------

class AdminRepoAction(RepoAction):

    def __init__(self, cfg):
        super(RepoAction, self).__init__(cfg)
        self.consumer_api = ConsumerAPI()
        self.errata_api = ErrataAPI()
        self.package_api = PackageAPI()
        self.service_api = ServiceAPI()
        self.file_api = FileAPI()
        self.repository_api = RepositoryAPI()
        self.task_api = TaskAPI()

    def get_repo(self, id):
        """
        Convenience method for getting a required repository from pulp, and
        exiting with an appropriate error message if the repository doesn't
        exist.
        @type id: str
        @param id: repository id
        @rtype: dict
        @return: dictionary representing the repository
        """
        repo = self.repository_api.repository(id)
        if repo is None:
            utils.system_exit(os.EX_DATAERR, _("Repository with id: [%s] not found") % id)
        return repo


    def handle_dependencies(self, srcrepo, tgtrepo=None, pkgnames=[], recursive=0, assumeyes=False):
        deps = self.service_api.dependencies(pkgnames, [srcrepo], recursive)['resolved']
        deplist = []
        for dep, pkgs in deps.items():
            for pkg in pkgs:
                deplist.append({'name'    : pkg['name'],
                                'version' : pkg['version'],
                                'release' : pkg['release'],
                                'epoch'   : pkg['epoch'],
                                'arch'    : pkg['arch'],
                                'filename': pkg['filename'],
                                'id'      : pkg['id']})
        new_deps = []
        if tgtrepo:
            avail_deps = self.repository_api.find_package_by_nvrea(tgtrepo, deplist) or []
            for dep, pkgs in deps.items():
                for pkg in pkgs:
                    if pkg['filename'] not in avail_deps:
                        new_deps.append(pkg)
        else:
            new_deps = deplist
        if not new_deps:
            # None relevant, return
            print(_("No dependencies to process.."))
            return []
        if not assumeyes:
            do_deps = ''
            while do_deps.lower() not in ['y', 'n', 'q']:
                do_deps = raw_input(_("\nFollowing dependencies are suggested. %s \nWould you like us to add these?(Y/N/Q):" \
                                      % [dep['filename'] for dep in new_deps]))
                if do_deps.strip().lower() == 'y':
                    assumeyes = True
                elif do_deps.strip().lower() == 'n':
                    print(_("Skipping dependencies"))
                    return []
                elif do_deps.strip().lower() == 'q':
                    utils.system_exit(os.EX_OK, _("Operation aborted upon user request."))
                else:
                    continue
        return new_deps

    def lookup_repo_packages(self, filename, repoid, checksum=None, checksum_type="sha256"):
        pkgobj = self.service_api.search_packages(filename=filename,
                                                  checksum=checksum,
                                                  checksum_type=checksum_type, regex=False)
        for pkg in pkgobj:
            pkg_repos = pkg["repos"]
            if repoid in pkg_repos:
                return pkg
        return None


# repo actions ----------------------------------------------------------------

class RepoProgressAction(AdminRepoAction):

    def __init__(self, cfg):
        AdminRepoAction.__init__(self, cfg)
        self._previous_progress = None
        self.wait_index = 0
        self.wait_symbols = "|/-\|/-\\"
        self._previous_step = None

    def terminal_size(self):
        import fcntl, termios, struct
        h, w, hp, wp = struct.unpack('HHHH',
            fcntl.ioctl(0, termios.TIOCGWINSZ,
                struct.pack('HHHH', 0, 0, 0, 0)))
        return w, h

    def count_linewraps(self, data):
        linewraps = 0
        width = height = 0
        try:
            width, height = self.terminal_size()
        except:
            # Unable to query terminal for size
            # so default to 0 and skip this
            # functionality
            return 0
        for line in data.split('\n'):
            count = 0
            for d in line:
                if d in string.printable:
                    count += 1
            linewraps += count / width
        return linewraps

    def write(self, current, prev=None):
        """ Use information of number of columns to guess if the terminal
        will wrap the text, at which point we need to add an extra 'backup line'
        """
        lines = 0
        if prev:
            lines = prev.count('\n')
            if prev.rstrip(' ')[-1] != '\n':
                lines += 1 # Compensate for the newline we inject in this method at end
            lines += self.count_linewraps(prev)
        # Move up 'lines' lines and move cursor to left
        sys.stdout.write('\033[%sF' % (lines))
        sys.stdout.write('\033[J')  # Clear screen cursor down
        sys.stdout.write(current)
        # In order for this to work in various situations
        # We are requiring a new line to be entered at the end of
        # the current string being printed.
        if current.rstrip(' ')[-1] != '\n':
            sys.stdout.write("\n")
        sys.stdout.flush()

    def get_wait_symbol(self):
        self.wait_index += 1
        if self.wait_index > len(self.wait_symbols) - 1:
            self.wait_index = 0
        return self.wait_symbols[self.wait_index]

    def print_progress(self, progress):
        current = ""
        if progress and progress.has_key("step") and progress["step"]:
            current += _("Step: %s\n") % (progress['step'])
            if "Downloading Items" in progress["step"]:
                current += self.form_progress_item_downloads(progress)
            else:
                current += "Waiting %s\n" % (self.get_wait_symbol())
            self._previous_step = progress["step"]
        else:
            current += "Waiting %s\n" % (self.get_wait_symbol())
            self._previous_step = None
        self.write(current, self._previous_progress)
        self._previous_progress = current

    def form_progress_item_details(self, details):
        result = ""
        for item_type in details:
            item_details = details[item_type]
            if item_details.has_key("num_success") and \
                item_details.has_key("total_count"):
                    result += _("%s: %s/%s\n") % \
                        (item_type.title(),
                         item_details["num_success"],
                         item_details["total_count"])
        return result

    def form_progress_item_downloads(self, progress):
        current = ""
        bar_width = 25
        # calculate the progress
        done = float(progress['size_total']) - float(progress['size_left'])
        total = float(progress['size_total'])
        if total > 0.0:
            portion = done / total
        else:
            portion = 1.0
        percent = str(int(100 * portion))
        items_done = str(progress['items_total'] - progress['items_left'])
        items_total = str(progress['items_total'])
        # create the progress bar
        bar_ticks = '=' * int(bar_width * portion)
        bar_spaces = ' ' * (bar_width - len(bar_ticks))
        bar = '[' + bar_ticks + bar_spaces + ']'
        current += _('%s %s%%\n') % (bar, percent)
        current += self.form_progress_item_details(progress["details"])
        current += _("Total: %s/%s items\n") % (items_done, items_total)
        return current

    def form_error_details(self, progress, num_err_display=5):
        """
        progress : dictionary of sync progress info
        num_err_display: how many errors to display per type, if less than 0 will display all errors
        """
        ret_val = ""
        if not progress.has_key("error_details"):
            return ret_val
        error_entry = {}
        for error in progress["error_details"]:
            if not error_entry.has_key(error["item_type"]):
                error_entry[error["item_type"]] = []
            if error.has_key("error"):
                error_entry[error["item_type"]].append(error["error"])
        for item_type in error_entry:
            ret_val += _("%s %s Error(s):\n") % (len(error_entry[item_type]), item_type.title())
            for index, errors in enumerate(error_entry[item_type]):
                if num_err_display > 0 and index >= num_err_display:
                    ret_val += _("\t... %s more error(s) occured.  See server logs for all errors.") % \
                            (len(error_entry[item_type]) - index)
                    break
                else:
                    ret_val += "\t" + str(errors) + "\n"
        return ret_val


class Status(AdminRepoAction):

    name = "status"
    description = _('show the status of a repository')

    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        syncs = self.repository_api.sync_list(id)
        print_header(_('Status for %s') % id)
        print _('Repository: %s') % repo['id']
        if repo['content_types'] in ('yum'):
            print _('Number of Packages: %d') % repo['package_count']
        if repo['content_types'] in ('file'):
            files_count = self.repository_api.list_files(id)
            print _('Number of Files: %d' % len(files_count))
        last_sync = repo['last_sync']
        if last_sync is None:
            last_sync = 'never'
        else:
            last_sync = str(parse_iso8601_datetime(last_sync))
        print _('Last Sync: %s') % last_sync
        running_sync = self.repository_api.running_task(syncs)
        if not syncs or running_sync is None:
            if syncs and syncs[0]['state'] in ('error'):
                print _("Last Error: %s\n%s") % \
                        (str(parse_iso8601_datetime(syncs[0]['finish_time'])),
                                syncs[0]['traceback'][-1])
        else:
            print _('Currently syncing:'),
            if running_sync['progress'] is None:
                print _('progress unknown')
            else:
                pkgs_left = running_sync['progress']['items_left']
                pkgs_total = running_sync['progress']['items_total']
                bytes_left = float(running_sync['progress']['size_left'])
                bytes_total = float(running_sync['progress']['size_total'])
                percent = 0
                if bytes_total > 0:
                    percent = ((bytes_total - bytes_left) / bytes_total) * 100.0
                print _('%d%% done (%d of %d packages downloaded)') % \
                    (int(percent), (pkgs_total - pkgs_left), pkgs_total)

        # Process cloning status, if exists
        clones = self.repository_api.clone_list(id)
        running_clone = self.repository_api.running_task(clones)
        if not clones or running_clone is None:
            if clones and clones[0]['state'] in ('error'):
                print _("Last Error: %s\n%s") % \
                        (str(parse_iso8601_datetime(clones[0]['finish_time'])),
                                clones[0]['traceback'][-1])
            return
        print _('Currently cloning:'),
        if running_clone['progress'] is None:
            print _('progress unknown')
        else:
            pkgs_left = running_clone['progress']['items_left']
            pkgs_total = running_clone['progress']['items_total']
            bytes_left = float(running_clone['progress']['size_left'])
            bytes_total = float(running_clone['progress']['size_total'])
            percent = 0
            if bytes_total > 0:
                percent = ((bytes_total - bytes_left) / bytes_total) * 100.0
            print _('%d%% done (%d of %d packages cloned)') % \
                    (int(percent), (pkgs_total - pkgs_left), pkgs_total)


class Content(AdminRepoAction):

    name = "content"
    description = _('list the contents of a repository')

    def setup_parser(self):
        super(Content, self).setup_parser()
        opt_group = self.parser.add_option_group("Updates Only")
        opt_group.add_option("--consumerid", dest="consumerid",
                               help=_("optional consumer id to list only available updates;"))
    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        all_packages = self.repository_api.packages(id)
        all_pnames = [pkg['filename'] for pkg in all_packages]
        all_errata = self.repository_api.errata(repo['id'])
        all_errata_ids = [e["id"] for e in all_errata]
        if self.opts.consumerid is not None:
            if not len(self.opts.consumerid):
                self.parser.error(_("error: --consumerid requires an argument"))
            consumer = self.consumer_api.consumer(self.opts.consumerid)
            errata_pkg_updates = self.consumer_api.errata_package_updates(consumer['id'])
            pkg_updates = errata_pkg_updates['packages']
            pkgs = []
            for p in pkg_updates:
                #limit updates to repo packages
                if p['filename'] in all_pnames:
                    pkgs.append(p['filename'])
            pnames = pkgs
            # limit errata to repo
            cerrata = errata_pkg_updates['errata']
            applicable_errata = []
            for e in cerrata:
                if e in all_errata_ids:
                    applicable_errata.append(e)
            errata = applicable_errata
        else:
            pnames = all_pnames
            errata = all_errata_ids
        print_header(_('Contents of %s') % id)

        print _('\nPackages in %s: \n') % id
        if not pnames:
            print _(' none')
        else:
            print '\n'.join(pnames[:])
        print _('\nErrata in %s: \n') % id
        if not errata:
            print _(' none')
        else:
            print '\n'.join(errata[:])
        print _('\nFiles in %s: \n') % id
        files = self.repository_api.list_files(repo['id'])
        if not files:
            print _(' none')
        else:
            for f in files:
                print ' ' + f['filename']



class Create(AdminRepoAction):

    name = "create"
    description = _('create a repository')

    def setup_parser(self):
        super(Create, self).setup_parser()
        self.parser.add_option("--name", dest="name",
                               help=_("common repository name"))
        self.parser.add_option("--arch", dest="arch",
                               help=_("package arch the repository should support"))
        self.parser.add_option("--feed", dest="feed",
                               help=_("url feed to populate the repository"))
        self.parser.add_option("--feed_ca", dest="feed_ca",
                               help=_("path location to the feed's ca certificate"))
        self.parser.add_option("--feed_cert", dest="feed_cert",
                               help=_("path location to the feed's entitlement certificate"))
        self.parser.add_option("--feed_key", dest="feed_key",
                               help=_("path location to the feed's entitlement certificate key"))
        self.parser.add_option("--consumer_ca", dest="consumer_ca",
                               help=_("path location to the ca certificate used to verify consumer requests"))
        self.parser.add_option("--consumer_cert", dest="consumer_cert",
                               help=_("path location to the entitlement certificate consumers will be provided at bind to grant access to this repo"))
        self.parser.add_option("--consumer_key", dest="consumer_key",
                               help=_("path location to the consumer entitlement certificate key"))
        #self.parser.add_option("--schedule", dest="schedule",
        #                       help=_("cron entry date and time syntax for scheduling automatic repository synchronizations"))
        self.parser.add_option("--symlinks", action="store_true", dest="symlinks",
                               help=_("use symlinks instead of copying bits locally; applicable for local syncs"))
        self.parser.add_option("--relativepath", dest="relativepath",
                               help=_("relative path where the repository is stored and exposed to clients; this defaults to feed path if not specified"))
        self.parser.add_option("--groupid", action="append", dest="groupid",
                               help=_("a group to which the repository belongs; this is just a string identifier"))
        self.parser.add_option("--gpgkeys", dest="keys",
                               help=_("a ',' separated list of directories and/or files containing GPG keys"))
        self.parser.add_option("--checksum_type", dest="checksum_type", default="sha256",
                               help=_("checksum type to use when yum metadata is generated for this repo; default:sha256"))
        self.parser.add_option("--notes", dest="notes",
                               help=_("additional information about repo in a dictionary form inside a string"))
        self.parser.add_option("--preserve_metadata", action="store_true", dest="preserve_metadata",
                               help=_("Preserves the original metadata; only works with feed repos"))
        self.parser.add_option('--content_type', dest='content_type', default="yum",
                            help=_('content type allowed in this repository; default:yum; supported: [yum, file]'))

    def run(self):
        id = self.get_required_option('id')
        name = self.opts.name or id
        arch = self.opts.arch or 'noarch'
        feed = self.opts.feed
        if self.opts.preserve_metadata and not feed:
            utils.system_exit(os.EX_USAGE, _('Cannot use `preserve_metadata` option for feedless repos'))
        preserve_metadata = False
        if self.opts.preserve_metadata:
            preserve_metadata = self.opts.preserve_metadata
        symlinks = self.opts.symlinks or False
        relative_path = self.opts.relativepath
        if self.opts.notes:
            try:
                notes = eval(self.opts.notes)
            except:
                utils.system_exit(os.EX_USAGE, _("Invalid argument for notes. Notes need to be specified in dictionary form inside a string eg. \"{'key':'value'}\""))

        else:
            notes = {}

        # Feed cert bundle
        feed_cert_data = None
        cacert = self.opts.feed_ca
        cert = self.opts.feed_cert
        key = self.opts.feed_key
        feed_cacert_tmp = None
        if cacert:
            feed_cacert_tmp = utils.readFile(cacert)
        feed_cert_tmp = None
        if cert:
            feed_cert_tmp = utils.readFile(cert)
        feed_key_tmp = None
        if key:
            feed_key_tmp = utils.readFile(key)
        feed_cert_data = {"ca": feed_cacert_tmp,
                              "cert": feed_cert_tmp,
                              "key": feed_key_tmp}

        # Consumer cert bundle
        consumer_cert_data = None
        cacert = self.opts.consumer_ca
        cert = self.opts.consumer_cert
        key = self.opts.consumer_key
        cons_cacert_tmp = None
        cons_cert_tmp = None
        cons_key_tmp = None
        if cacert:
            cons_cacert_tmp = utils.readFile(cacert)
        if cert:
            cons_cert_tmp = utils.readFile(cert)
        if key:
            cons_key_tmp = utils.readFile(key)
        consumer_cert_data = {"ca": cons_cacert_tmp,
                                  "cert": cons_cert_tmp,
                                  "key": cons_key_tmp}
        groupid = self.opts.groupid
        keylist = self.opts.keys
        if keylist:
            reader = KeyReader()
            keylist = reader.expand(keylist)

        repo = self.repository_api.create(id, name, arch, feed, symlinks,
                                          feed_cert_data=feed_cert_data,
                                          consumer_cert_data=consumer_cert_data,
                                          relative_path=relative_path,
                                          groupid=groupid,
                                          gpgkeys=keylist,
                                          checksum_type=self.opts.checksum_type,
                                          notes=notes, preserve_metadata=preserve_metadata,
                                          content_types=self.opts.content_type)
        print _("Successfully created repository [ %s ]") % repo['id']

class Clone(RepoProgressAction):

    name = "clone"
    description = _('clone a repository')

    def setup_parser(self):
        super(Clone, self).setup_parser()
        self.parser.add_option("--clone_id", dest="clone_id",
                               help=_("id of cloned repo (required)"))
        self.parser.add_option("--clone_name", dest="clone_name",
                               help=_("common repository name for cloned repo"))
        self.parser.add_option("--feed", dest="feed",
                               help=_("feed of cloned_repo: parent/origin/none"))
        self.parser.add_option("--relativepath", dest="relativepath",
                               help=_("relative path where the repository is stored and exposed to clients; this defaults to clone_id if not specified"))
        self.parser.add_option("--groupid", action="append", dest="groupid",
                               help=_("a group to which the repository belongs; this is just a string identifier"))
        self.parser.add_option("--timeout", dest="timeout",
                               help=_("repository clone timeout specified "
                               "in iso8601 duration format "
                               "(P[n]Y[n]M[n]DT[n]H[n]M[n]S)"))
        self.parser.add_option('-F', '--foreground', dest='foreground',
                               action='store_true', default=False,
                               help=_('clone repository in the foreground'))
        self.parser.add_option("-f", "--filter", action="append", dest="filters",
                       help=_("filters to be applied while cloning"))

    def print_clone_finish(self, state, progress):
        self.print_progress(progress)
        current = ""
        current += "Clone: %s\n" % (state.title())
        current += "Item Details: \n"
        current += self.form_progress_item_details(progress["details"])
        if type(progress) == type({}):
            if progress.has_key("num_error") and progress['num_error'] > 0:
                current += _("Warning: %s errors occurred\n" % (progress['num_error']))
            if progress.has_key("error_details"):
                current += self.form_error_details(progress)
        self.write(current, self._previous_progress)
        self._previous_progress = current

    def clone_foreground(self, task):
        print _('You can safely CTRL+C this current command and it will continue')
        try:
            while not task_end(task):
                self.print_progress(task['progress'])
                time.sleep(0.25)
                task = self.task_api.info(task['id'])
        except KeyboardInterrupt:
            print ''
            return
        self.print_clone_finish(task['state'], task['progress'])
        if task['state'] == 'error':
            raise SyncError(task['traceback'][-1])

    def get_task(self):
        id = self.get_required_option('id')
        self.get_repo(id)

        # find if sync in progress for parent repo
        tasks = self.repository_api.sync_list(id)
        running = self.repository_api.running_task(tasks)
        if running is not None:
            print _('Sync for parent repository %s already in progress') % id
            return running

        clone_id = self.get_required_option('clone_id')
        clone_name = self.opts.clone_name or clone_id
        feed = self.opts.feed or 'parent'
        groupid = self.opts.groupid
        timeout = self.opts.timeout
        if timeout is not None:
            try:
                delta = parse_iso8601_duration(timeout)
            except ISO8601Error:
                utils.system_exit(os.EX_USAGE, _('Improperly formatted timeout: %s , see --help') % timeout)
            if not isinstance(delta, timedelta):
                utils.system_exit(os.EX_USAGE, 'Timeout may not contain months or years')
        filters = self.opts.filters or []
        relative_path = self.opts.relativepath

        task = self.repository_api.clone(id, clone_id=clone_id, clone_name=clone_name, feed=feed,
                                relative_path=relative_path, groupid=groupid, timeout=timeout, filters=filters)
        print _('Repository [%s] is being cloned as [%s]' % (id, clone_id))
        return task

    def run(self):
        foreground = self.opts.foreground
        task = self.get_task()
        if not foreground:
            utils.system_exit(os.EX_OK, _('Use "repo status" to check on the progress'))
        self.clone_foreground(task)


class Delete(AdminRepoAction):

    name = "delete"
    description = _('delete a repository')

    def run(self):
        id = self.get_required_option('id')
        self.get_repo(id)
        self.repository_api.delete(id=id)
        print _("Successful deleted repository [ %s ]") % id


class Update(AdminRepoAction):

    name = "update"
    description = _('update a repository')

    def setup_parser(self):
        super(Update, self).setup_parser()
        self.parser.add_option("--name", dest="name",
                               help=_("common repository name"))
        self.parser.add_option("--arch", dest="arch",
                               help=_("package arch the repository should support"))
        self.parser.add_option("--feed", dest="feed",
                               help=_("url feed to populate the repository (repository must be empty to change path component of the url)"))
        self.parser.add_option("--feed_ca", dest="feed_ca",
                               help=_("path location to the feed's ca certificate"))
        self.parser.add_option("--feed_cert", dest="feed_cert",
                               help=_("path location to the feed's entitlement certificate"))
        self.parser.add_option("--feed_key", dest="feed_key",
                               help=_("path location to the feed's entitlement certificate key"))
        self.parser.add_option("--remove_feed_cert", dest="remove_feed_cert", action="store_true",
                               help=_("if specified, the feed certificate information will be removed from this repo"))
        self.parser.add_option("--consumer_ca", dest="consumer_ca",
                               help=_("path location to the ca certificate used to verify consumer requests"))
        self.parser.add_option("--consumer_cert", dest="consumer_cert",
                               help=_("path location to the entitlement certificate consumers will be provided at bind to grant access to this repo"))
        self.parser.add_option("--consumer_key", dest="consumer_key",
                               help=_("path location to the consumer entitlement certificate key"))
        self.parser.add_option("--remove_consumer_cert", dest="remove_consumer_cert", action="store_true",
                               help=_("if specified, the consumer certificate information will be removed from this repo"))
        self.parser.add_option("--addgroup", dest="addgroup",
                               help=_("group id to be added to the repository"))
        self.parser.add_option("--rmgroup", dest="rmgroup",
                               help=_("group id to be removed from the repository"))
        self.parser.add_option("--addkeys", dest="addkeys",
                               help=_("a ',' separated list of directories and/or files containing GPG keys"))
        self.parser.add_option("--rmkeys", dest="rmkeys",
                               help=_("a ',' separated list of GPG key names"))

    def run(self):
        id = self.get_required_option('id')
        delta = {}
        optdict = vars(self.opts)
        feed_cert_bundle = None
        consumer_cert_bundle = None

        for k, v in optdict.items():
            if not v:
                continue
            if k in ('remove_consumer_cert', 'remove_feed_cert'):
                continue
            if k == 'addgroup':
                delta['addgrp'] = v
                continue
            if k == 'rmgroup':
                delta['rmgrp'] = v
                continue
            if k == 'addkeys':
                reader = KeyReader()
                keylist = reader.expand(v)
                delta['addkeys'] = keylist
                continue
            if k == 'rmkeys':
                keylist = v.split(',')
                delta['rmkeys'] = keylist
                continue
            if k in ('feed_ca', 'feed_cert', 'feed_key'):
                f = open(v)
                v = f.read()
                f.close()
                feed_cert_bundle = feed_cert_bundle or {}
                feed_cert_bundle[k[5:]] = v
                continue
            if k in ('consumer_ca', 'consumer_cert', 'consumer_key'):
                f = open(v)
                v = f.read()
                f.close()
                consumer_cert_bundle = consumer_cert_bundle or {}
                consumer_cert_bundle[k[9:]] = v
                continue
            delta[k] = v

        # Certificate argument sanity check
        if optdict['remove_feed_cert'] and feed_cert_bundle:
            print _('remove_feed_cert cannot be specified while updating feed certificate items')
            return

        if optdict['remove_consumer_cert'] and consumer_cert_bundle:
            print _('remove_consumer_cert cannot be specified while updating consumer certificate items')
            return

        # If removing the cert bundle, set it to None in the delta. If updating any element
        # of the bundle, add it to the delta. Otherwise, no mention in the delta will
        # have no change to the cert bundles.
        if optdict['remove_feed_cert']:
            delta['feed_cert_data'] = {'ca' : None, 'cert' : None, 'key' : None}
        elif feed_cert_bundle:
            delta['feed_cert_data'] = feed_cert_bundle

        if optdict['remove_consumer_cert']:
            delta['consumer_cert_data'] = {'ca' : None, 'cert' : None, 'key' : None}
        elif consumer_cert_bundle:
            delta['consumer_cert_data'] = consumer_cert_bundle
        self.repository_api.update(id, delta)
        print _("Successfully updated repository [ %s ]") % id


class Schedule(RepoAction):

    name = 'schedule'
    description = _('manage automatically scheduled syncs')

    def setup_parser(self):
        super(Schedule, self).setup_parser()
        self.parser.add_option('--show', dest='show', action='store_true', default=False,
                               help=_('show existing schedule'))
        self.parser.add_option('--delete', dest='delete', action='store_true', default=False,
                               help=_('delete existing schedule'))
        self.parser.add_option('--set-interval', dest='interval', default=None,
                               help=_('length of time between each run in iso8601 duration format'))
        self.parser.add_option('--set-start', dest='start', default=None,
                               help=_('date and time of the first run in iso8601 combined date and time format, ommitting implies starting immediately'))
        self.parser.add_option('--set-runs', dest='runs', default=None,
                               help=_('number of times to run the scheduled sync, ommitting implies running indefinitely'))
        self.parser.add_option('--skip', dest='skip', acttion='append', default=[],
                               help=_('elements to skip: packages, errata, and/or distribution'))
        self.parser.add_option('--no-skip', dest='no_skip', action='append', default=[],
                               help=_('elements to not skip: packages, errata, and/or distribution'))


    def _new_schedule(self, obj):
        schedule = obj and obj['schedule']
        interval = start = runs = None
        if schedule is not None:
            interval, start, runs = parse_iso8601_interval(schedule)
            interval = interval and format_iso8601_duration(interval)
            start = start and format_iso8601_datetime(start)
            runs = runs and str(runs) # this will skip '0', but that's wrong anyway...
        new_interval = self.opts.interval or interval
        new_start = self.opts.start or start
        new_runs = self.opts.runs or runs
        new_shedule = parse_interval_schedule(new_interval, new_start, new_runs)
        if not isinstance(new_interval, timedelta) and new_start is None:
            msg =_('If interval has months or years, a start date must be specified')
            utils.system_exit(os.EX_USAGE,  msg)
        return new_shedule

    def _new_options(self, obj):
        valid_elements = ('packages', 'errata', 'distribution')
        invalid_elements = set()
        options = obj and obj['options']
        skip = options and options.get('skip', None)
        skip = skip or {}
        for element in self.opts.skip:
            if element not in valid_elements:
                invalid_elements.add(element)
                continue
            skip[element] = 1
        for element in self.opts.no_skip:
            if element not in valid_elements:
                invalid_elements.add(element)
                continue
            skip.pop(element, None)
        if invalid_elements:
            msg = _('Unknown elements for skip/no-skip: %s') % ', '.join(invalid_elements)
            utils.system_exit(os.EX_USAGE, msg)
        return {'skip': skip}

    def run(self):
        repo_id = self.get_required_option('id')

        if self.opts.show:
            obj = self.repository_api.get_sync_schedule(repo_id)
            print_header('Sync Schedule')
            # TODO put together nice output formatting here
            print obj['type'],
            print ':',
            print obj['schedule']
            utils.system_exit(os.EX_OK, '')

        if self.opts.delete:
            self.repository_api.delete_sync_schedule(repo_id)
            utils.system_exit(os.EX_OK, _('Sync schedule for repo [ %(r)s ] removed') % {'r': repo_id})

        schedule_opts = [getattr(self.opts, n) for n in ('interval', 'starts', 'runs')]
        options_opts = [getattr(self.opts, n) for n in ('skip', 'no_skip')]

        if reduce(lambda x,y: x or y, chain(schedule_opts, options_opts)):
            obj = self.repository_api.get_sync_schedule(repo_id)
            new_schedule = self._new_schedule(obj)
            new_options = self._new_options(obj)
            data = {'schedule': new_schedule,
                    'options': new_options}
            self.repository_api.change_sync_schedule(repo_id, data)
            print _('Sync schedule for repo [ %s ] changed to [ %s ]') % (repo_id, new_shedule)
            utils.system_exit(os.EX_OK, '')

        utils.system_exit(os.EX_NOINPUT, _('No options specified, see --help'))


class Sync(RepoProgressAction):

    name = "sync"
    description = _('synchronize data to a repository from its feed')

    def setup_parser(self):
        super(Sync, self).setup_parser()
        self.parser.add_option("--timeout", dest="timeout",
                               help=_("repository sync timeout specified "
                               "in iso8601 duration format "
                               "(P[n]Y[n]M[n]DT[n]H[n]M[n]S)"))
        self.parser.add_option("--no-packages", action="store_true", dest="nopackages",
                               help=_("skip packages from the sync process"))
        self.parser.add_option("--no-errata", action="store_true", dest="noerrata",
                               help=_("skip errata from the sync process"))
        self.parser.add_option("--no-distribution", action="store_true", dest="nodistro",
                               help=_("skip distributions from the sync process"))
        self.parser.add_option('-F', '--foreground', dest='foreground',
                               action='store_true', default=False,
                               help=_('synchronize repository in the foreground'))
        self.parser.add_option("--limit", dest="limit",
                               help=_("limit download bandwidth per thread to value in KB/sec"),
                               default=None)
        self.parser.add_option("--threads", dest="threads",
                               help=_("number of threads to use for downloading content"),
                               default=None)

    def print_sync_finish(self, state, progress):
        self.print_progress(progress)
        current = ""
        current += _('Sync: %s\n') % (state.title())
        if state.title() in ('Finished'):
            if progress \
                    and progress.has_key("num_download") \
                    and progress.has_key("items_total"):
                current += _('%s/%s new items downloaded\n') % \
                    (progress['num_download'], progress['items_total'])
                current += _('%s/%s existing items processed\n') % \
                    ((progress['items_total'] - progress['num_download']), progress['items_total'])
        current += "\nItem Details: \n"
        if progress and progress.has_key("details"):
            current += self.form_progress_item_details(progress["details"])
        if type(progress) == type({}):
            if progress.has_key("num_error") and progress['num_error'] > 0:
                current += _("Warning: %s errors occurred\n" % (progress['num_error']))
            if progress.has_key("error_details"):
                current += self.form_error_details(progress)
        self.write(current, self._previous_progress)
        self._previous_progress = current

    def sync_foreground(self, task):
        print _('You can safely CTRL+C this current command and it will continue')
        try:
            while not task_end(task):
                self.print_progress(task['progress'])
                time.sleep(0.25)
                task = self.task_api.info(task['id'])
        except KeyboardInterrupt:
            print ''
            return
        self.print_sync_finish(task['state'], task['progress'])
        if task['state'] == 'error':
            if task['traceback']:
                utils.system_exit(-1, task['traceback'][-1])

    def get_task(self):
        id = self.get_required_option('id')
        self.get_repo(id)
        tasks = self.repository_api.sync_list(id)
        running = self.repository_api.running_task(tasks)
        if running is not None:
            print _('Sync for repository %s already in progress') % id
            return running
        skip = {}
        if self.opts.nopackages:
            skip['packages'] = 1
            # skip errata as well, no point of errata without pkgs
            skip['errata'] = 1
        if self.opts.noerrata:
            skip['errata'] = 1
        if self.opts.nodistro:
            skip['distribution'] = 1
        timeout = self.opts.timeout
        if timeout is not None:
            try:
                delta = parse_iso8601_duration(timeout)
            except ISO8601Error:
                utils.system_exit(os.EX_USAGE, _('Improperly formatted timeout: %s , see --help') % timeout)
            if not isinstance(delta, timedelta):
                utils.system_exit(os.EX_USAGE, 'Timeout may not contain months or years')
        limit = self.opts.limit
        threads = self.opts.threads
        task = self.repository_api.sync(id, skip, timeout, limit=limit, threads=threads)
        print _('Sync for repository %s started') % id
        return task

    def run(self):
        foreground = self.opts.foreground
        task = self.get_task()
        if not foreground:
            utils.system_exit(os.EX_OK, _('Use "repo status" to check on the progress'))
        self.sync_foreground(task)



class CancelSync(AdminRepoAction):

    name = "cancel_sync"
    description = _('cancel a running sync')

    def run(self):
        id = self.get_required_option('id')
        self.get_repo(id)
        syncs = self.repository_api.sync_list(id)
        task = None
        for task in syncs:
            if task['state'] == 'running':
                break
            if task['state'] == 'waiting' and task['scheduler'] == 'immediate':
                break
        else:
            utils.system_exit(os.EX_OK, _('There is no sync in progress for this repository'))
        taskid = task['id']
        self.task_api.cancel(taskid)
        print _("Sync for repository %s is being canceled") % id


class CancelClone(AdminRepoAction):

    name = "cancel_clone"
    description = _('cancel a running clone')

    def run(self):
        id = self.get_required_option('id')
        self.get_repo(id)
        clones = self.repository_api.clone_list(id)
        if not clones:
            utils.system_exit(os.EX_OK, _('There is no clone in progress for this repository'))
        task = clones[0]
        if task_end(task):
            utils.system_exit(os.EX_OK, _('There is no clone in progress for this repository'))
        taskid = task['id']
        self.task_api.cancel(taskid)
        print _("Clone for this repository %s is being canceled") % id


class GenerateMetadata(AdminRepoAction):

    name = "generate_metadata"
    description =  _('schedule metadata generation for a repository')

    def setup_parser(self):
        super(GenerateMetadata, self).setup_parser()
        self.parser.add_option("--status", action="store_true", dest="status",
                help=_("Check metadata status for a repository (optional)."))

    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        if self.opts.status:
            task = self.repository_api.generate_metadata_status(id)[0]
            start_time = None
            if task['start_time']:
                start_time = str(parse_iso8601_datetime(task['start_time']))
            finish_time = None
            if task['finish_time']:
                finish_time = str(parse_iso8601_datetime(task['finish_time']))
            status = constants.METADATA_STATUS % (task['id'], task['state'], task['exception'], start_time, finish_time)
            utils.system_exit(os.EX_OK, _(status))
        else:
            task = self.repository_api.generate_metadata(id)
            utils.system_exit(os.EX_OK, _('Metadata generation has been successfully scheduled for repo id [%s]. Use --status to check the status.') % id)

class AddMetadata(AdminRepoAction):

    name = "add_metadata"
    description =  _('add a metadata type to an existing repository')

    def setup_parser(self):
        super(AddMetadata, self).setup_parser()
        self.parser.add_option("--mdtype", dest="mdtype",
                help=_("metadata type to add to the repository metadata"))
        self.parser.add_option("--path", dest="path",
                help=_("path to the metadata file to be added"))

    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        if not self.opts.mdtype:
            utils.system_exit(os.EX_USAGE, _("Error: mdtype is a required option"))
        else:
            filetype = self.opts.mdtype
        if not self.opts.path:
            utils.system_exit(os.EX_USAGE, _("Error: path is a required option"))
        else:
            filepath = self.opts.path
        filedata = None
        try:
            filedata = open(filepath, 'r').read()
        except Exception, e:
            utils.system_exit(os.EX_DATAERR, _("Error occurred while reading the metadata file at [%s]" % self.opts.path))
        self.repository_api.add_metadata(id, self.opts.mdtype, filedata)
        utils.system_exit(os.EX_OK, _("Successfully added metadata type [%s] to repo [%s]" % (filetype, id)))

class RemoveMetadata(AdminRepoAction):

    name = "remove_metadata"
    description =  _('remove a metadata type from an existing repository')

    def setup_parser(self):
        super(RemoveMetadata, self).setup_parser()
        self.parser.add_option("--mdtype", dest="mdtype",
                help=_("metadata type to remove from the repository metadata. see `pulp-admin list_metadata` for mdtypes"))

    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        if not self.opts.mdtype:
            utils.system_exit(os.EX_USAGE, _("Error: mdtype is a required option"))
        try:
            self.repository_api.remove_metadata(id, self.opts.mdtype)
            utils.system_exit(os.EX_OK, _("Successfully removed metadata type [%s] from repo [%s]" % (self.opts.mdtype, id)))
        except:
            raise

class DownloadMetadata(AdminRepoAction):

    name = "download_metadata"
    description =  _('download a metadata type if available from an existing repository')

    def setup_parser(self):
        super(DownloadMetadata, self).setup_parser()
        self.parser.add_option("--mdtype", dest="mdtype",
                help=_("metadata type to download from the repository"))
        self.parser.add_option("-o", "--out", dest="out",
                help=_("output file to store the exported metadata file (optional); default is stdout"))

    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        if not self.opts.mdtype:
            utils.system_exit(os.EX_USAGE, _("Error: mdtype is a required option"))
        else:
            filetype = self.opts.mdtype
        try:
            file_stream = self.repository_api.download_metadata(repo['id'], filetype)
        except Exception, e:
            log.error(e)
            utils.system_exit(os.EX_DATAERR, _("Error:%s") % e[1])
        if not file_stream:
            utils.system_exit(os.EX_DATAERR, _("Error:No file data found for file type [%s]") % filetype)
        if self.opts.out:
            try:
                f = open(self.opts.out, 'w')
                f.write(file_stream.encode("utf8"))
                f.close()
            except Exception,e:
                utils.system_exit(os.EX_DATAERR, _("Error occurred while storing the file data %s" % e))
            utils.system_exit(os.EX_OK, _("Successfully exported the metadata type data to [%s]" % self.opts.out))
        else:
            print file_stream.encode("utf8")

class ListMetadata(AdminRepoAction):

    name = "list_metadata"
    description =  _('list metadata type information associated to an existing repository')

    def setup_parser(self):
        super(ListMetadata, self).setup_parser()

    def run(self):
        id = self.get_required_option('id')
        repo = self.get_repo(id)
        filetype_info_dict = self.repository_api.list_metadata(repo['id'])
        if not filetype_info_dict:
            utils.system_exit(os.EX_DATAERR, _('No metadata types to list'))
        print_header(_('Metadata Type information for Respoitory [%s]' % id))
        for filetype, value in filetype_info_dict.items():
            print '  datatype: %s' % filetype
            print '    location     : %s' % value['location']
            print '    timestamp    : %s' % value['timestamp']
            print '    size         : %s' % value['size']
            print '    checksum     : %s - %s' % tuple(value['checksum'])
            print '    dbversion    : %s' % value['dbversion']
            print ''



class Schedules(AdminRepoAction):

    name = "schedules"
    description = _('list all repository schedules')

    def setup_parser(self):
        pass

    def run(self):
        print_header(_('Available Repository Schedules'))
        schedules = self.repository_api.all_schedules()
        for id in schedules.keys():
            print(constants.REPO_SCHEDULES_LIST % (id, schedules[id]))

class ListKeys(AdminRepoAction):

    name = "list_keys"
    description = _('list gpg keys')

    def run(self):
        id = self.get_required_option('id')
        keys = self.repository_api.listkeys(id)
        if not len(keys):
            utils.system_exit(os.EX_OK, _("No GPG keys in this repository"))
        for key in keys:
            print os.path.basename(key)

class Publish(AdminRepoAction):

    name = "publish"
    description = _('enable/disable repository being published by apache')

    def setup_parser(self):
        super(Publish, self).setup_parser()
        self.parser.add_option("--disable", dest="disable", action="store_true",
                default=False, help=_("disable publish for this repository"))
        self.parser.add_option("--enable", dest="enable", action="store_true",
                default=False, help=_("enable publish for this repository"))

    def run(self):
        id = self.get_required_option('id')
        if self.opts.enable and self.opts.disable:
            utils.system_exit(os.EX_USAGE, _("Error: Both enable and disable are set to True"))
        if not self.opts.enable and not self.opts.disable:
            utils.system_exit(os.EX_USAGE, _("Error: Either --enable or --disable needs to be chosen"))
        if self.opts.enable:
            state = True
        if self.opts.disable:
            state = False
        if self.repository_api.update_publish(id, state):
            print _("Repository [%s] 'published' has been set to [%s]") % (id, state)
        else:
            print _("Unable to set 'published' to [%s] on repository [%s]") % (state, id)


class AddPackages(AdminRepoAction):

    name = "add_package"
    description = _('associate an already uploaded package to a repository')

    def setup_parser(self):
        super(AddPackages, self).setup_parser()
        self.parser.add_option("-p", "--package", action="append", dest="pkgname",
                help=_("package filename to associate to this repository"))
        self.parser.add_option("--source", dest="srcrepo",
            help=_("source repository with specified packages (optional)"))
        self.parser.add_option("--csv", dest="csv",
                help=_("csv file to perform batch operations on; Format:filename,checksum"))
        self.parser.add_option("-y", "--assumeyes", action="store_true", dest="assumeyes",
                            help=_("assume yes; automatically process dependencies as part of the operation"))
        self.parser.add_option("-r", "--recursive", action="store_true", dest="recursive",
                            help=_("recursively lookup the dependency list; defaults to one level of lookup"))

    def run(self):
        id = self.get_required_option('id')

        if not self.opts.pkgname and not self.opts.csv:
            utils.system_exit(os.EX_USAGE, _("Error: At least one package id is required to perform an association."))
        if self.opts.pkgname and self.opts.csv:
            utils.system_exit(os.EX_USAGE, _("Error: Both --package and --csv cannot be used in the same command."))
        # check if repos are valid
        self.get_repo(id)
        if self.opts.srcrepo:
            self.get_repo(self.opts.srcrepo)
        # lookup requested pkgs in the source repository
        pnames = []
        pids = []
        if self.opts.csv:
            if not os.path.exists(self.opts.csv):
                utils.system_exit(os.EX_DATAERR, _("CSV file [%s] not found"))
            pkglist = utils.parseCSV(self.opts.csv)
        else:
            pkglist = self.opts.pkgname
        for pkginfo in pkglist:
            if isinstance(pkginfo, list) and len(pkginfo) == 2:
                #default to sha256
                pkg, checksum = pkginfo
            else:
                checksum_type = None
                pkg, checksum = pkginfo, None
            if self.opts.srcrepo:
                src_pkgobj = self.lookup_repo_packages(pkg, self.opts.srcrepo,
                                                       checksum=checksum)
                if not src_pkgobj: # not in src_pkgobjs:
                    print(_("Package %s could not be found skipping" % pkg))
                    continue
            else:
                src_pkgobj = self.service_api.search_packages(filename=pkg, regex=False)
                if not src_pkgobj:
                    print(_("Package %s could not be found skipping" % pkg))
                    continue
                if len(src_pkgobj) > 1:
                    if not self.opts.csv:
                        print _("There is more than one file with filename [%s]. Please use csv option to include checksum.; Skipping associate" % pkg)
                        continue
                    else:
                        for fo in src_pkgobj:
                            if fo['filename'] == pkg and fo['checksum']['sha256'] == checksum:
                                src_pkgobj = fo
                else:
                    src_pkgobj = src_pkgobj[0]
            tgt_pkgobj = self.lookup_repo_packages(pkg, id, checksum=checksum)
            if tgt_pkgobj:
                print (_("Package [%s] are already part of repo [%s]. skipping" % (pkg, id)))
                continue
            name = "%s-%s-%s.%s" % (src_pkgobj['name'], src_pkgobj['version'],
                                    src_pkgobj['release'], src_pkgobj['arch'])
            pnames.append(name)
            pids.append(src_pkgobj['id'])

        if not pnames:
            utils.system_exit(os.EX_DATAERR)
        if self.opts.srcrepo:
            # lookup dependencies and let use decide whether to include them
            pkgdeps = self.handle_dependencies(self.opts.srcrepo, id, pnames, self.opts.recursive, self.opts.assumeyes)
            for pdep in pkgdeps:
                pnames.append("%s-%s-%s.%s" % (pdep['name'], pdep['version'], pdep['release'], pdep['arch']))
                pids.append(pdep['id'])
        else:
            print _("No Source repo specified, skipping dependency lookup")
        errors = {}
        try:
            errors = self.repository_api.add_package(id, pids)
        except Exception:
            utils.system_exit(os.EX_DATAERR, _("Unable to associate package [%s] to repo [%s]" % (pnames, id)))
        if not errors:
            print _("Successfully associated packages %s to repo [%s]. Please run `pulp-admin repo generate_metadata` to update the repository metadata." % (pnames, id))
        else:
            for e in errors:
                # Format, [pkg_id, NEVRA, filename, sha256]
                filename = e[2]
                checksum = e[3]
                print _("Error unable to associate: %s with sha256sum of %s") % (filename, checksum)
            print _("Errors occurred see /var/log/pulp/pulp.log for more info")
            print _("Note: any packages not listed in error output have been associated")
        print _("%s packages associated to repo [%s]") % (len(pids) - len(errors), id)


class RemovePackages(AdminRepoAction):

    name = "remove_package"
    description = _('remove package from the repository')

    def setup_parser(self):
        super(RemovePackages, self).setup_parser()
        self.parser.add_option("-p", "--package", action="append", dest="pkgname",
                help=_("package filename to remove from this repository"))
        self.parser.add_option("--csv", dest="csv",
                help=_("csv file to perform batch operations on; Format:filename,checksum"))
        self.parser.add_option("-y", "--assumeyes", action="store_true", dest="assumeyes",
                            help=_("assume yes; automatically process dependencies as part of remove operation"))
        self.parser.add_option("-r", "--recursive", action="store_true", dest="recursive",
                            help=_("recursively lookup the dependency list; defaults to one level of lookup"))

    def run(self):
        id = self.get_required_option('id')
        if not self.opts.pkgname and not self.opts.csv:
            utils.system_exit(os.EX_USAGE, _("Error: At least one package id is required to perform a remove."))
        if self.opts.pkgname and self.opts.csv:
            utils.system_exit(os.EX_USAGE, _("Error: Both --package and --csv cannot be used in the same command."))
        # check if repo is valid
        self.get_repo(id)
        pnames = []
        pobj = []
        if self.opts.csv:
            if not os.path.exists(self.opts.csv):
                utils.system_exit(os.EX_DATAERR, _("CSV file [%s] not found"))
            pkglist = utils.parseCSV(self.opts.csv)
        else:
            pkglist = self.opts.pkgname
        for pkginfo in pkglist:
            if isinstance(pkginfo, list) and len(pkginfo) == 2:
                pkg, checksum = pkginfo
            else:
                pkg, checksum = pkginfo, None
            src_pkgobj = self.lookup_repo_packages(pkg, id, checksum)
            if not src_pkgobj:
                print(_("Package %s could not be found skipping" % pkg))
                continue
            name = "%s-%s-%s.%s" % (src_pkgobj['name'], src_pkgobj['version'],
                                    src_pkgobj['release'], src_pkgobj['arch'])
            pnames.append(name)
            pobj.append(src_pkgobj)
        if not pnames:
            utils.system_exit(os.EX_DATAERR)
        pkgdeps = self.handle_dependencies(id, None, pnames, self.opts.recursive, self.opts.assumeyes)
        pobj += pkgdeps
        pkg = list(set([p['filename'] for p in pobj]))
        try:
            self.repository_api.remove_package(id, pobj)
            print _("Successfully removed package %s from repo [%s]. Please run `pulp-admin repo generate_metadata` to update the repository metadata." % (pkg, id))
        except Exception:
            print _("Unable to remove package [%s] to repo [%s]" % (pkg, id))


class AddErrata(AdminRepoAction):

    name = "add_errata"
    description = _('associate an existing errata to a repository')

    def setup_parser(self):
        super(AddErrata, self).setup_parser()
        self.parser.add_option("-e", "--errata", action="append", dest="errataid",
                help=_("errata id to associate to this repository"))
        self.parser.add_option("--source", dest="srcrepo",
            help=_("optional source repository with specified packages to perform selective association"))
        self.parser.add_option("-y", "--assumeyes", action="store_true", dest="assumeyes",
                            help=_("assume yes; automatically process dependencies as part of associate operation"))
        self.parser.add_option("-r", "--recursive", action="store_true", dest="recursive",
                            help=_("recursively lookup the dependency list; defaults to one level of lookup"))

    def run(self):
        id = self.get_required_option('id')
        if not self.opts.errataid:
            utils.system_exit(os.EX_USAGE, _("Error: At least one erratum id is required to perform an association."))
        # check if repos are valid
        self.get_repo(id)
        if self.opts.srcrepo:
            self.get_repo(self.opts.srcrepo)
        errataids = self.opts.errataid
        effected_pkgs = []
        for eid in errataids:
            e_repos = self.errata_api.find_repos(eid) or []
            if id in e_repos:
                print(_("Errata Id [%s] is already in target repo [%s]. skipping" % (eid, id)))
                continue
            if self.opts.srcrepo and self.opts.srcrepo not in e_repos:
                print(_("Errata Id [%s] is not in source repo [%s]. skipping" % (eid, self.opts.srcrepo)))
                continue
            erratum = self.errata_api.erratum(eid)
            if not erratum:
                print(_("Errata Id [%s] could not be found. skipping" % eid))
                continue
            effected_pkgs += [str(pinfo['filename'])
                         for pkg in erratum['pkglist']
                         for pinfo in pkg['packages']]


        pkgs = {}
        for pkg in effected_pkgs:
            if self.opts.srcrepo:
                src_pkgobj = self.lookup_repo_packages(pkg, self.opts.srcrepo)
                if not src_pkgobj: # not in src_pkgobjs:
                    log.info("Errata Package %s could not be found in source repo. skipping" % pkg)
                    continue
            else:
                src_pkgobj = self.service_api.search_packages(filename=pkg, regex=False)
                if not src_pkgobj:
                    print(_("Package %s could not be found skipping" % pkg))
                    continue
                src_pkgobj = src_pkgobj[0]
            name = "%s-%s-%s.%s" % (src_pkgobj['name'], src_pkgobj['version'],
                                    src_pkgobj['release'], src_pkgobj['arch'])
            pkgs[name] = src_pkgobj
        if self.opts.srcrepo and len(pkgs.keys()):
            # lookup dependencies and let use decide whether to include them
            pkgdeps = self.handle_dependencies(self.opts.srcrepo, id, pkgs.keys(), self.opts.recursive, self.opts.assumeyes)
            pids = [pdep['id'] for pdep in pkgdeps]
        else:
            pids = [pkg['id'] for pkg in pkgs.values()]
        try:
            self.repository_api.add_errata(id, errataids)
            if pids:
                # add dependencies to repo
                self.repository_api.add_package(id, pids)
            print _("Successfully associated Errata %s to repo [%s]. Please run `pulp-admin repo generate_metadata` to update the repository metadata." % (errataids, id))
        except Exception:
            utils.system_exit(os.EX_DATAERR, _("Unable to associate errata [%s] to repo [%s]" % (errataids, id)))


class RemoveErrata(AdminRepoAction):

    name = "remove_errata"
    description = _('remove errata from the repository')

    def setup_parser(self):
        super(RemoveErrata, self).setup_parser()
        self.parser.add_option("-e", "--errata", action="append", dest="errataid",
                help=_("errata id to delete from this repository"))
        self.parser.add_option("-y", "--assumeyes", action="store_true", dest="assumeyes",
                            help=_("assume yes; automatically process dependencies as part of remove operation"))
        self.parser.add_option("-r", "--recursive", action="store_true", dest="recursive",
                            help=_("recursively lookup the dependency list; defaults to one level of lookup"))

    def run(self):
        id = self.get_required_option('id')
        # check if repo is valid
        self.get_repo(id)
        if not self.opts.errataid:
            utils.system_exit(os.EX_USAGE, _("Error: At least one erratum id is required to perform a remove."))
        errataids = self.opts.errataid
        effected_pkgs = []
        for eid in errataids:
            e_repos = self.errata_api.find_repos(eid)

            if id not in e_repos:
                print(_("Errata Id [%s] is not in the repo [%s]. skipping" % (eid, id)))
                continue
            erratum = self.errata_api.erratum(eid)
            if not erratum:
                print(_("Errata Id [%s] could not be found. skipping" % eid))
                continue
            effected_pkgs += [str(pinfo['filename'])
                         for pkg in erratum['pkglist']
                         for pinfo in pkg['packages']]
        pobj = []
        pnames = []
        for pkg in effected_pkgs:
            src_pkgobj = self.lookup_repo_packages(pkg, id)
            if not src_pkgobj:
                log.info("Package %s could not be found skipping" % pkg)
                continue
            name = "%s-%s-%s.%s" % (src_pkgobj['name'], src_pkgobj['version'],
                                    src_pkgobj['release'], src_pkgobj['arch'])
            pnames.append(name)
            pobj.append(src_pkgobj)
        pkgdeps = []
        if pnames:
            # log.info("Associated Errata packages for id [%s] are not in the repo." % errataids)
            # lookup dependencies and let use decide whether to include them
            pkgdeps = self.handle_dependencies(id, None, pnames, self.opts.recursive, self.opts.assumeyes)
        try:
            self.repository_api.delete_errata(id, errataids)
            if pkgdeps:
                self.repository_api.remove_package(id, pkgdeps)
        except Exception:
            print _("Unable to remove errata [%s] to repo [%s]" % (errataids, id))
        print _("Successfully removed Errata %s from repo [%s]. Please run `pulp-admin repo generate_metadata` to update the repository metadata." % (errataids, id))


class AddFiles(AdminRepoAction):

    name = "add_file"
    description = _('associate an already uploaded file to a repository')

    def setup_parser(self):
        super(AddFiles, self).setup_parser()
        self.parser.add_option("-f", "--filename", action="append", dest="filename",
                help=_("file to associate to this repository"))
        self.parser.add_option("--source", dest="srcrepo",
            help=_("source repository with specified files to perform association (optional)"))
        self.parser.add_option("--csv", dest="csv",
                help=_("csv file to perform batch operations on; Format:filename,checksum"))

    def run(self):
        id = self.get_required_option('id')
        # check if repos are valid
        self.get_repo(id)
        if self.opts.srcrepo:
            self.get_repo(self.opts.srcrepo)
        fids = {}
        if self.opts.filename and self.opts.csv:
            utils.system_exit(os.EX_USAGE, _("Both --filename and --csv cannot be used in the same command."))
        if self.opts.csv:
            if not os.path.exists(self.opts.csv):
                utils.system_exit(os.EX_DATAERR, _("CSV file [%s] not found"))
            flist = utils.parseCSV(self.opts.csv)
        else:
            if not self.opts.filename:
                utils.system_exit(os.EX_USAGE, _("Error: At least one file is required to perform an association."))
            flist = self.opts.filename
        for f in flist:
            if isinstance(f, list) or len(f) == 2:
                filename, checksum = f
                if not len(f) == 2:
                    log.error("Bad format [%s] in csv, skipping" % f)
                    continue
            else:
                filename, checksum = f, None

            fobj = self.service_api.search_file(filename=filename, checksum=checksum)
            if not len(fobj):
                print _("File [%s] could not be found on server; Skipping association" % filename)
                continue
            if len(fobj) > 1:
                if not self.opts.csv:
                    print fobj
                    print _("There is more than one file with filename [%s]. Please use csv option to include checksum.; Skipping association" % filename)
                    continue
                else:
                    for fo in fobj:
                        if fo['filename'] == filename and fo['checksum']['sha256'] == checksum:
                            fids[filename] = fo
            else:
                fids[filename] = fobj[0]

        for fname, fobj in fids.items():
            if self.opts.srcrepo and not self.opts.srcrepo in fobj["repos"]:
                print _("File [%s] Could not be found in the repo [%s]" % (filename, self.opts.srcrepo))
                continue
            try:
                self.repository_api.add_file(id, [fobj['id']])
            except Exception:
                print _("Unable to associate package [%s] to repo [%s]" % (fname, id))
                continue
            print _("Successfully associated packages %s to repo [%s]." % (fname, id))

class RemoveFiles(AdminRepoAction):

    name = "remove_file"
    description = _('remove file from a repository')

    def setup_parser(self):
        super(RemoveFiles, self).setup_parser()
        self.parser.add_option("-f", "--filename", action="append", dest="filename",
                help=_("file to remove from this repository"))
        self.parser.add_option("--csv", dest="csv",
                help=_("csv file to perform batch operations on; Format:filename,checksum"))


    def run(self):
        id = self.get_required_option('id')
        # check if repos are valid
        self.get_repo(id)
        if self.opts.filename and self.opts.csv:
            utils.system_exit(os.EX_USAGE, _("Error: Both --filename and --csv cannot be used in the same command."))

        fids = {}
        if self.opts.csv:
            if not os.path.exists(self.opts.csv):
                utils.system_exit(os.EX_DATAERR, _("CSV file [%s] not found"))
            flist = utils.parseCSV(self.opts.csv)
        else:
            if not self.opts.filename:
                utils.system_exit(os.EX_USAGE, _("Error: At least one file is required to perform a remove."))
            flist = self.opts.filename
        for f in flist:
            if isinstance(f, list) or len(f) == 2:
                filename, checksum = f
                if not len(f) == 2:
                    log.error("Bad format [%s] in csv, skipping" % f)
                    continue
            else:
                filename, checksum = f, None
            fobj = self.service_api.search_file(filename=filename, checksum=checksum)
            if not len(fobj):
                print _("File [%s] could not be found on server; Skipping remove" % filename)
                continue
            if len(fobj) > 1:
                if not self.opts.csv:
                    print fobj
                    print _("There is more than one file with filename [%s]. Please use csv option to include checksum.; Skipping remove" % filename)
                    continue
                else:
                    for fo in fobj:
                        print fo['filename'], checksum
                        if fo['filename'] == filename and fo['checksum']['sha256'] == checksum:
                            fids[filename] = fo['id']
            else:
                fids[filename] = fobj[0]['id']
        for fname, fid in fids.items():
            try:
                self.repository_api.remove_file(id, [fid])
            except Exception:
                utils.system_exit(os.EX_DATAERR, _("Unable to remove file [%s] from repo [%s]" % (fname, id)))
            print _("Successfully removed file [%s] from repo [%s]." % (fname, id))


class AddFilters(AdminRepoAction):

    name = "add_filters"
    description = _('add filters to a repository')

    def setup_parser(self):
        super(AddFilters, self).setup_parser()
        self.parser.add_option("-f", "--filter", action="append", dest="filters",
                       help=_("filter identifiers to be added to the repo (required)"))

    def run(self):
        repoid = self.get_required_option('id')
        if not self.opts.filters:
            utils.system_exit(os.EX_USAGE, _("Error: At least one filter id is required to perform an association."))
        self.repository_api.add_filters(repoid=repoid, filters=self.opts.filters)
        print _("Successfully added filters %s to repository [%s]" % (self.opts.filters, repoid))


class RemoveFilters(AdminRepoAction):

    name = "remove_filters"
    description = _('remove filters from a repository')

    def setup_parser(self):
        super(RemoveFilters, self).setup_parser()
        self.parser.add_option("-f", "--filter", action="append", dest="filters",
                               help=_("list of filter identifiers (required)"))

    def run(self):
        repoid = self.get_required_option('id')
        if not self.opts.filters:
            utils.system_exit(os.EX_USAGE, _("Error: At least one filter id is required to remove an association."))
        self.repository_api.remove_filters(repoid=repoid, filters=self.opts.filters)
        print _("Successfully removed filters %s from repository [%s]") % \
                (self.opts.filters, repoid)

class Discovery(RepoProgressAction):

    name = "discovery"
    description = _('discover and create repositories')
    selected = []

    def setup_parser(self):
        self.parser.add_option("-u", "--url", dest="url",
                               help=_("root url to perform discovery (required)"))
        self.parser.add_option("--ca", dest="ca",
                               help=_("path location to the url ca certificate"))
        self.parser.add_option("--cert", dest="cert",
                               help=_("path location to the url entitlement combined private key and certificate"))
        self.parser.add_option("-g", "--groupid", action="append", dest="groupid",
                               help=_("groupids to associate the discovered repos (optional)"))
        self.parser.add_option("-y", "--assumeyes", action="store_true", dest="assumeyes",
                            help=_("assume yes; automatically create candidate repos for discovered urls (optional)"))
        self.parser.add_option("-t", "--type", dest="type",
                               help=_("content type to look for during discovery(required); supported types: ['yum',]"))

    def print_discovery_progress(self, progress):
        current = ""
        if progress and progress.has_key("num_of_urls"):
            current += _("Number of Urls Discovered (%s): %s\n") % (self.get_wait_symbol(), progress['num_of_urls'])
            self._previous_step = progress["num_of_urls"]
        else:
            current +=  _("Number of Urls Discovered (%s): %s\n") % (self.get_wait_symbol(),0)
            self._previous_step = None
        self.write(current, self._previous_progress)
        self._previous_progress = current

    def run(self):
        success = 0
        url = self.get_required_option('url')
        ctype = self.get_required_option('type')
        # Feed cert bundle
        cacert = self.opts.ca
        cert = self.opts.cert
        cacert_tmp = None
        if cacert:
            cacert_tmp = utils.readFile(cacert)
        cert_tmp = None
        if cert:
            cert_tmp = utils.readFile(cert)
        cert_data = {}
        if cert_tmp or cacert_tmp:
            cert_data = {"ca": cacert_tmp,
                         "cert": cert_tmp,}
        print(_("Discovering urls with yum metadata, This could take some time..."))
        try:
            task = self.service_api.repo_discovery(url, type=ctype, cert_data=cert_data)
        except Exception,e:
            utils.system_exit(os.EX_DATAERR, _("Error: %s" % e[1]))
        print task['progress']
        while not task_end(task):
            self.print_discovery_progress(task['progress'])
            time.sleep(0.25)
            task = self.task_api.info(task['id'])

        repourls = task['result'] or []

        if not len(repourls):
            utils.system_exit(os.EX_OK, "No repos discovered @ url location [%s]" % url)
        print_header(_("Repository Urls discovered @ [%s]" % url))
        assumeyes =  self.opts.assumeyes
        if not assumeyes:
            proceed = ''
            num_selects = [str(i+1) for i in range(len(repourls))]
            select_range_str = constants.SELECTION_QUERY % len(repourls)
            while proceed.strip().lower() not in  ['q', 'y']:
                if not proceed.strip().lower() == 'h':
                    self.__print_urls(repourls)
                proceed = raw_input(_("\nSelect urls for which candidate repos should be created; use `y` to confirm (h for help):"))
                select_val = proceed.strip().lower()
                if select_val == 'h':
                    print select_range_str
                elif select_val == 'a':
                    self.__add_selection(repourls)
                elif select_val in num_selects:
                    self.__add_selection([repourls[int(proceed.strip().lower())-1]])
                elif select_val == 'q':
                    self.selection = []
                    utils.system_exit(os.EX_OK, _("Operation aborted upon user request."))
                elif set(select_val.split(":")).issubset(num_selects):
                    lower, upper = tuple(select_val.split(":"))
                    self.__add_selection(repourls[int(lower)-1:int(upper)])
                elif select_val == 'c':
                    self.selected = []
                elif select_val == 'y':
                    if not len(self.selected):
                        proceed = ''
                        continue
                    else:
                        break
                else:
                    continue
        else:
            #select all
            self.__add_selection( repourls)
            self.__print_urls(repourls)
        # create repos for selected urls
        print _("\nCreating candidate repos for selected urls..")
        for repourl in self.selected:
            try:
                url_str = urlparse.urlparse(repourl)[2].split('/')
                id = '-'.join([s for s in url_str if len(s)]) or None
                if not id:
                    #no valid id formed, continue
                    continue
                repo = self.repository_api.create(id, id, 'noarch',
                                                  groupid=self.opts.groupid or [],
                                                  feed=repourl, feed_cert_data=cert_data,)
                print("Successfully created repo [%s]" % repo['id'])
            except Exception, e:
                success = -1
                print("Error: %s" % e[1])
                log.error("Error creating candidate repos %s" % e[1])
        utils.system_exit(success)

    def __add_selection(self, urls):
        for url in urls:
            if url not in self.selected:
                self.selected.append(url)

    def __print_urls(self, repourls):
        for index, url in enumerate(repourls):
            if url in self.selected:
                print "(+)  [%s] %-5s" % (index+1, url)
            else:
                print "(-)  [%s] %-5s" % (index+1, url)

class Export(RepoProgressAction):

    name = "export"
    description = _('export repository content')

    def setup_parser(self):
        self.parser.add_option( "--id", dest="id",
                               help=_("repository id"))
        self.parser.add_option("-g", "--groupid", dest="groupid",
                               help=_("repository group id to export a group of repos"))
        self.parser.add_option("-t", "--target_dir", dest="target",
                               help=_("target location on server to write the exported content"))
        self.parser.add_option(  "--generate-isos", action="store_true", dest="generate_isos", default=False,
                               help=_("wrap exported content into iso images (optional)"))
        self.parser.add_option(  "--overwrite", action="store_true", dest="overwrite", default=False,
                               help=_("overwrite existing content in target location (optional)"))
        self.parser.add_option('-F', '--foreground', dest='foreground',
                               action='store_true', default=False,
                               help=_('export repository in the foreground'))
        self.parser.add_option(  "--status", action="store_true", dest="status", default=False,
                               help=_("exporter status for given repository (optional)"))
        
    def run(self):
        repoid = self.opts.id
        if self.opts.status:
            if not repoid:
                utils.system_exit(os.EX_USAGE, _("Error: repo id is required to check status of export"))
            self.export_status()
            return
        groupid = self.opts.groupid
        if not repoid and not groupid:
            utils.system_exit(os.EX_USAGE, _("Error: repo id or group id is required to perform an export; see --help"))
        if repoid and groupid:
            utils.system_exit(os.EX_USAGE, _("Error: Cannot specify both repoid and groupid; see --help"))
        if not self.opts.target:
            utils.system_exit(os.EX_USAGE, _("Error: Target location is required to export content; see --help"))
        try:
            if repoid:
                task = self.service_api.repo_export(repoid, self.opts.target, generate_isos=self.opts.generate_isos, overwrite=self.opts.overwrite)
                print(_("Export on repository %s started" % repoid))
                if not self.opts.foreground:
                    utils.system_exit(os.EX_OK, _('Use "repo export --status" to check on the progress'))
                self.export_foreground(task)
            if groupid:
                job = self.service_api.repo_group_export(groupid, self.opts.target, generate_isos=self.opts.generate_isos, overwrite=self.opts.overwrite)
                print(_("Export on repository group [%s] started with job id [%s]" % (groupid, job['id'])))
        except Exception,e:
            utils.system_exit(os.EX_DATAERR, _("Error: %s" % e[1]))

    def export_foreground(self, task):
        print _('You can safely CTRL+C this current command and it will continue')
        print ' '
        try:
            while not task_end(task):
                self.print_exporter_progress(task['progress'])
                time.sleep(0.25)
                task = self.task_api.info(task['id'])
            # print the finish line
            self.print_exporter_progress(task['progress'])
            self.print_error_report(task['progress'])
            print _("Export completed; Content is written to target location @ %s on server" % self.opts.target)
        except KeyboardInterrupt:
            print ''
            return

    def export_status(self):
        id = self.opts.id
        repo = self.get_repo(id)
        export_task = self.repository_api.export_list(id)
        print_header(_('Status for %s') % id)
        print _('Repository: %s') % repo['id']
        self.print_exporter_progress(export_task[0]['progress'])

    def print_exporter_progress(self, progress):
        current = ""
        if progress and progress.has_key("step"):
            current += _("Step: %s (%s)\n") % \
                       (progress['step'], self.get_wait_symbol())
            current += self.form_progress_item_details(progress['details'])
            self._previous_step = progress["num_success"]
        else:
            current +=  _("Step: Export in progress (%s)\n") %  self.get_wait_symbol()
            self._previous_step = None
        self.write(current, self._previous_progress)
        self._previous_progress = current

    def print_error_report(self, progress):
        if not len(progress['errors']):
            return
        #print '\n'.join(progress['errors'])
        print(_("No. of Errors: %s ; See /var/log/pulp/pulp.log for more info." % len(progress['errors'])))

class CancelExport(AdminRepoAction):

    name = "cancel_export"
    description = _('cancel a running export')

    def run(self):
        id = self.get_required_option('id')
        self.get_repo(id)
        exports = self.repository_api.export_list(id)
        if not exports:
            utils.system_exit(os.EX_OK, _('There is no export in progress for this repository'))
        task = exports[0]
        if task_end(task):
            utils.system_exit(os.EX_OK, _('There is no export in progress for this repository'))
        taskid = task['id']
        self.task_api.cancel(taskid)
        print _("Export for repository %s is being canceled") % id

class AddDistribution(AdminRepoAction):

    name = "add_distribution"
    description = _('associate an already existing distribution to a repository')

    def setup_parser(self):
        super(AddDistribution, self).setup_parser()
        self.parser.add_option("-d", "--distributionid", dest="distributionid",
                help=_("distribution to associate to this repository"))
        self.parser.add_option("--source", dest="srcrepo",
            help=_("source repository with specified distributionid to perform association (optional)"))

    def run(self):
        id = self.get_required_option('id')
        # check if repos are valid
        tgt_repo = self.get_repo(id)
        if not self.opts.distributionid:
            utils.system_exit(os.EX_USAGE, _("Error: At least one distribution id is required to perform an association."))
        if self.opts.distributionid in tgt_repo['distributionid']:
            utils.system_exit(os.EX_OK, _("Distribution id [%s] already exists in repo [%s]." % (self.opts.distributionid, id)))
        if self.opts.srcrepo:
            srcrepo = self.get_repo(self.opts.srcrepo)
            if not self.opts.distributionid in srcrepo['distributionid']:
                utils.system_exit(os.EX_DATAERR, _(" distribution id [%s] does not exist in source repo [%s]" % (self.opts.distributionid, id)))
        self.repository_api.add_distribution(id, self.opts.distributionid)
        print _("Successfully associated distribution id %s to repo [%s]." % (self.opts.distributionid, id))

class RemoveDistribution(AdminRepoAction):

    name = "remove_distribution"
    description = _('remove a distribution from a repository')

    def setup_parser(self):
        super(RemoveDistribution, self).setup_parser()
        self.parser.add_option("-d", "--distributionid", dest="distributionid",
                help=_("distributionid to remove from this repository"))

    def run(self):
        id = self.get_required_option('id')
        # check if repos are valid
        repo = self.get_repo(id)
        if self.opts.distributionid not in repo['distributionid']:
            utils.system_exit(os.EX_DATAERR, _("Error: Distribution id [%s] does not exists in repo [%s] to perform a remove" % (self.opts.distributionid, id)))
        if not self.opts.distributionid:
            utils.system_exit(os.EX_USAGE, _("Error: At least one distribution id is required to perform an association."))
        self.repository_api.remove_distribution(id, self.opts.distributionid)
        print _("Successfully removed distribution id %s to repo [%s]." % (self.opts.distributionid, id))

class KeyReader:

    def expand(self, keylist):
        """ expand the list of directories/files and read content """
        if keylist:
            keylist = keylist.split(',')
        else:
            return []
        try:
            paths = []
            for key in keylist:
                if os.path.isdir(key):
                    for fn in os.listdir(key):
                        paths.append(os.path.join(key, fn))
                    continue
                if os.path.isfile(key):
                    paths.append(key)
                    continue
                raise Exception, _('%s must be file/directory') % key
            keylist = []
            for path in paths:
                print _('uploading %s') % path
                f = open(path)
                fn = os.path.basename(path)
                content = f.read()
                keylist.append((fn, content))
                f.close()
            return keylist
        except Exception, e:
            utils.system_exit(os.EX_DATAERR, _(str(e)))


class AddNote(AdminRepoAction):

    name = "add_note"
    description = _('add key-value note to a repository')

    def setup_parser(self):
        super(AddNote, self).setup_parser()
        self.parser.add_option("--key", dest="key",
                               help=_("key identifier (required)"))
        self.parser.add_option("--value", dest="value",
                               help=_("value corresponding to the key (required)"))

    def run(self):
        repoid = self.get_required_option('id')
        key = self.get_required_option('key')
        value = self.get_required_option('value')
        self.repository_api.add_note(repoid, key, value)
        print _("Successfully added key-value pair %s:%s") % (key, value)


class DeleteNote(AdminRepoAction):

    name = "delete_note"
    description = _('delete note from a repository')

    def setup_parser(self):
        super(DeleteNote, self).setup_parser()
        self.parser.add_option("--key", dest="key",
                       help=_("key identifier (required)"))

    def run(self):
        repoid = self.get_required_option('id')
        key = self.get_required_option('key')
        self.repository_api.delete_note(repoid, key)
        print _("Successfully deleted key: %s") % key


class UpdateNote(AdminRepoAction):

    name = "update_note"
    description = _('update a note of a respository')

    def setup_parser(self):
        super(UpdateNote, self).setup_parser()
        self.parser.add_option("--key", dest="key",
                       help=_("key identifier (required)"))
        self.parser.add_option("--value", dest="value",
                       help=_("value corresponding to the key (required)"))

    def run(self):
        repoid = self.get_required_option('id')
        key = self.get_required_option('key')
        value = self.get_required_option('value')
        self.repository_api.update_note(repoid, key, value)
        print _("Successfully updated key-value pair %s:%s") % (key, value)




# repo command ----------------------------------------------------------------

class AdminRepo(Repo):

    name = "repo"
    description = _('repository specific actions to pulp server')

    actions = [ List,
                Status,
                Content,
                Create,
                Clone,
                Delete,
                Update,
                Schedule,
                Sync,
                CancelSync,
                CancelClone,
                ListKeys,
                Publish,
                AddPackages,
                RemovePackages,
                AddErrata,
                RemoveErrata,
                AddFiles,
                RemoveFiles,
                AddFilters,
                RemoveFilters,
                GenerateMetadata,
                AddMetadata,
                ListMetadata,
                DownloadMetadata,
                RemoveMetadata,
                Discovery,
                Export,
                CancelExport,
                AddDistribution,
                RemoveDistribution,
                AddNote,
                DeleteNote,
                UpdateNote,]

# repo plugin ----------------------------------------------------------------

class AdminRepoPlugin(AdminPlugin):

    name = "repo"
    commands = [ AdminRepo ]
