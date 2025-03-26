#
# -*- coding: utf-8 -*-
#
# This file is part of reclass

import collections
import fnmatch
import os
import pygit2

import reclass.errors
from reclass.storage import NodeStorageBase
from reclass.storage.common import NameMangler
from reclass.storage.yamldata import YamlData

FILE_EXTENSION = '.yml'
STORAGE_NAME = 'yaml_git'

def path_mangler(inventory_base_uri, nodes_uri, classes_uri):
    if nodes_uri == classes_uri:
        raise errors.DuplicateUriError(nodes_uri, classes_uri)
    return nodes_uri, classes_uri


GitMD = collections.namedtuple('GitMD', ['name', 'path', 'id'], verbose=False, rename=False)


class GitURI(object):

    def __init__(self, dictionary):
        self.repo = dictionary.get('repo', None)
        self.branch = dictionary.get('branch', None)

    def update(self, dictionary):
        if 'repo' in dictionary: self.repo = dictionary['repo']
        if 'branch' in dictionary: self.branch = dictionary['branch']

    def __repr__(self):
        return '<{0}: {1} {2}>'.format(self.__class__.__name__, self.repo, self.branch)


class GitRepo(object):

    def __init__(self, name):
        self.name = name
        self.repo = pygit2.Repository(name)
        self.branches = self.repo.listall_branches()
        self.files = self.files_in_repo()

    def get(self, id):
        return self.repo.get(id)

    def files_in_tree(self, tree, path):
        files = []
        for entry in tree:
            if entry.filemode == pygit2.GIT_FILEMODE_TREE:
                subtree = self.repo.get(entry.id)
                if path == '':
                    subpath = entry.name
                else:
                    subpath = '/'.join([path, entry.name])
                files.extend(self.files_in_tree(subtree, subpath))
            else:
                if path == '':
                   relpath = entry.name
                else:
                   relpath = '/'.join([path, entry.name])
                files.append(GitMD(entry.name, relpath, entry.id))
        return files

    def files_in_branch(self, branch):
        tree = self.repo.revparse_single(branch).tree
        return self.files_in_tree(tree, '')

    def files_in_repo(self):
        ret = {}
        for bname in self.branches:
            branch = {}
            files = self.files_in_branch(bname)
            for file in files:
                if fnmatch.fnmatch(file.name, '*{0}'.format(FILE_EXTENSION)):
                    name = os.path.splitext(file.name)[0]
                    relpath = os.path.dirname(file.path)
                    relpath, name = NameMangler.classes(relpath, name)
                    if name in ret:
                        raise reclass.errors.DuplicateNodeNameError(self.name + ' - ' + bname, name, ret[name], path)
                    else:
                        branch[name] = file
            ret[bname] = branch
        return ret

    def nodes(self, branch):
        ret = {}
        for name, file in self.files[branch].iteritems():
            if name in ret:
                raise reclass.errors.DuplicateNodeNameError(self.name, name, files[name], path)
            else:
                ret[name] = file
        return ret

class ExternalNodeStorage(NodeStorageBase):

    _repos = dict()

    def __init__(self, nodes_uri, classes_uri):
        super(ExternalNodeStorage, self).__init__(STORAGE_NAME)

        if nodes_uri is not None:
            self._nodes_uri = GitURI({ 'branch': 'master', 'repo': None })
            self._nodes_uri.update(nodes_uri)
            self._load_repo(self._nodes_uri.repo)
            self._nodes = self._repos[self._nodes_uri.repo].nodes(self._nodes_uri.branch)

        if classes_uri is not None:
            self._classes_default_uri = GitURI({ 'branch': '__env__', 'repo': None })
            self._classes_default_uri.update(classes_uri)
            self._load_repo(self._classes_default_uri.repo)

            self._classes_uri = []
            if 'env_overrides' in classes_uri:
                for override in classes_uri['env_overrides']:
                    for env, options in override.iteritems():
                        uri = GitURI({ 'branch': env, 'repo': self._classes_default_uri.repo })
                        uri.update(options)
                        self._classes_uri.append((env, uri))
                        self._load_repo(uri.repo)

            self._classes_uri.append(('*', self._classes_default_uri))

    nodes_uri = property(lambda self: self._nodes_uri)
    classes_uri = property(lambda self: self._classes_uri)

    def get_node(self, name):
        file = self._nodes[name]
        blob = self._repos[self._nodes_uri.repo].get(file.id)
        entity = YamlData.from_string(blob.data, 'git_fs://{0}#{1}/{2}'.format(self._nodes_uri.repo, self._nodes_uri.branch, file.path)).get_entity(name)
        return entity

    def get_class(self, name, environment):
        uri = self._env_to_uri(environment)
        file = self._repos[uri.repo].files[uri.branch][name]
        blob = self._repos[uri.repo].get(file.id)
        entity = YamlData.from_string(blob.data, 'git_fs://{0}#{1}/{2}'.format(uri.repo, uri.branch, file.path)).get_entity(name)
        return entity

    def enumerate_nodes(self):
        return self._nodes.keys()

    def _load_repo(self, url):
        if url not in self._repos:
            self._repos[url] = GitRepo(url)

    def _env_to_uri(self, environment):
        ret = None
        if environment is None:
            ret = self._classes_default_uri
        else:
            for env, uri in self._classes_uri:
                if env == environment:
                    ret = uri
                    break
        if ret is None:
            ret = self._classes_default_uri
        if ret.branch == '__env__':
            ret.branch = environment
        if ret.branch == None:
            ret.branch = 'master'
        return ret
