r"""
SageDev

This module provides :class:`SageDev`, the central object of the developer
scripts for sage.

AUTHORS:

- David Roe, Frej Drejhammar, Julian Rueth, Martin Raum, Nicolas M. Thiery, R.
  Andrew Ohana, Robert Bradshaw, Timo Kluck: initial version

"""
#*****************************************************************************
#       Copyright (C) 2013 David Roe <roed.math@gmail.com>
#                          Frej Drejhammar <frej.drejhammar@gmail.com>
#                          Julian Rueth <julian.rueth@fsfe.org>
#                          Martin Raum <martin@raum-brothers.eu>
#                          Nicolas M. Thiery <Nicolas.Thiery@u-psud.fr>
#                          R. Andrew Ohana <andrew.ohana@gmail.com>
#                          Robert Bradshaw <robertwb@gmail.com>
#                          Timo Kluck <tkluck@infty.nl>
#
#  Distributed under the terms of the GNU General Public License (GPL)
#  as published by the Free Software Foundation; either version 2 of
#  the License, or (at your option) any later version.
#                  http://www.gnu.org/licenses/
#*****************************************************************************

from user_interface_error import OperationCancelledError
from trac_error import TracConnectionError, TracInternalError, TracError
from git_error import GitError

from sage.env import SAGE_VERSION

import re
# regular expressions to parse mercurial patches
HG_HEADER_REGEX = re.compile(r"^# HG changeset patch$")
HG_USER_REGEX = re.compile(r"^# User (.*)$")
HG_DATE_REGEX = re.compile(r"^# Date (\d+) (-?\d+)$")
HG_NODE_REGEX = re.compile(r"^# Node ID ([0-9a-f]+)$")
HG_PARENT_REGEX = re.compile(r"^# Parent +([0-9a-f]+)$")
HG_DIFF_REGEX = re.compile(r"^diff (?:-r [0-9a-f]+ ){1,2}(.*)$")
PM_DIFF_REGEX = re.compile(r"^(?:(?:\+\+\+)|(?:---)) [ab]/([^ ]*)(?: .*)?$")
MV_DIFF_REGEX = re.compile(r"^rename (?:(?:to)|(?:from)) (.*)$")

# regular expressions to parse git patches -- at least those created by us
GIT_FROM_REGEX = re.compile(r"^From: (.*)$")
GIT_SUBJECT_REGEX = re.compile(r"^Subject: (.*)$")
GIT_DATE_REGEX = re.compile(r"^Date: (.*)$")
GIT_DIFF_REGEX = re.compile(r"^diff --git a/(.*) b/(.*)$") # this regex should work for our patches since we do not have spaces in file names

# regular expressions to determine whether a path was written for the new git
# repository of for the old hg repository
HG_PATH_REGEX = re.compile(r"^(?=sage/)|(?=doc/)|(?=module_list\.py)|(?=setup\.py)|(?=c_lib/)")
GIT_PATH_REGEX = re.compile(r"^(?=src/)")

# regular expression to check validity of git options
GIT_BRANCH_REGEX = re.compile(r'^(?!.*/\.)(?!.*\.\.)(?!/)(?!.*//)(?!.*@\{)(?!.*\\)[^\040\177 ~^:?*[]+(?<!\.lock)(?<!/)(?<!\.)$') # http://stackoverflow.com/questions/12093748/how-do-i-check-for-valid-git-branch-names

# the name of the branch which holds the vanilla clone of sage
MASTER_BRANCH = "master"
USER_BRANCH = re.compile(r"^u/([^/]+)/")

COMMIT_GUIDE=r"""


# Please type your commit message above.
# The first line should contain a short summary of your changes, the following
# lines should contain a more detailed description.
# Lines starting with '#' are ignored.
#
# An empty file aborts the commit.
"""

class SageDev(object):
    r"""
    The developer interface for sage.

    This class facilitates access to git and trac.

    INPUT:

    - ``config`` -- a :class:`config.Config` or ``None`` (default: ``None``),
      the configuration of this object; the defaults uses the configuration
      stored in ``DOT_SAGE/devrc``.

    - ``UI`` -- a :class:`user_interface.UserInterface` or ``None`` (default:
      ``None``), the default creates a
      :class:`cmd_line_interface.CmdLineInterface` from ``config['UI']``.

    - ``trac`` -- a :class:`trac_interface.TracInterface` or ``None`` (default:
      ``None``), the default creates a :class:`trac_interface.TracInterface`
      from ``config['trac']``.

    - ``git`` -- a :class:`git_interface.GitInterface` or ``None`` (default:
      ``None``), the default creates a :class:`git_interface.GitInterface` from
      ``config['git']``.

    EXAMPLES::

        sage: dev._sagedev
        SageDev()

    """
    def __init__(self, config=None, UI=None, trac=None, git=None):
        r"""
        Initialization.

        TESTS::

            sage: type(dev._sagedev)
            <class 'sage.dev.sagedev.SageDev'>

        """
        self.config = config
        if self.config is None:
            from config import Config
            self.config = Config()

        # create some empty config sections if they do not yet exist
        for section in ['UI','trac','git','sagedev']:
            if section not in self.config:
                self.config[section] = {}

        self._UI = UI
        if self._UI is None:
            from cmd_line_interface import CmdLineInterface
            self._UI = CmdLineInterface(self.config['UI'])

        self.trac = trac
        if self.trac is None:
            from trac_interface import TracInterface
            self.trac = TracInterface(self.config['trac'], self._UI)

        self.git = git
        if self.git is None:
            from git_interface import GitInterface
            self.git = GitInterface(self.config['git'], self._UI, self.upload_ssh_key)

        # create some SavingDicts to store the relations between branches and tickets
        from sage.env import DOT_SAGE
        import os
        def move_legacy_saving_dict(key, old_file, new_file):
            '''
            We used to have these files in DOT_SAGE - this is not a good idea
            because a user might have multiple copies of sage which should each
            have their own set of files.

            This method moves an existing file mentioned in the config to its
            new position to support repositories created earlier.
            '''
            import sage.doctest
            if sage.doctest.DOCTEST_MODE:
                return
            import shutil
            if not os.path.exists(new_file) and os.path.exists(old_file):
                shutil.move(old_file, new_file)
                self._UI.show("The developer scripts used to store some of their data in `{0}`. This file has now moved to `{1}`. I moved `{0}` to `{1}`. This might cause trouble if this is a fresh clone of the repository in which you never used the developer scripts before. In that case you should manually delete `{1}` now.".format(old_file, new_file))
            if key in self.config['sagedev']:
                del self.config['sagedev'][key]

        ticket_file = os.path.join(self.git._dot_git, 'branch_to_ticket')
        move_legacy_saving_dict('ticketfile', self.config['sagedev'].get('ticketfile', os.path.join(DOT_SAGE, 'branch_to_ticket')), ticket_file)
        branch_file = os.path.join(self.git._dot_git, 'ticket_to_branch')
        move_legacy_saving_dict('branchfile', self.config['sagedev'].get('branchfile', os.path.join(DOT_SAGE, 'ticket_to_branch')), branch_file)
        dependencies_file = os.path.join(self.git._dot_git, 'dependencies')
        move_legacy_saving_dict('dependenciesfile', self.config['sagedev'].get('dependenciesfile', os.path.join(DOT_SAGE, 'dependencies')), dependencies_file)
        remote_branches_file = os.path.join(self.git._dot_git, 'remote_branches')
        move_legacy_saving_dict('remotebranchesfile', self.config['sagedev'].get('remotebranchesfile', os.path.join(DOT_SAGE, 'remote_branches')), remote_branches_file)

        # some people dislike double underscore fields; here you can very
        # seriously screw up your setup if you put something invalid into
        # these. Ideally these fields should only be touched by single
        # underscore methods such as _set_remote_branch which do some checking
        # on the parameters
        from saving_dict import SavingDict
        self.__branch_to_ticket = SavingDict(ticket_file)
        self.__ticket_to_branch = SavingDict(branch_file, paired=self.__branch_to_ticket)
        self.__ticket_dependencies = SavingDict(dependencies_file, default=tuple)
        self.__branch_to_remote_branch = SavingDict(remote_branches_file)

    @property
    def tmp_dir(self):
        r"""
        A lazy property to provide a temporary directory

        TESTS::

            sage: import os
            sage: os.path.isdir(dev._sagedev.tmp_dir)
            True

        """
        try:
            return self._tmp_dir
        except AttributeError:
            import tempfile
            self._tmp_dir = tempfile.mkdtemp()
            import atexit, shutil
            atexit.register(shutil.rmtree, self._tmp_dir)
            return self._tmp_dir

    def __repr__(self):
        r"""
        Return a printable representation of this object.

        TESTS::

            sage: dev # indirect doctest
            SageDev()

        """
        return "SageDev()"

    def create_ticket(self, branch=None, base=MASTER_BRANCH, remote_branch=None):
        r"""
        Create a new ticket on trac and switch to a new local branch to work on
        said ticket.

        INPUT:

        - ``branch`` -- a string or ``None`` (default: ``None``), the
          name of the local branch that will be used for the new
          ticket; if ``None``, the branch will be called
          ``'ticket/ticket_number'``.

        - ``base`` -- a string or ``None``, a branch on which to base
          the ticket (default: the master branch ``'master'``), or a
          ticket; if ``base`` is set to ``None``, then the current
          ticket is used. If ``base`` is a ticket, then the
          corresponding dependency will be added.

        - ``remote_branch`` -- a string or ``None`` (default:
          ``None``), the branch to pull from and push to on trac's git
          server; if ``None``, then the default branch
          ``'u/username/ticket/ticket_number'`` will be used.

        OUTPUT:

        Returns the number of the newly created ticket as an int.

        .. SEEALSO::

            :meth:`switch_ticket`, :meth:`download`, :meth:`edit_ticket`

        TESTS:

        Set up a single user environment::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev._wrap("_dependencies_for_ticket")

        Create some tickets::

            sage: UI.append("Summary: ticket1\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("Summary: ticket2\ndescription")
            sage: dev.create_ticket()
            2
            sage: dev.git.silent.commit(allow_empty=True, message="second commit")
            sage: dev.git.commit_for_branch('ticket/2') != dev.git.commit_for_branch('ticket/1')
            True

        Check that ``base`` works::

            sage: UI.append("Summary: ticket3\ndescription")
            sage: dev.create_ticket(base=2)
            3
            sage: dev.git.commit_for_branch('ticket/3') == dev.git.commit_for_branch('ticket/2')
            True
            sage: dev._dependencies_for_ticket(3)
            (2,)
            sage: UI.append("Summary: ticket4\ndescription")
            sage: dev.create_ticket(base='ticket/2')
            4
            sage: dev.git.commit_for_branch('ticket/4') == dev.git.commit_for_branch('ticket/2')
            True
            sage: dev._dependencies_for_ticket(4)
            ()

        In this example ``base`` does not exist::

            sage: UI.append("Summary: ticket5\ndescription")
            sage: dev.create_ticket(base=1000)
            Ticket #5 has been created. However, I could not switch to a branch for this ticket.
            ValueError: `1000` is not a valid ticket name or ticket does not exist on trac.

        In this example ``base`` does not exist locally::

            sage: UI.append("Summary: ticket6\ndescription")
            sage: dev.create_ticket(base=5)
            Ticket #6 has been created. However, I could not switch to a branch for this ticket.
            ValueError: Branch field is not set for ticket #5 on trac.

        This also fails if the internet connection is broken::

            sage: dev.trac._connected = False
            sage: UI.append("Summary: ticket7\ndescription")
            sage: dev.create_ticket(base=4)
            A network error ocurred, ticket creation aborted.
            Your command failed because no connection to trac could be established.
            sage: dev.trac._connected = True

        Creating a ticket when in detached HEAD state::

            sage: dev.git.super_silent.checkout('HEAD', detach=True)
            sage: UI.append("Summary: ticket detached\ndescription")
            sage: dev.create_ticket()
            7
            sage: dev.git.current_branch()
            'ticket/7'

        Creating a ticket when in the middle of a merge::

            sage: dev.git.super_silent.checkout('-b','merge_branch')
            sage: with open('merge', 'w') as f: f.write("version 0")
            sage: dev.git.silent.add('merge')
            sage: dev.git.silent.commit('-m','some change')
            sage: dev.git.super_silent.checkout('ticket/7')
            sage: with open('merge', 'w') as f: f.write("version 1")
            sage: dev.git.silent.add('merge')
            sage: dev.git.silent.commit('-m','conflicting change')
            sage: from sage.dev.git_error import GitError
            sage: try:
            ....:     dev.git.silent.merge('merge_branch')
            ....: except GitError: pass
            sage: UI.append("n")
            sage: UI.append("Summary: ticket merge\ndescription")
            sage: dev.create_ticket()
            Your repository is in an unclean state. It seems you are in the middle of a merge of some sort. To complete this command you have to reset your repository to a clean state. Do you want me to reset your repository? (This will discard many changes which are not commited.) [yes/No] n
            Could not switch to branch `ticket/8` because your working directory is not in a clean state.
            Ticket #8 has been created. However, I could not switch to a branch for this ticket.
            sage: dev.git.reset_to_clean_state()

        Creating a ticket with uncommitted changes::

            sage: open('tracked', 'w').close()
            sage: dev.git.silent.add('tracked')
            sage: UI.append("keep")
            sage: UI.append("Summary: ticket merge\ndescription")
            sage: dev.create_ticket() # the new branch is based on master which is not the same commit as the current branch ticket/7 - so it is not a valid option to 'keep' changes
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] keep
            Could not switch to branch `ticket/9` because your working directory is not clean.
            Ticket #9 has been created. However, I could not switch to a branch for this ticket.

            sage: UI.append("keep")
            sage: UI.append("Summary: ticket merge\ndescription")
            sage: dev.create_ticket(base='ticket/7') # now we can keep changes because the base is the same commit as the current branch
            The following files in your working directory contain uncommitted changes:
             tracked
             Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? [discard/Keep/stash] keep
             10

        """
        if branch is not None:
            self._check_local_branch_name(branch, exists=False)

        if remote_branch is not None:
            self._check_remote_branch_name(remote_branch, exists=any)

        # now that we have checked that the parameters are valid, let the user
        # interactively create a ticket
        try:
            ticket = self.trac.create_ticket_interactive()
            self._UI.info("Created ticket #{0}.".format(ticket))
        except OperationCancelledError:
            self._UI.info("Ticket creation aborted.")
            raise
        except TracConnectionError as e:
            self._UI.error("A network error ocurred, ticket creation aborted.")
            raise

        try:
            self.switch_ticket(ticket, base=base, branch=branch)
        except:
            self._UI.error("Ticket #{0} has been created. However, I could not switch to a branch for this ticket.".format(ticket))
            kwds = { }
            if branch is not None:
                kwds['branch'] = branch
            if base != "":
                kwds['base'] = base
            self._UI.info("To manually switch to a branch for this ticket, use `{0}`.".format(self._format_command("switch_ticket", ticket, **kwds)))
            raise

        if remote_branch is not None:
            branch = self._branch_for_ticket(ticket)
            self._set_remote_branch_for_branch(branch, remote_branch)
            self._UI.info("The local branch `{0}` will push to `{1}`.".format(branch, remote_branch))

        return ticket

    def switch_ticket(self, ticket, branch=None, base=''):
        r"""
        Switch to a branch associated to ``ticket``.

        If ``branch`` is an existing local branch, then ``ticket`` will be
        associated to it, and the working directory will be switched to
        ``branch``.

        Otherwise, if there is no local branch for ``ticket``, the branch
        specified on trac will be downloaded to ``branch`` unless ``base`` is
        set to something other than the empty string ``''``. If the trac ticket
        does not specify a branch yet or if ``base`` is not the empty string,
        then a new one will be created from ``base`` (per default, the master
        branch).

        INPUT:

        - ``ticket`` -- a string or an integer identifying a ticket

        - ``branch`` -- a string, the name of the local branch that stores
          changes for ``ticket`` (default: ticket/``ticket``)

        - ``base`` -- a string or ``None``, a branch on which to base a new
          branch if one is going to be created (default: the empty string
          ``''`` to create the new branch from the master branch), or a ticket;
          if ``base`` is set to ``None``, then the current ticket is used. If
          ``base`` is a ticket, then the corresponding dependency will be
          added.

        .. SEEALSO::

            :meth:`download`, :meth:`create_ticket`, :meth:`vanilla`

        TESTS:

        Create a doctest setup with two users::

            sage: from sage.dev.test.sagedev import two_user_setup
            sage: alice, config_alice, bob, config_bob, server = two_user_setup()

        Alice tries to switch to ticket #1 which does not exist yet::

            sage: alice._chdir()
            sage: alice.switch_ticket(1)
            ValueError: `1` is not a valid ticket name or ticket does not exist on trac.

        Bob creates that ticket::

            sage: bob._chdir()
            sage: bob._UI.append("Summary: summary1\ndescription")
            sage: bob.create_ticket()
            1

        Now alice can switch to it, even though there is no branch on the
        ticket description::

            sage: alice._chdir()
            sage: alice.switch_ticket(1)

        If Bob commits something to the ticket, a ``switch_ticket`` by Alice
        does not take his changes into account::

            sage: bob._chdir()
            sage: bob.git.super_silent.commit(allow_empty=True,message="empty commit")
            sage: bob._UI.append("y")
            sage: bob.upload()
            The branch `u/bob/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y

            sage: alice._chdir()
            sage: alice.switch_ticket(1)
            sage: alice.git.echo.log('--pretty=%s')
            initial commit

        If Alice had not switched to that ticket before, she would of course
        see Bob's changes (this also checks that we can handle a corrupt ticket
        database and a detached HEAD)::

            sage: alice.git.super_silent.checkout('HEAD', detach=True)
            sage: alice.git.super_silent.branch('-d','ticket/1')
            sage: alice.switch_ticket(1) # ticket #1 refers to the non-existant branch 'ticket/1'
            Ticket #1 refers to the non-existant local branch `ticket/1`. If you have not manually interacted with git, then this is a bug in sagedev. Removing the association from ticket #1 to branch `ticket/1`.
            sage: alice.git.current_branch()
            'ticket/1'
            sage: alice.git.echo.log('--pretty=%s')
            empty commit
            initial commit

        Switching to a ticket with untracked files::

            sage: alice._UI.append("Summary: summary2\ndescription")
            sage: alice.create_ticket()
            2
            sage: alice.git.echo.log('--pretty=%s')
            initial commit
            sage: open("untracked","w").close()
            sage: alice.switch_ticket(1)
            sage: alice.git.echo.log('--pretty=%s')
            empty commit
            initial commit

        Switching to a ticket with untracked files which make a switch
        impossible::

            sage: alice.git.super_silent.add("untracked")
            sage: alice.git.super_silent.commit(message="added untracked")
            sage: alice.switch_ticket(2)
            sage: open("untracked","w").close()
            sage: alice.switch_ticket(1)
            GitError: git exited with a non-zero exit code (1).
            This happened while executing `git -c user.email=doc@test.test -c user.name=alice checkout ticket/1`.
            git printed nothing to STDOUT.
            git printed the following to STDERR:
            error: The following untracked working tree files would be overwritten by checkout:
                untracked
            Please move or remove them before you can switch branches.
            Aborting

        Switching to a ticket with uncommited changes::

            sage: open("tracked","w").close()
            sage: alice.git.super_silent.add("tracked")
            sage: alice._UI.append('d')
            sage: alice.switch_ticket(2)
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? [discard/Keep/stash] d

        """
        self._check_ticket_name(ticket, exists=True)
        ticket = self._ticket_from_ticket_name(ticket)

        # if branch points to an existing branch make it the ticket's branch and switch to it
        if branch is not None and self._is_local_branch_name(branch, exists=True):
            if base != MASTER_BRANCH:
                raise SageDevValueError("base must not be specified if branch is an existing branch")
            if branch == MASTER_BRANCH:
                raise SageDevValueError("branch must not be the master branch")

            self._set_local_branch_for_ticket(ticket, branch)
            self._UI.info("The branch for ticket #{0} is now `{1}`.".format(ticket, branch))
            self._UI.info("Now switching to branch `{0}`.".format(branch))
            self.switch_branch(branch)
            return

        # if there is a branch for ticket locally, switch to it
        if branch is None:
            if self._has_local_branch_for_ticket(ticket):
                branch = self._local_branch_for_ticket(ticket)
                self._UI.info("Switching to branch `{0}`.".format(branch))
                self.switch_branch(branch)
                return
            else:
                branch = self._new_local_branch_for_ticket(ticket)

        # branch does not exist, so we have to create a new branch for ticket
        # depending on the value of base, this will either be base or a copy of
        # the branch mentioned on trac if any
        dependencies = self.trac.dependencies(ticket)
        if base is None:
            base = self._current_ticket()
        if base is None:
            raise SageDevValueError("currently on no ticket, `base` must not be None")
        if self._is_ticket_name(base):
            base = self._ticket_from_ticket_name(base)
            dependencies = [base] # we create a new branch for this ticket - ignore the dependencies which are on trac
            base = self._local_branch_for_ticket(base, download_if_not_found=True)

        remote_branch = self.trac._branch_for_ticket(ticket)
        try:
            if base == '':
                base = MASTER_BRANCH
                if remote_branch is None: # branch field is not set on ticket
                    # create a new branch off master
                    self._UI.info("The branch field on ticket #{0} is not set. Creating a new branch `{1}` off the master branch `{2}`.".format(ticket, branch, MASTER_BRANCH))
                    self.git.silent.branch(branch, MASTER_BRANCH)
                else:
                    # download the branch mentioned on trac
                    if not self._is_remote_branch_name(remote_branch, exists=True):
                        self._UI.error("The branch field on ticket #{0} is set to `{1}`. However, the branch `{1}` does not exist. Please set the field on trac to a field value.".format(ticket, remote_branch))
                        raise OperationCancelledError("remote branch does not exist")
                    try:
                        self.download(remote_branch, branch)
                        self._UI.info("Created a new branch `{0}` based on `{1}`.".format(branch, remote_branch))
                    except:
                        self._UI.error("Could not switch to ticket #{0} because the remote branch `{1}` for that ticket could not be downloaded.".format(ticket, remote_branch))
                        raise
            else:
                self._check_local_branch_name(base, exists=True)
                if remote_branch is not None:
                    if not self._UI.confirm("Creating a new branch for #{0} based on `{1}`. The trac ticket for #{0} already refers to the branch `{2}`. As you are creating a new branch for that ticket, it seems that you want to ignore the work that has already been done on `{2}` and start afresh. Is this what you want?".format(ticket, base, remote_branch), default=False):
                        command = ""
                        if self._has_local_branch_for_ticket(ticket):
                            command += self._format_command("abandon", self._local_branch_for_ticket(ticket)) + "; "
                        command += self._format_command("switch_ticket", ticket)
                        self._UI.info("To work on a fresh copy of `{0}`, use `{1}`.".format(remote_branch, command))
                        raise OperationCancelledError("user requested")

                self._UI.info("Creating a new branch for #{0} based on `{1}`.".format(ticket, base))
                self.git.silent.branch(branch, base)
        except:
            if self._is_local_branch_name(branch, exists=True):
                self._UI.info("Deleting local branch `{0}`.")
                self.git.super_silent.branch(branch, D=True)
            raise

        self._set_local_branch_for_ticket(ticket, branch)
        if dependencies:
            self._UI.info("Locally recording dependency on {0} for #{1}.".format(", ".join(["#"+str(dep) for dep in dependencies]), ticket))
            self._set_dependencies_for_ticket(ticket, dependencies)
        self._set_remote_branch_for_branch(branch, self._remote_branch_for_ticket(ticket)) # set the remote branch for branch to the default u/username/ticket/12345
        self._UI.info("Switching to newly created branch `{0}`.".format(branch))
        self.switch_branch(branch)

    def switch_branch(self, branch):
        r"""
        Switch to the local branch ``branch``.

        INPUT:

        - ``branch`` - a string, the name of a local branch

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a few branches::

            sage: dev.git.silent.branch("branch1")
            sage: dev.git.silent.branch("branch2")

        Switch to a branch::

            sage: dev.switch_branch("branch1")
            sage: dev.git.current_branch()
            'branch1'

        The branch must exist::

            sage: dev.switch_branch("branch3")
            ValueError: Branch `branch3` does not exist locally.

        Switching branches with untracked files::

            sage: open("untracked","w").close()
            sage: dev.switch_branch("branch2")

        Switching branches with uncommitted changes::

            sage: open("tracked","w").close()
            sage: dev.git.silent.add("tracked")
            sage: dev.git.silent.commit(message="added tracked")
            sage: with open("tracked", "w") as f: f.write("foo")
            sage: UI.append("keep")
            sage: dev.switch_branch("branch1")
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] keep
            Could not switch to branch `branch1` because your working directory is not clean.

        We can stash uncommitted changes::

            sage: UI.append("s")
            sage: dev.switch_branch("branch1")
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] s
            Your changes have been recorded on a new branch `stash/1`.

        And unstash the changes later::

            sage: dev.switch_branch('branch2')
            sage: dev.unstash()
            stash/1
            sage: dev.unstash('stash/1')

        Or we can just discard the changes::

            sage: UI.append("d")
            sage: dev.switch_branch("branch1")
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] d

        Switching branches when in the middle of a merge::

            sage: dev.git.super_silent.checkout('-b','merge_branch')
            sage: with open('merge', 'w') as f: f.write("version 0")
            sage: dev.git.silent.add('merge')
            sage: dev.git.silent.commit('-m','some change')
            sage: dev.git.super_silent.checkout('branch1')
            sage: with open('merge', 'w') as f: f.write("version 1")
            sage: dev.git.silent.add('merge')
            sage: dev.git.silent.commit('-m','conflicting change')
            sage: from sage.dev.git_error import GitError
            sage: try:
            ....:     dev.git.silent.merge('merge_branch')
            ....: except GitError: pass
            sage: UI.append('n')
            sage: dev.switch_branch('merge_branch')
            Your repository is in an unclean state. It seems you are in the middle of a merge of some sort. To complete this command you have to reset your repository to a clean state. Do you want me to reset your repository? (This will discard many changes which are not commited.) [yes/No] n
            Could not switch to branch `merge_branch` because your working directory is not in a clean state.
            sage: dev.git.reset_to_clean_state()

        Switching branches when in a detached HEAD::

            sage: dev.git.super_silent.checkout('branch2', detach=True)
            sage: dev.switch_branch('branch1')

        With uncommitted changes::

            sage: dev.git.super_silent.checkout('branch2', detach=True)
            sage: with open('tracked', 'w') as f: f.write("boo")
            sage: UI.append("discard")
            sage: dev.switch_branch('branch1')
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] discard

        Switching branches with untracked files that would be overwritten by
        the switch::

            sage: with open('tracked', 'w') as f: f.write("boo")
            sage: dev.switch_branch('branch2')
            GitError: git exited with a non-zero exit code (1).
            This happened while executing `git -c user.email=doc@test.test -c user.name=doctest checkout branch2`.
            git printed nothing to STDOUT.
            git printed the following to STDERR:
            error: The following untracked working tree files would be overwritten by checkout:
                tracked
            Please move or remove them before you can switch branches.
            Aborting

        """
        self._check_local_branch_name(branch, exists=True)

        try:
            self.reset_to_clean_state()
        except OperationCancelledError:
            self._UI.error("Could not switch to branch `{0}` because your working directory is not in a clean state.".format(branch))
            self._UI.info("To switch to branch `{0}`, use `{1}`.".format(branch, self._format_command("switch-branch",branch=branch)))
            raise

        current_commit = self.git.commit_for_ref('HEAD')
        target_commit = self.git.commit_for_ref(branch)
        try:
            self.reset_to_clean_working_directory(cancel_unless_clean = (current_commit != target_commit))
        except OperationCancelledError:
            self._UI.error("Could not switch to branch `{0}` because your working directory is not clean.".format(branch))
            raise

        try:
            # this leaves locally modified files intact (we only allow this to happen if current_commit == target_commit
            self.git.super_silent.checkout(branch)
        except GitError as e:
            # the error message should be self explanatory
            raise

    def download(self, ticket_or_remote_branch=None, branch=None):
        r"""
        Download ``ticket_or_remote_branch`` to ``branch``.

        INPUT:

        - ``ticket_or_remote_branch`` -- a string or an integer or ``None`` (default:
          ``None``), a ticket or a remote branch name; setting this to ``None``
          has the same effect as setting it to the :meth:`current_ticket`.

        - ``branch`` -- a string or ``None`` (default: ``None``), the branch to
          create or merge the changes into. If ``None``, then a new branch will
          be created unless there is already a branch for this ticket.

        TESTS:

        Create a doctest setup with two users::

            sage: from sage.dev.test.sagedev import two_user_setup
            sage: alice, config_alice, bob, config_bob, server = two_user_setup()

        Alice creates ticket 1::

            sage: alice._chdir()
            sage: alice._UI.append("Summary: summary1\ndescription")
            sage: ticket = alice.create_ticket()

        Bob attempts to download the ticket but fails because there is no
        branch for the ticket yet::

            sage: bob._chdir()
            sage: bob.download(ticket)
            ValueError: Branch field is not set for ticket #1 on trac.

        So, Bob starts to work on the ticket on a new branch::

            sage: bob.switch_ticket(ticket)

        Alice pushes a commit::

            sage: alice._chdir()
            sage: alice.git.super_silent.commit(allow_empty=True, message="alice: empty commit")
            sage: alice._UI.append("y")
            sage: alice.upload()
            The branch `u/alice/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y

        Bob downloads the changes for ticket 1::

            sage: bob._chdir()
            sage: bob.download()
            sage: bob.git.echo.log('--pretty=%s')
            alice: empty commit
            initial commit

        Bob commits a change::

            sage: open("bobs_file","w").close()
            sage: bob.git.silent.add("bobs_file")
            sage: bob.git.super_silent.commit(message="bob: added bobs_file")
            sage: bob._UI.append("y")
            sage: bob._UI.append("y")
            sage: bob.upload()
            The branch `u/bob/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            I will now change the branch field of ticket #1 from its current value `u/alice/ticket/1` to `u/bob/ticket/1`. Is this what you want? [Yes/no] y

        Alice commits non-conflicting changes::

            sage: alice._chdir()
            sage: with open("alices_file","w") as f: f.write("1")
            sage: alice.git.silent.add("alices_file")
            sage: alice.git.super_silent.commit(message="alice: added alices_file")

        Alice can now download the changes by Bob without the need to merge
        manually::

            sage: alice.download()
            sage: alice.git.echo.log('--pretty=%s')
            Merge branch 'u/bob/ticket/1' of /dev/shm/... into ticket/1
            alice: added alices_file
            bob: added bobs_file
            alice: empty commit
            initial commit

        Now, Bob commits some conflicting changes::

            sage: bob._chdir()
            sage: with open("alices_file","w") as f: f.write("2")
            sage: bob.git.silent.add("alices_file")
            sage: bob.git.super_silent.commit(message="bob: added alices_file")
            sage: bob._UI.append('y')
            sage: bob.upload()
            I will now upload the following new commits to the remote branch `u/bob/ticket/1`:
            ...: bob: added alices_file
            Is this what you want? [Yes/no] y

        Now, the download fails; one would have to use :meth:`merge`::

            sage: alice._chdir()
            sage: alice.download()
            GitError: git exited with a non-zero exit code (1).
            Pulling `u/bob/ticket/1` into `ticket/1` failed. Most probably this happened because this did not resolve as a fast-forward, i.e., there were conflicting changes. Maybe there are untracked files in your working directory which made the pull impossible.

        Undo the latest commit by alice, so we can download again::

            sage: alice.git.super_silent.reset('HEAD~~', hard=True)
            sage: alice.download()
            sage: alice.git.echo.log('--pretty=%s')
            bob: added alices_file
            bob: added bobs_file
            alice: empty commit
            initial commit

        Now, Alice creates an untracked file which makes a trivial merge
        impossible::

            sage: alice._chdir()
            sage: open("bobs_other_file","w").close()

            sage: bob._chdir()
            sage: open("bobs_other_file","w").close()
            sage: bob.git.super_silent.add("bobs_other_file")
            sage: bob.git.super_silent.commit(message="bob: added bobs_other_file")
            sage: bob._UI.append('y')
            sage: bob.upload()
            I will now upload the following new commits to the remote branch `u/bob/ticket/1`:
            ...: bob: added bobs_other_file
            Is this what you want? [Yes/no] y

            sage: alice._chdir()
            sage: alice.download()
            GitError: git exited with a non-zero exit code (1).
            Pulling `u/bob/ticket/1` into `ticket/1` failed. Most probably this happened because this did not resolve as a fast-forward, i.e., there were conflicting changes. Maybe there are untracked files in your working directory which made the pull impossible.

        """
        if ticket_or_remote_branch is None:
            ticket_or_remote_branch = self._current_ticket()
            if branch is not None and branch != self.git.current_branch():
                raise SageDevValueError("local_branch must be None")
            branch = self.git.current_branch()

        if ticket_or_remote_branch is None:
            raise SageDevValueError("No `ticket_or_remote_branch` specified to download.")

        if self._is_ticket_name(ticket_or_remote_branch):
            ticket = self._ticket_from_ticket_name(ticket_or_remote_branch)
            self._check_ticket_name(ticket, exists=True)

            remote_branch = self.trac._branch_for_ticket(ticket)
            if remote_branch is None:
                raise SageDevValueError("Branch field is not set for ticket #{0} on trac.".format(ticket))
            if branch is None:
                branch = self._new_local_branch_for_ticket(ticket)
            self._check_local_branch_name(branch)

        else:
            remote_branch = ticket_or_remote_branch
            self._check_remote_branch_name(remote_branch)

            if branch is None:
                branch = remote_branch
            self._check_local_branch_name(branch)

        self._check_remote_branch_name(remote_branch, exists=True)

        self._UI.info("Fetching remote branch `{0}` into `{1}`.".format(remote_branch, branch))
        from git_error import DetachedHeadError
        try:
            current_branch = self.git.current_branch()
        except DetachedHeadError:
            current_branch = None

        if current_branch == branch:
            self.merge(remote_branch=remote_branch)
        else:
            try:
                self.git.super_silent.fetch(self.git._repository, "{0}:{1}".format(remote_branch, branch))
            except GitError as e:
                # there is not many scenarios in which this can fail - the most
                # likely being that branch already exists and this does not
                # resolve as a fast-forward; in any case, if the fetch fails,
                # then just nothing happened and we can abort the download
                # safely without a need to cleanup
                e.explain = "Fetching `{0}` into `{1}` failed.".format(remote_branch, branch)
                if self._is_local_branch_name(branch, exists=True):
                    e.explain += " Most probably this happened because the fetch did not resolve as a fast-forward, i.e., there were conflicting changes."
                    e.advice = "You can try to use `{2}` to switch to `{1}` and then use `{3}` to resolve these conflicts manually.".format(remote_branch, branch, self._format_command("switch-branch",branch), self._format_command("merge",{"remote_branch":remote_branch}))
                else:
                    e.explain += "We did not expect this case to occur.  If you can explain your context in sage.dev.sagedev it might be useful to others."
                    pass
                raise

    def commit(self, message=None, interactive=False):
        r"""
        Create a commit from the pending changes on the current branch.

        This is most akin to mercurial's commit command, not git's,
        since we do not require users to add files.

        INPUT:

        - ``message`` -- the message of the commit (default: ``None``), if
          ``None``, prompt for a message.

        - ``interactive`` -- if set, interactively select which part of the
          changes should be part of the commit

        .. SEEALSO::

        - :meth:`upload` -- Upload changes to the remote server.  This
          is the next step once you've committed some changes.

        - :meth:`diff` -- Show changes that will be committed.

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Commit an untracked file::

            sage: dev.git.super_silent.checkout('-b','branch1')
            sage: open("tracked","w").close()
            sage: dev._UI.extend(["added tracked","y","y","y"])
            sage: dev.commit()
            The following files in your working directory are not tracked by git:
             tracked
            Do you want to add any of these files in this commit? [yes/No] y
            Do you want to add `tracked`? [yes/No] y
            Do you want to commit your changes to branch `branch1`? I will prompt you for a commit message if you do. [Yes/no] y

        Commit a tracked file::

            sage: with open("tracked","w") as F: F.write("foo")
            sage: dev._UI.extend(["modified tracked","y"])
            sage: dev.commit()
            Do you want to commit your changes to branch `branch1`? I will prompt you for a commit message if you do. [Yes/no] y

        """
        from git_error import DetachedHeadError
        try:
            branch = self.git.current_branch()
        except DetachedHeadError:
            self._UI.error("Cannot commit changes when not on any branch.")
            self._UI.info("Use `{0}` or `{1}` to switch to a branch.".format(self._format_command("switch_branch"), self._format_command("switch_ticket")))
            raise OperationCancelledError("cannot proceed in detached HEAD mode")

        # make sure the index is clean
        self.git.super_silent.reset()

        try:
            self._UI.info("Committing pending changes to branch `{0}`.".format(branch))

            try:
                untracked_files = self.git.untracked_files()
                if untracked_files:
                    if self._UI.confirm("The following files in your working directory are not tracked by git:\n{0}\nDo you want to add any of these files in this commit?".format("\n".join([" "+fname for fname in untracked_files])), default=False):
                        for file in untracked_files:
                            if self._UI.confirm("Do you want to add `{0}`?".format(file), default=False):
                                self.git.add(file)

                if interactive:
                    self.git.echo.add(patch=True)
                else:
                    self.git.echo.add(update=True)

                if not self._UI.confirm("Do you want to commit your changes to branch `{0}`?{1}".format(branch, " I will prompt you for a commit message if you do." if message is None else ""), default=True):
                    self._UI.info("If you want to commit to a different branch/ticket, run `{0}` or `{1}` first.".format(self._format_command("switch_branch"), self._format_command("switch_ticket")))
                    raise OperationCancelledError("user does not want to create a commit")

                if message is None:
                    from tempfile import NamedTemporaryFile
                    commit_message = NamedTemporaryFile()
                    commit_message.write(COMMIT_GUIDE)
                    commit_message.flush()

                    self._UI.edit(commit_message.name)

                    message = "\n".join([line for line in open(commit_message.name).read().splitlines() if not line.startswith("#")]).strip()

                if not message:
                    raise OperationCancelledError("empty commit message")

                self.git.commit(message=message)
                self._UI.info("A commit has been created.")

            except OperationCancelledError:
                self._UI.info("Not creating a commit.")
                raise
            except:
                self._UI.error("No commit has been created.")
                raise

        finally:
            # do not leave a non-clean index behind
            self.git.super_silent.reset()

    def set_remote(self, branch_or_ticket, remote_branch):
        r"""
        Set the remote branch to push to for ``branch_or_ticket`` to
        ``remote_branch``.

        INPUT:

        - ``branch_or_ticket`` -- a string, the name of a local branch, or a
          string or an integer identifying a ticket or ``None``; if ``None``,
          the current branch is used.

        - ``remote_branch`` -- a string, the name of a remote branch (this
          branch may not exist yet)

        .. SEEALSO::

        - :meth:`upload` -- To upload changes after setting the remote branch

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev._wrap("_remote_branch_for_ticket")

        Create a new branch::

            sage: UI.append("Summary: ticket1\ndescription")
            sage: dev.create_ticket()
            1

        Modify the remote branch for this ticket's branch::

            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/ticket/1'
            sage: dev.set_remote('ticket/1', 'u/doctest/foo')
            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/foo'
            sage: dev.set_remote('ticket/1', 'foo')
            The remote branch `foo` is not in your user scope. You might not have permission to push to that branch. Did you mean to set the remote branch to `u/doctest/foo`?
            sage: dev._remote_branch_for_ticket(1)
            'foo'
            sage: dev.set_remote('#1', 'u/doctest/foo')
            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/foo'

        """
        if branch_or_ticket is None:
            from git_error import DetachedHeadError
            try:
                branch = self.git.current_branch()
            except DetachedHeadError:
                self._UI.error("`branch` must not be None because you are in detached HEAD state.")
                self._UI.info("Switch to a branch with `{0}` or specify branch explicitly.".format(self._format_command('switch_branch')))
                raise OperationCancelledError("detached head state")
        elif self._is_ticket_name(branch_or_ticket):
            ticket = self._ticket_from_ticket_name(branch_or_ticket)
            if not self._has_local_branch_for_ticket(ticket):
                self._UI.error("no local branch for ticket #{0} found. Cannot set remote branch for that ticket.".format(ticket))
                raise OperationCancelledError("no such ticket")
            branch = self._local_branch_for_ticket(ticket)
        else:
            branch = branch_or_ticket

        self._check_local_branch_name(branch, exists=True)
        self._check_remote_branch_name(remote_branch)

        # If we add restrictions on which branches users may push to, we should append them here.
        m = USER_BRANCH.match(remote_branch)
        if remote_branch == 'master' or m and m.groups()[0] != self.trac._username:
            self._UI.warning("The remote branch `{0}` is not in your user scope. You might not have permission to push to that branch. Did you mean to set the remote branch to `u/{1}/{0}`?".format(remote_branch, self.trac._username))

        self._set_remote_branch_for_branch(branch, remote_branch)

    def upload(self, ticket=None, remote_branch=None, force=False):
        r"""
        Upload the current branch to the Sage repository.

        INPUT:

        - ``ticket`` -- an integer or string identifying a ticket or ``None``
          (default: ``None``), if ``None`` and currently working on a ticket or
          if ``ticket`` specifies a ticket, then the branch on that ticket is
          set to ``remote_branch`` after the current branch has been uploaded there.

        - ``remote_branch`` -- a string or ``None`` (default: ``None``), the remote
          branch to upload to; if ``None``, then a default is chosen

        - ``force`` -- a boolean (default: ``False``), whether to upload if
          this is not a fast-forward.

        .. SEEALSO::

        - :meth:`commit` -- Save changes to the local repository.

        - :meth:`download` -- Update a ticket with changes from the remote
          repository.

        TESTS::

        Create a doctest setup with two users::

            sage: from sage.dev.test.sagedev import two_user_setup
            sage: alice, config_alice, bob, config_bob, server = two_user_setup()

        Alice tries to upload to ticket 1 which does not exist yet::

            sage: alice._chdir()
            sage: alice.upload(ticket=1)
            ValueError: `1` is not a valid ticket name or ticket does not exist on trac.

        Alice creates ticket 1 and uploads some changes to it::

            sage: alice._UI.append("Summary: summary1\ndescription")
            sage: ticket = alice.create_ticket()
            sage: open("tracked", "w").close()
            sage: alice.git.super_silent.add("tracked")
            sage: alice.git.super_silent.commit(message="alice: added tracked")
            sage: alice._UI.append("y")
            sage: alice.upload()
            The branch `u/alice/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y

        Now Bob can switch to that ticket and upload changes himself::

            sage: bob._chdir()
            sage: bob.switch_ticket(1)
            sage: with open("tracked", "w") as f: f.write("bob")
            sage: bob.git.super_silent.add("tracked")
            sage: bob.git.super_silent.commit(message="bob: modified tracked")
            sage: bob._UI.append("y")
            sage: bob._UI.append("y")
            sage: bob.upload()
            The branch `u/bob/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            I will now change the branch field of ticket #1 from its current value `u/alice/ticket/1` to `u/bob/ticket/1`. Is this what you want? [Yes/no] y

        Now Alice can download these changes::

            sage: alice._chdir()
            sage: alice.download()

        Alice and Bob make non-conflicting changes simultaneously::

            sage: with open("tracked", "w") as f: f.write("alice")
            sage: alice.git.super_silent.add("tracked")
            sage: alice.git.super_silent.commit(message="alice: modified tracked")

            sage: bob._chdir()
            sage: open("tracked2", "w").close()
            sage: bob.git.super_silent.add("tracked2")
            sage: bob.git.super_silent.commit(message="bob: added tracked2")

        After Alice uploaded her changes, Bob can not set the branch field anymore::

            sage: alice._chdir()
            sage: alice._UI.append("y")
            sage: alice._UI.append("y")
            sage: alice.upload()
            I will now upload the following new commits to the remote branch `u/alice/ticket/1`:
            ...: alice: modified tracked
            ...: bob: modified tracked
            Is this what you want? [Yes/no] y
            I will now change the branch field of ticket #1 from its current value `u/bob/ticket/1` to `u/alice/ticket/1`. Is this what you want? [Yes/no] y

            sage: bob._chdir()
            sage: bob._UI.append("y")
            sage: bob.upload()
            I will now upload the following new commits to the remote branch `u/bob/ticket/1`:
            ...: bob: added tracked2
            Is this what you want? [Yes/no] y
            Not setting the branch field for ticket #1 to `u/bob/ticket/1` because `u/bob/ticket/1` and the current value of the branch field `u/alice/ticket/1` have diverged.

        After merging the changes, this works again::

            sage: bob.download()
            sage: bob._UI.append("y")
            sage: bob._UI.append("y")
            sage: bob.upload()
            I will now upload the following new commits to the remote branch `u/bob/ticket/1`:
            ...: Merge branch 'u/alice/ticket/1' of ... into ticket/1
            ...: alice: modified tracked
            Is this what you want? [Yes/no] y
            I will now change the branch field of ticket #1 from its current value `u/alice/ticket/1` to `u/bob/ticket/1`. Is this what you want? [Yes/no] y

        Check that ``ticket`` works::

            sage: bob.upload(2)
            ValueError: `2` is not a valid ticket name or ticket does not exist on trac.

        After creating the ticket, this works with a warning::

            sage: bob._UI.append("Summary: summary2\ndescription")
            sage: bob.create_ticket()
            2
            sage: bob.switch_ticket(1)
            sage: bob._UI.append("y")
            sage: bob._UI.append("y")
            sage: bob.upload(2)
            You are trying to push the branch `ticket/1` to `u/bob/ticket/2` for ticket #2. However, your local branch for ticket #2 seems to be `ticket/2`. Do you really want to proceed? [yes/No] y
            The branch `u/bob/ticket/2` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y

        Check that ``remote_branch`` works::

            sage: bob._UI.append("y")
            sage: bob._UI.append("y")
            sage: bob.upload(remote_branch="u/bob/branch1")
            The branch `u/bob/branch1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            I will now change the branch field of ticket #1 from its current value `u/bob/ticket/1` to `u/bob/branch1`. Is this what you want? [Yes/no] y

        Check that dependencies are pushed correctly::

            sage: bob.merge(2)
            Merging the remote branch `u/bob/ticket/2` into the local branch `ticket/1`.
            Added dependency on #2 to #1.
            sage: bob._UI.append("y")
            sage: bob.upload()
            I will now change the branch field of ticket #1 from its current value `u/bob/branch1` to `u/bob/ticket/1`. Is this what you want? [Yes/no] y
            Uploading your dependencies for ticket #1: `` => `#2`
            sage: bob._sagedev._set_dependencies_for_ticket(1,())
            sage: bob._UI.append("keep")
            sage: bob.upload()
            According to trac, ticket #1 depends on #2. Your local branch depends on no tickets. Do you want to upload your dependencies to trac? Or do you want to download the dependencies from trac to your local branch? Or do you want to keep your local dependencies and the dependencies on trac in its current state? [upload/download/keep] keep
            sage: bob._UI.append("download")
            sage: bob.upload()
            According to trac, ticket #1 depends on #2. Your local branch depends on no tickets. Do you want to upload your dependencies to trac? Or do you want to download the dependencies from trac to your local branch? Or do you want to keep your local dependencies and the dependencies on trac in its current state? [upload/download/keep] download
            sage: bob.upload()

        """
        if ticket is None:
            ticket = self._current_ticket()
        if ticket is not None:
            ticket = self._ticket_from_ticket_name(ticket)
            self._check_ticket_name(ticket, exists=True)

        from git_error import DetachedHeadError
        try:
            branch = self.git.current_branch()
        except DetachedHeadError:
            self._UI.error("Cannot upload while in detached HEAD state.")
            raise OperationCancelledError("cannot upload while in detached HEAD state")

        if remote_branch is None:
            if ticket:
                remote_branch = self._remote_branch_for_ticket(ticket)
                if remote_branch is None:
                    raise SageDevValueError("remote_branch must be specified since #{0} has no remote branch set.".format(ticket))
            else:
                remote_branch = self._remote_branch_for_branch(branch)
                if remote_branch is None:
                    raise SageDevValueError("remote_branch must be specified since the current branch has no remote branch set.")

        self._check_remote_branch_name(remote_branch)

        # whether the user already confirmed that he really wants to push and set the branch field
        user_confirmation = force

        if ticket is not None:
            if self._has_local_branch_for_ticket(ticket) and self._local_branch_for_ticket(ticket) == branch:
                pass
            elif self._has_local_branch_for_ticket(ticket) and self._local_branch_for_ticket(ticket) != branch:
                if user_confirmation or self._UI.confirm("You are trying to push the branch `{0}` to `{1}` for ticket #{2}. However, your local branch for ticket #{2} seems to be `{3}`. Do you really want to proceed?".format(branch, remote_branch, ticket, self._local_branch_for_ticket(ticket)), default=False):
                    self._UI.info("To permanently set the branch associated to ticket #{0} to `{1}`, use `{2}`.".format(ticket, branch, self._format_command("switch_ticket",ticket=ticket,branch=branch)))
                    user_confirmation = True
                else:
                    raise OperationCancelledError("user requsted")
            elif self._has_ticket_for_local_branch(branch) and self._ticket_for_local_branch(branch) != ticket:
                if user_confirmation or self._UI.confirm("You are trying to push the branch `{0}` to `{1}` for ticket #{2}. However, that branch is associated to ticket #{3}. Do you really want to proceed?".format(branch, remote_branch, ticket, self._ticket_for_local_branch(branch))):
                    self._UI.info("To permanently set the branch associated to ticket #{0} to `{1}`, use `{2}`. To create a new branch from `{1}` for #{0}, use `{3}` and `{4}`.".format(ticket, branch, self._format_command("switch_ticket",ticket=ticket,branch=branch), self._format_command("switch_ticket",ticket=ticket), self._format_command("merge", branch=branch)))
                    user_confirmation = True

        self._UI.info("Uploading your changes in `{0}` to `{1}`.".format(branch, remote_branch))
        try:
            remote_branch_exists = self._is_remote_branch_name(remote_branch, exists=True)
            if not remote_branch_exists:
                if not self._UI.confirm("The branch `{0}` does not exist on the remote server yet. Do you want to create the branch?".format(remote_branch), default=True):
                    raise OperationCancelledError("User did not want to create remote branch.")
            else:
                self.git.super_silent.fetch(self.git._repository, remote_branch)

            # check whether force is necessary
            if remote_branch_exists and not self.git.is_child_of(branch, 'FETCH_HEAD'):
                if not force:
                    self._UI.error("Not uploading your changes because they would discard some of the commits on the remote branch `{0}`.".format(remote_branch))
                    self._UI.info("If this is really what you want, use `{0}` to upload your changes.".format(remote_branch, self._format_command("upload",ticket=ticket,remote_branch=remote_branch,force=True)))
                    raise OperationCancelledError("not a fast-forward")

            # check whether this is a nop
            if remote_branch_exists and not force and self.git.commit_for_branch(branch) == self.git.commit_for_ref('FETCH_HEAD'):
                self._UI.info("Not uploading your changes because the remote branch `{0}` is idential to your local branch `{1}`. Did you forget to commit your changes with `{2}`?".format(remote_branch, branch, self._format_command("commit")))
            else:
                try:
                    if not force:
                        if remote_branch_exists:
                            commits = self.git.log("{0}..{1}".format('FETCH_HEAD', branch), '--pretty=%h: %s')
                            if not self._UI.confirm("I will now upload the following new commits to the remote branch `{0}`:\n{1}Is this what you want?".format(remote_branch, commits), default=True):
                                raise OperationCancelledError("user requested")

                    self.git.super_silent.push(self.git._repository, "{0}:{1}".format(branch, remote_branch), force=force)
                except GitError as e:
                    # can we give any advice if this fails?
                    raise

            self._UI.info("Your changes in `{0}` have been uploaded to `{1}`.".format(branch, remote_branch))

        except OperationCancelledError:
            self._UI.info("Did not upload any changes.")
            raise


        if ticket:
            current_remote_branch = self.trac._branch_for_ticket(ticket)
            if current_remote_branch == remote_branch:
                self._UI.info("Not setting the branch field for ticket #{0} because it already points to your branch `{1}`.".format(ticket, remote_branch))
            else:
                self._UI.info("Setting the branch field of ticket #{0} to `{1}`.".format(ticket, remote_branch))

                if current_remote_branch is not None:
                    self.git.super_silent.fetch(self.git._repository, current_remote_branch)
                    if force or self.git.is_ancestor_of('FETCH_HEAD', branch):
                        pass
                    else:
                        self._UI.error("Not setting the branch field for ticket #{0} to `{1}` because `{1}` and the current value of the branch field `{2}` have diverged.".format(ticket, remote_branch, current_remote_branch))
                        self._UI.info("If you really want to overwrite the branch field use `{0}`. Otherwise, you need to merge in the changes introduced by `{0}` by using `{1}`.".format(self._format_command("upload",ticket=ticket,remote_branch=remote_branch,force=True), self._format_command("download", ticket=ticket)))
                        raise OperationCancelledError("not a fast-forward")

                if current_remote_branch is not None and not force and not user_confirmation:
                    if not self._UI.confirm("I will now change the branch field of ticket #{0} from its current value `{1}` to `{2}`. Is this what you want?".format(ticket, current_remote_branch, remote_branch), default=True):
                        raise OperationCancelledError("user requested")

                attributes = self.trac._get_attributes(ticket)
                attributes['branch'] = remote_branch
                self.trac._authenticated_server_proxy.ticket.update(ticket, "", attributes)

        if ticket:
            old_dependencies_ = self.trac.dependencies(ticket)
            old_dependencies = ", ".join(["#"+str(dep) for dep in old_dependencies_])
            new_dependencies_ = self._dependencies_for_ticket(ticket)
            new_dependencies = ", ".join(["#"+str(dep) for dep in new_dependencies_])

            upload = True
            if old_dependencies != new_dependencies:
                if old_dependencies:
                    sel = self._UI.select("According to trac, ticket #{0} depends on {1}. Your local branch depends on {2}. Do you want to upload your dependencies to trac? Or do you want to download the dependencies from trac to your local branch? Or do you want to keep your local dependencies and the dependencies on trac in its current state?".format(ticket,old_dependencies,new_dependencies or "no tickets"),options=("upload","download","keep"))
                    if sel == "keep":
                        upload = False
                    elif sel == "download":
                        self._set_dependencies_for_ticket(ticket, old_dependencies_)
                        self._UI.info("Setting dependencies for #{0} to {1}.".format(ticket, old_dependencies))
                        upload = False
                    elif sel == "upload":
                        pass
                    else:
                        raise NotImplementedError
            else:
                self._UI.info("Not uploading your dependencies for ticket #{0} because the dependencies on trac are already up-to-date.".format(ticket))
                upload = False

            if upload:
                self._UI.show("Uploading your dependencies for ticket #{0}: `{1}` => `{2}`".format(ticket, old_dependencies, new_dependencies))

                attributes = self.trac._get_attributes(ticket)
                attributes['dependencies'] = new_dependencies
                self.trac._authenticated_server_proxy.ticket.update(ticket, "", attributes)

    def reset_to_clean_state(self, cancel_unless_clean=True):
        r"""
        Reset the current working directory to a clean state.

        INPUT:

        - ``cancel_unless_clean`` -- a boolean (default: ``True``), whether to
          raise an :class:`user_interface_error.OperationCancelledError` if the
          directory remains in an unclean state; used internally.

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Nothing happens if the directory is already clean::

            sage: dev.reset_to_clean_state()

        Bring the directory into a non-clean state::

            sage: dev.git.super_silent.checkout(b="branch1")
            sage: with open("tracked", "w") as f: f.write("boo")
            sage: dev.git.silent.add("tracked")
            sage: dev.git.silent.commit(message="added tracked")

            sage: dev.git.super_silent.checkout('HEAD~')
            sage: dev.git.super_silent.checkout(b="branch2")
            sage: with open("tracked", "w") as f: f.write("foo")
            sage: dev.git.silent.add("tracked")
            sage: dev.git.silent.commit(message="added tracked")
            sage: from sage.dev.git_error import GitError
            sage: try:
            ....:     dev.git.silent.merge("branch1")
            ....: except GitError: pass
            sage: UI.append("n")
            sage: dev.reset_to_clean_state()
            Your repository is in an unclean state. It seems you are in the middle of a merge of some sort. To complete this command you have to reset your repository to a clean state. Do you want me to reset your repository? (This will discard many changes which are not commited.) [yes/No] n
            sage: UI.append("y")
            sage: dev.reset_to_clean_state()
            Your repository is in an unclean state. It seems you are in the middle of a merge of some sort. To complete this command you have to reset your repository to a clean state. Do you want me to reset your repository? (This will discard many changes which are not commited.) [yes/No] y
            sage: dev.reset_to_clean_state()

        A detached HEAD does not count as a non-clean state::

            sage: dev.git.super_silent.checkout('HEAD', detach=True)
            sage: dev.reset_to_clean_state()

        """
        states = self.git.get_state()
        if not states:
            return
        if not self._UI.confirm("Your repository is in an unclean state. It seems you are in the middle of a merge of some sort. {0}Do you want me to reset your repository? (This will discard many changes which are not commited.)".format("To complete this command you have to reset your repository to a clean state. " if cancel_unless_clean else ""), default=False):
            if not cancel_unless_clean:
                return
            raise OperationCancelledError("User requested not to clean the current state.")

        self.git.reset_to_clean_state()

    def reset_to_clean_working_directory(self, cancel_unless_clean=True):
        r"""
        Drop any uncommitted changes in the working directory.

        INPUT:

        - ``cancel_unless_clean`` -- a boolean (default: ``True``), whether to
          raise an :class:`user_interface_error.OperationCancelledError` if the
          directory remains in an unclean state; used internally.

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Check that nothing happens if there no changes::

            sage: dev.reset_to_clean_working_directory()

        Check that nothing happens if there are only untracked files::

            sage: open("untracked","w").close()
            sage: dev.reset_to_clean_working_directory()

        Uncommitted changes can simply be dropped::

            sage: open("tracked","w").close()
            sage: dev.git.silent.add("tracked")
            sage: dev.git.silent.commit(message="added tracked")
            sage: with open("tracked", "w") as f: f.write("foo")
            sage: UI.append("discard")
            sage: dev.reset_to_clean_working_directory()
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] discard
            sage: dev.reset_to_clean_working_directory()

        Uncommitted changes can be kept::

            sage: with open("tracked", "w") as f: f.write("foo")
            sage: UI.append("keep")
            sage: dev.reset_to_clean_working_directory()
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] keep

        Or stashed::

            sage: UI.append("stash")
            sage: dev.reset_to_clean_working_directory()
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] stash
            Your changes have been recorded on a new branch `stash/1`.
            sage: dev.reset_to_clean_working_directory()

        """
        try:
            self.reset_to_clean_state(cancel_unless_clean)
        except OperationCancelledError:
            self._UI.error("Can not clean the working directory unless in a clean state.")
            raise

        if not self.git.has_uncommitted_changes():
            return

        files = "\n".join([line[2:] for line in self.git.status(porcelain=True).splitlines() if not line.startswith('?')])
        sel = self._UI.select("The following files in your working directory contain uncommitted changes:\n{0}\nDo you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later?{1}".format(files, " Your command can only be completed if you discard or stash your changes." if cancel_unless_clean else ""), options=('discard','keep','stash'), default=1)
        if sel == 'discard':
            self.git.reset_to_clean_working_directory()
        elif sel == 'keep':
            if cancel_unless_clean:
                raise OperationCancelledError("User requested not to clean the working directory.")
        elif sel == 'stash':
            from git_error import DetachedHeadError
            try:
                current_branch = self.git.current_branch()
            except DetachedHeadError:
                current_branch = None
                current_commit = self.git.current_commit()

            branch = self._new_local_branch_for_stash()
            try:
                try:
                    self.git.super_silent.stash()
                    try:
                        self._UI.info("Creating a new branch `{0}` which contains your stashed changes.".format(branch))
                        self.git.super_silent.stash('branch',branch,'stash@{0}')
                        self._UI.info("Committing your changes to `{0}`.".format(branch))
                        self.git.super_silent.commit('-a',message="Changes stashed by reset_to_clean_working_directory()")
                    except:
                        self.git.super_silent.stash('drop')
                        raise
                except:
                    if self._is_local_branch_name(branch, exists=True):
                        self.git.super_silent.branch("-D",branch)
                    raise
            finally:
                self.git.super_silent.checkout(current_branch or current_commit)

            self._UI.show("Your changes have been recorded on a new branch `{0}`.".format(branch))
            self._UI.info("To recover your changes later use `{1}`.".format(branch, self._format_command("unstash",branch=branch)))
        else:
            raise NotImplementedError

    def unstash(self, branch=None, show_diff=False):
        r"""
        Unstash the changes recorded in ``branch``.

        INPUT:

        - ``branch`` -- the name of a local branch or ``None`` (default:
          ``None``), if ``None`` list all stashes.
        - ``show_diff`` -- if ``True``, shows the diff stored in the
          stash rather than applying it.

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create some stashes::

            sage: dev.unstash()
            (no stashes)
            sage: with open("tracked", "w") as f: f.write("foo")
            sage: dev.git.silent.add("tracked")
            sage: UI.append("s")
            sage: dev.reset_to_clean_working_directory()
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] s
            Your changes have been recorded on a new branch `stash/1`.
            sage: with open("tracked", "w") as f: f.write("boo")
            sage: dev.git.silent.add("tracked")
            sage: UI.append("s")
            sage: dev.reset_to_clean_working_directory()
            The following files in your working directory contain uncommitted changes:
             tracked
            Do you want me to discard any changes which are not committed? Should the changes be kept? Or do you want to stash them for later? Your command can only be completed if you discard or stash your changes. [discard/Keep/stash] s
            Your changes have been recorded on a new branch `stash/2`.
            sage: dev.unstash()
            stash/1
            stash/2

        See what's in a stash::

            sage: dev.unstash("stash/1", show_diff=True)

        Unstash a change::

            sage: dev.unstash("stash/1")

        Unstash something that is not a stash::

            sage: dev.unstash("HEAD")
            ValueError: `HEAD` is not a valid name for a stash.

        Unstash a conflicting change::

            sage: dev.unstash("stash/2")
            The changes recorded in `stash/2` do not apply cleanly to your working directory.

        """
        if branch is None:
            stashes = [stash for stash in self.git.local_branches() if self._is_stash_name(stash)]
            stashes.sort()
            stashes = "\n".join(stashes)
            stashes = stashes or "(no stashes)"
            self._UI.info("Use `{0}` to apply the changes recorded in the stash to your working directory, or `{1}` to see the changes recorded in the stash, where `name` is one of the following:\n{2}".format(self._format_command("unstash",branch="name"), self._format_command("unstash",branch="name",show_diff=True), stashes))
            self._UI.show(stashes)
            return
        elif show_diff:
            self.git.echo.diff(branch + '^..' + branch)
            return

        self._check_stash_name(branch, exists=True)

        self.reset_to_clean_state()

        try:
            self.git.super_silent.cherry_pick(branch, no_commit=True)
        except GitError as e:
            self._UI.error("The changes recorded in `{0}` do not apply cleanly to your working directory.".format(branch))
            self._UI.info("You can try to resolve the conflicts manually with `{0}`.".format(self._format_command("merge", branch_or_ticket=branch)))
            raise OperationCancelledError("unstash failed")

        self.git.super_silent.reset()

        if self._UI.select("The changes recorded in `{0}` have been restored in your working directory.  Would you like to delete the branch they were stashed in?", ["yes","no"], "yes"):
            self.git.branch(branch, d=True)

    def edit_ticket(self, ticket=None):
        r"""
        Edit the description of ``ticket`` on trac.

        INPUT:

        - ``ticket`` -- an integer or string identifying a ticket or ``None``
          (default: ``None``), the number of the ticket to edit. If ``None``,
          edit the :meth:`_current_ticket`.

        .. SEEALSO::

            :meth:`create_ticket`, :meth:`add_comment`

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a ticket and edit it::

            sage: UI.append("Summary: summary1\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("Summary: summary1\ndescription...")
            sage: dev.edit_ticket()
            sage: dev.trac._get_attributes(1)
            {'description': 'description...', 'summary': 'summary1'}

        """
        if ticket is None:
            ticket = self._current_ticket()

        if ticket is None:
            raise SageDevValueError("ticket must be specified if not currently on a ticket.")

        self._check_ticket_name(ticket, exists=True)
        ticket = self._ticket_from_ticket_name(ticket)
        self.trac.edit_ticket_interactive(ticket)

    def add_comment(self, ticket=None):
        r"""
        Add a comment to ``ticket`` on trac.

        INPUT:

        - ``ticket`` -- an integer or string identifying a ticket or ``None``
          (default: ``None``), the number of the ticket to edit. If ``None``,
          edit the :meth:`_current_ticket`.

        .. SEEALSO::

            :meth:`create_ticket`, :meth:`edit_ticket`

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a ticket and add a comment::

            sage: UI.append("Summary: summary1\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("comment")
            sage: dev.add_comment()
            sage: server.tickets[1].comments
            ['comment']

        """
        if ticket is None:
            ticket = self._current_ticket()

        if ticket is None:
            raise SageDevValueError("ticket must be specified if not currently on a ticket.")

        self._check_ticket_name(ticket, exists=True)
        ticket = self._ticket_from_ticket_name(ticket)
        self.trac.add_comment_interactive(ticket)

    def browse_ticket(self, ticket=None):
        r"""
        Start a webbrowser at the ticket page on trac.

        INPUT:

        - ``ticket`` -- an integer or string identifying a ticket or ``None``
          (default: ``None``), the number of the ticket to edit. If ``None``,
          browse the :meth:`_current_ticket`.

        .. SEEALSO::

            :meth:`edit_ticket`, :meth:`add_comment`

        EXAMPLES::

            sage: dev.browse_ticket(10000) # not tested

        """
        if ticket is None:
            ticket = self._current_ticket()

        if ticket is None:
            raise SageDevValueError("ticket must be specified if not currently on a ticket.")

        self._check_ticket_name(ticket, exists=True)
        ticket = self._ticket_from_ticket_name(ticket)

        from sage.misc.viewer import browser
        from sage.env import TRAC_SERVER_URI
        browser_cmdline = browser() + ' ' + TRAC_SERVER_URI + '/ticket/' + str(ticket)
        import os
        os.system(browser_cmdline)

    def remote_status(self, ticket=None):
        r"""
        Show information about the status of ``ticket``.

        INPUT:

        - ``ticket`` -- an integer or string identifying a ticket or ``None``
          (default: ``None``), the number of the ticket to edit.  If ``None``,
          show information for the :meth:`_current_ticket`.

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        It is an error to call this without parameters if not on a ticket::

            sage: dev.remote_status()
            ValueError: ticket must be specified if not currently on a ticket.

        Create a ticket and show its remote status::

            sage: UI.append("Summary: ticket1\ndescription")
            sage: dev.create_ticket()
            1
            sage: dev.remote_status()
            Ticket #1 (https://trac.sagemath.org/ticket/1)
            ==============================================
            Your branch `ticket/1` has 0 commits.
            No branch has been set on the trac ticket yet.
            You have not created a remote branch yet.

        After uploading the local branch::

            sage: UI.append("y")
            sage: dev.upload()
            The branch `u/doctest/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: dev.remote_status()
            Ticket #1 (https://trac.sagemath.org/ticket/1)
            ==============================================
            Your branch `ticket/1` has 0 commits.
            The trac ticket points to the branch `u/doctest/ticket/1` which has 0 commits. It does not differ from `ticket/1`.

        Making local changes::

            sage: open("tracked", "w").close()
            sage: dev.git.silent.add("tracked")
            sage: dev.git.silent.commit(message="added tracked")
            sage: dev.remote_status()
            Ticket #1 (https://trac.sagemath.org/ticket/1)
            ==============================================
            Your branch `ticket/1` has 1 commits.
            The trac ticket points to the branch `u/doctest/ticket/1` which has 0 commits. `ticket/1` is ahead of `u/doctest/ticket/1` by 1 commits:
            ...: added tracked

        Uploading them::

            sage: UI.append("y")
            sage: dev.upload()
            I will now upload the following new commits to the remote branch `u/doctest/ticket/1`:
            ...: added tracked
            Is this what you want? [Yes/no] y
            sage: dev.remote_status()
            Ticket #1 (https://trac.sagemath.org/ticket/1)
            ==============================================
            Your branch `ticket/1` has 1 commits.
            The trac ticket points to the branch `u/doctest/ticket/1` which has 1 commits. It does not differ from `ticket/1`.

        The branch on the ticket is ahead of the local branch::

            sage: dev.git.silent.reset('HEAD~', hard=True)
            sage: dev.remote_status()
            Ticket #1 (https://trac.sagemath.org/ticket/1)
            ==============================================
            Your branch `ticket/1` has 0 commits.
            The trac ticket points to the branch `u/doctest/ticket/1` which has 1 commits. `u/doctest/ticket/1` is ahead of `ticket/1` by 1 commits:
            ...: added tracked

        A mixed case::

            sage: open("tracked2", "w").close()
            sage: dev.git.silent.add("tracked2")
            sage: dev.git.silent.commit(message="added tracked2")
            sage: open("tracked3", "w").close()
            sage: dev.git.silent.add("tracked3")
            sage: dev.git.silent.commit(message="added tracked3")
            sage: open("tracked4", "w").close()
            sage: dev.git.silent.add("tracked4")
            sage: dev.git.silent.commit(message="added tracked4")
            sage: dev._UI.append("y")
            sage: dev.upload(remote_branch="u/doctest/branch1", force=True)
            The branch `u/doctest/branch1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: dev.git.silent.reset('HEAD~', hard=True)
            sage: dev.remote_status()
            Ticket #1 (https://trac.sagemath.org/ticket/1)
            ==============================================
            Your branch `ticket/1` has 2 commits.
            The trac ticket points to the branch `u/doctest/branch1` which has 3 commits. `u/doctest/branch1` is ahead of `ticket/1` by 1 commits:
            ...: added tracked4
            Your remote branch `u/doctest/ticket/1` has 1 commits. The branches `u/doctest/ticket/1` and `ticket/1` have diverged.
            `u/doctest/ticket/1` is ahead of `ticket/1` by 1 commits:
            ...: added tracked
            `ticket/1` is ahead of `u/doctest/ticket/1` by 2 commits:
            ...: added tracked2
            ...: added tracked3

        """
        if ticket is None:
            ticket = self._current_ticket()

        if ticket is None:
            raise SageDevValueError("ticket must be specified if not currently on a ticket.")

        self._check_ticket_name(ticket, exists=True)
        ticket = self._ticket_from_ticket_name(ticket)

        from sage.env import TRAC_SERVER_URI
        header = "Ticket #{0} ({1})".format(ticket, TRAC_SERVER_URI + '/ticket/' + str(ticket))
        underline = "="*len(header)

        commits = lambda a, b: list(reversed(self.git.log("{0}..{1}".format(a,b), "--pretty=%an <%ae>: %s").splitlines()))

        def detail(a, b, a_to_b, b_to_a):
            if not a_to_b and not b_to_a:
                return "It does not differ from `{0}`.".format(b)
            elif not a_to_b:
                return "`{0}` is ahead of `{1}` by {2} commits:\n{3}".format(a,b,len(b_to_a),"\n".join(b_to_a))
            elif not b_to_a:
                return "`{0}` is ahead of `{1}` by {2} commits:\n{3}".format(b,a,len(a_to_b),"\n".join(a_to_b))
            else:
                return "The branches `{0}` and `{1}` have diverged.\n`{0}` is ahead of `{1}` by {2} commits:\n{3}\n`{1}` is ahead of `{0}` by {4} commits:\n{5}".format(a,b,len(b_to_a),"\n".join(b_to_a),len(a_to_b),"\n".join(a_to_b))

        branch = None
        if self._has_local_branch_for_ticket(ticket):
            branch = self._local_branch_for_ticket(ticket)
            if not self.git.is_ancestor_of(MASTER_BRANCH, branch):
                local_summary = "Your branch is `{0}`.".format(branch)
            else:
                master_to_branch = commits(MASTER_BRANCH, branch)
                local_summary = "Your branch `{0}` has {1} commits.".format(branch, len(master_to_branch))
        else:
            local_summary = "You have no local branch for this ticket"

        ticket_branch = self.trac._branch_for_ticket(ticket)
        if ticket_branch:
            ticket_to_local = None
            local_to_ticket = None
            if not self._is_remote_branch_name(ticket_branch, exists=True):
                ticket_summary = "The trac ticket points to the branch `{0}` which does not exist."
            else:
                self.git.super_silent.fetch(self.git._repository, ticket_branch)
                if not self.git.is_ancestor_of(MASTER_BRANCH, 'FETCH_HEAD'):
                    ticket_summary = "The trac ticket points to the branch `{0}`.".format(ticket_branch)
                else:
                    master_to_ticket = commits(MASTER_BRANCH, 'FETCH_HEAD')
                    ticket_summary = "The trac ticket points to the branch `{0}` which has {1} commits.".format(ticket_branch, len(master_to_ticket))
                    if self.git.is_ancestor_of(MASTER_BRANCH, branch):
                        ticket_to_local = commits('FETCH_HEAD', branch)
                        local_to_ticket = commits(branch, 'FETCH_HEAD')
                        ticket_summary += " "+detail(ticket_branch, branch, ticket_to_local, local_to_ticket)
        else:
            ticket_summary = "No branch has been set on the trac ticket yet."

        remote_branch = self._remote_branch_for_ticket(ticket)
        if self._is_remote_branch_name(remote_branch, exists=True):
            remote_to_local = None
            local_to_remote = None
            self.git.super_silent.fetch(self.git._repository, remote_branch)
            if not self.git.is_ancestor_of(MASTER_BRANCH, 'FETCH_HEAD'):
                remote_summary = "Your remote branch is `{0}`.".format(remote_branch)
            else:
                master_to_remote = commits(MASTER_BRANCH, 'FETCH_HEAD')
                remote_summary = "Your remote branch `{0}` has {1} commits.".format(remote_branch, len(master_to_remote))
                if self.git.is_ancestor_of(MASTER_BRANCH, branch):
                    remote_to_local = commits('FETCH_HEAD', branch)
                    local_to_remote = commits(branch, 'FETCH_HEAD')
                    remote_summary += " "+detail(remote_branch, branch, remote_to_local, local_to_remote)
        else:
            remote_summary = "You have not created a remote branch yet."

        show = [header, underline, local_summary, ticket_summary]
        if not self._is_remote_branch_name(remote_branch, exists=True) or remote_branch != ticket_branch:
            show.append(remote_summary)

        self._UI.show("\n".join(show))

    def import_patch(self, patchname=None, url=None, local_file=None, diff_format=None, header_format=None, path_format=None):
        r"""
        Import a patch into the current branch.

        If ``local_file`` is specified, apply the file it points to.

        Otherwise, download the patch using :meth:`download_patch` and apply
        it.

        INPUT:

        - ``patchname`` -- a string or ``None`` (default: ``None``), passed on
          to :meth:`download_patch`

        - ``url`` -- a string or ``None`` (default: ``None``), passed on to
          :meth:`download_patch`

        - ``local_file`` -- a string or ``None`` (default: ``None``), if
          specified, ``url`` and ``patchname`` must be ``None``; instead of
          downloading the patch, apply this patch file.

        - ``diff_format`` -- a string or ``None`` (default: ``None``), per
          default the format of the patch file is autodetected; it can be
          specified explicitly with this parameter

        - ``header_format`` -- a string or ``None`` (default: ``None``), per
          default the format of the patch header is autodetected; it can be
          specified explicitly with this parameter

        - ``path_format`` -- a string or ``None`` (default: ``None``), per
          default the format of the paths is autodetected; it can be specified
          explicitly with this parameter

        .. NOTE::

            This method calls :meth:`_rewrite_patch` if necessary to rewrite
            patches which were created for sage before the move to git
            happened. In other words, this is not just a simple wrapper for
            ``git am``.

        .. SEEALSO::

        - :meth:`download_patch` -- download a patch to a local file.

        - :meth:`download` -- merges in changes from a git branch rather than a
          patch.

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a patch::

            sage: open("tracked", "w").close()
            sage: open("tracked2", "w").close()
            sage: import os
            sage: patchfile = os.path.join(dev._sagedev.tmp_dir,"tracked.patch")
            sage: dev.git.silent.add("tracked", "tracked2")
            sage: with open(patchfile, "w") as f: f.write(dev.git.diff(cached=True))
            sage: dev.git.silent.reset()

        Applying this patch fails::

            sage: dev.import_patch(local_file=patchfile, path_format="new") # the autodetection of the path format fails since we are not in a sage repository
            There are untracked files in your working directory:
            tracked
            tracked2
            The patch cannot be imported unless these files are removed.

        After moving away ``tracked`` and ``tracked2``, this works::

            sage: os.unlink("tracked")
            sage: os.unlink("tracked2")
            sage: dev.import_patch(local_file=patchfile, path_format="new")
            Applying: No Subject. Modified: tracked, tracked2

         We create a patch which does not apply::

            sage: with open("tracked", "w") as f: f.write("foo")
            sage: dev.git.silent.add("tracked")
            sage: with open("tracked", "w") as f: f.write("boo")
            sage: with open("tracked2", "w") as f: f.write("boo")
            sage: with open(patchfile, "w") as f: f.write(dev.git.diff())
            sage: dev.git.reset_to_clean_working_directory()
            sage: open("tracked").read()
            ''

         The import fails::

            sage: UI.append("abort")
            sage: UI.append("y")
            sage: dev.import_patch(local_file=patchfile, path_format="new")
            Applying: No Subject. Modified: tracked, tracked2
            error: patch failed: tracked:1
            error: tracked: patch does not apply
            Patch failed at 0001 No Subject. Modified: tracked, tracked2
            The copy of the patch that failed is found in:
               .../rebase-apply/patch
            <BLANKLINE>
            The patch does not apply cleanly. Would you like to apply it anyway and create reject files for the parts that do not apply? [yes/No] y
            Checking patch tracked...
            error: while searching for:
            foo
            error: patch failed: tracked:1
            Checking patch tracked2...
            Applying patch tracked with 1 reject...
            Rejected hunk #1.
            Applied patch tracked2 cleanly.
            The patch did not apply cleanly. Please integrate the `.rej` files that were created and resolve conflicts. After you do, type `resolved`. If you want to abort this process, type `abort`. [resolved/abort] abort
            Removing tracked.rej
            sage: open("tracked").read()
            ''

            sage: UI.append("resolved")
            sage: UI.append("y")
            sage: dev.import_patch(local_file=patchfile, path_format="new")
            Applying: No Subject. Modified: tracked, tracked2
            error: patch failed: tracked:1
            error: tracked: patch does not apply
            Patch failed at 0001 No Subject. Modified: tracked, tracked2
            The copy of the patch that failed is found in:
               .../rebase-apply/patch
            <BLANKLINE>
            The patch does not apply cleanly. Would you like to apply it anyway and create reject files for the parts that do not apply? [yes/No] y
            Checking patch tracked...
            error: while searching for:
            foo
            error: patch failed: tracked:1
            Checking patch tracked2...
            Applying patch tracked with 1 reject...
            Rejected hunk #1.
            Applied patch tracked2 cleanly.
            The patch did not apply cleanly. Please integrate the `.rej` files that were created and resolve conflicts. After you do, type `resolved`. If you want to abort this process, type `abort`. [resolved/abort] resolved
            Removing tracked.rej
            sage: open("tracked").read() # we did not actually incorporate the .rej files in this doctest, so nothing has changed
            ''
            sage: open("tracked2").read()
            'boo'

        """
        try:
            self.reset_to_clean_state()
            self.reset_to_clean_working_directory()
        except OperationCancelledError:
            self._UI.error("Cannot import patch. Your working directory is not in a clean state.")
            raise

        untracked = self.git.untracked_files()
        # do not exclude .patch files here: they would be deleted by reset_to_clean_working_directory() later
        if untracked:
            self._UI.error("There are untracked files in your working directory:\n{0}\nThe patch cannot be imported unless these files are removed.".format("\n".join(untracked)))
            raise OperationCancelledError("untracked files make import impossible")

        if not local_file:
            local_file = self.download_patch(patchname=patchname, url=url)
            try:
                return self.import_patch(
                        local_file=local_file,
                        diff_format=diff_format, header_format=header_format, path_format=path_format)
            finally:
                import os
                os.unlink(local_file)
        elif patchname or url:
            raise SageDevValueError("if local_file is specified, patchname and url must not be specified")
        else:
            lines = open(local_file).read().splitlines()
            lines = self._rewrite_patch(lines, to_header_format="git",
                    to_path_format="new", from_diff_format=diff_format,
                    from_header_format=header_format,
                    from_path_format=path_format)

            import tempfile, os
            fd, outfile = tempfile.mkstemp(dir=self.tmp_dir)
            os.fdopen(fd, 'w').writelines("\n".join(lines)+"\n")

            self._UI.info("Trying to apply reformatted patch `%s`"%outfile)
            try:
                self.git.echo.am(outfile, "--resolvemsg= ", ignore_whitespace=True)
            except GitError:
                if not self._UI.confirm("The patch does not apply cleanly. Would you like to apply it anyway and create reject files for the parts that do not apply?", default=False):
                    self._UI.info("Not applying patch.")
                    self.git.reset_to_clean_state()
                    self.git.reset_to_clean_working_directory(remove_untracked_files=True)
                    raise OperationCancelledError("User requested to cancel the apply.")

                try:
                    try:
                        self.git.silent.apply(outfile, ignore_whitespace=True, reject=True)
                    except GitError:
                        if self._UI.select("The patch did not apply cleanly. Please integrate the `.rej` files that were created and resolve conflicts. After you do, type `resolved`. If you want to abort this process, type `abort`.", ("resolved","abort")) == "abort":
                            self.git.reset_to_clean_state()
                            self.git.reset_to_clean_working_directory(remove_untracked_files=True)
                            raise OperationCancelledError("User requested to cancel the apply.")
                    else:
                        self._UI.show("It seemed that the patch would not apply, but in fact it did.")
                        return

                    self.git.super_silent.add(update=True)
                    untracked = [fname for fname in self.git.untracked_files() if not fname.endswith(".rej")]
                    if untracked:
                        self._UI.confirm("The patch will introduce the following new files to the repository:\n{0}\nIs this correct?".format("\n".join(untracked)), default=True)
                        self.git.super_silent.add(*untracked)
                    self.git.am('--resolvemsg= ', resolved=True)
                    self._UI.info("A commit on the current branch has been created from the patch.")
                finally:
                    self.git.reset_to_clean_working_directory(remove_untracked_files=True)

    def download_patch(self, ticket=None, patchname=None, url=None):
        r"""
        Download a patch to a temporary directory.

        If only ``ticket`` is specified and the ticket has only one
        attachment, download the patch attached to ``ticket``.

        If ``ticket`` and ``patchname`` are specified, download the
        patch ``patchname`` attached to ``ticket``.

        If ``url`` is specified, download ``url``.

        If nothing is specified, and if the ''current'' ticket has only
        one attachment, download it.

        Raise an error on any other combination of parameters.

        INPUT:

        - ``ticket`` -- an integer or string identifying a ticket or ``None``
          (default: ``None``)

        - ``patchname`` -- a string or ``None`` (default: ``None``)

        - ``url`` -- a string or ``None`` (default: ``None``)

        OUTPUT:

        Returns the absolute file name of the returned file.

        .. SEEALSO::

        - :meth:`import_patch` -- also creates a commit on the current branch
          from the patch.

        EXAMPLES::

            sage: dev.download_patch(ticket=14882) # optional: internet
            ValueError: Ticket #14882 has more than one attachment but parameter `patchname` is not present, please set it to one of: trac_14882-backtrack_longtime-dg-v2.patch, trac_14882-backtrack_longtime-dg.patch, trac_14882-spelling_in_backtrack-dg.patch
            sage: dev.download_patch(ticket=14882, patchname='trac_14882-backtrack_longtime-dg.patch') # optional: internet
            '...'

        TESTS:

        Set up a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a new ticket::

            sage: UI.append("Summary: summary1\ndescription")
            sage: dev.create_ticket()
            1

        There are no attachment to download yet::

            sage: dev.download_patch(ticket=1)
            ValueError: Ticket #1 has no attachments.

        After adding one attachment, this works::

            sage: server.tickets[1].attachments['first.patch'] = ''
            sage: dev.download_patch(ticket=1) # not tested, download_patch tries to talk to the live server

        After adding another attachment, this does not work anymore, one needs
        to specify which attachment should be downloaded::

            sage: server.tickets[1].attachments['second.patch'] = ''
            sage: dev.download_patch(ticket=1)
            ValueError: Ticket #1 has more than one attachment but parameter `patchname` is not present, please set it to one of: first.patch, second.patch
            sage: dev.download_patch(ticket=1, patchname = 'second.patch') # not tested, download_patch tries to talk to the live server

        It is an error not to specify any parameters if not on a ticket::

            sage: dev.vanilla()
            sage: dev.download_patch()
            ValueError: ticket or url must be specified if not currently on a ticket

        """
        if url is not None:
            if ticket or patchname:
                raise ValueError("If `url` is specifed, `ticket` and `patchname` must not be specified.")
            import urllib
            return urllib.urlretrieve(url)[0]

        if ticket is None:
            ticket is self._current_ticket()

        if ticket is None:
            raise SageDevValueError("ticket or url must be specified if not currently on a ticket")

        ticket = self._ticket_from_ticket_name(ticket)

        if patchname:
            from sage.env import TRAC_SERVER_URI
            url = TRAC_SERVER_URI+"/raw-attachment/ticket/%s/%s"%(ticket,patchname)
            if url.startswith("https://"):
                try:
                    import ssl
                except ImportError:
                    # python is not build with ssl support by default. to make
                    # downloading patches work even if ssl is not present, we try
                    # to access trac through http
                    url = url.replace("https","http",1)
            return self.download_patch(url = url)
        else:
            attachments = self.trac.attachment_names(ticket)
            if len(attachments) == 0:
                raise SageDevValueError("Ticket #%s has no attachments."%ticket)
            if len(attachments) == 1:
                return self.download_patch(ticket = ticket, patchname = attachments[0])
            else:
                raise SageDevValueError("Ticket #%s has more than one attachment but parameter `patchname` is not present, please set it to one of: %s"%(ticket,", ".join(sorted(attachments))))

    def prune_closed_tickets(self):
        r"""
        Remove branches for tickets that are already merged into master.

        .. SEEALSO::

            :meth:`abandon` -- Abandon a single ticket or branch.

        TESTS:

        Create a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a ticket branch::

            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: dev.local_tickets()
              : master
            #1: ticket/1

        With a commit on it, the branch is not abandoned::

            sage: open("tracked","w").close()
            sage: dev.git.silent.add("tracked")
            sage: dev.git.super_silent.commit(message="added tracked")
            sage: dev.prune_closed_tickets()
            sage: dev.local_tickets()
              : master
            #1: ticket/1

        After merging it to the master branch, it is abandoned. This does not
        work, because we cannot move the current branch::

            sage: dev.git.super_silent.checkout("master")
            sage: dev.git.super_silent.merge("ticket/1")

            sage: dev.git.super_silent.checkout("ticket/1")
            sage: dev.prune_closed_tickets()
            Abandoning #1.
            Can not delete `ticket/1` because you are currently on that branch.

        Now, the branch is abandoned::

            sage: dev.vanilla()
            sage: dev.prune_closed_tickets()
            Abandoning #1.
            Moved your branch `ticket/1` to `trash/ticket/1`.
            sage: dev.local_tickets()
            : master
            sage: dev.prune_closed_tickets()

        """
        for branch in self.git.local_branches():
            if self._has_ticket_for_local_branch(branch):
                ticket = self._ticket_for_local_branch(branch)
                if self.git.is_ancestor_of(branch, MASTER_BRANCH):
                    self._UI.show("Abandoning #{0}.".format(ticket))
                    self.abandon(ticket)

    def abandon(self, ticket_or_branch=None):
        r"""
        Abandon a ticket or branch.

        INPUT:

        - ``ticket_or_branch`` -- an integer or string identifying a ticket or
          the name of a local branch or ``None`` (default: ``None``), remove
          the branch ``ticket_or_branch`` or the branch for the ticket
          ``ticket_or_branch`` (or the current branch if ``None``). Also
          removes the users remote tracking branch.

        .. SEEALSO::

        - :meth:`prune_closed_tickets` -- abandon tickets that have
          been closed.

        - :meth:`local_tickets` -- list local non-abandoned tickets.

        TESTS:

        Create a single user for doctesting::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create a ticket branch and abandon it::

            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("y")
            sage: dev.upload()
            The branch `u/doctest/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: dev.abandon(1)
            Can not delete `ticket/1` because you are currently on that branch.
            sage: dev.vanilla()
            sage: dev.abandon(1)
            Moved your branch `ticket/1` to `trash/ticket/1`.

        Start to work on a new branch for this ticket::

            sage: from sage.dev.sagedev import MASTER_BRANCH
            sage: UI.append("y")
            sage: dev.switch_ticket(1, base=MASTER_BRANCH)
            Creating a new branch for #1 based on `master`. The trac ticket for #1 already refers to the branch `u/doctest/ticket/1`. As you are creating a new branch for that ticket, it seems that you want to ignore the work that has already been done on `u/doctest/ticket/1` and start afresh. Is this what you want? [yes/No] y

        """
        ticket = None

        if self._is_ticket_name(ticket_or_branch):
            ticket = self._ticket_from_ticket_name(ticket_or_branch)

            if not self._has_local_branch_for_ticket(ticket):
                raise SageDevValueError("Can not abandon #{0}. You have no local branch for this ticket.".format(ticket))
            ticket_or_branch = self._local_branch_for_ticket(ticket)

        if self._has_ticket_for_local_branch(ticket_or_branch):
            ticket = self._ticket_for_local_branch(ticket_or_branch)

        if self._is_local_branch_name(ticket_or_branch):
            branch = ticket_or_branch
            self._check_local_branch_name(branch, exists=True)

            if branch == MASTER_BRANCH:
                self._UI.error("I will not delete the master branch.")
                raise OperationCancelledError("protecting the user")

            if not self.git.is_ancestor_of(branch, MASTER_BRANCH):
                if not self._UI.confirm("I will delete your local branch `{0}`. Is this what you want?".format(branch), default=False):
                    raise OperationCancelledError("user requested")
            from git_error import DetachedHeadError
            try:
                if self.git.current_branch() == branch:
                    self._UI.error("Can not delete `{0}` because you are currently on that branch.".format(branch))
                    self._UI.info("Use `{0}` to move to a different branch.".format(self._format_command("vanilla")))
                    raise OperationCancelledError("can not delete current branch")
            except DetachedHeadError:
                pass

            new_branch = self._new_local_branch_for_trash(branch)
            self.git.super_silent.branch("-m", branch, new_branch)
            self._UI.show("Moved your branch `{0}` to `{1}`.".format(branch, new_branch))
        else:
            raise SageDevValueError("ticket_or_branch must be the name of a ticket or a local branch")

        if ticket:
            self._set_local_branch_for_ticket(ticket, None)
            self._UI.info("If you want to work on #{0} starting from a fresh copy of the master branch, use `{1}`.".format(ticket, self._format_command("switch_ticket",ticket,base=MASTER_BRANCH)))

    def gather(self, branch, *tickets_or_branches):
        r"""
        Create a new branch ``branch`` with ``tickets_or_remote_branches``
        applied.

        INPUT:

        - ``branch`` -- a string, the name of the new branch

        - ``tickets_or_branches`` -- a list of integers and strings; for an
          integer or string identifying a ticket, the branch on the trac ticket
          gets merged, for the name of a local or remote branch, that branch
          gets merged.

        .. SEEALSO::

        - :meth:`merge` -- merge into the current branch rather than creating a
          new one

        TESTS:

        Create a doctest setup with a single user::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create tickets and branches::

            sage: dev._UI.append("Summary: summary1\ndescription")
            sage: dev.create_ticket()
            1
            sage: open("tracked","w").close()
            sage: dev.git.silent.add("tracked")
            sage: dev.git.super_silent.commit(message="added tracked")
            sage: dev._UI.append("y")
            sage: dev._UI.append("y")
            sage: dev.upload()
            The branch `u/doctest/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y

        Gather all these branches::

            sage: dev.gather("gather_branch", "#1", "ticket/1", "u/doctest/ticket/1")

        """
        try:
            self.reset_to_clean_state()
            self.reset_to_clean_working_directory()
        except OperationCancelledError:
            self._UI.error("Cannot gather branches because working directory is not in a clean state.")
            raise OperationCancelledError("working directory not clean")

        self._check_local_branch_name(branch, exists=False)

        branches = []
        for ticket_or_branch in tickets_or_branches:
            local_branch = None
            remote_branch = None
            if self._is_ticket_name(ticket_or_branch):
                ticket = self._ticket_from_ticket_name(ticket_or_branch)
                remote_branch = self.trac._branch_for_ticket(ticket)
                if remote_branch is None:
                    raise SageDevValueError("Ticket #{0} does not have a branch set yet.".format(ticket))
            elif self._is_local_branch_name(ticket_or_branch, exists=True):
                local_branch = ticket_or_branch
            else:
                remote_branch = ticket_or_branch

            if local_branch:
                self._check_local_branch_name(local_branch, exists=True)
                branches.append(("local",local_branch))
            if remote_branch:
                self._check_remote_branch_name(remote_branch, exists=True)
                branches.append(("remote",remote_branch))

        self._UI.info("Creating a new branch `{0}`.".format(branch))
        self.git.super_silent.branch(branch, MASTER_BRANCH)
        self.git.super_silent.checkout(branch)

        try:
            for local_remote,branch_name in branches:
                self._UI.info("Merging {2} branch `{0}` into `{1}`.".format(branch_name, branch, local_remote))
                self.merge(branch, download=local_remote=="remote")
        except:
            self.git.reset_to_clean_state()
            self.git.reset_to_clean_working_directory()
            self.vanilla()
            self.git.super_silent.branch("-D", branch)
            self._UI.info("Deleted branch `{0}`.".format(branch))

    def merge(self, ticket_or_branch=MASTER_BRANCH, download=None, create_dependency=None):
        r"""
        Merge changes from ``ticket_or_branch`` into the current branch.

        INPUT:

        - ``ticket_or_branch`` -- an integer or strings (default:
          ``'master'``); for an integer or string identifying a ticket, the
          branch on the trac ticket gets merged (or the local branch for the
          ticket, if ``download`` is ``False``), for the name of a local or
          remote branch, that branch gets merged. If ``'dependencies'``, the
          dependencies are merged in one by one, starting with one listed first
          in the dependencies field on trac.

        - ``download`` -- a boolean or ``None`` (default: ``None``); if
          ``ticket_or_branch`` identifies a ticket, whether to download the
          latest branch on the trac ticket (the default); if
          ``ticket_or_branch`` is a remote branch, whether to download that
          remote branch (the default); if ``ticket_or_branch`` is a local
          branch, whether to download its remote branch (not the default)

        - ``create_dependency`` -- a boolean or ``None`` (default: ``None``),
          whether to create a dependency to ``ticket_or_branch``. If ``None``,
          then a dependency is created if ``ticket_or_branch`` identifies a
          ticket and if the current branch is associated to a ticket.

        .. NOTE::

            Dependencies are stored locally and only updated with respect to
            the remote server during :meth:`upload` and :meth:`download`.

            Adding a dependency has some consequences:

            - the other ticket must be positively reviewed and merged before
              this ticket may be merged into the official release of sage.  The
              commits included from a dependency don't need to be reviewed in
              this ticket, whereas commits reviewed in this ticket from a
              non-dependency may make reviewing the other ticket easier.

            - you can more easily merge in future changes to dependencies.  So
              if you need a feature from another ticket it may be appropriate
              to create a dependency to that you may more easily benefit
              from others' work on that ticket.

            - if you depend on another ticket then you need to worry about the
              progress on that ticket.  If that ticket is still being actively
              developed then you may need to make many merges to keep up.

        .. SEEALSO::

        - :meth:`show_dependencies` -- see the current dependencies.

        - :meth:`GitInterface.merge` -- git's merge command has more options
          and can merge multiple branches at once.

        - :meth:`gather` -- creates a new branch to merge into rather than
          merging into the current branch.

        TESTS::

        Create a doctest setup with two users::

            sage: from sage.dev.test.sagedev import two_user_setup
            sage: alice, config_alice, bob, config_bob, server = two_user_setup()

        Create tickets and branches::

            sage: alice._chdir()
            sage: alice._UI.append("Summary: summary1\ndescription")
            sage: alice.create_ticket()
            1
            sage: alice._UI.append("Summary: summary2\ndescription")
            sage: alice.create_ticket()
            2

        Alice creates two branches and merges them::

            sage: alice.switch_ticket(1)
            sage: open("alice1","w").close()
            sage: alice.git.silent.add("alice1")
            sage: alice.git.super_silent.commit(message="added alice1")
            sage: alice.switch_ticket(2)
            sage: with open("alice2","w") as f: f.write("alice")
            sage: alice.git.silent.add("alice2")
            sage: alice.git.super_silent.commit(message="added alice2")

        When merging for a ticket, the branch on the trac ticket matters::

            sage: alice.merge("#1")
            Can not merge remote branch for #1. No branch has been set on the trac ticket.
            sage: alice.switch_ticket(1)
            sage: alice._UI.append("y")
            sage: alice.upload()
            The branch `u/alice/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: alice.switch_ticket(2)
            sage: alice.merge("#1", download=False)
            Merging the local branch `ticket/1` into the local branch `ticket/2`.
            Added dependency on #1 to #2.

        Merging local branches::

            sage: alice.merge("ticket/1")
            Merging the local branch `ticket/1` into the local branch `ticket/2`.

        A remote branch for a local branch is only merged in if ``download`` is set::

            sage: alice._sagedev._set_remote_branch_for_branch("ticket/1", "nonexistant")
            sage: alice.merge("ticket/1")
            Merging the local branch `ticket/1` into the local branch `ticket/2`.
            sage: alice.merge("ticket/1", download=True)
            Can not merge remote branch `nonexistant`. It does not exist.

        Bob creates a conflicting commit::

            sage: bob._chdir()
            sage: bob.switch_ticket(1)
            sage: with open("alice2","w") as f: f.write("bob")
            sage: bob.git.silent.add("alice2")
            sage: bob.git.super_silent.commit(message="added alice2")
            sage: bob._UI.append("y")
            sage: bob._UI.append("y")
            sage: bob.upload()
            The branch `u/bob/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            I will now change the branch field of ticket #1 from its current value `u/alice/ticket/1` to `u/bob/ticket/1`. Is this what you want? [Yes/no] y

        The merge now requires manual conflict resolution::

            sage: alice._chdir()
            sage: alice._UI.append("abort")
            sage: alice.merge("#1")
            Merging the remote branch `u/bob/ticket/1` into the local branch `ticket/2`.
            There was an error during the merge. Most probably there were conflicts when merging. The following should make it clear which files are affected:
            Auto-merging alice2
            CONFLICT (add/add): Merge conflict in alice2
            Please fix conflicts in the affected files (in a different terminal) and type 'resolved'. Or type 'abort' to abort the merge. [resolved/abort] abort
            sage: alice._UI.append("resolved")
            sage: alice.merge("#1")
            Merging the remote branch `u/bob/ticket/1` into the local branch `ticket/2`.
            There was an error during the merge. Most probably there were conflicts when merging. The following should make it clear which files are affected:
            Auto-merging alice2
            CONFLICT (add/add): Merge conflict in alice2
            Please fix conflicts in the affected files (in a different terminal) and type 'resolved'. Or type 'abort' to abort the merge. [resolved/abort] resolved

        We cannot merge a ticket into itself::

            sage: alice.merge(2)
            ValueError: cannot merge a ticket into itself

        """
        try:
            self.reset_to_clean_state()
            self.reset_to_clean_working_directory()
        except OperationCancelledError:
            self._UI.error("Cannot merge because working directory is not in a clean state.")
            raise OperationCancelledError("working directory not clean")

        from git_error import DetachedHeadError
        try:
            current_branch = self.git.current_branch()
        except DetachedHeadError:
            self._UI.error("You are currently not on any branch. Use `{0}` or `{1}` to switch to a branch.".format(self._format_command("switch_branch"), self._format_command("switch_ticket")))
            raise OperationCancelledError("detached head")

        current_ticket = self._current_ticket()

        ticket = None
        branch = None
        remote_branch = None

        if self._is_ticket_name(ticket_or_branch):
            ticket = self._ticket_from_ticket_name(ticket_or_branch)
            if ticket == current_ticket:
                raise SageDevValueError("cannot merge a ticket into itself")
            self._check_ticket_name(ticket, exists=True)
            if download is None:
                download = True
            if create_dependency is None:
                create_dependency = True
            if self._has_local_branch_for_ticket(ticket):
                branch = self._local_branch_for_ticket(ticket)
            if download:
                remote_branch = self.trac._branch_for_ticket(ticket)
                if remote_branch is None:
                    self._UI.error("Can not merge remote branch for #{0}. No branch has been set on the trac ticket.".format(ticket))
                    raise OperationCancelledError("remote branch not set on trac")
        elif self._is_local_branch_name(ticket_or_branch, exists=True):
            branch = ticket_or_branch
            if download is None:
                download = False
            if self._has_ticket_for_local_branch(branch):
                ticket = self._ticket_for_local_branch(branch)
                if create_dependency is None:
                    create_dependency = False
            else:
                if create_dependency:
                    raise SageDevValueError("Can not create a dependency to `{0}` because it is not associated to a ticket.".format(branch))
                create_dependency = False
            remote_branch = self._remote_branch_for_branch(branch)
        else:
            remote_branch = ticket_or_branch
            if download is None:
                download = True
            if download == False:
                raise SageDevValueError("download must be `True` for a remote branch")
            if create_dependency is None:
                create_dependency = False
            if create_dependency == True:
                raise SageDevValueError("Can not create a dependency to the remote branch `{0}`.".format(remote_branch))

        local_merge_branch = branch

        if download:
            assert remote_branch
            if not self._is_remote_branch_name(remote_branch, exists=True):
                self._UI.error("Can not merge remote branch `{0}`. It does not exist.".format(remote_branch))
                raise OperationCancelledError("no such branch")
            self._UI.show("Merging the remote branch `{0}` into the local branch `{1}`.".format(remote_branch, current_branch))
            self.git.super_silent.fetch(self.git._repository, remote_branch)
            local_merge_branch = 'FETCH_HEAD'
        else:
            assert branch
            self._UI.show("Merging the local branch `{0}` into the local branch `{1}`.".format(branch, current_branch))

        from git_error import GitError
        try:
            self.git.super_silent.merge(local_merge_branch)
        except GitError as e:
            try:
                lines = e.stdout.splitlines() + e.stderr.splitlines()
                lines = [line for line in lines if line != "Automatic merge failed; fix conflicts and then commit the result."]
                lines.insert(0, "There was an error during the merge. Most probably there were conflicts when merging. The following should make it clear which files are affected:")
                lines.append("Please fix conflicts in the affected files (in a different terminal) and type 'resolved'. Or type 'abort' to abort the merge.")
                if self._UI.select("\n".join(lines),['resolved','abort']) == 'resolved':
                    self.git.silent.commit(a=True, no_edit=True)
                    self._UI.info("Created a commit from your conflict resolution.")
                else:
                    raise OperationCancelledError("user requested")
            except Exception as e:
                self.git.reset_to_clean_state()
                self.git.reset_to_clean_working_directory()
                raise

        if create_dependency:
            assert ticket and current_ticket
            dependencies = list(self._dependencies_for_ticket(current_ticket))
            if ticket in dependencies:
                self._UI.info("Not recording dependency on #{0} because #{1} already depends on #{0}.".format(ticket, current_ticket))
            else:
                self._UI.show("Added dependency on #{0} to #{1}.".format(ticket, current_ticket))
                self._set_dependencies_for_ticket(current_ticket, dependencies+[ticket])

    def local_tickets(self, include_abandoned=False):
        r"""
        Print the tickets currently being worked on in your local
        repository.

        This function shows the branch names as well as the ticket numbers for
        all active tickets.  It also shows local branches that are not
        associated to ticket numbers.

        INPUT:

        - ``include_abandoned`` -- boolean (default: ``False``), whether to
          include abandoned branches.

        .. SEEALSO::

        - :meth:`abandon_ticket` -- hide tickets from this method.

        - :meth:`remote_status` -- also show status compared to the
          trac server.

        - :meth:`current_ticket` -- get the current ticket.

        TESTS:

        Create a doctest setup with a single user::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create some tickets::

            sage: dev.local_tickets()
            : master

            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            2
            sage: dev.local_tickets()
              : master
            #1: ticket/1
            #2: ticket/2

        """
        branches = self.git.local_branches()
        branches = [ branch for branch in branches if include_abandoned or not self._is_trash_name(branch) ]
        if not branches:
            return
        branches = [ "{0:>7}: {1}".format("#"+str(self._ticket_for_local_branch(branch)) if self._has_ticket_for_local_branch(branch) else "", branch) for branch in branches ]
        while all([branch.startswith(' ') for branch in branches]):
            branches = [branch[1:] for branch in branches]
        branches = sorted(branches)
        self._UI.show("\n".join(branches))

    def vanilla(self, release=SAGE_VERSION):
        r"""
        Returns to an official release of Sage.

        INPUT:

        - ``release`` -- a string or decimal giving the release name.
          In fact, any tag, commit or branch will work.  If the tag
          does not exist locally an attempt to fetch it from the
          server will be made.

        Git equivalent::

            Checks out a given tag, commit or branch in detached head mode.

        .. SEEALSO::

        - :meth:`switch_ticket` -- switch to another branch, ready to
          develop on it.

        - :meth:`download` -- download a branch from the server and
          merge it.

        TESTS:

        Create a doctest setup with a single user::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Go to a sage release::

            sage: dev.git.current_branch()
            'master'
            sage: dev.vanilla()
            sage: dev.git.current_branch()
            Traceback (most recent call last):
            ...
            DetachedHeadError: unexpectedly, git is in a detached HEAD state

        """
        if hasattr(release, 'literal'):
            release = release.literal

        try:
            self.reset_to_clean_state()
            self.reset_to_clean_working_directory()
        except OperationCancelledError:
            self._UI.error("Cannot switch to a release while your working directory is not clean.")
            raise OperationCancelledError("working directory not clean")

        # we do not do any checking on the argument here, trying to be liberal
        # about what are valid inputs
        try:
            self.git.super_silent.checkout(release, detach=True)
        except GitError as e:
            try:
                self.git.super_silent.fetch(self.git._repository, release)
            except GitError as e:
                self._UI.error("`{0}` does not exist locally or on the remote server.".format(release))
                raise OperationCancelledError("no such tag/branch/...")

            self.git.super_silent.checkout('FETCH_HEAD', detach=True)

    def diff(self, base='commit'):
        r"""
        Show how the current file system differs from ``base``.

        INPUT:

        - ``base`` -- a string; show the differences against the latest
          ``'commit'`` (the default), against the branch ``'master'`` (or any
          other branch name), or the merge of the ``'dependencies'`` of the
          current ticket (if the dependencies merge cleanly)

        .. SEEALSO::

        - :meth:`commit` -- record changes into the repository.

        - :meth:`local_tickets` -- list local tickets (you may want to commit
          your changes to a branch other than the current one).

        TESTS:

        Create a doctest setup with a single user::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create some tickets and make one depend on the others::

            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("y")
            sage: dev.upload()
            The branch `u/doctest/ticket/1` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            2
            sage: UI.append("y")
            sage: dev.upload()
            The branch `u/doctest/ticket/2` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            3
            sage: UI.append("y")
            sage: dev.upload()
            The branch `u/doctest/ticket/3` does not exist on the remote server yet. Do you want to create the branch? [Yes/no] y
            sage: dev.merge("#1")
            Merging the remote branch `u/doctest/ticket/1` into the local branch `ticket/3`.
            Added dependency on #1 to #3.
            sage: dev.merge("#2")
            Merging the remote branch `u/doctest/ticket/2` into the local branch `ticket/3`.
            Added dependency on #2 to #3.

        Make some non-conflicting changes on the tickets::

            sage: dev.switch_ticket("#1")
            sage: with open("ticket1","w") as f: f.write("ticket1")
            sage: dev.git.silent.add("ticket1")
            sage: dev.git.super_silent.commit(message="added ticket1")

            sage: dev.switch_ticket("#2")
            sage: with open("ticket2","w") as f: f.write("ticket2")
            sage: dev.git.silent.add("ticket2")
            sage: dev.git.super_silent.commit(message="added ticket2")
            sage: UI.append("y")
            sage: dev.upload()
            I will now upload the following new commits to the remote branch `u/doctest/ticket/2`:
            ...: added ticket2
            Is this what you want? [Yes/no] y

            sage: dev.switch_ticket("#3")
            sage: open("ticket3","w").close()
            sage: dev.git.silent.add("ticket3")
            sage: dev.git.super_silent.commit(message="added ticket3")
            sage: UI.append("y")
            sage: dev.upload()
            I will now upload the following new commits to the remote branch `u/doctest/ticket/3`:
            ...: added ticket3
            Is this what you want? [Yes/no] y
            Uploading your dependencies for ticket #3: `` => `#1, #2`

        A diff against the previous commit::

            sage: dev.diff()

        A diff against a ticket will always take the branch on trac::

            sage: dev.diff("#1")
            diff --git a/ticket3 b/ticket3
            new file mode ...
            index ...
            sage: dev.diff("ticket/1")
            diff --git a/ticket1 b/ticket1
            deleted file mode ...
            index ...
            diff --git a/ticket3 b/ticket3
            new file mode ...
            index ...
            sage: dev.switch_ticket("#1")
            sage: UI.append("y")
            sage: dev.upload()
            I will now upload the following new commits to the remote branch `u/doctest/ticket/1`:
            ...: added ticket1
            Is this what you want? [Yes/no] y
            sage: dev.switch_ticket("#3")
            sage: dev.diff("#1")
            diff --git a/ticket1 b/ticket1
            deleted file mode ...
            index ...
            diff --git a/ticket3 b/ticket3
            new file mode ...
            index ...

        A diff against the dependencies::

            sage: dev.diff("dependencies")
            Dependency #1 has not been merged into `ticket/3` (at least not its latest version). Use `...` to merge it.
            Dependency #2 has not been merged into `ticket/3` (at least not its latest version). Use `...` to merge it.
            diff --git a/ticket1 b/ticket1
            deleted file mode ...
            index ...
            diff --git a/ticket2 b/ticket2
            deleted file mode ...
            index ...
            diff --git a/ticket3 b/ticket3
            new file mode ...
            index ...
            sage: dev.merge("#1")
            Merging the remote branch `u/doctest/ticket/1` into the local branch `ticket/3`.
            sage: dev.merge("#2")
            Merging the remote branch `u/doctest/ticket/2` into the local branch `ticket/3`.
            sage: dev.diff("dependencies")
            diff --git a/ticket3 b/ticket3
            new file mode ...
            index ...

        This does not work if the dependencies do not merge::

            sage: dev.switch_ticket("#1")
            sage: with open("ticket2","w") as f: f.write("foo")
            sage: dev.git.silent.add("ticket2")
            sage: dev.git.super_silent.commit(message="added ticket2")
            sage: UI.append("y")
            sage: dev.upload()
            I will now upload the following new commits to the remote branch `u/doctest/ticket/1`:
            ...: added ticket2
            Is this what you want? [Yes/no] y

            sage: dev.switch_ticket("#3")
            sage: dev.diff("dependencies")
            Dependency #1 has not been merged into `ticket/3` (at least not its latest version). Use `sage --dev merge --ticket=1` to merge it.
            #2 does not merge cleanly with the other dependencies. Your diff could not be computed.

        """
        if base == "dependencies":
            current_ticket = self._current_ticket()
            if current_ticket is None:
                raise SageDevValueError("'dependencies' are only supported if currently on a ticket.")

            try:
                self.reset_to_clean_state()
                self.reset_to_clean_working_directory()
            except OperationCancelledError:
                self._UI.error("Cannot create merge of dependencies because working directory is not clean.")
                raise

            branch = self.git.current_branch()
            temporary_branch = self._new_local_branch_for_trash("diff")
            self.git.super_silent.branch(temporary_branch, MASTER_BRANCH)
            try:
                self.git.super_silent.checkout(temporary_branch)
                try:
                    self._UI.info("Merging dependencies of #{0}.".format(current_ticket))
                    for dependency in self._dependencies_for_ticket(current_ticket):
                        self._check_ticket_name(dependency, exists=True)
                        remote_branch = self.trac._branch_for_ticket(dependency)
                        if remote_branch is None:
                            raise SageDevValueError("Dependency #{0} has no branch field set.".format(dependency))
                        self._check_remote_branch_name(remote_branch, exists=True)
                        self.git.super_silent.fetch(self.git._repository, remote_branch)
                        if self.git.is_child_of(MASTER_BRANCH, 'FETCH_HEAD'):
                            self._UI.info("Dependency #{0} has already been merged into the master branch.".format(dependency))
                        else:
                            if not self.git.is_child_of(branch, 'FETCH_HEAD'):
                                self._UI.warning("Dependency #{0} has not been merged into `{1}` (at least not its latest version). Use `{2}` to merge it.".format(dependency, branch, self._format_command("merge",ticket_or_branch="{0}".format(dependency))))
                            from git_error import GitError
                            try:
                                self.git.super_silent.merge('FETCH_HEAD')
                            except GitError as e:
                                self._UI.error("#{0} does not merge cleanly with the other dependencies. Your diff could not be computed.".format(dependency))
                                raise OperationCancelledError("merge failed")

                    self.git.echo.diff("{0}..{1}".format(temporary_branch, branch))
                    return
                finally:
                    self.git.reset_to_clean_state()
                    self.git.reset_to_clean_working_directory()
                    self.git.super_silent.checkout(branch)
            finally:
                self.git.super_silent.branch("-D", temporary_branch)

        if base == "commit":
            base = "HEAD"
        else:
            if self._is_ticket_name(base):
                ticket = self._ticket_from_ticket_name(base)
                self._check_ticket_name(ticket, exists=True)
                base = self.trac._branch_for_ticket(ticket)
                if base is None:
                    self._UI.error("Ticket #{0} has no branch set on trac.".format(ticket))

            if self._is_local_branch_name(base, exists=True):
                pass
            else:
                self._check_remote_branch_name(base, exists=True)
                self.git.super_silent.fetch(self.git._repository, base)
                base = 'FETCH_HEAD'

        self.git.echo.diff(base)

    def show_dependencies(self, ticket=None, all=False, _seen=None): # all = recursive
        r"""
        Show the dependencies of ``ticket``.

        INPUT:

        - ``ticket`` -- a string or integer identifying a ticket or ``None``
          (default: ``None``), the ticket for which dependencies are displayed.
          If ``None``, then the dependencies for the current ticket are
          displayed.

        - ``all`` -- boolean (default: ``True``), whether to recursively list
          all tickets on which this ticket depends (in depth-first order), only
          including tickets that have a local branch.

        .. NOTE::

            Ticket dependencies are stored locally and only updated with
            respect to the remote server during :meth:`upload` and
            :meth:`download`.

        .. SEEALSO::

        - :meth:`TracInterface.dependencies` -- Query Trac to find
          dependencies.

        - :meth:`remote_status` -- will show the status of tickets
          with respect to the remote server.

        - :meth:`merge` -- Merge in changes from a dependency.

        - :meth:`diff` -- Show the changes in this branch over the
          dependencies.

        TESTS::

        Create a doctest setup with a single user::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create some tickets and add dependencies::

            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            2
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            3
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            4

            sage: dev.merge('ticket/2',create_dependency=True)
            Merging the local branch `ticket/2` into the local branch `ticket/4`.
            Added dependency on #2 to #4.
            sage: dev.merge('ticket/3',create_dependency=True)
            Merging the local branch `ticket/3` into the local branch `ticket/4`.
            Added dependency on #3 to #4.
            sage: dev.switch_ticket('#2')
            sage: dev.merge('ticket/1', create_dependency=True)
            Merging the local branch `ticket/1` into the local branch `ticket/2`.
            Added dependency on #1 to #2.
            sage: dev.switch_ticket('#3')
            sage: dev.merge('ticket/1', create_dependency=True)
            Merging the local branch `ticket/1` into the local branch `ticket/3`.
            Added dependency on #1 to #3.

        Check that the dependencies show correctly::

            sage: dev.switch_ticket('#4')
            sage: dev.show_dependencies()
            Ticket #4 depends on #2, #3.
            sage: dev.show_dependencies('#4')
            Ticket #4 depends on #2, #3.
            sage: dev.show_dependencies('#3')
            Ticket #3 depends on #1.
            sage: dev.show_dependencies('#2')
            Ticket #2 depends on #1.
            sage: dev.show_dependencies('#1')
            Ticket #1 has no dependencies.
            sage: dev.show_dependencies('#4', all=True)
            Ticket #4 depends on #3, #1, #2.

        """
        if ticket is None:
            ticket = self._current_ticket()

        if ticket is None:
            raise SageDevValueError("ticket must be specified")

        self._check_ticket_name(ticket)
        ticket = self._ticket_from_ticket_name(ticket)

        if not self._has_local_branch_for_ticket(ticket):
            raise SageDevValueError("ticket must be a ticket with a local branch. Use `{0}` to download the ticket first.".format(self._format_command("switch_ticket",ticket=ticket)))

        branch = self._local_branch_for_ticket(ticket)
        if all:
            ret = []
            stack = [ticket]
            while stack:
                t = stack.pop()
                if t in ret: continue
                ret.append(t)
                if not self._has_local_branch_for_ticket(t):
                    self._UI.warning("no local branch for ticket #{0} present, some dependencies might be missing in the output.".format(t))
                    continue
                deps = self._dependencies_for_ticket(t)
                for d in deps:
                    if d not in stack and d not in ret:
                        stack.append(d)
            ret = ret[1:]
        else:
            ret = self._dependencies_for_ticket(ticket)

        if ret:
            self._UI.show("Ticket #{0} depends on {1}.".format(ticket,", ".join(["#{0}".format(d) for d in ret])))
        else:
            self._UI.show("Ticket #{0} has no dependencies.".format(ticket))

    def _detect_patch_diff_format(self, lines):
        r"""
        Determine the format of the ``diff`` lines in ``lines``.

        INPUT:

        - ``lines`` -- a list of strings

        OUTPUT:

        Either ``git`` (for ``diff --git`` lines) or ``hg`` (for ``diff -r`` lines).

        .. NOTE::

            Most Sage developpers have configured mercurial to export
            patches in git format.

        TESTS::

            sage: dev = dev._sagedev
            sage: dev._detect_patch_diff_format(
            ....:     ["diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py"])
            'hg'
            sage: dev._detect_patch_diff_format(
            ....:     ["diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi"])
            'git'

            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: dev._detect_patch_diff_format(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","trac_8703-trees-fh.patch"
            ....:         )).read().splitlines())
            'git'
            sage: dev._detect_patch_diff_format(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","diff.patch"
            ....:         )).read().splitlines())
            'hg'

            sage: dev._detect_patch_diff_format(["# HG changeset patch"])
            Traceback (most recent call last):
            ...
            NotImplementedError: Failed to detect diff format.
            sage: dev._detect_patch_diff_format(
            ... ["diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py",
            ...  "diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi"])
            Traceback (most recent call last):
            ...
            SageDevValueError: File appears to have mixed diff formats.

        """
        format = None
        regexs = { "hg" : HG_DIFF_REGEX, "git" : GIT_DIFF_REGEX }

        for line in lines:
            for name,regex in regexs.items():
                if regex.match(line):
                    if format is None:
                        format = name
                    if format != name:
                        raise SageDevValueError("File appears to have mixed diff formats.")

        if format is None:
            raise NotImplementedError("Failed to detect diff format.")
        else:
            return format

    def _detect_patch_path_format(self, lines, diff_format = None):
        r"""
        Determine the format of the paths in the patch given in ``lines``.

        INPUT:

        - ``lines`` -- a list (or iterable) of strings

        - ``diff_format`` -- ``'hg'``,``'git'``, or ``None`` (default:
          ``None``), the format of the ``diff`` lines in the patch. If
          ``None``, the format will be determined by
          :meth:`_detect_patch_diff_format`.

        OUTPUT:

        A string, ``'new'`` (new repository layout) or ``'old'`` (old
        repository layout).

        EXAMPLES::

            sage: dev._wrap("_detect_patch_path_format", require_cwd=False)
            sage: dev._detect_patch_path_format(
            ....:     ["diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py"])
            'old'
            sage: dev._detect_patch_path_format(
            ....:     ["diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py"],
            ....:     diff_format="git")
            Traceback (most recent call last):
            ...
            NotImplementedError: Failed to detect path format.
            sage: dev._detect_patch_path_format(
            ....:     ["diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi"])
            'old'
            sage: dev._detect_patch_path_format(
            ....:     ["diff --git a/src/sage/rings/padics/FM_template.pxi b/src/sage/rings/padics/FM_template.pxi"])
            'new'
            sage: dev._detect_patch_path_format(
            ....:     ["rename to sage/rings/number_field/totallyreal.pyx"], diff_format='hg')
            'old'
            sage: dev._detect_patch_path_format(
            ....:     ["rename from src/sage/rings/number_field/totalyreal.pyx"], diff_format='git')
            'new'

            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: dev._detect_patch_path_format(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","trac_8703-trees-fh.patch"
            ....:         )).read().splitlines())
            'old'

        """
        lines = list(lines)
        if diff_format is None:
            diff_format = self._detect_patch_diff_format(lines)

        path_format = None

        if diff_format == "git":
            diff_regexs = (GIT_DIFF_REGEX, PM_DIFF_REGEX, MV_DIFF_REGEX)
        elif diff_format == "hg":
            diff_regexs = (HG_DIFF_REGEX, PM_DIFF_REGEX, MV_DIFF_REGEX)
        else:
            raise NotImplementedError(diff_format)

        regexs = { "old" : HG_PATH_REGEX, "new" : GIT_PATH_REGEX }

        for line in lines:
            for regex in diff_regexs:
                match = regex.match(line)
                if match:
                    for group in match.groups():
                        for name, regex in regexs.items():
                            if regex.match(group):
                                if path_format is None:
                                    path_format = name
                                if path_format != name:
                                    raise SageDevValueError("File appears to have mixed path formats.")

        if path_format is None:
            raise NotImplementedError("Failed to detect path format.")
        else:
           return path_format

    def _rewrite_patch_diff_paths(self, lines, to_format, from_format=None, diff_format=None):
        r"""
        Rewrite the ``diff`` lines in ``lines`` to use ``to_format``.

        INPUT:

        - ``lines`` -- a list or iterable of strings

        - ``to_format`` -- ``'old'`` or ``'new'``

        - ``from_format`` -- ``'old'``, ``'new'``, or ``None`` (default:
          ``None``), the current formatting of the paths; detected
          automatically if ``None``

        - ``diff_format`` -- ``'git'``, ``'hg'``, or ``None`` (default:
          ``None``), the format of the ``diff`` lines; detected automatically
          if ``None``

        OUTPUT:

        A list of string, ``lines`` rewritten to conform to ``lines``.

        EXAMPLES:

        Paths in the old format::

            sage: dev._wrap("_rewrite_patch_diff_paths", require_cwd=False)
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py'],
            ....:     to_format="old")
            ['diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi'],
            ....:     to_format="old")
            ['diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['--- a/sage/rings/padics/pow_computer_ext.pxd',
            ....:      '+++ b/sage/rings/padics/pow_computer_ext.pxd'],
            ....:     to_format="old", diff_format="git")
            ['--- a/sage/rings/padics/pow_computer_ext.pxd',
             '+++ b/sage/rings/padics/pow_computer_ext.pxd']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py'],
            ....:     to_format="new")
            ['diff -r 1492e39aff50 -r 5803166c5b11 src/sage/schemes/elliptic_curves/ell_rational_field.py']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi'],
            ....:     to_format="new")
            ['diff --git a/src/sage/rings/padics/FM_template.pxi b/src/sage/rings/padics/FM_template.pxi']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['--- a/sage/rings/padics/pow_computer_ext.pxd',
            ....:      '+++ b/sage/rings/padics/pow_computer_ext.pxd'],
            ....:     to_format="new", diff_format="git")
            ['--- a/src/sage/rings/padics/pow_computer_ext.pxd',
             '+++ b/src/sage/rings/padics/pow_computer_ext.pxd']

        Paths in the new format::

            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff -r 1492e39aff50 -r 5803166c5b11 src/sage/schemes/elliptic_curves/ell_rational_field.py'],
            ....:     to_format="old")
            ['diff -r 1492e39aff50 -r 5803166c5b11 sage/schemes/elliptic_curves/ell_rational_field.py']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff --git a/src/sage/rings/padics/FM_template.pxi b/src/sage/rings/padics/FM_template.pxi'],
            ....:     to_format="old")
            ['diff --git a/sage/rings/padics/FM_template.pxi b/sage/rings/padics/FM_template.pxi']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['--- a/src/sage/rings/padics/pow_computer_ext.pxd',
            ....:      '+++ b/src/sage/rings/padics/pow_computer_ext.pxd'],
            ....:     to_format="old", diff_format="git")
            ['--- a/sage/rings/padics/pow_computer_ext.pxd',
             '+++ b/sage/rings/padics/pow_computer_ext.pxd']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff -r 1492e39aff50 -r 5803166c5b11 src/sage/schemes/elliptic_curves/ell_rational_field.py'],
            ....:     to_format="new")
            ['diff -r 1492e39aff50 -r 5803166c5b11 src/sage/schemes/elliptic_curves/ell_rational_field.py']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['diff --git a/src/sage/rings/padics/FM_template.pxi b/src/sage/rings/padics/FM_template.pxi'],
            ....:     to_format="new")
            ['diff --git a/src/sage/rings/padics/FM_template.pxi b/src/sage/rings/padics/FM_template.pxi']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['--- a/src/sage/rings/padics/pow_computer_ext.pxd',
            ....:      '+++ b/src/sage/rings/padics/pow_computer_ext.pxd'],
            ....:     to_format="new", diff_format="git")
            ['--- a/src/sage/rings/padics/pow_computer_ext.pxd',
             '+++ b/src/sage/rings/padics/pow_computer_ext.pxd']

            sage: dev._rewrite_patch_diff_paths(
            ....:     ['rename from sage/combinat/crystals/letters.py',
            ....:      'rename to sage/combinat/crystals/letters.pyx'],
            ....:     to_format="new", diff_format="hg")
            ['rename from src/sage/combinat/crystals/letters.py',
             'rename to src/sage/combinat/crystals/letters.pyx']
            sage: dev._rewrite_patch_diff_paths(
            ....:     ['rename from src/sage/combinat/crystals/letters.py',
            ....:      'rename to src/sage/combinat/crystals/letters.pyx'],
            ....:     to_format="old", diff_format="git")
            ['rename from sage/combinat/crystals/letters.py',
             'rename to sage/combinat/crystals/letters.pyx']

            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: result = dev._rewrite_patch_diff_paths(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","trac_8703-trees-fh.patch"
            ....:         )).read().splitlines(),
            ....:     to_format="new", diff_format="git")
            sage: len(result)
            2980
            sage: result[0]
            '#8703: Enumerated sets and data structure for ordered and binary trees'
            sage: result[12]
            'diff --git a/src/doc/en/reference/combinat/index.rst b/src/doc/en/reference/combinat/index.rst'

        """
        lines = list(lines)
        if diff_format is None:
            diff_format = self._detect_patch_diff_format(lines)

        if from_format is None:
            from_format = self._detect_patch_path_format(lines, diff_format=diff_format)

        if to_format == from_format:
            return lines

        def hg_path_to_git_path(path):
            if any([path.startswith(p) for p in "module_list.py","setup.py","c_lib/","sage/","doc/"]):
                return "src/%s"%path
            else:
                raise NotImplementedError("mapping hg path `%s`"%path)

        def git_path_to_hg_path(path):
            if any([path.startswith(p) for p in "src/module_list.py","src/setup.py","src/c_lib/","src/sage/","src/doc/"]):
                return path[4:]
            else:
                raise NotImplementedError("mapping git path `%s`"%path)

        def apply_replacements(lines, diff_regexs, replacement):
            ret = []
            for line in lines:
                for diff_regex in diff_regexs:
                    m = diff_regex.match(line)
                    if m:
                        line = line[:m.start(1)] + ("".join([ line[m.end(i-1):m.start(i)]+replacement(m.group(i)) for i in range(1,m.lastindex+1) ])) + line[m.end(m.lastindex):]
                ret.append(line)
            return ret

        diff_regex = None
        if diff_format == "hg":
            diff_regex = (HG_DIFF_REGEX, PM_DIFF_REGEX, MV_DIFF_REGEX)
        elif diff_format == "git":
            diff_regex = (GIT_DIFF_REGEX, PM_DIFF_REGEX, MV_DIFF_REGEX)
        else:
            raise NotImplementedError(diff_format)

        if from_format == "old":
            return self._rewrite_patch_diff_paths(apply_replacements(lines, diff_regex, hg_path_to_git_path), from_format="new", to_format=to_format, diff_format=diff_format)
        elif from_format == "new":
            if to_format == "old":
                return apply_replacements(lines, diff_regex, git_path_to_hg_path)
            else:
                raise NotImplementedError(to_format)
        else:
            raise NotImplementedError(from_format)

    def _detect_patch_header_format(self, lines):
        r"""
        Detect the format of the patch header in ``lines``.

        INPUT:

        - ``lines`` -- a list (or iterable) of strings

        OUTPUT:

        A string, ``'hg-export'`` (mercurial export header), ``'hg'``
        (mercurial header), ``'git'`` (git mailbox header), ``'diff'`` (no
        header)

        EXAMPLES::

            sage: dev._wrap("_detect_patch_header_format", require_cwd=False)
            sage: dev._detect_patch_header_format(
            ... ['# HG changeset patch','# Parent 05fca316b08fe56c8eec85151d9a6dde6f435d46'])
            'hg'
            sage: dev._detect_patch_header_format(
            ... ['# HG changeset patch','# User foo@bar.com'])
            'hg-export'
            sage: dev._detect_patch_header_format(
            ... ['From: foo@bar'])
            'git'

            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: dev._detect_patch_header_format(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","trac_8703-trees-fh.patch"
            ....:         )).read().splitlines())
            'diff'
            sage: dev._detect_patch_header_format(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","diff.patch"
            ....:         )).read().splitlines())
            'diff'
        """
        lines = list(lines)
        if not lines:
            raise SageDevValueError("patch is empty")

        if HG_HEADER_REGEX.match(lines[0]):
            if HG_USER_REGEX.match(lines[1]):
                return "hg-export"
            elif HG_PARENT_REGEX.match(lines[1]):
                return "hg"
        elif GIT_FROM_REGEX.match(lines[0]):
            return "git"

        return "diff"

    def _detect_patch_modified_files(self, lines, diff_format = None):
        r"""
        Return a list of files which are modified by the patch in ``lines``.

        TESTS::

            sage: dev._wrap("_detect_patch_modified_files", require_cwd=False)
            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: dev._detect_patch_modified_files(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","trac_8703-trees-fh.patch"
            ....:         )).read().splitlines())
            ['ordered_tree.py', 'binary_tree.pyx', 'list_clone.pyx', 'permutation.py', 'index.rst', 'abstract_tree.py', 'all.py', 'binary_tree.py']

        """
        if diff_format is None:
            diff_format = self._detect_patch_diff_format(lines)

        if diff_format == "hg":
            regex = HG_DIFF_REGEX
        elif diff_format == "git":
            regex = GIT_DIFF_REGEX
        else:
            raise NotImplementedError(diff_format)

        ret = set()
        for line in lines:
            m = regex.match(line)
            if m:
                for group in m.groups():
                    split = group.split('/')
                    if split:
                        ret.add(split[-1])
        return list(ret)

    def _rewrite_patch_header(self, lines, to_format, from_format = None, diff_format = None):
        r"""
        Rewrite ``lines`` to match ``to_format``.

        INPUT:

        - ``lines`` -- a list of strings, the lines of the patch file

        - ``to_format`` -- one of ``'hg'``, ``'hg-export'``, ``'diff'``,
          ``'git'``, the format of the resulting patch file.

        - ``from_format`` -- one of ``None``, ``'hg'``, ``'hg-export'``, ``'diff'``, ``'git'``
          (default: ``None``), the format of the patch file.  The format is
          determined automatically if ``format`` is ``None``.

        OUTPUT:

        A list of lines, in the format specified by ``to_format``.

        Some sample patch files are in data/, in hg and git
        format. Since the translation is not perfect, the resulting
        file is also put there for comparison.

        EXAMPLES::

            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: hg_lines = open(
            ....:     os.path.join(SAGE_SRC, "sage", "dev", "test", "data", "hg.patch")
            ....:     ).read().splitlines()
            sage: hg_output_lines = open(
            ....:     os.path.join(SAGE_SRC, "sage", "dev", "test", "data", "hg-output.patch")
            ....:     ).read().splitlines()
            sage: git_lines = open(
            ....:     os.path.join(SAGE_SRC, "sage", "dev", "test", "data", "git.patch")
            ....:     ).read().splitlines()
            sage: git_output_lines = open(
            ....:     os.path.join(SAGE_SRC, "sage", "dev", "test", "data", "git-output.patch")
            ....:     ).read().splitlines()

            sage: dev._wrap("_rewrite_patch_header", require_cwd=False)
            sage: dev._rewrite_patch_header(git_lines, 'git') == git_lines
            True
            sage: dev._rewrite_patch_header(hg_lines, 'hg-export') == hg_lines
            True

            sage: dev._rewrite_patch_header(git_lines, 'hg-export') == hg_output_lines
            True
            sage: dev._rewrite_patch_header(hg_lines, 'git') == git_output_lines
            True

            sage: dev._rewrite_patch_header(
            ....:     open(os.path.join(
            ....:             SAGE_SRC,"sage","dev","test","data","trac_8703-trees-fh.patch"
            ....:         )).read().splitlines(), 'git')[:5]
            ['From: "Unknown User" <unknown@sagemath.org>',
            'Subject: #8703: Enumerated sets and data structure for ordered and binary trees',
            'Date: ...',
            '',
            '- The Class Abstract[Labelled]Tree allows for inheritance from different']
        """
        import email.utils, time

        lines = list(lines)
        if not lines:
            raise SageDevValueError("empty patch file")

        if from_format is None:
            from_format = self._detect_patch_header_format(lines)

        if from_format == to_format:
            return lines

        def parse_header(lines, regexs, mandatory=False):
            header = {}
            i = 0
            for (key, regex) in regexs:
                if i > len(lines):
                    if mandatory:
                        raise SageDevValueError("Malformed patch. Missing line for regular expression `%s`."%(regex.pattern))
                    else:
                        return
                match = regex.match(lines[i])
                if match is not None:
                    if len(match.groups()) > 0:
                        header[key] = match.groups()[0]
                    i += 1
                elif mandatory:
                    raise SageDevValueError("Malformed patch. Line `%s` does not match regular expression `%s`."%(lines[i],regex.pattern))

            message = []
            for i in range(i,len(lines)):
                if lines[i].startswith("diff -"):
                    break
                else:
                    message.append(lines[i])

            header["message"] = message
            return header, lines[i:]

        if from_format == "git":
            header, diff = parse_header(lines, (("user", GIT_FROM_REGEX), ("subject", GIT_SUBJECT_REGEX), ("date", GIT_DATE_REGEX)),
                                        mandatory=True)

            if to_format == "hg-export":
                ret = []
                ret.append('# HG changeset patch')
                ret.append('# User %s'%(header["user"]))
                import os
                old_TZ = os.environ.get('TZ')
                try:
                    os.environ['TZ'] = 'UTC'
                    time.tzset()
                    ret.append('# Date %s 00000'%int(time.mktime(email.utils.parsedate(header["date"])))) # this is not portable
                finally:
                    if old_TZ:
                        os.environ['TZ'] = old_TZ
                    else:
                        del os.environ['TZ']
                    time.tzset()
                ret.append('# Node ID 0000000000000000000000000000000000000000')
                ret.append('# Parent  0000000000000000000000000000000000000000')
                ret.append(header["subject"])
                ret.extend(header["message"])
                ret.extend(diff)
                return ret
            else:
                raise NotImplementedError(to_format)
        elif from_format in ["hg", "diff", "hg-export"]:
            header, diff = parse_header(lines,
                                        (("hg_header", HG_HEADER_REGEX),
                                         ("user", HG_USER_REGEX),
                                         ("date", HG_DATE_REGEX),
                                         ("node", HG_NODE_REGEX),
                                         ("parent", HG_PARENT_REGEX)))
            user    = header.get("user", '"Unknown User" <unknown@sagemath.org>')
            date    = email.utils.formatdate(int(header.get("date", time.time())))
            message = header.get("message", [])
            if message:
                subject = message[0]
                message = message[1:]
            else:
                subject = 'No Subject. Modified: %s'%(", ".join(sorted(self._detect_patch_modified_files(lines))))
            ret = []
            ret.append('From: %s'%user)
            ret.append('Subject: %s'%subject)
            ret.append('Date: %s'%date)
            ret.append('')
            if message and message != ['']: # avoid a double empty line
                ret.extend(message)
            ret.extend(diff)
            return self._rewrite_patch_header(ret, to_format=to_format, from_format="git", diff_format=diff_format)
        else:
            raise NotImplementedError(from_format)

    def _rewrite_patch(self, lines, to_path_format, to_header_format, from_diff_format=None, from_path_format=None, from_header_format=None):
        r"""
        Rewrite the patch in ``lines`` to the path format given in
        ``to_path_format`` and the header format given in ``to_header_format``.

        TESTS::

            sage: dev._wrap("_rewrite_patch", require_cwd=False)
            sage: import os.path
            sage: from sage.env import SAGE_SRC
            sage: git_lines = open(
            ....:     os.path.join(SAGE_SRC, "sage", "dev", "test", "data", "git.patch")
            ....:     ).read().splitlines()
            sage: dev._rewrite_patch(git_lines, "old", "git") == git_lines
            True

        """
        return self._rewrite_patch_diff_paths(self._rewrite_patch_header(lines, to_format=to_header_format, from_format=from_header_format, diff_format=from_diff_format), to_format=to_path_format, diff_format=from_diff_format, from_format=from_path_format)

    def upload_ssh_key(self, public_key=None):
        r"""
        Upload ``public_key`` to gitolite through the trac interface.

        INPUT:

        - ``public_key`` -- a string or ``None`` (default: ``None``), the path
          of the key file, defaults to ``~/.ssh/id_rsa.pub`` (or
          ``~/.ssh/id_dsa.pub`` if it exists).

        TESTS:

        Create a doctest setup with a single user::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()

        Create and upload a key file::

            sage: import os
            sage: public_key = os.path.join(dev._sagedev.tmp_dir,"id_rsa.pub")
            sage: UI.append("no")
            sage: UI.append("yes")
            sage: dev.upload_ssh_key(public_key=public_key)
            I will now upload your ssh key at `...` to trac. This will enable access to the git repository there. Is this what you want? [Yes/no] yes
            I could not find a public key at `{0}`. Do you want me to create one for you? [Yes/no] no
            sage: UI.append("yes")
            sage: UI.append("yes")
            sage: dev.upload_ssh_key(public_key=public_key)
            I will now upload your ssh key at `...` to trac. This will enable access to the git repository there. Is this what you want? [Yes/no] yes
            I could not find a public key at `{0}`. Do you want me to create one for you? [Yes/no] yes
            Generating ssh key.
            Your key has been uploaded.
            sage: UI.append("yes")
            sage: dev.upload_ssh_key(public_key=public_key)
            I will now upload your ssh key at `...` to trac. This will enable access to the git repository there. Is this what you want? [Yes/no] yes
            Your key has been uploaded.

        """
        try:
            import os
            if public_key is None:
                public_key = os.path.expanduser("~/.ssh/id_dsa.pub")
                if not os.path.exists(public_key):
                    public_key = os.path.expanduser("~/.ssh/id_rsa.pub")

            if not self._UI.confirm("I will now upload your ssh key at `{0}` to trac. This will enable access to the git repository there. Is this what you want?".format(public_key), default=True):
                raise OperationCancelledError("do not upload key")

            if not os.path.exists(public_key):
                if not public_key.endswith(".pub"):
                    raise SageDevValueError("public key must end with `.pub`.")

                if not self._UI.confirm("I could not find a public key at `{0}`. Do you want me to create one for you?", default=True):
                    raise OperationCancelledError("no keyfile found")

                private_key = public_key[:-4]
                self._UI.show("Generating ssh key.")
                from subprocess import call
                success = call(["ssh-keygen", "-q", "-f", private_key, "-P", ""])
                if success == 0:
                    self._UI.info("Key generated.")
                else:
                    self._UI.error("Key generation failed.")
                    self._UI.info("Please create a key in `{0}` and retry.".format(public_key))
                    raise OperationCancelledError("ssh-keygen failed")

            with open(public_key, 'r') as F:
                public_key = F.read().strip()

            self.trac._authenticated_server_proxy.sshkeys.addkey(public_key)
            self._UI.show("Your key has been uploaded.")
            self._UI.info("Use `{0}` to upload another key.".format(self._format_command("upload_ssh_key",public_key="keyfile.pub")))
        except OperationCancelledError:
            from sage.env import TRAC_SERVER_URI
            server = self.config.get('server', TRAC_SERVER_URI)

            import os, urllib, urllib, urlparse
            url = urlparse.urljoin(server, urllib.pathname2url(os.path.join('prefs', 'sshkeys')))
            self._UI.info("Use `{0}` to upload a public key. Or set your key manually at {1}.".format(self._format_command("upload_ssh_key"), url))
            raise

    def _is_ticket_name(self, name, exists=False):
        r"""
        Return whether ``name`` is a valid ticket name, i.e., an integer.

        INPUT:

        - ``name`` -- a string or an int

        - ``exists`` -- a boolean (default: ``False``), if ``True``, return
          whether ``name`` is the name of an existing ticket

        EXAMPLES::

            sage: dev = dev._sagedev
            sage: dev._is_ticket_name(1000)
            True
            sage: dev._is_ticket_name("1000")
            True
            sage: dev._is_ticket_name("1 000")
            False
            sage: dev._is_ticket_name("#1000")
            True
            sage: dev._is_ticket_name("master")
            False
            sage: dev._is_ticket_name(1000, exists=True) # optional: internet
            True
            sage: dev._is_ticket_name(2^30, exists=True) # optional: internet
            False
            sage: dev._is_ticket_name('')
            False

        """
        if name is None:
            return False

        if not isinstance(name, int):
            try:
                name = self._ticket_from_ticket_name(name)
            except SageDevValueError:
                return False

        if exists:
            try:
                self.trac._anonymous_server_proxy.ticket.get(name)
            except TracInternalError as e:
                if e.faultCode == 404: # ticket does not exist
                    return False
                raise
            except TracConnectionError as e:
                # if we cannot connect to trac, we assume that the ticket
                # exists; this makes more of the dev scripts usable in offline
                # scenarios
                pass

        return True

    def _check_ticket_name(self, name, exists=False):
        r"""
        Check that ``name`` is a valid ticket name.

        INPUT:

        - ``name`` -- a string or int

        - ``exists`` -- a boolean (default: ``False``), whether to check that
          the ticket exists on trac

        TESTS::

            sage: dev = dev._sagedev
            sage: dev._check_ticket_name(1000)
            sage: dev._check_ticket_name("1000")
            sage: dev._check_ticket_name("1 000")
            Traceback (most recent call last):
            ...
            SageDevValueError: `1 000` is not a valid ticket name.
            sage: dev._check_ticket_name("#1000")
            sage: dev._check_ticket_name("master")
            Traceback (most recent call last):
            ...
            SageDevValueError: `master` is not a valid ticket name.
            sage: dev._check_ticket_name(1000, exists=True) # optional: internet
            sage: dev._check_ticket_name(2^30, exists=True) # optional: internet
            Traceback (most recent call last):
            ...
            SageDevValueError: `1073741824` is not a valid ticket name or ticket does not exist on trac.

        """
        if not self._is_ticket_name(name, exists=exists):
            if exists:
                raise SageDevValueError("`{0}` is not a valid ticket name or ticket does not exist on trac.".format(name))
            else:
                raise SageDevValueError("`{0}` is not a valid ticket name.".format(name))

    def _ticket_from_ticket_name(self, name):
        r"""
        Return the ticket number for the ticket ``name``.

        EXAMPLES::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._ticket_from_ticket_name("1000")
            1000
            sage: dev._ticket_from_ticket_name("#1000")
            1000
            sage: dev._ticket_from_ticket_name(1000)
            1000
            sage: dev._ticket_from_ticket_name(int(1000))
            1000
            sage: dev._ticket_from_ticket_name("1 000")
            Traceback (most recent call last):
            ...
            SageDevValueError: `1 000` is not a valid ticket name.

        """
        ticket = name
        if not isinstance(ticket, int):
            if isinstance(ticket, str) and ticket and ticket[0] == "#":
                ticket = ticket[1:]
            try:
                ticket = int(ticket)
            except ValueError:
                raise SageDevValueError("`{0}` is not a valid ticket name.".format(name))

        if ticket < 0:
            raise SageDevValueError("`{0}` is not a valid ticket name.".format(name))

        return ticket

    def _is_local_branch_name(self, name, exists=any):
        r"""
        Return whether ``name`` is a valid name for a local branch.

        INPUT:

        - ``name`` -- a string

        - ``exists`` -- a boolean or ``any`` (default: ``any``), if ``True``,
          check whether ``name`` is the name of an existing local branch; if
          ``False``, check whether ``name`` is the name of a branch that does
          not exist yet.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._is_local_branch_name('')
            False
            sage: dev._is_local_branch_name('ticket/1')
            True
            sage: dev._is_local_branch_name('ticket/1', exists=True)
            False
            sage: dev._is_local_branch_name('ticket/1', exists=False)
            True
            sage: dev.git.silent.branch('ticket/1')
            sage: dev._is_local_branch_name('ticket/1', exists=True)
            True
            sage: dev._is_local_branch_name('ticket/1', exists=False)
            False

        """
        if not isinstance(name, str):
            raise ValueError("name must be a string")

        if not GIT_BRANCH_REGEX.match(name):
            return False
        # branches which could be tickets are calling for trouble - cowardly refuse to accept them
        if self._is_ticket_name(name):
            return False
        if name in ["None", "True", "False"]:
            return False

        if exists == True:
            return self.git.commit_for_branch(name) is not None
        elif exists == False:
            return self.git.commit_for_branch(name) is None
        elif exists is any:
            return True
        else:
            raise ValueError("exists")

    def _is_trash_name(self, name, exists=any):
        r"""
        Return whether ``name`` is a valid name for an abandoned branch.

        INPUT:

        - ``name`` -- a string

        - ``exists`` - a boolean or ``any`` (default: ``any``), if ``True``,
          check whether ``name`` is the name of an existing branch; if
          ``False``, check whether ``name`` is the name of a branch that does
          not exist yet.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._is_trash_name("branch1")
            False
            sage: dev._is_trash_name("trash")
            False
            sage: dev._is_trash_name("trash/")
            False
            sage: dev._is_trash_name("trash/1")
            True
            sage: dev._is_trash_name("trash/1", exists=True)
            False

        """
        if not isinstance(name, str):
            raise ValueError("name must be a string")

        if not name.startswith("trash/"):
            return False

        return self._is_local_branch_name(name, exists)

    def _is_stash_name(self, name, exists=any):
        r"""
        Return whether ``name`` is a valid name for a stash.

        INPUT:

        - ``name`` -- a string

        - ``exists`` - a boolean or ``any`` (default: ``any``), if ``True``,
          check whether ``name`` is the name of an existing stash; if
          ``False``, check whether ``name`` is the name of a stash that does
          not exist yet.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._is_stash_name("branch1")
            False
            sage: dev._is_stash_name("stash")
            False
            sage: dev._is_stash_name("stash/")
            False
            sage: dev._is_stash_name("stash/1")
            True
            sage: dev._is_stash_name("stash/1", exists=True)
            False

        """
        if not isinstance(name, str):
            raise ValueError("name must be a string")

        if not name.startswith("stash/"):
            return False

        return self._is_local_branch_name(name, exists)

    def _check_stash_name(self, name, exists=any):
        r"""
        Check whether ``name`` is a valid name for a stash.

        INPUT:

        - ``name`` -- a string

        - ``exists`` - a boolean or ``any`` (default: ``any``), if ``True``,
          check whether ``name`` is the name of an existing stash; if
          ``False``, check whether ``name`` is the name of a stash that does
          not exist yet.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._check_stash_name("stash/1")
            sage: dev._check_stash_name("stash/1", exists=True)
            Traceback (most recent call last):
            ...
            SageDevValueError: `stash/1` does not exist.
            sage: dev._check_stash_name("stash/1", exists=False)

        """
        if not self._is_stash_name(name):
            raise SageDevValueError("`{0}` is not a valid name for a stash.".format(name))
        if exists == True and not self._is_stash_name(name, exists):
            raise SageDevValueError("`{0}` does not exist.".format(name))
        elif exists == False and not self._is_stash_name(name, exists):
            raise SageDevValueError("`{0}` already exists, please choose a different name for the stash.")

    def _is_remote_branch_name(self, name, exists=any):
        r"""
        Return whether ``name`` is a valid name for a remote branch.

        INPUT:

        - ``name`` -- a string

        - ``exists`` -- a boolean or ``any`` (default: ``any``), if ``True``,
          check whether ``name`` is the name of an existing remote branch; if
          ``False``, check whether ``name`` is the name of a branch that does
          not exist yet.

        .. NOTE::

            Currently, this does not check whether name is in accordance with
            naming scheme configured on gitolite.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._is_remote_branch_name('')
            False
            sage: dev._is_remote_branch_name('ticket/1')
            True

            sage: dev._is_remote_branch_name('ticket/1', exists=True)
            False
            sage: dev._is_remote_branch_name('ticket/1', exists=False)
            True

        """
        if not isinstance(name, str):
            raise ValueError("name must be a string")

        if not GIT_BRANCH_REGEX.match(name):
            return False
        # branches which could be tickets are calling for trouble - cowardly refuse to accept them
        if self._is_ticket_name(name):
            return False

        if exists is any:
            return True

        from git_error import GitError
        try:
            self.git.super_silent.ls_remote(self.git._repository, name, exit_code=True)
            remote_exists = True
        except GitError as e:
            if e.exit_code == 2:
                remote_exists = False
            else:
                raise

        if exists == True or exists == False:
            return remote_exists == exists
        else:
            raise ValueError("exists")

    def _check_local_branch_name(self, name, exists=any):
        r"""
        Check whether ``name`` is a valid name for a local branch, raise a
        ``SageDevValueError`` if it is not.

        INPUT:

        same as for :meth:`_is_local_branch_name`

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._check_local_branch_name('')
            Traceback (most recent call last):
            ...
            SageDevValueError: `` is not a valid name for a local branch.
            sage: dev._check_local_branch_name('ticket/1')
            sage: dev._check_local_branch_name('ticket/1', exists=True)
            Traceback (most recent call last):
            ...
            SageDevValueError: Branch `ticket/1` does not exist locally.
            sage: dev._check_local_branch_name('ticket/1', exists=False)
            sage: dev.git.silent.branch('ticket/1')
            sage: dev._check_local_branch_name('ticket/1', exists=True)
            sage: dev._check_local_branch_name('ticket/1', exists=False)
            Traceback (most recent call last):
            ...
            SageDevValueError: Branch `ticket/1` already exists, please choose a different name.

        """
        try:
            if not self._is_local_branch_name(name, exists=any):
                raise SageDevValueError("caught below")
        except SageDevValueError:
            raise SageDevValueError("`{0}` is not a valid name for a local branch.".format(name))

        if exists == any:
            return
        elif exists == True:
            if not self._is_local_branch_name(name, exists=exists):
                raise SageDevValueError("Branch `{0}` does not exist locally.".format(name))
        elif exists == False:
            if not self._is_local_branch_name(name, exists=exists):
                raise SageDevValueError("Branch `{0}` already exists, please choose a different name.".format(name))
        else:
            assert False

    def _check_remote_branch_name(self, name, exists=any):
        r"""
        Check whether ``name`` is a valid name for a remote branch, raise a
        ``SageDevValueError`` if it is not.

        INPUT:

        same as for :meth:`_is_remote_branch_name`

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._check_remote_branch_name('')
            Traceback (most recent call last):
            ...
            SageDevValueError: `` is not a valid name for a remote branch.
            sage: dev._check_remote_branch_name('ticket/1')

            sage: dev._check_remote_branch_name('ticket/1', exists=True)
            Traceback (most recent call last):
            ...
            SageDevValueError: Branch `ticket/1` does not exist on the remote system.
            sage: dev._check_remote_branch_name('ticket/1', exists=False)

        """
        try:
            if not self._is_remote_branch_name(name, exists=any):
                raise SageDevValueError("caught below")
        except SageDevValueError:
            raise SageDevValueError("`{0}` is not a valid name for a remote branch.".format(name))

        if exists == any:
            return
        elif exists == True:
            if not self._is_remote_branch_name(name, exists=exists):
                raise SageDevValueError("Branch `{0}` does not exist on the remote system.".format(name))
        elif exists == False:
            if not self._is_remote_branch_name(name, exists=exists):
                raise SageDevValueError("Branch `{0}` already exists, please choose a different name.".format(name))
        else:
            assert False

    def _remote_branch_for_ticket(self, ticket):
        r"""
        Return the name of the remote branch for ``ticket``.

        INPUT:

        - ``ticket`` -- an int or a string identifying a ticket

        .. NOTE:

            This does not take into account the ``branch`` field of the ticket
            on trac.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/ticket/1'
            sage: dev._remote_branch_for_ticket("#1")
            'u/doctest/ticket/1'
            sage: dev._remote_branch_for_ticket("1")
            'u/doctest/ticket/1'
            sage: dev._remote_branch_for_ticket("master")
            Traceback (most recent call last):
            ...
            SageDevValueError: `master` is not a valid ticket name.

            sage: UI.append("Summary: summary1\ndescription")
            sage: ticket = dev.create_ticket()

            sage: dev._set_remote_branch_for_branch("ticket/1", "public/1")
            sage: dev._remote_branch_for_ticket(1)
            'public/1'
            sage: dev._set_remote_branch_for_branch("ticket/1", None)
            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/ticket/1'

        """
        ticket = self._ticket_from_ticket_name(ticket)

        default = "u/{0}/ticket/{1}".format(self.trac._username, ticket)

        try:
            branch = self._local_branch_for_ticket(ticket)
        except KeyError: # ticket has no branch yet
            return default

        ret = self._remote_branch_for_branch(branch)
        if ret is None:
            return default
        return ret

    def _ticket_for_local_branch(self, branch):
        r"""
        Return the ticket associated to the local ``branch``.

        INPUT:

        - ``branch`` -- a string, the name of a local branch

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: dev._sagedev._ticket_for_local_branch("ticket/1")
            1

        """
        self._check_local_branch_name(branch, exists=True)

        if not self._has_ticket_for_local_branch(branch):
            raise SageDevValueError("branch must be associated to a ticket")

        return self.__branch_to_ticket[branch]

    def _has_ticket_for_local_branch(self, branch):
        r"""
        Return whether ``branch`` is associated to a ticket.

        INPUT:

        - ``branch`` -- a string, the name of a local branch

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: UI.append("Summary: summary\ndescription")
            sage: dev.create_ticket()
            1
            sage: dev._sagedev._has_ticket_for_local_branch("ticket/1")
            True

        """
        self._check_local_branch_name(branch, exists=True)

        return branch in self.__branch_to_ticket

    def _has_local_branch_for_ticket(self, ticket):
        r"""
        Return whether there is a local branch for ``ticket``.

        INPUT:

        - ``ticket`` -- an int or a string identifying a ticket

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev._sagedev._has_local_branch_for_ticket(1)
            False

        """
        ticket = self._ticket_from_ticket_name(ticket)

        if ticket not in self.__ticket_to_branch:
            return False

        branch = self.__ticket_to_branch[ticket]
        if not self._is_local_branch_name(branch, exists=True):
            self._UI.warning("Ticket #{0} refers to the non-existant local branch `{1}`. If you have not manually interacted with git, then this is a bug in sagedev. Removing the association from ticket #{0} to branch `{1}`.".format(ticket, branch))
            del self.__ticket_to_branch[ticket]
            return False

        return True

    def _local_branch_for_ticket(self, ticket, download_if_not_found=False):
        r"""
        Return the name of the local branch for ``ticket``.

        INPUT:

        - ``ticket`` -- an int or a string identifying a ticket

        - ``download_if_not_found`` -- a boolean (default: ``False``), whether
          to attempt to download a branch for ``ticket`` from trac if it does
          not exist locally

        TESTS:

        Create a doctest setup with two users::

            sage: from sage.dev.test.sagedev import two_user_setup
            sage: alice, config_alice, bob, config_bob, server = two_user_setup()

        If a local branch for the ticket exists, its name is returned::

            sage: alice._chdir()
            sage: alice._UI.append("Summary: ticket1\ndescription")
            sage: ticket = alice.create_ticket()
            sage: alice._sagedev._local_branch_for_ticket(ticket)
            'ticket/1'

        If no local branch exists, the behaviour depends on ``download_if_not_found``::

            sage: bob._chdir()
            sage: bob._sagedev._local_branch_for_ticket(ticket)
            Traceback (most recent call last):
            ...
            KeyError: 'No branch for ticket #1 in your repository.'
            sage: bob._sagedev._local_branch_for_ticket(ticket, download_if_not_found=True)
            Traceback (most recent call last):
            ...
            SageDevValueError: Branch field is not set for ticket #1 on trac.
            sage: attributes = alice.trac._get_attributes(ticket)
            sage: attributes['branch'] = 'public/ticket/1'
            sage: alice.trac._authenticated_server_proxy.ticket.update(ticket, "", attributes)
            'https://trac.sagemath.org/ticket/1#comment:1'
            sage: bob._sagedev._local_branch_for_ticket(ticket, download_if_not_found=True)
            Traceback (most recent call last):
            ...
            SageDevValueError: Branch `public/ticket/1` does not exist on the remote system.

            sage: import os
            sage: os.chdir(server.git._config['src'])
            sage: server.git.silent.branch('public/ticket/1')
            sage: bob._chdir()
            sage: bob._sagedev._local_branch_for_ticket(ticket, download_if_not_found=True)
            'ticket/1'
            sage: bob._sagedev._local_branch_for_ticket(ticket)
            'ticket/1'

        """
        ticket = self._ticket_from_ticket_name(ticket)

        if self._has_local_branch_for_ticket(ticket):
            return self.__ticket_to_branch[ticket]

        if not download_if_not_found:
            raise KeyError("No branch for ticket #{0} in your repository.".format(ticket))

        branch = self._new_local_branch_for_ticket(ticket)
        self.download(ticket, branch)
        self._set_local_branch_for_ticket(ticket, branch)
        return self._local_branch_for_ticket(ticket, download_if_not_found=False)

    def _new_local_branch_for_trash(self, branch):
        r"""
        Return a new local branch name to trash ``branch``.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._new_local_branch_for_trash('branch')
            'trash/branch'
            sage: dev.git.silent.branch('trash/branch')
            sage: dev._new_local_branch_for_trash('branch')
            'trash/branch_'

        """
        while True:
            trash_branch = 'trash/{0}'.format(branch)
            if self._is_trash_name(trash_branch, exists=False):
                return trash_branch
            branch = branch + "_"

    def _new_local_branch_for_stash(self):
        r"""
        Return a new local branch name for a stash.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._new_local_branch_for_stash()
            'stash/1'
            sage: dev.git.silent.branch('stash/1')
            sage: dev._new_local_branch_for_stash()
            'stash/2'

        """
        i = 0
        while True:
            i+=1
            branch = 'stash/{0}'.format(i)
            if self._is_stash_name(branch, exists=False):
                return branch

    def _new_local_branch_for_ticket(self, ticket):
        r"""
        Return a local branch name for ``ticket`` which does not exist yet.

        INPUT:

        - ``ticket`` -- a string or an int identifying a ticket

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._new_local_branch_for_ticket(1)
            'ticket/1'
            sage: dev.git.silent.branch('ticket/1')
            sage: dev._new_local_branch_for_ticket(1)
            'ticket/1_'

        """
        ticket = self._ticket_from_ticket_name(ticket)

        branch = 'ticket/{0}'.format(ticket)

        while self._is_local_branch_name(branch, exists=True):
            branch = branch + "_"

        assert self._is_local_branch_name(branch, exists=False)

        return branch

    def _set_dependencies_for_ticket(self, ticket, dependencies):
        r"""
        Locally record ``dependencies`` for ``ticket``.

        INPUT:

        - ``ticket`` -- an int or string identifying a ticket

        - ``dependencies`` -- an iterable of ticket numbers or ``None`` for no
          dependencies

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: UI.append("Summary: ticket1\ndescription")
            sage: ticket = dev.create_ticket()
            sage: dev._set_dependencies_for_ticket(ticket, [2, 3])
            sage: dev._dependencies_for_ticket(ticket)
            (2, 3)
            sage: dev._set_dependencies_for_ticket(ticket, None)
            sage: dev._dependencies_for_ticket(ticket)
            ()

        """
        ticket = self._ticket_from_ticket_name(ticket)

        if dependencies is None:
            dependencies = []

        dependencies = [self._ticket_from_ticket_name(dep) for dep in dependencies]

        if not(dependencies):
            if ticket in self.__ticket_dependencies:
                del self.__ticket_dependencies[ticket]
            return

        if not self._has_local_branch_for_ticket(ticket):
            raise KeyError("no local branch for ticket #{0} found.".format(ticket))

        self.__ticket_dependencies[ticket] = tuple(sorted(dependencies))

    def _dependencies_for_ticket(self, ticket, download_if_not_found=False):
        r"""
        Return the locally recorded dependencies for ``ticket``.

        INPUT:

        - ``ticket`` -- an int or string identifying a ticket

        - ``download_if_not_found`` -- a boolean (default: ``False``), whether
          to take the information from trac if the ticket does not exist
          locally

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: UI.append("Summary: ticket1\ndescription")
            sage: ticket = dev.create_ticket()

            sage: dev._set_dependencies_for_ticket(ticket, [2, 3])
            sage: dev._dependencies_for_ticket(ticket)
            (2, 3)
            sage: dev._set_dependencies_for_ticket(ticket, None)
            sage: dev._dependencies_for_ticket(ticket)
            ()

            sage: dev._dependencies_for_ticket(2, download_if_not_found=True)
            Traceback (most recent call last):
            ...
            NotImplementedError

        """
        ticket = self._ticket_from_ticket_name(ticket)

        if not self._has_local_branch_for_ticket(ticket):
            if download_if_not_found:
                raise NotImplementedError
            else:
                raise KeyError("no local branch for ticket #{0} found.".format(ticket))
        else:
            ret = self.__ticket_dependencies[ticket]

        return tuple(sorted([self._ticket_from_ticket_name(dep) for dep in ret]))

    def _set_remote_branch_for_branch(self, branch, remote_branch):
        r"""
        Set the remote branch of ``branch`` to ``remote_branch``.

        INPUT:

        - ``branch`` -- a string, a name of a local branch

        - ``remote_branch`` -- a string or ``None``, unset the remote branch if
          ``None``

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev.git.silent.branch('ticket/1')

            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/ticket/1'
            sage: dev._set_remote_branch_for_branch("ticket/1", "public/1")
            sage: dev._remote_branch_for_ticket(1) # ticket/1 has not been set to be the branch for ticket #1
            'u/doctest/ticket/1'
            sage: dev._set_local_branch_for_ticket(1, 'ticket/1')
            sage: dev._remote_branch_for_ticket(1)
            'public/1'
            sage: dev._set_remote_branch_for_branch("ticket/1", None)
            sage: dev._remote_branch_for_ticket(1)
            'u/doctest/ticket/1'

        """
        self._check_local_branch_name(branch, exists=any)

        if remote_branch is None:
            if branch in self.__branch_to_remote_branch:
                del self.__branch_to_remote_branch[branch]
            return

        self._check_local_branch_name(branch, exists=True)
        self._check_remote_branch_name(remote_branch)

        self.__branch_to_remote_branch[branch] = remote_branch

    def _remote_branch_for_branch(self, branch):
        r"""
        Return the remote branch of ``branch`` or ``None`` if no remote branch is set.

        INPUT:

        - ``branch`` -- a string, the name of a local branch

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev.git.silent.branch('ticket/1')

            sage: dev._remote_branch_for_branch('ticket/1') is None
            True
            sage: dev._set_remote_branch_for_branch("ticket/1", "public/1")
            sage: dev._remote_branch_for_branch('ticket/1')
            'public/1'
            sage: dev._set_remote_branch_for_branch("ticket/1", None)
            sage: dev._remote_branch_for_branch('ticket/1') is None
            True

        """
        self._check_local_branch_name(branch, exists=True)

        if branch in self.__branch_to_remote_branch:
            return self.__branch_to_remote_branch[branch]
        if branch == MASTER_BRANCH:
            return MASTER_BRANCH

        return None

    def _set_local_branch_for_ticket(self, ticket, branch):
        r"""
        Record that ``branch`` is the local branch associated to ``ticket``.

        INPUT:

        - ``ticket`` -- a string or int identifying a ticket

        - ``branch`` -- a string, the name of a local branch, or ``None`` to
          delete the association

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._local_branch_for_ticket(1)
            Traceback (most recent call last):
            ...
            KeyError: 'No branch for ticket #1 in your repository.'

            sage: dev._set_local_branch_for_ticket(1, 'ticket/1')
            Traceback (most recent call last):
            ...
            SageDevValueError: Branch `ticket/1` does not exist locally.
            sage: dev.git.silent.branch('ticket/1')
            sage: dev._set_local_branch_for_ticket(1, 'ticket/1')
            sage: dev._local_branch_for_ticket(1)
            'ticket/1'

        """
        ticket = self._ticket_from_ticket_name(ticket)

        if branch is None:
            if ticket in self.__ticket_to_branch:
                del self.__ticket_to_branch[ticket]
            return

        self._check_local_branch_name(branch, exists=True)

        self.__ticket_to_branch[ticket] = branch

    def _format_command(self, command, *args, **kwargs):
        r"""
        Helper method for informational messages.

        OUTPUT:

        A command which the user can run from the command line/sage interactive
        shell to execute ``command`` with ``args`` and ``kwargs``.

        EXAMPLES::

            sage: dev._format_command('switch-ticket') # not tested (output depends on whether this test is run from within sage or not)
            'dev.switch_ticket()'
            sage: dev._format_command('switch-ticket',int(1)) # not tested
            'dev.switch_ticket(1)'

        """
        try:
            __IPYTHON__
        except NameError:
            args = [str(arg) for arg in args]
            kwargs = [ "--{0}={1}".format(str(key.split("_or_")[0]).replace("_","-"),kwargs[key]) for key in kwargs ]
            return "sage --dev {0} {1}".format(command.replace("_","-"), " ".join(args+kwargs))
        else:
            args = [str(arg) for arg in args]
            kwargs = [ "{0}={1}".format(str(key).replace("-","_"),kwargs[key]) for key in kwargs ]
            return "dev.{0}({1})".format(command.replace("-","_"), ", ".join(args+kwargs))

    def _current_ticket(self):
        r"""
        Return the ticket corresponding to the current branch or ``None`` if
        there is no ticket associated to that branch.

        TESTS::

            sage: from sage.dev.test.sagedev import single_user_setup
            sage: dev, config, UI, server = single_user_setup()
            sage: dev = dev._sagedev

            sage: dev._current_ticket() is None
            True

            sage: UI.append("Summary: ticket1\ndescription")
            sage: ticket = dev.create_ticket()
            sage: dev._current_ticket()
            1

        """
        from git_error import DetachedHeadError
        try:
            branch = self.git.current_branch()
        except DetachedHeadError:
            return None

        if branch in self.__branch_to_ticket:
            return self.__branch_to_ticket[branch]

        return None

class SageDevValueError(ValueError):
    r"""
    A ``ValueError`` to indicate that the user supplied an invaid value.

    EXAMPLES::

        sage: from sage.dev.test.sagedev import single_user_setup
        sage: dev, config, UI, server = single_user_setup()

        sage: dev.switch_ticket(-1)
        ValueError: `-1` is not a valid ticket name or ticket does not exist on trac.

    """
    def __init__(self, message):
        r"""
        Initialization.

        TESTS::

            sage: from sage.dev.sagedev import SageDevValueError
            sage: type(SageDevValueError("message"))
            <class 'sage.dev.sagedev.SageDevValueError'>

        """
        ValueError.__init__(self, message)
