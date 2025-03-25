# -*- coding: utf8 -*-

from __future__ import absolute_import
import base64
import os
import subprocess
import commonware.log


log = commonware.log.getLogger('pontoon')


class PullFromRepositoryException(Exception):
    pass


class PullFromRepository(object):

    def __init__(self, source, target):
        self.source = source
        self.target = target

    def pull(self, source=None, target=None):
        raise NotImplementedError


class PullFromGit(PullFromRepository):

    def pull(self, source=None, target=None):
        log.debug("Git: Update repository.")

        source = source or self.source
        target = target or self.target

        command = ["git", "fetch", "--all"]
        execute(command, target)

        # Undo local changes
        command = ["git", "reset", "--hard", "origin/master"]
        code, output, error = execute(command, target)

        if code == 0:
            log.debug("Git: Repository at " + source + " updated.")

        else:
            log.debug("Git: " + unicode(error))
            log.debug("Git: Clone instead.")
            command = ["git", "clone", source, target]
            code, output, error = execute(command)

            if code == 0:
                log.debug("Git: Repository at " + source + " cloned.")

            else:
                raise PullFromRepositoryException(unicode(error))


class PullFromHg(PullFromRepository):

    def pull(self, source=None, target=None):
        log.debug("Mercurial: Update repository.")

        source = source or self.source
        target = target or self.target

        # Undo local changes
        command = ["hg", "revert", "--all", "--no-backup"]
        execute(command, target)

        command = ["hg", "pull", "-u"]
        code, output, error = execute(command, target)

        if code == 0:
            log.debug("Mercurial: Repository at " + source + " updated.")

        else:
            log.debug("Mercurial: " + unicode(error))
            log.debug("Mercurial: Clone instead.")
            command = ["hg", "clone", source, target]
            code, output, error = execute(command)

            if code == 0:
                log.debug("Mercurial: Repository at " + source + " cloned.")

            else:
                raise PullFromRepositoryException(unicode(error))


class PullFromSvn(PullFromRepository):

    def pull(self, source=None, target=None):
        log.debug("Subversion: Checkout or update repository.")

        source = source or self.source
        target = target or self.target

        if os.path.exists(target):
            status = "updated"
            command = ["svn", "update", "--accept", "theirs-full", target]

        else:
            status = "checked out"
            command = ["svn", "checkout", "--trust-server-cert",
                       "--non-interactive", source, target]

        code, output, error = execute(command)

        if code != 0:
            raise PullFromRepositoryException(unicode(error))

        log.debug("Subversion: Repository at " + source + " %s." % status)


class CommitToRepositoryException(Exception):
    pass


class CommitToRepository(object):

    def __init__(self, path, message, user):
        self.path = path
        self.message = message
        self.user = user

    def commit(self, path=None, message=None, user=None):
        raise NotImplementedError


class CommitToGit(CommitToRepository):

    def commit(self, path=None, message=None, user=None):
        log.debug("Git: Commit to repository.")

        path = path or self.path
        message = message or self.message
        user = user or self.user
        author = get_author(user)

        # Add
        add = ["git", "add", "-A"]
        execute(add, path)

        # Commit
        commit = ["git", "commit", "-m", message, "--author", author]
        code, output, error = execute(commit, path)
        if code != 0 and len(error):
            raise CommitToRepositoryException(unicode(error))

        # Push
        push = ["git", "push"]
        code, output, error = execute(push, path)
        if code != 0:
            raise CommitToRepositoryException(unicode(error))

        log.info(message)


class CommitToHg(CommitToRepository):

    def commit(self, path=None, message=None, user=None):
        log.debug("Mercurial: Commit to repository.")

        path = path or self.path
        message = message or self.message
        user = user or self.user
        author = get_author(user)

        # Commit
        commit = ["hg", "commit", "-m", message, "-u", author]
        code, output, error = execute(commit, path)
        if code != 0 and len(error):
            raise CommitToRepositoryException(unicode(error))

        # Push
        push = ["hg", "push"]
        code, output, error = execute(push, path)
        if code != 0:
            raise CommitToRepositoryException(unicode(error))

        log.info(message)


class CommitToSvn(CommitToRepository):

    def commit(self, path=None, message=None, user=None):
        log.debug("Subversion: Commit to repository.")

        path = path or self.path
        message = message or self.message
        user = user or self.user
        author = get_author(user)

        # Commit
        command = ["svn", "commit", "-m", message, "--with-revprop",
                   "translate:author=%s" % author, path]
        code, output, error = execute(command)
        if code != 0:
            raise CommitToRepositoryException(unicode(error))

        log.info(message)


def get_author(user):
    name = user.first_name
    if not name:
        name = user.email.split('@')[0]
    return (' '.join([name, '<%s>' % user.email])).encode('utf8')


def execute(command, cwd=None):
    try:
        st = subprocess.PIPE
        proc = subprocess.Popen(
            args=command, stdout=st, stderr=st, stdin=st, cwd=cwd)

        (output, error) = proc.communicate()
        code = proc.returncode
        return code, output, error

    except OSError as error:
        return -1, "", error


def update_from_vcs(repo_type, url, path):
    try:
        obj = globals()['PullFrom%s' % repo_type.capitalize()](url, path)
        obj.pull()

    except PullFromRepositoryException as e:
        error = '%s Pull Error for %s: %s' % (repo_type.upper(), url, e)
        log.debug(error)
        raise Exception(error)


def commit_to_vcs(repo_type, path, message, user):
    try:
        obj = globals()['CommitTo%s' % repo_type.capitalize()](
            path, message.encode('utf8'), user)
        return obj.commit()

    except CommitToRepositoryException as e:
        log.debug('%s Commit Error for %s: %s' % (repo_type.upper(), path, e))
        return {
            'type': 'error',
            'message': unicode(e)
        }
