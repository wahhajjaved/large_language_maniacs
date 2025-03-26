#!/usr/bin/python
"""Script to bootstrap the chroot using new toolchain.

This script allows you to build/install a customized version of gcc/binutils,
either by specifying branch or a local directory.

This script must be executed outside chroot.

Below is some typical usage -

## Build gcc located at /local/gcc/dir and do a bootstrap using the new compiler
## for the chromeos root.  The script tries to find a valid chromeos tree all
## the way up from your current working directory.
./build_tool.py --gcc_dir=/loca/gcc/dir --bootstrap

## Build binutils, using remote branch "mobile_toolchain_v17" and do a bootstrap
## using the new binutils for the chromeos root. The script tries to find a
## valid chromeos tree all the way up from your current working directory.
./build_tool.py --binutils_branch=cros/mobile_toolchain_v17 \
    --chromeos_root=/chromeos/dir --bootstrap

## Same as above except only do it for board daisy - no bootstrapping involved.
./build_tool.py --binutils_branch=cros/mobile_toolchain_v16 \
    --chromeos_root=/chromeos/dir --board=daisy
"""

__author__ = 'shenhan@google.com (Han Shen)'

import optparse
import os
import re
import sys

import repo_to_repo
from utils import command_executer
from utils import logger
from utils import misc

REPO_PATH_PATTERN = 'src/third_party/{0}'
TEMP_BRANCH_NAME = 'internal_testing_branch_no_use'
CHROMIUMOS_OVERLAY_PATH = 'src/third_party/chromiumos-overlay'
EBUILD_PATH_PATTERN = 'src/third_party/chromiumos-overlay/sys-devel/{0}'


class Bootstrapper(object):
  """Class that handles bootstrap process.
  """

  def __init__(self, chromeos_root, gcc_branch=None, gcc_dir=None,
               binutils_branch=None, binutils_dir=None,
               board=None, setup_tool_ebuild_file_only=False):
    self._chromeos_root = chromeos_root

    self._gcc_branch = gcc_branch
    self._gcc_branch_tree = None
    self._gcc_dir = gcc_dir
    self._gcc_ebuild_file = None
    self._gcc_ebuild_file_name = None

    self._binutils_branch = binutils_branch
    self._binutils_branch_tree = None
    self._binutils_dir = binutils_dir
    self._binutils_ebuild_file = None
    self._binutils_ebuild_file_name = None

    self._setup_tool_ebuild_file_only = setup_tool_ebuild_file_only

    self._ce = command_executer.GetCommandExecuter()
    self._logger = logger.GetLogger()
    self._board = board

  def IsTreeSame(self, t1, t2):
    diff = 'diff -qr -x .git -x .svn "{0}" "{1}"'.format(t1, t2)
    if self._ce.RunCommand(diff, print_to_console=False) == 0:
      self._logger.LogOutput('"{0}" and "{1}" are the same."'.format(t1, t2))
      return True
    self._logger.LogWarning('"{0}" and "{1}" are different."'.format(t1, t2))
    return False

  def SubmitToLocalBranch(self):
    """Copy source code to the chromium source tree and submit it locally."""
    if self._gcc_dir:
      if not self.SubmitToolToLocalBranch(
          tool_name='gcc', tool_dir=self._gcc_dir):
        return False
      self._gcc_branch = TEMP_BRANCH_NAME

    if self._binutils_dir:
      if not self.SubmitToolToLocalBranch(
          tool_name='binutils', tool_dir=self._binutils_dir):
        return False
      self._binutils_branch = TEMP_BRANCH_NAME

    return True

  def SubmitToolToLocalBranch(self, tool_name, tool_dir):
    """Copy the source code to local chromium source tree.

    Args:
      tool_name: either 'gcc' or 'binutils'
      tool_dir: the tool source dir to be used
    Returns:
      True if all succeeded False otherwise.
    """

    # The next few steps creates an internal branch to sync with the tool dir
    # user provided.
    chrome_tool_dir = self.GetChromeOsToolDir(tool_name)

    # 0. Test to see if git tree is free of local changes.
    if not misc.IsGitTreeClean(chrome_tool_dir):
      self._logger.LogError(
          'Git repository "{0}" not clean, aborted.'.format(chrome_tool_dir))
      return False

    # 1. Checkout/create a (new) branch for testing.
    command = 'cd "{0}" && git checkout -B {1}'.format(
        chrome_tool_dir, TEMP_BRANCH_NAME)
    ret = self._ce.RunCommand(command)
    if ret:
      self._logger.LogError('Failed to create a temp branch for test, aborted.')
      return False

    if self.IsTreeSame(tool_dir, chrome_tool_dir):
      self._logger.LogOutput(
          '"{0}" and "{1}" are the same, sync skipped.'.format(
              tool_dir, chrome_tool_dir))
      return True

    # 2. Sync sources from user provided tool dir to chromiumos tool git.
    local_tool_repo = repo_to_repo.FileRepo(tool_dir)
    chrome_tool_repo = repo_to_repo.GitRepo(chrome_tool_dir, TEMP_BRANCH_NAME)
    chrome_tool_repo._root_dir = chrome_tool_dir
    # Delete all stuff before start mapping.
    self._ce.RunCommand('cd {0} && rm -rf *'.format(chrome_tool_dir))
    local_tool_repo.MapSources(chrome_tool_repo.GetRoot())

    # 3. Ensure after sync tree is the same.
    if self.IsTreeSame(tool_dir, chrome_tool_dir):
      self._logger.LogOutput('Sync successfully done.')
    else:
      self._logger.LogError('Sync not successful, aborted.')
      return False

    # 4. Commit all changes.
    ret = chrome_tool_repo.CommitLocally(
        'Synced with tool source tree at - "{0}".'.format(tool_dir))
    if ret:
      self._logger.LogError('Commit to local branch "{0}" failed, aborted.'.
                            format(TEMP_BRANCH_NAME))
      return False
    return True

  def CheckoutBranch(self):
    """Checkout working branch for the tools.

    Returns:
      True: if operation succeeds.
    """

    if self._gcc_branch:
      rv = self.CheckoutToolBranch('gcc', self._gcc_branch)
      if rv:
        self._gcc_branch_tree = rv
      else:
        return False

    if self._binutils_branch:
      rv = self.CheckoutToolBranch('binutils', self._binutils_branch)
      if rv:
        self._binutils_branch_tree = rv
      else:
        return False

    return True

  def CheckoutToolBranch(self, tool_name, tool_branch):
    """Checkout the tool branch for a certain tool.

    Args:
      tool_name: either 'gcc' or 'binutils'
      tool_branch: tool branch to use
    Returns:
      True: if operation succeeds. Otherwise False.
    """

    chrome_tool_dir = self.GetChromeOsToolDir(tool_name)
    command = 'cd "{0}" && git checkout {1}'.format(
        chrome_tool_dir, tool_branch)
    if not self._ce.RunCommand(command, print_to_console=True):
      # Get 'TREE' value of this commit
      command = ('cd "{0}" && git cat-file -p {1} '
                 '| grep -E "^tree [a-f0-9]+$" '
                 '| cut -d" " -f2').format(chrome_tool_dir, tool_branch)
      ret, stdout, _ = self._ce.RunCommand(
          command, return_output=True, print_to_console=False)
      # Pipe operation always has a zero return value. So need to check if
      # stdout is valid.
      if not ret and stdout and re.match(
          '[0-9a-h]{40}', stdout.strip(), re.IGNORECASE):
        tool_branch_tree = stdout.strip()
        self._logger.LogOutput('Find tree for {0} branch "{1}" - "{2}"'.format(
            tool_name, tool_branch, tool_branch_tree))
        return tool_branch_tree
    self._logger.LogError(('Failed to checkout "{0}" or failed to '
                           'get tree value, aborted.').format(tool_branch))
    return None

  def FindEbuildFile(self):
    """Find the ebuild files for the tools.

    Returns:
      True: if operation succeeds.
    """

    if self._gcc_branch:
      (rv, ef, efn) = self.FindToolEbuildFile('gcc')
      if rv:
        self._gcc_ebuild_file = ef
        self._gcc_ebuild_file_name = efn
      else:
        return False

    if self._binutils_branch:
      (rv, ef, efn) = self.FindToolEbuildFile('binutils')
      if rv:
        self._binutils_ebuild_file = ef
        self._binutils_ebuild_file_name = efn
      else:
        return False

    return True

  def FindToolEbuildFile(self, tool_name):
    """Find ebuild file for a specific tool.

    Args:
      tool_name: either "gcc" or "binutils".
    Returns:
      A triplet that consisits of whether operation succeeds or not,
      tool ebuild file full path and tool ebuild file name.
    """

    # To get the active gcc ebuild file, we need a workable chroot first.
    if not os.path.exists(
        os.path.join(self._chromeos_root, 'chroot')) and self._ce.RunCommand(
            'cd "{0}" && cros_sdk --create'.format(self._chromeos_root)):
      self._logger.LogError(('Failed to install a initial chroot, aborted.\n'
                             'If previous bootstrap failed, do a '
                             '"cros_sdk --delete" to remove '
                             'in-complete chroot.'))
      return (False, None, None)

    rv, stdout, _ = self._ce.ChrootRunCommand(
        self._chromeos_root, 'equery w sys-devel/{0}'.format(tool_name),
        return_output=True, print_to_console=True)
    if rv:
      self._logger.LogError(
          ('Failed to execute inside chroot '
           '"equery w sys-devel/{0}", aborted.').format(tool_name))
      return (False, None, None)
    m = re.match(r'^.*/({0}/(.*\.ebuild))$'.format(
        EBUILD_PATH_PATTERN.format(tool_name)), stdout)
    if not m:
      self._logger.LogError(
          ('Failed to find {0} ebuild file, aborted. '
           'If previous bootstrap failed, do a "cros_sdk --delete" to remove '
           'in-complete chroot.').format(tool_name))
      return (False, None, None)
    tool_ebuild_file = os.path.join(self._chromeos_root, m.group(1))
    tool_ebuild_file_name = m.group(2)

    return (True, tool_ebuild_file, tool_ebuild_file_name)

  def InplaceModifyEbuildFile(self):
    """Modify the ebuild file.

    Returns:
      True if operation succeeds.
    """

    # Note we shall not use remote branch name (eg. "cros/gcc.gnu.org/...") in
    # CROS_WORKON_COMMIT, we have to use GITHASH. So we call GitGetCommitHash on
    # tool_branch.
    if self._gcc_branch:
      tool_branch_githash = misc.GitGetCommitHash(
          self.GetChromeOsToolDir('gcc'), self._gcc_branch)
      if not tool_branch_githash:
        return False
      if not self.InplaceModifyToolEbuildFile(
          tool_branch_githash, self._gcc_branch_tree, self._gcc_ebuild_file):
        return False

    if self._binutils_branch:
      tool_branch_githash = misc.GitGetCommitHash(
          self.GetChromeOsToolDir('binutils'), self._binutils_branch)
      if not self.InplaceModifyToolEbuildFile(
          tool_branch_githash, self._binutils_branch_tree,
          self._binutils_ebuild_file):
        return False
    return True

  @staticmethod
  def ResetToolEbuildFile(chromeos_root, tool_name):
    """Reset tool ebuild file to clean state.

    Args:
      chromeos_root: chromeos source tree
      tool_name: either "gcc" or "binutils"
    Returns:
      True if operation succeds.
    """
    rv = misc.GetGitChangesAsList(
        os.path.join(chromeos_root, CHROMIUMOS_OVERLAY_PATH),
        path=('sys-devel/{0}/{0}-*.ebuild'.format(tool_name)),
        staged=False)
    if rv:
      cmd = 'cd {0} && git checkout --'.format(os.path.join(
          chromeos_root, CHROMIUMOS_OVERLAY_PATH))
      for g in rv:
        cmd += ' ' + g
      rv = command_executer.GetCommandExecuter().RunCommand(cmd)
      if rv:
        logger.GetLogger().LogWarning(
            'Failed to reset the ebuild file. Please refer to log above.')
        return False
    else:
      logger.GetLogger().LogWarning(
          'Note - did not find any modified {0} ebuild file.'.format(tool_name))
      # Fall through
    return True

  def GetChromeOsToolDir(self, tool_name):
    """Return the chromeos git dir for a specific tool.

    Args:
      tool_name: either 'gcc' or 'binutils'.
    Returns:
      Absolute git path for the tool.
    """

    return os.path.join(
        self._chromeos_root, REPO_PATH_PATTERN.format(tool_name))

  def InplaceModifyToolEbuildFile(
      self, tool_branch_githash, tool_branch_tree, tool_ebuild_file):
    """Using sed to fill properly values into the ebuild file.

    Args:
      tool_branch_githash: githash for tool_branch
      tool_branch_tree: treeish for the tool branch
      tool_ebuild_file: tool ebuild file
    Returns:
      True: if operation succeeded.
    """

    command = ('sed -i '
               '-e \'/^CROS_WORKON_COMMIT=".*"/i'
               ' # The following line is modified by script.\' '
               '-e \'s!^CROS_WORKON_COMMIT=".*"$!CROS_WORKON_COMMIT="{0}"!\' '
               '-e \'/^CROS_WORKON_TREE=".*"/i'
               ' # The following line is modified by script.\' '
               '-e \'s!^CROS_WORKON_TREE=".*"$!CROS_WORKON_TREE="{1}"!\' '
               '{2}').format(tool_branch_githash,
                             tool_branch_tree,
                             tool_ebuild_file)
    rv = self._ce.RunCommand(command)
    if rv:
      self._logger.LogError(
          'Failed to modify commit and tree value for "{0}"", aborted.'.format(
              tool_ebuild_file))
      return False

    # Warn that the ebuild file has been modified.
    self._logger.LogWarning(
        ('Ebuild file "{0}" is modified, to revert the file - \n'
         'bootstrap_compiler.py --chromeos_root={1} '
         '--reset_tool_ebuild_file').format(
             tool_ebuild_file, self._chromeos_root))
    return True

  def DoBuildForBoard(self):
    """Build tool for a specific board.

    Returns:
      True if operation succeeds.
    """

    if self._gcc_branch:
      if not self.DoBuildToolForBoard('gcc'):
        return False
    if self._binutils_branch:
      if not self.DoBuildToolForBoard('binutils'):
        return False
    return True

  def DoBuildToolForBoard(self, tool_name):
    """Build a specific tool for a specific board.

    Args:
      tool_name: either "gcc" or "binutils"
    Returns:
      True if operation succeeds.
    """

    boards_to_build = self._board.split(',')

    failed = []
    for board in boards_to_build:
      if board == 'host':
        command = 'sudo emerge sys-devel/{0}'.format(tool_name)
      else:
        target = misc.GetCtargetFromBoard(board, self._chromeos_root)
        if not target:
          self._logger.LogError(
              'Unsupported board "{0}", skip.'.format(board))
          failed.append(board)
          continue
        command = 'sudo emerge cross-{0}/{1}'.format(target, tool_name)

      rv = self._ce.ChrootRunCommand(self._chromeos_root, command,
                                     return_output=False, print_to_console=True)
      if rv:
        self._logger.LogError(
            'Build "{0}" failed for "{1}", aborted.'.format(tool_name, board))
        failed.append(board)
      else:
        self._logger.LogOutput(
            'Successfully built "{0}" for board "{1}".'.format(tool_name, board))

    if failed:
      self._logger.LogError(
          'Failed to build {0} for the following board(s): "{1}"'.format(
              tool_name, ' '.join(failed)))
      return False
    # All boards build successfully
    return True

  def DoBootstrapping(self):
    """Do bootstrapping the chroot.

    Returns:
      True if operation succeeds.
    """

    logfile = os.path.join(self._chromeos_root, 'bootstrap.log')
    command = 'cd "{0}" && cros_sdk --delete --bootstrap |& tee "{1}"'.format(
        self._chromeos_root, logfile)
    rv = self._ce.RunCommand(command, return_output=False,
                             print_to_console=True)
    if rv:
      self._logger.LogError('Bootstrapping failed, log file - "{0}"\n'.format(
          logfile))
      return False

    ## Workaround for - crbug/331713.
    ## We do not test for success, failure is not important at this step.
    self._ce.ChrootRunCommand(
        self._chromeos_root, 'sudo emerge dev-util/pkgconfig',
        return_output=False, print_to_console=True)

    self._logger.LogOutput('Bootstrap succeeded.')
    return True

  def Do(self):
    """Entrance of the class.

    Returns:
      True if everything is ok.
    """

    if (self.SubmitToLocalBranch() and
        self.CheckoutBranch() and
        self.FindEbuildFile() and
        self.InplaceModifyEbuildFile()):
      if self._setup_tool_ebuild_file_only:
        # Everything is done, we are good.
        ret = True
      else:
        if self._board:
          ret = self.DoBuildForBoard()
        else:
          # This implies '--bootstrap'.
          ret = self.DoBootstrapping()
    else:
      ret = False
    return ret


def Main(argv):
  parser = optparse.OptionParser()
  parser.add_option('-c', '--chromeos_root', dest='chromeos_root',
                    help=('Optional. ChromeOs root dir. '
                          'When not specified, chromeos root will be deduced '
                          'from current working directory.'))
  parser.add_option('--gcc_branch', dest='gcc_branch',
                    help=('The branch to test against. '
                          'This branch must be a local branch '
                          'inside "src/third_party/gcc". '
                          'Notice, this must not be used with "--gcc_dir".'))
  parser.add_option('--binutils_branch', dest='binutils_branch',
                    help=('The branch to test against binutils. '
                          'This branch must be a local branch '
                          'inside "src/third_party/binutils". '
                          'Notice, this must not be used with '
                          '"--binutils_dir".'))
  parser.add_option('-g', '--gcc_dir', dest='gcc_dir',
                    help=('Use a local gcc tree to do bootstrapping. '
                          'Notice, this must not be used with "--gcc_branch".'))
  parser.add_option('--binutils_dir', dest='binutils_dir',
                    help=('Use a local binutils tree to do bootstrapping. '
                          'Notice, this must not be used with '
                          '"--binutils_branch".'))
  parser.add_option('--fixperm', dest='fixperm',
                    default=False, action='store_true',
                    help=('Fix the (notorious) permission error '
                          'while trying to bootstrap the chroot. '
                          'Note this takes an extra 10-15 minutes '
                          'and is only needed once per chromiumos tree.'))
  parser.add_option('--setup_tool_ebuild_file_only',
                    dest='setup_tool_ebuild_file_only',
                    default=False, action='store_true',
                    help=('Setup gcc and/or binutils ebuild file '
                          'to pick up the branch (--gcc/binutils_branch) or '
                          'use gcc and/or binutils source (--gcc/binutils_dir) '
                          'and exit. Keep chroot as is. This should not be '
                          'used with --gcc/binutils_dir/branch options.'))
  parser.add_option('--reset_tool_ebuild_file', dest='reset_tool_ebuild_file',
                    default=False, action='store_true',
                    help=('Reset the modification that is done by this script.'
                          'Note, when this script is running, it will modify '
                          'the active gcc/binutils ebuild file. Use this '
                          'option to reset (what this script has done) '
                          'and exit. This should not be used with -- '
                          'gcc/binutils_dir/branch options.'))
  parser.add_option('--board', dest='board', default=None,
                    help=('Only build toolchain for specific board(s). '
                          'Use "host" to build for host. '
                          'Use "," to seperate multiple boards. '
                          'This does not perform a chroot bootstrap.'))
  parser.add_option('--bootstrap', dest='bootstrap',
                    default=False, action='store_true',
                    help=('Performs a chroot bootstrap. '
                          'Note, this will *destroy* your current chroot.'))

  options = parser.parse_args(argv)[0]
  # Trying to deduce chromeos root from current directory.
  if not options.chromeos_root:
    logger.GetLogger().LogOutput('Trying to deduce chromeos root ...')
    wdir = os.getcwd()
    while wdir and wdir != '/':
      if misc.IsChromeOsTree(wdir):
        logger.GetLogger().LogOutput('Find chromeos_root: {}'.format(wdir))
        options.chromeos_root = wdir
        break
      wdir = os.path.dirname(wdir)

  if not options.chromeos_root:
    parser.error('Missing or failing to deduce mandatory option "--chromeos".')
    return 1

  options.chromeos_root = os.path.abspath(
      os.path.expanduser(options.chromeos_root))

  if not os.path.isdir(options.chromeos_root):
    logger.GetLogger().LogError(
        '"{0}" does not exist.'.format(options.chromeos_root))
    return 1

  if options.fixperm:
    # Fix perm error before continuing.
    cmd = (r'sudo find "{0}" \( -name ".cache" -type d -prune \) -o '
           r'\( -name "chroot" -type d -prune \) -o '
           r'\( -type f -exec chmod a+r {{}} \; \) -o '
           r'\( -type d -exec chmod a+rx {{}} \; \)').format(
               options.chromeos_root)
    logger.GetLogger().LogOutput(
        'Fixing perm issues for chromeos root, this might take some time.')
    command_executer.GetCommandExecuter().RunCommand(cmd)

  if options.reset_tool_ebuild_file:
    if (options.gcc_dir or options.gcc_branch or
        options.binutils_dir or options.binutils_branch):
      logger.GetLogger().LogWarning(
          'Ignoring any "--gcc/binutils_dir" and/or "--gcc/binutils_branch".')
    if options.setup_tool_ebuild_file_only:
      logger.GetLogger().LogError(
          ('Conflict options "--reset_tool_ebuild_file" '
           'and "--setup_tool_ebuild_file_only".'))
      return 1
    rv = Bootstrapper.ResetToolEbuildFile(options.chromeos_root, 'gcc')
    rv1 = Bootstrapper.ResetToolEbuildFile(options.chromeos_root, 'binutils')
    return 0 if (rv and rv1) else 1

  if options.gcc_dir:
    options.gcc_dir = os.path.abspath(os.path.expanduser(options.gcc_dir))
    if not os.path.isdir(options.gcc_dir):
      logger.GetLogger().LogError(
          '"{0}" does not exist.'.format(options.gcc_dir))
      return 1

  if options.gcc_branch and options.gcc_dir:
    parser.error('Only one of "--gcc_dir" and "--gcc_branch" can be specified.')
    return 1

  if options.binutils_dir:
    options.binutils_dir = os.path.abspath(
        os.path.expanduser(options.binutils_dir))
    if not os.path.isdir(options.binutils_dir):
      logger.GetLogger().LogError(
          '"{0}" does not exist.'.format(options.binutils_dir))
      return 1

  if options.binutils_branch and options.binutils_dir:
    parser.error('Only one of "--binutils_dir" and '
                 '"--binutils_branch" can be specified.')
    return 1

  if (not (options.binutils_branch or options.binutils_dir or
           options.gcc_branch or options.gcc_dir)):
    parser.error(('At least one of "--gcc_dir", "--gcc_branch", '
                  '"--binutils_dir" and "--binutils_branch" must '
                  'be specified.'))
    return 1

  if not options.board and not options.bootstrap:
    parser.error('You must specify either "--board" or "--bootstrap".')
    return 1

  if options.board and options.bootstrap:
    parser.error('You must specify only one of "--board" and "--bootstrap".')
    return 1

  if Bootstrapper(
      options.chromeos_root,
      gcc_branch=options.gcc_branch, gcc_dir=options.gcc_dir,
      binutils_branch=options.binutils_branch,
      binutils_dir=options.binutils_dir,
      board=options.board,
      setup_tool_ebuild_file_only=options.setup_tool_ebuild_file_only).Do():
    return 0
  return 1


if __name__ == '__main__':
  retval = Main(sys.argv)
  sys.exit(retval)
