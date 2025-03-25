# -*- coding: utf-8 -*- 

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:

### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2005 Aaron Bentley <aaron.bentley@utoronto.ca>
### Copyright (C) 2007 José Fonseca <j_r_fonseca@yahoo.co.uk>

### Redistribution and use in source and binary forms, with or without
### modification, are permitted provided that the following conditions
### are met:
### 
### 1. Redistributions of source code must retain the above copyright
###    notice, this list of conditions and the following disclaimer.
### 2. Redistributions in binary form must reproduce the above copyright
###    notice, this list of conditions and the following disclaimer in the
###    documentation and/or other materials provided with the distribution.

### THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
### IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
### OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
### IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
### INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
### NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
### DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
### THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
### (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
### THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import errno
import _vc

class Vc(_vc.CachedVc):

    CMD = "git"
    NAME = "Git"
    VC_DIR = ".git"
    PATCH_STRIP_NUM = 1
    PATCH_INDEX_RE = "^diff --git a/(.*) b/.*$"
    state_map = {
        "X": _vc.STATE_NONE,     # Unknown
        "A": _vc.STATE_NEW,      # New
        "D": _vc.STATE_REMOVED,  # Deleted
        "M": _vc.STATE_MODIFIED, # Modified
        "T": _vc.STATE_MODIFIED, # Type-changed
        "U": _vc.STATE_CONFLICT, # Unmerged
    }

    def check_repo_root(self, location):
        # Check exists instead of isdir, since .git might be a git-file
        if not os.path.exists(os.path.join(location, self.VC_DIR)):
            raise ValueError
        return location

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD, "diff", "--relative", "HEAD"]
    def update_command(self):
        return [self.CMD,"pull"]
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm"]
    def revert_command(self):
        return [self.CMD,"checkout"]
    def get_working_directory(self, workdir):
        if workdir.startswith("/"):
            return self.root
        else:
            return ''

    def _lookup_tree_cache(self, rootdir):
        while 1:
            try:
                proc = _vc.popen([self.CMD, "diff-index", "--name-status", \
                    "HEAD", "./"], cwd=self.location)
                entries = proc.read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise
        tree_state = {}
        for entry in entries:
            statekey, name = entry.split("\t", 2)
            path = os.path.join(self.root, name.strip())
            state = self.state_map.get(statekey.strip(), _vc.STATE_NONE)
            tree_state[path] = state

        return tree_state

    def _get_dirsandfiles(self, directory, dirs, files):

        tree = self._get_tree_cache(directory)

        retfiles = []
        retdirs = []
        for name,path in files:
            state = tree.get(path, _vc.STATE_IGNORED)
            retfiles.append( _vc.File(path, name, state) )
        for name,path in dirs:
            # git does not operate on dirs, just files
            retdirs.append( _vc.Dir(path, name, _vc.STATE_NORMAL))
        for path, state in tree.iteritems():
            # removed files are not in the filesystem, so must be added here
            if state is _vc.STATE_REMOVED:
                folder, name = os.path.split(path)
                if folder == directory:
                    retfiles.append( _vc.File(path, name, state) )
        return retdirs, retfiles
