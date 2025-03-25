# -*- mode: python; coding: utf-8 -*-

__author__    = "Alvaro Lopez Ortega"
__email__     = "alvaro@alobbs.com"
__license__   = "MIT"

import os
import conf
import pickle
import patches
import projects
import companies


def figure_out_company (commits):
    for commit in commits:
        companies.commit_set_company (commit)

    return commits


def parse_git_log (project, with_company=True):
    # Non-cached
    cmd = 'git log --no-merges \'--pretty=format:{"author":"%aN", "author_email":"%aE", "author_date": "%at", "committer":"%cN", "committer_email":"%cE", "committer_date": "%ct", "hash":"%H"},\''
    f = projects.popen (project, cmd)
    commits = eval('[' + f.read() + ']')
    commitsn = len(commits)

    # Fix the type of the time entries
    for n in range(commitsn):
        commits[n]['author_date']    = int(commits[n]['author_date'])
        commits[n]['committer_date'] = int(commits[n]['committer_date'])

    # Populate patch sizes
    for n in range(commitsn):
        commit = commits[n]

        cmd = 'git show --no-notes %s' %(commit['hash'])
        f = projects.popen (project, cmd)

        commit['size'] = len (patches.filter_contribution(f.read()))
        print '\r%d%% [%d/%d] %s size=%d%s' %(((n+1) * 100) / commitsn, n, commitsn, commit['hash'], commit['size'], ' '*10),

    # Try to infeer the company
    commits = figure_out_company (commits)

    return commits


_commits = {}
def get_commits (project):
    # Cache
    global _commits
    if _commits.has_key (project):
        return _commits[project]

    cache_fp = os.path.join (conf.CACHE_PATH, project + '-log.pickle')

    # Disk cache
    if not os.path.exists(cache_fp):
        print ("%s not found: Execute ./preprocessor.py"%(cache_fp))

    _commits[project] = pickle.load (open (cache_fp, 'r'))
    return _commits[project]


def generate_cache_file (project):
    save_cache_file (project, parse_git_log (project))

def save_cache_file (project, content):
    cache_fp = os.path.join (conf.CACHE_PATH, project + '-log.pickle')
    pickle.dump (content, open(cache_fp, 'w+'))
