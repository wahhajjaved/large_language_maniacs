# System imports
import os
from os.path import join

# 3rd party libs
from nose.tools import *
from git import *

# PyGitup imports
from tests import basepath, capture, update_file, init_master

test_name = 'no-fetch'
new_branch_name = test_name + '.2'
another_file_name = 'another_file.txt'

origin_test_name = 'origin/' + test_name

repo_path = join(basepath, test_name + os.sep)


def setup():
    master_path, master = init_master(test_name)

    # Prepare master repo
    master.git.checkout(b=test_name)

    # Clone to test repo
    path = join(basepath, test_name)
    master.clone(path, b=test_name)

    repo = Repo(path, odbt=GitCmdObjectDB)

    assert repo.working_dir == path

    # Create new local branch and set upstream
    repo.git.checkout(b=new_branch_name)
    repo.git.branch(u=origin_test_name)

    # Make non-conflicting change in new branch
    update_file(repo, new_branch_name, filename=another_file_name)

    # Modify file in master
    update_file(master, test_name)

    # Update first branch
    repo.git.checkout(test_name)
    repo.git.pull()



def test_no_fetch():
    """ Run 'git up' with '--no-fetch' argument """
    os.chdir(repo_path)

    from PyGitUp.gitup import GitUp
    gitup = GitUp(testing=True)
    gitup.should_fetch = False

    with capture() as [stdout, _]:
        gitup.run()

    stdout = stdout.getvalue()

    assert_false('Fetching' in stdout)

    assert_true('rebasing' in stdout)
    assert_true('up to date' in stdout)
    assert_true(test_name in stdout)
    assert_true(new_branch_name in stdout)

