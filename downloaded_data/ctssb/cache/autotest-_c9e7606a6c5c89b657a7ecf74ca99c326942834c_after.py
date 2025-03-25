"""
This module defines the BasePackageManager Class which provides an
implementation of the packaging system API providing methods to fetch,
upload and remove packages. Site specific extensions to any of these methods
should inherit this class.
"""

import fcntl, logging, os, re, shutil
from autotest.client import os_dep
from autotest.client.shared import error, utils
from autotest.client.shared.settings import settings, SettingsError

# the name of the checksum file that stores the packages' checksums
CHECKSUM_FILE = "packages.checksum"


def has_pbzip2():
    '''
    Check if parallel bzip2 is available on this system.

    @return: True if pbzip2 is available, False otherwise
    '''
    try:
        os_dep.command('pbzip2')
    except ValueError:
        return False
    return True


# is parallel bzip2 available for use?
_PBZIP2_AVAILABLE = has_pbzip2()


def parse_ssh_path(repo):
    '''
    Parse an SSH url

    @type repo: string
    @param repo: a repo uri like ssh://xx@xx/path/to/
    @returns: tuple with (host, remote_path)
    '''
    match = re.search('^ssh://([^/]+)(/.*)$', repo)
    if match:
        return match.groups()
    else:
        raise error.PackageUploadError(
            "Incorrect SSH path in settings: %s" % repo)


def repo_run_command(repo, cmd, ignore_status=False, cd=True):
    """
    Run a command relative to the repo path

    This is basically a utils.run() wrapper that sets itself in a repo
    directory if it is appropriate, so parameters such as cmd and ignore_status
    are passed along to it.

    @type repo: string
    @param repo: a repository url
    @type cmd: string
    @param cmd: the command to be executed. This is passed along to utils.run()
    @type ignore_status: boolean
    @param ignore_status: do not raise an exception, no matter what the exit
            code of the command is.
    @type cd: boolean
    @param cd: wether to change the working directory to the repo directory
            before running the specified command.
    @return: a CmdResult object or None
    @raise CmdError: the exit code of the command execution was not 0
    """
    repo = repo.strip()
    run_cmd = None
    cd_str = ''
    if repo.startswith('ssh://'):
        username = None
        hostline, remote_path = parse_ssh_path(repo)
        if cd:
            cd_str = 'cd %s && ' % remote_path
        if '@' in hostline:
            username, host = hostline.split('@')
            run_cmd = 'ssh %s@%s "%s%s"' % (username, host, cd_str, cmd)
        else:
            run_cmd = 'ssh %s "%s%s"' % (hostline, cd_str, cmd)

    else:
        if cd:
            cd_str = 'cd %s && ' % repo
        run_cmd = "%s%s" % (cd_str, cmd)

    if run_cmd:
        return utils.run(run_cmd, ignore_status=ignore_status)


def create_directory(repo):
    '''
    Create a directory over at the remote repository

    @type repo: string
    @param repo: the repo URL containing the remote directory path
    @return: a CmdResult object or None
    '''
    remote_path = repo
    if repo.startswith('ssh://'):
        _, remote_path = parse_ssh_path(repo)
    repo_run_command(repo, 'mkdir -p %s' % remote_path, cd=False)


def check_diskspace(repo, min_free=None):
    '''
    Check if the remote directory over at the pkg repo has available diskspace

    If the amount of free space is not supplied, it is taken from the global
    configuration file, section [PACKAGES], key 'mininum_free_space'. The unit
    used are in SI, that is, 1 GB = 10**9 bytes.

    @type repo: string
    @param repo: a remote package repo URL
    @type min_free: int
    @param: min_free mininum amount of free space, in GB (10**9 bytes)
    @raise error.RepoUnknownError: general repository error condition
    @raise error.RepoDiskFullError: repository does not have at least the
        requested amount of free disk space.
    '''
    if min_free is None:
        min_free = settings.get_value('PACKAGES', 'minimum_free_space',
                                      type=int, default=1)
    try:
        df = repo_run_command(repo,
                              'df -PB %d . | tail -1' % 10 ** 9).stdout.split()
        free_space_gb = int(df[3])
    except Exception, e:
        raise error.RepoUnknownError('Unknown Repo Error: %s' % e)
    if free_space_gb < min_free:
        raise error.RepoDiskFullError('Not enough disk space available '
                                      '%sg < %sg' % (free_space_gb, min_free))


def check_write(repo):
    '''
    Checks that the remote repository directory is writable

    @type repo: string
    @param repo: a remote package repo URL
    @raise error.RepoWriteError: repository write error
    '''
    try:
        repo_testfile = '.repo_test_file'
        repo_run_command(repo, 'touch %s' % repo_testfile).stdout.strip()
        repo_run_command(repo, 'rm ' + repo_testfile)
    except error.CmdError:
        raise error.RepoWriteError('Unable to write to ' + repo)


def trim_custom_directories(repo, older_than_days=None):
    '''
    Remove old files from the remote repo directory

    The age of the files, if not provided by the older_than_days parameter is
    taken from the global configuration file, at section [PACKAGES],
    configuration item 'custom_max_age'.

    @type repo: string
    @param repo: a remote package repo URL
    '''
    if not repo:
        return

    if older_than_days is None:
        older_than_days = settings.get_value('PACKAGES', 'custom_max_age',
                                             type=int, default=40)
    cmd = 'find . -type f -atime +%s -exec rm -f {} \;' % older_than_days
    repo_run_command(repo, cmd, ignore_status=True)


class RepositoryFetcher(object):
    '''
    Base class with common functionality for repository fetchers
    '''


    url = None


    def __init__(self, package_manager, repository_url):
        """
        Initializes a new Repository Fetcher

        @type package_manager: BasePackageManager instance
        @param package_manager: and instance of BasePackageManager class
        @type repository_url: string
        @param repository_url: The base URL of the repository
        """
        self.run_command = package_manager._run_command
        self.url = repository_url
        self.pkgmgr = package_manager


    def install_pkg_setup(self, name, fetch_dir, install):
        """
        Install setup for a package based on fetcher type.

        @type name: string
        @param name:  The filename to be munged
        @type fetch_dir: string
        @param fetch_dir: The destination path to be munged
        @type install: boolean
        @param install: Whether this is be called from the install path or not
        @return: tuple with (name, fetch_dir)
        """
        if install:
            fetch_dir = os.path.join(fetch_dir, re.sub("/", "_", name))

        return (name, fetch_dir)


    def fetch_pkg_file(self, filename, dest_path):
        """
        Fetch a package file from a package repository.

        @type filename: string
        @param filename: The filename of the package file to fetch.
        @type dest_path: string
        @param dest_path: Destination path to download the file to.
        @raises PackageFetchError: if the fetch failed
        """
        raise NotImplementedError()


    def install_pkg_post(self, filename, fetch_dir,
                         install_dir, preserve_install_dir=False):
        """
        Fetcher specific post install

        @type filename: string
        @param filename: The filename of the package to install
        @type fetch_dir: string
        @param fetch_dir: The fetched path of the package
        @type install_dir: string
        @param install_dir: The path to install the package to
        @type preserve_install_dir: boolean
        @preserve_install_dir: Preserve the install directory
        """
        # check to see if the install_dir exists and if it does
        # then check to see if the .checksum file is the latest
        install_dir_exists = False
        try:
            self.pkgmgr._run_command("ls %s" % install_dir)
            install_dir_exists = True
        except (error.CmdError, error.AutoservRunError):
            pass

        fetch_path = os.path.join(fetch_dir, re.sub("/","_",filename))
        if (install_dir_exists and
            not self.pkgmgr.untar_required(fetch_path, install_dir)):
            return

        # untar the package into install_dir and
        # update the checksum in that directory
        if not preserve_install_dir:
            # Make sure we clean up the install_dir
            self.pkgmgr._run_command('rm -rf %s' % install_dir)
        self.pkgmgr._run_command('mkdir -p %s' % install_dir)

        self.pkgmgr.untar_pkg(fetch_path, install_dir)


class HttpFetcher(RepositoryFetcher):
    '''
    Repository Fetcher using HTTP
    '''


    #
    # parameters: url, destination file path
    #
    wget_cmd_pattern = 'wget --connect-timeout=15 -nv %s -O %s'


    def _quick_http_test(self):
        """
        Runs a wget command with a 30s timeout

        This checks that the repository is reachable, and avoids the need to
        wait for a full 10min timeout.
        """
        # just make a temp file to write a test fetch into
        mktemp = 'mktemp -u /tmp/tmp.XXXXXX'
        dest_file_path = self.run_command(mktemp).stdout.strip()

        try:
            # build up a wget command
            http_cmd = self.wget_cmd_pattern % (self.url, dest_file_path)
            try:
                self.run_command(http_cmd, _run_command_dargs={'timeout': 30})
            except Exception, e:
                msg = 'HTTP test failed, unable to contact %s: %s'
                raise error.PackageFetchError(msg % (self.url, e))
        finally:
            self.run_command('rm -rf %s' % dest_file_path)


    def fetch_pkg_file(self, filename, dest_path):
        """
        Fetch a package file from a package repository.

        @type filename: string
        @param filename: The filename of the package file to fetch.
        @type dest_path: string
        @param dest_path: Destination path to download the file to.
        @raises PackageFetchError: if the fetch failed
        """
        logging.info('Fetching %s from %s to %s', filename, self.url,
                     dest_path)

        # do a quick test to verify the repo is reachable
        self._quick_http_test()

        # try to retrieve the package via http
        package_url = os.path.join(self.url, filename)
        try:
            cmd = self.wget_cmd_pattern % (package_url, dest_path)
            result = self.run_command(cmd)

            file_exists = self.run_command(
                'ls %s' % dest_path,
                _run_command_dargs={'ignore_status': True}).exit_status == 0
            if not file_exists:
                logging.error('wget failed: %s', result)
                raise error.CmdError(cmd, result)

            logging.debug('Successfully fetched %s from %s', filename,
                          package_url)
        except error.CmdError:
            # remove whatever junk was retrieved when the get failed
            self.run_command('rm -f %s' % dest_path)

            raise error.PackageFetchError('%s not found in %s' % (filename,
                                                                  package_url))


class GitFetcher(RepositoryFetcher):
    """
    A git based repository fetcher
    """


    #
    # parameters: url, destination file path, <branch>:<file name>
    #
    git_archive_cmd_pattern = 'git archive --remote=%s -o %s %s'


    def __init__(self, package_manager, repository_url):
        """
        Initializes a new GitFetcher

        @type package_manager: BasePackageManager class
        @param package_manager: and instance of BasePackageManager class
        @type repository_url: string
        @param repository_url: The base URL of the git repository
        """
        super(GitFetcher, self).__init__(package_manager, repository_url)
        self._set_repo_url_branch(repository_url)
        logging.debug('GitFetcher initialized with repo=%s and branch=%s',
                      self.url, self.branch)


    def _set_repo_url_branch(self, repository_url):
        '''
        Parse the url, look for a branch and set it accordingly

        @type repository_url: string
        @param repository_url: The base URL of the git repository
        '''
        #do we have branch info in the repoistory_url?
        branch = "master"
        match = repository_url.split(":")
        if len(match) > 2:
            #we have a branch
            branch = match[2]
            repository_url = re.sub(":" + branch, "", repository_url)
        self.branch = branch


    def fetch_pkg_file(self, filename, dest_path):
        """
        Fetch a package file and save it to the given destination path

        git is an SCM, you can download the test directly.  No need to fetch
        a bz2'd tarball file.  However 'filename' is <type>-<name>.tar.bz2
        break this up and only fetch <name>.

        @type filename: string
        @param filename: The filename of the package file to fetch.
        @type dest_path: string
        @param dest_path: Destination path to download the file to.
        """
        logging.info('Fetching %s from %s to %s', filename, self.url,
                     dest_path)
        name, _ = self.pkgmgr.parse_tarball_name(filename)
        package_path = self.branch + " " + name
        try:
            cmd = self.git_archive_cmd_pattern % (self.url, dest_path, package_path)
            result = self.run_command(cmd)

            file_exists = self.run_command(
                'ls %s' % dest_path,
                _run_command_dargs={'ignore_status': True}).exit_status == 0
            if not file_exists:
                logging.error('git archive failed: %s', result)
                raise error.CmdError(cmd, result)

            logging.debug('Successfully fetched %s from %s', package_path,
                          self.url)
        except error.CmdError:
            raise error.PackageFetchError('%s not found in %s' % (name,
                                                                  package_path))


    def install_pkg_post(self, filename, fetch_dir, install_dir,
                         preserve_install_dir=False):
        filename, _ = self.pkgmgr.parse_tarball_name(filename)
        install_path = re.sub(filename, "", install_dir)
        for suffix in ['', '.tar', '.tar.bz2']:
            pkg_name = "%s%s" % (suffix, re.sub("/","_", filename))
            fetch_path = os.path.join(fetch_dir, pkg_name)
            if os.path.exists(fetch_path):
                self.pkgmgr._run_command('tar -xf %s -C %s' % (fetch_path,
                                                               install_path))


class LocalFilesystemFetcher(RepositoryFetcher):
    def fetch_pkg_file(self, filename, dest_path):
        logging.info('Fetching %s from %s to %s', filename, self.url,
                     dest_path)
        local_path = os.path.join(self.url, filename)
        try:
            self.run_command('cp %s %s' % (local_path, dest_path))
            logging.debug('Successfully fetched %s from %s', filename,
                          local_path)
        except error.CmdError, e:
            raise error.PackageFetchError(
                'Package %s could not be fetched from %s'
                % (filename, self.url), e)


class BasePackageManager(object):
    def __init__(self, pkgmgr_dir, hostname=None, repo_urls=None,
                 upload_paths=None, do_locking=True, run_function=utils.run,
                 run_function_args=[], run_function_dargs={}):
        '''
        Initializes a new BasePackageManager instance

        One of most used interfaces on this class is the _run_command(), which
        is controlled by the run_function parameter. It defaults to utils.run()
        but a custom method (if provided) should be of the same schema as
        utils.run. It should return a CmdResult object and throw a CmdError
        exception. The reason for using a separate function to run the commands
        is that the same code can be run to fetch a package on the local
        machine or on a remote machine (in which case ssh_host's run function
        is passed in for run_function).

        @type pkgmgr_dir: string
        @param pkgmgr_dir: A directory that can be used by the package manager
                 to dump stuff (like checksum files of the repositories etc)
        @type hostname: string
        @param hostname: hostname from where to fetch a list of package repos
        @type repo_urls: list of strings
        @param repo_urls: The list of the repository urls which is consulted
                 whilst fetching the package
        @type upload_paths: list of strings
        @param upload_paths: The list of the upload of repositories to which
                 the package is uploaded to
        @type do_locking: boolean
        @param do_locking: Enable locking when the packages are installed.
        @type run_function: function
        @param run_function: function used to execute commands.
        @type run_function_args: tuple
        @param run_function_args: positional (tuple-like) arguments to
                 run_function
        @param run_function_dargs: dictionary
        @param run_function_dargs: named (dictionary-like) arguments to
                 run_function
        '''
        # In memory dictionary that stores the checksum's of packages
        self._checksum_dict = {}

        self.pkgmgr_dir = pkgmgr_dir
        self.do_locking = do_locking
        self.hostname = hostname
        self.repositories = []

        # Create an internal function that is a simple wrapper of
        # run_function and takes in the args and dargs as arguments
        def _run_command(command, _run_command_args=run_function_args,
                         _run_command_dargs={}):
            '''
            Special internal function that takes in a command as
            argument and passes it on to run_function (if specified).
            The _run_command_dargs are merged into run_function_dargs
            with the former having more precedence than the latter.
            '''
            new_dargs = dict(run_function_dargs)
            new_dargs.update(_run_command_dargs)
            # avoid polluting logs with extremely verbose packaging output
            new_dargs.update({'stdout_tee' : None})

            return run_function(command, *_run_command_args,
                                **new_dargs)

        self._run_command = _run_command

        # Process the repository URLs
        if not repo_urls:
            repo_urls = []
        elif hostname:
            repo_urls = self.get_mirror_list(repo_urls)
        for url in repo_urls:
            self.add_repository(url)

        # Process the upload URLs
        if not upload_paths:
            self.upload_paths = []
        else:
            self.upload_paths = list(upload_paths)


    def add_repository(self, repo):
        if isinstance(repo, basestring):
            self.repositories.append(self.get_fetcher(repo))
        elif isinstance(repo, RepositoryFetcher):
            self.repositories.append(repo)
        else:
            raise TypeError("repo must be RepositoryFetcher or url string")


    def get_fetcher(self, url):
        if url.startswith('http://'):
            return HttpFetcher(self, url)
        elif url.startswith('git://'):
            return GitFetcher(self, url)
        else:
            return LocalFilesystemFetcher(self, url)


    def repo_check(self, repo):
        '''
        Check to make sure the repo is in a sane state:
        ensure we have at least XX amount of free space
        Make sure we can write to the repo
        '''
        if not repo.startswith('/') and not repo.startswith('ssh:'):
            return
        try:
            create_directory(repo)
            check_diskspace(repo)
            check_write(repo)
        except (error.RepoWriteError, error.RepoUnknownError,
                error.RepoDiskFullError), e:
            raise error.RepoError("ERROR: Repo %s: %s" % (repo, e))


    def upkeep(self, custom_repos=None):
        '''
        Clean up custom upload/download areas
        '''
        from autotest.server import subcommand
        if not custom_repos:
            # Not all package types necessarily require or allow custom repos
            try:
                custom_repos = settings.get_value('PACKAGES',
                                            'custom_upload_location').split(',')
            except SettingsError:
                custom_repos = []
            try:
                custom_download = settings.get_value('PACKAGES',
                                                     'custom_download_location')
                custom_repos += [custom_download]
            except SettingsError:
                pass

            if not custom_repos:
                return

        subcommand.parallel_simple(trim_custom_directories, custom_repos,
                                   log=False)


    def install_pkg(self, name, pkg_type, fetch_dir, install_dir,
                    preserve_install_dir=False, repo_url=None):
        '''
        Remove install_dir if it already exists and then recreate it unless
        preserve_install_dir is specified as True.
        Fetch the package into the pkg_dir. Untar the package into install_dir
        The assumption is that packages are of the form :
        <pkg_type>.<pkg_name>.tar.bz2
        name        : name of the package
        type        : type of the package
        fetch_dir   : The directory into which the package tarball will be
                      fetched to.
        install_dir : the directory where the package files will be untarred to
        repo_url    : the url of the repository to fetch the package from.
        '''

        # do_locking flag is on by default unless you disable it (typically
        # in the cases where packages are directly installed from the server
        # onto the client in which case fcntl stuff wont work as the code
        # will run on the server in that case..
        if self.do_locking:
            lockfile_name = '.%s-%s-lock' % (re.sub("/","_",name), pkg_type)
            lockfile = open(os.path.join(self.pkgmgr_dir, lockfile_name), 'w')

        try:
            if self.do_locking:
                fcntl.flock(lockfile, fcntl.LOCK_EX)

            self._run_command('mkdir -p %s' % fetch_dir)
            pkg_name = self.get_tarball_name(name, pkg_type)
            try:
                # Fetch the package into fetch_dir
                fetcher = self.fetch_pkg(pkg_name, fetch_dir, use_checksum=True,
                                         repo_url=repo_url, install=True)

                fetcher.install_pkg_post(pkg_name, fetch_dir, install_dir, preserve_install_dir)
            except error.PackageFetchError, why:
                raise error.PackageInstallError(
                    'Installation of %s(type:%s) failed : %s'
                    % (name, pkg_type, why))
        finally:
            if self.do_locking:
                fcntl.flock(lockfile, fcntl.LOCK_UN)
                lockfile.close()


    def fetch_pkg(self, pkg_name, dest_path, repo_url=None, use_checksum=False, install=False):
        '''
        Fetch the package into dest_dir from repo_url. By default repo_url
        is None and the package is looked in all the repositories specified.
        Otherwise it fetches it from the specific repo_url.
        pkg_name     : name of the package (ex: test-sleeptest.tar.bz2,
                                            dep-gcc.tar.bz2, kernel.1-1.rpm)
        repo_url     : the URL of the repository where the package is located.
        dest_path    : complete path of where the package will be fetched to.
        use_checksum : This is set to False to fetch the packages.checksum file
                       so that the checksum comparison is bypassed for the
                       checksum file itself. This is used internally by the
                       packaging system. It should be ignored by externals
                       callers of this method who use it fetch custom packages.
        install      : install path has unique name and destination requirements
                       that vary based on the fetcher that is used.  So call them
                       here as opposed to install_pkg.
        '''

        try:
            self._run_command("ls %s" % os.path.dirname(dest_path))
        except (error.CmdError, error.AutoservRunError):
            raise error.PackageFetchError("Please provide a valid "
                                          "destination: %s " % dest_path)

        # See if the package was already fetched earlier, if so
        # the checksums need to be compared and the package is now
        # fetched only if they differ.
        pkg_exists = False
        try:
            self._run_command("ls %s" % dest_path)
            pkg_exists = True
        except (error.CmdError, error.AutoservRunError):
            pass

        # if a repository location is explicitly provided, fetch the package
        # from there and return
        if repo_url:
            repositories = [self.get_fetcher(repo_url)]
        elif self.repositories:
            repositories = self.repositories
        else:
            raise error.PackageFetchError("No repository urls specified")

        # install the package from the package repos, try the repos in
        # reverse order, assuming that the 'newest' repos are most desirable
        for fetcher in reversed(repositories):
            try:
                if isinstance(fetcher, GitFetcher):
                    use_checksum  = False
                # different fetchers have different install requirements
                dest = fetcher.install_pkg_setup(pkg_name, dest_path, install)[1]

                # Fetch the package if it is not there, the checksum does
                # not match, or checksums are disabled entirely
                need_to_fetch = (
                        not use_checksum or not pkg_exists
                        or not self.compare_checksum(dest, fetcher.url))
                if need_to_fetch:
                    fetcher.fetch_pkg_file(pkg_name, dest)
                    # update checksum so we won't refetch next time.
                    if use_checksum:
                        self.update_checksum(dest)
                return fetcher
            except (error.PackageFetchError, error.AutoservRunError):
                # The package could not be found in this repo, continue looking
                logging.debug('%s could not be fetched from %s', pkg_name,
                              fetcher.url)

        repo_url_list = [repo.url for repo in repositories]
        message = ('%s could not be fetched from any of the repos %s' %
                   (pkg_name, repo_url_list))
        logging.error(message)
        # if we got here then that means the package is not found
        # in any of the repositories.
        raise error.PackageFetchError(message)


    def upload_pkg(self, pkg_path, upload_path=None, update_checksum=False,
                   timeout=300):
        from autotest.server import subcommand
        if upload_path:
            upload_path_list = [upload_path]
            self.upkeep(upload_path_list)
        elif len(self.upload_paths) > 0:
            self.upkeep()
            upload_path_list = self.upload_paths
        else:
            raise error.PackageUploadError("Invalid Upload Path specified")

        if update_checksum:
            # get the packages' checksum file and update it with the current
            # package's checksum
            self.update_checksum(pkg_path)

        commands = []
        for path in upload_path_list:
            commands.append(subcommand.subcommand(self.upload_pkg_parallel,
                                                  (pkg_path, path,
                                                   update_checksum)))

        results = subcommand.parallel(commands, timeout, return_results=True)
        for result in results:
            if result:
                print str(result)


    # TODO(aganti): Fix the bug with the current checksum logic where
    # packages' checksums that are not present consistently in all the
    # repositories are not handled properly. This is a corner case though
    # but the ideal solution is to make the checksum file repository specific
    # and then maintain it.
    def upload_pkg_parallel(self, pkg_path, upload_path, update_checksum=False):
        '''
        Uploads to a specified upload_path or to all the repos.
        Also uploads the checksum file to all the repos.
        pkg_path        : The complete path to the package file
        upload_path     : the absolute path where the files are copied to.
                          if set to 'None' assumes 'all' repos
        update_checksum : If set to False, the checksum file is not
                          going to be updated which happens by default.
                          This is necessary for custom
                          packages (like custom kernels and custom tests)
                          that get uploaded which do not need to be part of
                          the checksum file and bloat it.
        '''
        self.repo_check(upload_path)
        # upload the package
        if os.path.isdir(pkg_path):
            self.upload_pkg_dir(pkg_path, upload_path)
        else:
            self.upload_pkg_file(pkg_path, upload_path)
            if update_checksum:
                self.upload_pkg_file(self._get_checksum_file_path(),
                                     upload_path)


    def upload_pkg_file(self, file_path, upload_path):
        '''
        Upload a single file. Depending on the upload path, the appropriate
        method for that protocol is called. Currently this simply copies the
        file to the target directory (but can be extended for other protocols)
        This assumes that the web server is running on the same machine where
        the method is being called from. The upload_path's files are
        basically served by that web server.
        '''
        try:
            if upload_path.startswith('ssh://'):
                # parse ssh://user@host[autotest_top_path]/packages
                hostline, remote_path = parse_ssh_path(upload_path)
                try:
                    utils.run('scp %s %s:%s' % (file_path, hostline,
                                                remote_path))
                    r_path = os.path.join(remote_path,
                                          os.path.basename(file_path))
                    utils.run("ssh %s 'chmod 644 %s'" % (hostline, r_path))
                except error.CmdError:
                    logging.error("Error uploading to repository %s",
                                  upload_path)
            else:
                shutil.copy(file_path, upload_path)
                os.chmod(os.path.join(upload_path,
                                      os.path.basename(file_path)), 0644)
        except (IOError, os.error), why:
            logging.error("Upload of %s to %s failed: %s", file_path,
                          upload_path, why)


    def upload_pkg_dir(self, dir_path, upload_path):
        '''
        Upload a full directory. Depending on the upload path, the appropriate
        method for that protocol is called. Currently this copies the whole
        tmp package directory to the target directory.
        This assumes that the web server is running on the same machine where
        the method is being called from. The upload_path's files are
        basically served by that web server.
        '''
        local_path = os.path.join(dir_path, "*")
        try:
            if upload_path.startswith('ssh://'):
                hostline, remote_path = parse_ssh_path(upload_path)
                try:
                    utils.run('scp %s %s:%s' % (local_path, hostline,
                                                remote_path))
                    ssh_path = os.path.join(remote_path, "*")
                    utils.run("ssh %s 'chmod 644 %s'" % (hostline, ssh_path))
                except error.CmdError:
                    logging.error("Error uploading to repository: %s",
                                  upload_path)
            else:
                utils.run("cp %s %s " % (local_path, upload_path))
                up_path = os.path.join(upload_path, "*")
                utils.run("chmod 644 %s" % up_path)
        except (IOError, os.error), why:
            raise error.PackageUploadError("Upload of %s to %s failed: %s"
                                           % (dir_path, upload_path, why))


    def remove_pkg(self, pkg_name, remove_path=None, remove_checksum=False):
        '''
        Remove the package from the specified remove_path
        pkg_name    : name of the package (ex: test-sleeptest.tar.bz2,
                                           dep-gcc.tar.bz2)
        remove_path : the location to remove the package from.

        '''
        if remove_path:
            remove_path_list = [remove_path]
        elif len(self.upload_paths) > 0:
            remove_path_list = self.upload_paths
        else:
            raise error.PackageRemoveError(
                "Invalid path to remove the pkg from")

        checksum_path = self._get_checksum_file_path()

        if remove_checksum:
            self.remove_checksum(pkg_name)

        # remove the package and upload the checksum file to the repos
        for path in remove_path_list:
            self.remove_pkg_file(pkg_name, path)
            self.upload_pkg_file(checksum_path, path)


    def remove_pkg_file(self, filename, pkg_dir):
        '''
        Remove the file named filename from pkg_dir
        '''
        try:
            # Remove the file
            if pkg_dir.startswith('ssh://'):
                hostline, remote_path = parse_ssh_path(pkg_dir)
                path = os.path.join(remote_path, filename)
                utils.run("ssh %s 'rm -rf %s/%s'" % (hostline, remote_path,
                          path))
            else:
                os.remove(os.path.join(pkg_dir, filename))
        except (IOError, os.error), why:
            raise error.PackageRemoveError("Could not remove %s from %s: %s "
                                           % (filename, pkg_dir, why))


    def get_mirror_list(self, repo_urls):
        '''
            Stub function for site specific mirrors.

            Returns:
                Priority ordered list
        '''
        return repo_urls


    def _get_checksum_file_path(self):
        '''
        Return the complete path of the checksum file (assumed to be stored
        in self.pkgmgr_dir
        '''
        return os.path.join(self.pkgmgr_dir, CHECKSUM_FILE)


    def _get_checksum_dict(self):
        '''
        Fetch the checksum file if not already fetched. If the checksum file
        cannot be fetched from the repos then a new file is created with
        the current package's (specified in pkg_path) checksum value in it.
        Populate the local checksum dictionary with the values read from
        the checksum file.
        The checksum file is assumed to be present in self.pkgmgr_dir
        '''
        checksum_path = self._get_checksum_file_path()
        if not self._checksum_dict:
            # Fetch the checksum file
            try:
                try:
                    self._run_command("ls %s" % checksum_path)
                except (error.CmdError, error.AutoservRunError):
                    # The packages checksum file does not exist locally.
                    # See if it is present in the repositories.
                    self.fetch_pkg(CHECKSUM_FILE, checksum_path)
            except error.PackageFetchError:
                # This should not happen whilst fetching a package..if a
                # package is present in the repository, the corresponding
                # checksum file should also be automatically present. This
                # case happens only when a package
                # is being uploaded and if it is the first package to be
                # uploaded to the repos (hence no checksum file created yet)
                # Return an empty dictionary in that case
                return {}

            # Read the checksum file into memory
            checksum_file_contents = self._run_command('cat '
                                                       + checksum_path).stdout

            # Return {} if we have an empty checksum file present
            if not checksum_file_contents.strip():
                return {}

            # Parse the checksum file contents into self._checksum_dict
            for line in checksum_file_contents.splitlines():
                checksum, package_name = line.split(None, 1)
                self._checksum_dict[package_name] = checksum

        return self._checksum_dict


    def _save_checksum_dict(self, checksum_dict):
        '''
        Save the checksum dictionary onto the checksum file. Update the
        local _checksum_dict variable with this new set of values.
        checksum_dict :  New checksum dictionary
        checksum_dir  :  The directory in which to store the checksum file to.
        '''
        checksum_path = self._get_checksum_file_path()
        self._checksum_dict = checksum_dict.copy()
        checksum_contents = '\n'.join(checksum + ' ' + pkg_name
                                      for pkg_name, checksum in
                                      checksum_dict.iteritems())
        # Write the checksum file back to disk
        self._run_command('echo "%s" > %s' % (checksum_contents,
                                              checksum_path),
                          _run_command_dargs={'verbose': False})


    def compute_checksum(self, pkg_path):
        '''
        Compute the MD5 checksum for the package file and return it.
        pkg_path : The complete path for the package file
        '''
        md5sum_output = self._run_command("md5sum %s " % pkg_path).stdout
        return md5sum_output.split()[0]


    def update_checksum(self, pkg_path):
        '''
        Update the checksum of the package in the packages' checksum
        file. This method is called whenever a package is fetched just
        to be sure that the checksums in the local file are the latest.
        pkg_path : The complete path to the package file.
        '''
        # Compute the new checksum
        new_checksum = self.compute_checksum(pkg_path)
        checksum_dict = self._get_checksum_dict()
        checksum_dict[os.path.basename(pkg_path)] = new_checksum
        self._save_checksum_dict(checksum_dict)


    def remove_checksum(self, pkg_name):
        '''
        Remove the checksum of the package from the packages checksum file.
        This method is called whenever a package is removed from the
        repositories in order clean its corresponding checksum.
        pkg_name :  The name of the package to be removed
        '''
        checksum_dict = self._get_checksum_dict()
        if pkg_name in checksum_dict:
            del checksum_dict[pkg_name]
        self._save_checksum_dict(checksum_dict)


    def compare_checksum(self, pkg_path, repo_url):
        '''
        Calculate the checksum of the file specified in pkg_path and
        compare it with the checksum in the checksum file
        Return True if both match else return False.
        pkg_path : The full path to the package file for which the
                   checksum is being compared
        repo_url : The URL to fetch the checksum from
        '''
        checksum_dict = self._get_checksum_dict()
        package_name = os.path.basename(pkg_path)
        if not checksum_dict or package_name not in checksum_dict:
            return False

        repository_checksum = checksum_dict[package_name]
        local_checksum = self.compute_checksum(pkg_path)
        return (local_checksum == repository_checksum)


    def tar_package(self, pkg_name, src_dir, dest_dir, include_string=None,
                    exclude_string=None):
        '''
        Create a tar.bz2 file with the name 'pkg_name' say test-blah.tar.bz2.

        Includes the files specified in include_string, and excludes the files
        specified on the exclude string, while tarring the source. Returns the
        destination tarball path.

        @param pkg_name: Package name.
        @param src_dir: Directory that contains the data to be packaged.
        @param dest_dir: Directory that will hold the destination tarball.
        @param include_string: Pattern that represents the files that will be
                added to the tar package.
        @param exclude_string: Pattern that represents the files that should be
                excluded from the tar package. It could be either a string or
                a list.
        '''
        tarball_path = os.path.join(dest_dir, pkg_name)
        temp_path = tarball_path + '.tmp'
        cmd_list = ['tar', '-cf', temp_path, '-C', src_dir]
        if _PBZIP2_AVAILABLE:
            cmd_list.append('--use-compress-prog=pbzip2')
        else:
            cmd_list.append('-j')
        if include_string is not None:
            cmd_list.append(include_string)
        if exclude_string is not None:
            if isinstance(exclude_string, list):
                for exc_str in exclude_string:
                    cmd_list.append('--exclude %s' % exc_str)
            else:
                if not "--exclude" in exclude_string:
                    cmd_list.append('--exclude')
                cmd_list.append(exclude_string)

        try:
            utils.system(' '.join(cmd_list))
        except Exception:
            os.unlink(temp_path)
            raise

        os.rename(temp_path, tarball_path)
        return tarball_path


    def untar_required(self, tarball_path, dest_dir):
        '''
        Compare the checksum of the tarball_path with the .checksum file
        in the dest_dir and return False if it matches. The untar
        of the package happens only if the checksums do not match.
        '''
        checksum_path = os.path.join(dest_dir, '.checksum')
        try:
            existing_checksum = self._run_command('cat ' + checksum_path).stdout
        except (error.CmdError, error.AutoservRunError):
            # If the .checksum file is not present (generally, this should
            # not be the case) then return True so that the untar happens
            return True

        new_checksum = self.compute_checksum(tarball_path)
        return (new_checksum.strip() != existing_checksum.strip())


    def untar_pkg(self, tarball_path, dest_dir):
        '''
        Untar the package present in the tarball_path and put a
        ".checksum" file in the dest_dir containing the checksum
        of the tarball. This method
        assumes that the package to be untarred is of the form
        <name>.tar.bz2
        '''
        self._run_command('tar xjf %s -C %s' % (tarball_path, dest_dir))
        # Put the .checksum file in the install_dir to note
        # where the package came from
        pkg_checksum = self.compute_checksum(tarball_path)
        pkg_checksum_path = os.path.join(dest_dir,
                                         '.checksum')
        self._run_command('echo "%s" > %s '
                          % (pkg_checksum, pkg_checksum_path))


    @staticmethod
    def get_tarball_name(name, pkg_type):
        """
        Converts a package name and type into a tarball name.

        @param name: The name of the package
        @param pkg_type: The type of the package

        @returns A tarball filename for that specific type of package
        """
        assert '-' not in pkg_type
        return '%s-%s.tar.bz2' % (pkg_type, name)


    @staticmethod
    def parse_tarball_name(tarball_name):
        """Coverts a package tarball name into a package name and type.

        @param tarball_name: The filename of the tarball

        @returns (name, pkg_type) where name is the package name and pkg_type
            is the package type.
        """
        match = re.search(r'^([^-]*)-(.*)\.tar\.bz2$', tarball_name)
        pkg_type, name = match.groups()
        return name, pkg_type


    def get_package_name(self, url, pkg_type):
        '''
        Extract the group and test name for the url. This method is currently
        used only for tests.
        '''
        if pkg_type == 'test':
            regex = '[^:]+://(.*)/([^/]*)$'
            return self._get_package_name(url, regex)
        else:
            return ('', url)


    def _get_package_name(self, url, regex):
        if not utils.is_url(url):
            if url.endswith('.tar.bz2'):
                testname = url.replace('.tar.bz2', '')
                testname = re.sub(r'(\d*)\.', '', testname)
                return (testname, testname)
            else:
                return ('', url)

        match = re.match(regex, url)
        if not match:
            return ('', url)
        group, filename = match.groups()
        # Generate the group prefix.
        group = re.sub(r'\W', '_', group)
        # Drop the extension to get the raw test name.
        testname = re.sub(r'\.tar\.bz2', '', filename)
        # Drop any random numbers at the end of the test name if any
        testname = re.sub(r'\.(\d*)', '', testname)
        return (group, testname)
