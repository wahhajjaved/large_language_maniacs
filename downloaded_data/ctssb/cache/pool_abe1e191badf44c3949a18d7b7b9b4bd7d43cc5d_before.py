import os
from os.path import *

import re
import shutil
import tempfile
import commands

from paths import Paths

from common import *
import verseek

from git import Git

class Error(Exception):
    pass

class CircularDependency(Error):
    pass

def deb_parse_filename(filename):
    """Parses package filename -> (name, version)"""

    if not filename.endswith(".deb"):
        raise Error("not a package `%s'" % filename)
    
    name, version = filename.split("_")[:2]

    return name, version

def deb_cmp_versions(a, b):
    """Compare a with b according to Debian versioning criteria"""

    def normalize(v):
        return re.sub(r'(\D|\b)0+', r'\1', v).rstrip("-")
        
    return cmp(normalize(a), normalize(b))

def deb_get_packages(srcpath):
    controlfile = join(srcpath, "debian/control")
    return [ re.sub(r'^.*?:', '', line).strip()
             for line in file(controlfile).readlines()
             if re.match(r'^Package:', line, re.I) ]

def parse_package_id(package):
    """Parse package_id string

    <package> := package-name[=package-version]

    Returns (name, version)
    Returns (name, None) if no version is provided
    """
    if "=" in package:
        name, version = package.split("=", 1)
    else:
        name = package
        version = None

    return name, version

def fmt_package_id(name, version):
    if version:
        return "%s=%s" % (name, version)
    return name

def mkargs(*args):
    return tuple(map(commands.mkarg, args))

class PackageCache:
    """Class representing the pool's package cache"""
    def __init__(self, path):
        self.path = path

    def getpath(self, package):
        """Returns path to package if it exists, or None otherwise.

        <package> := package-name[=package-version]
        """

        name, version = parse_package_id(package)
        for filename in os.listdir(self.path):
            filepath = join(self.path, filename)
            
            if not isfile(filepath) or not filename.endswith(".deb"):
                continue

            cached_name, cached_version = deb_parse_filename(filename)
            if name == cached_name and (version is None or version == cached_version):
                return filepath

        return None
        
    def exists(self, package):
        """Returns True if <package> exists in cache.

        <package> := filename | package-name[=package-version]
        """

        if exists(join(self.path, basename(package))):
            return True

        return self.getpath(package) != None

    def add(self, path):
        """Add binary to cache. Hardlink if possible, copy otherwise."""
        if self.exists(basename(path)):
            return

        cached_path = join(self.path, basename(path))
        hardlink_or_copy(path, cached_path)

    def list(self):
        """List packages in package cache -> list of (package, version)"""
        arr = []
        for filename in os.listdir(self.path):
            name, version = deb_parse_filename(filename)
            arr.append((name, version))
        return arr

def make_relative(root, path):
    """Return <path> relative to <root>.

    For example:
        make_relative("../../", "file") == "path/to/file"
        make_relative("/root", "/tmp") == "../tmp"
        make_relative("/root", "/root/backups/file") == "backups/file"
        
    """

    up_count = 0

    root = realpath(root).rstrip('/')
    path = realpath(path).rstrip('/')

    while True:
        if path == root or path.startswith(root.rstrip("/") + "/"):
            return ("../" * up_count) + path[len(root) + 1:]

        root = dirname(root).rstrip('/')
        up_count += 1

class StockBase(object):
    class Paths(Paths):
        files = [ 'link' ]

    @classmethod
    def create(cls, path, link):
        mkdir(path)
        paths = self.Paths(path)
        os.symlink(realpath(link), paths.link)

    def __init__(self, path):
        self.paths = self.Paths(path)
        
        self.name = basename(path)
        self.link = os.readlink(self.paths.link)
        if not isdir(self.link):
            raise Error("stock link to non-directory `%s'" % stock.link)

class StockPool(StockBase):
    """Class for managing a subpool-type stock"""
    def __init__(self, path, recursed_paths=[]):
        StockBase.__init__(self, path)
        if self.link in recursed_paths:
            raise CircularDependency("circular dependency detected `%s' is in recursed paths %s" %
                                     (self.link, recursed_paths))

        self.pool = Pool(self.link, recursed_paths)
        
class Stock(StockBase):
    """Class for managing a non-subpool-type stock."""

    class Paths(StockBase.Paths):
        files = [ 'source-versions', 'SYNC_HEAD', 'checkout' ]
                
    class SyncHead(object):
        """Magical attribute.

        Set writes to the stock's HEAD.
        Get reads the value from it.
        """
        def __get__(self, obj, type):
            path = obj.paths.SYNC_HEAD
            if exists(path):
                return file(path).read().rstrip()

            return None

        def __set__(self, obj, val):
            path = obj.paths.SYNC_HEAD
            file(path, "w").write(val + "\n")

    sync_head = SyncHead()

    def _get_workdir(self):
        """Return an initialized workdir path.

        If the stock links to a plain directory, the workdir is simply its path.
        
        If the stock links to a git repository, the workdir will point to a
        persistent lightweight checkout of the desired branch.
        """
        if not self.branch:
            return self.link

        orig = Git(self.link)
        checkout_path = self.paths.checkout
        
        if not exists(checkout_path):
            mkdir(checkout_path)
            checkout = Git.init_create(checkout_path)
            checkout.set_alternates(orig)
        else:
            checkout = Git(checkout_path)

        # checkout latest changes
        commit = orig.rev_parse(self.branch)
        if not commit:
            raise Error("no such branch `%s' at %s" % (self.branch, self.link))
        
        checkout.update_ref("refs/heads/" + self.branch, commit)
        checkout.checkout("-q", "-f", self.branch)

        if exists(join(checkout_path, "arena.internals")):
            command = "cd %s && sumo-open" % commands.mkarg(checkout_path)
            error = os.system(command)
            if error:
                raise Error("failed command: " + command)
            return join(checkout_path, "arena")

        # update tags
        for tag in orig.list_tags():
            checkout.update_ref("refs/tags/" + tag, orig.rev_parse(tag))

        return checkout_path

    class Workdir(object):
        """Magical attribute for performing lazy evaluation of workdir.
        If workdir is False, we evaluate its value.
        """
        def __get__(self, obj, type):
            if not obj._workdir:
                obj._workdir = obj._get_workdir()

            return obj._workdir

        def __set__(self, obj, val):
            obj._workdir = val

    workdir = Workdir()

    def _init_read_versions(self):
        source_versions = {}
        for dpath, dnames, fnames in os.walk(self.paths.source_versions):
            relative_path = make_relative(self.paths.source_versions, dpath)
            for fname in fnames:
                fpath = join(dpath, fname)
                versions = [ line.strip() for line in file(fpath).readlines() if line.strip() ]
                source_versions[join(relative_path, fname)] = versions

        return source_versions

    def __init__(self, path, pkgcache):
        StockBase.__init__(self, path)

        self.branch = None
        if "#" in self.name:
            self.branch = self.name.split("#")[1]

        self.source_versions = self._init_read_versions()
        self.workdir = None
        self.pkgcache = pkgcache

    def _sync_update_source_versions(self, dir):
        """update versions for a particular source package at <dir>"""
        packages = deb_get_packages(dir)
        versions = verseek.list(dir)

        relative_path = make_relative(self.workdir, dir)
        source_versions_path = join(self.paths.source_versions, relative_path)
        mkdir(source_versions_path)
        
        for package in packages:
            fh = file(join(source_versions_path, package), "w")
            for version in versions:
                print >> fh, version
            fh.close()

            self.source_versions[join(relative_path, package)] = versions
    
    def _sync(self, dir=None):
        """recursive sync back-end.
        updates versions of source packages and adds binaries to cache"""

        if dir is None:
            dir = self.workdir
            
        if isfile(join(dir, "debian/control")):
            return self._sync_update_source_versions(dir)

        for fname in os.listdir(dir):
            fpath = join(dir, fname)
            if not islink(fpath) and isfile(fpath) and fname.endswith(".deb"):
                self.pkgcache.add(fpath)

            if isdir(fpath):
                self._sync(fpath)
        
    def sync(self):
        """sync stock by updating source versions and importing binaries into the cache"""

        if self.branch:
            if Git(self.link).rev_parse(self.branch) == self.sync_head:
                return

        # delete old cached versions
        if exists(self.paths.source_versions):
            shutil.rmtree(self.paths.source_versions)
            mkdir(self.paths.source_versions)
        self.source_versions = {}
        
        self._sync()

        if self.branch:
            self.sync_head = Git(self.paths.checkout).rev_parse("HEAD")

class Stocks:
    """Class for managing and quering Pool Stocks in aggregate.

    Iterating an instance of this class produces all non-subpool type stocks.
    """
    def _init_stock(self, path_stock):
        stock = None
        try:
            stock = StockPool(path_stock, self.recursed_paths)
            self.subpools[stock.name] = stock.pool
        except CircularDependency:
            raise
        except Error:
            pass

        if not stock:
            stock = Stock(path_stock, self.pkgcache)

        self.stocks[stock.name] = stock
    
    def __init__(self, path, pkgcache, recursed_paths=[]):
        self.path = path
        self.pkgcache = pkgcache

        self.stocks = {}
        self.subpools = {}
        self.recursed_paths = recursed_paths
        
        for stock_name in os.listdir(path):
            path_stock = join(path, stock_name)
            if not isdir(path_stock):
                continue

            self._init_stock(path_stock)
            
    def __iter__(self):
        # iterate across all stocks except subpools
        return iter((stock for stock in self.stocks.values()
                     if not isinstance(stock, StockPool)))

    def __len__(self):
        return len(self.stocks) - len(self.subpools)

    @staticmethod
    def _parse_stock(stock):
        try:
            dir, branch = stock.split("#", 1)
        except ValueError:
            dir = stock
            branch = None

        return realpath(dir), branch

    def register(self, stock):
        dir, branch = self._parse_stock(stock)
        if not isdir(dir):
            raise Error("not a directory `%s'" % dir)

        try:
            git = Git(dir)
        except Git.Error:
            git = None

        if (not git and branch) or (git and branch and not git.show_ref(branch)):
            raise Error("no such branch `%s' at `%s'" % (branch, dir))

        if git and not branch:
            branch = basename(git.symbolic_ref("HEAD"))

        stock_name = basename(abspath(dir))
        if branch:
            stock_name += "#" + branch
        
        if self.stocks.has_key(stock_name):
            raise Error("stock already registered under name `%s'" % stock_name)

        stock_path = join(self.path, stock_name)
        Stock.create(stock_path, dir)
        self._init_stock(stock_path)
        
    def unregister(self, stock):
        dir, branch = self._parse_stock(stock)
        stock_name = basename(dir)
        if branch:
            stock_name += "#" + branch
            
        matches = [ stock for stock in self.stocks.values()
                    if stock.link == dir and (not branch or stock.branch == branch) ]
        if not matches:
            raise Error("no matches for unregister")

        if len(matches) > 1:
            raise Error("multiple implicit matches for unregister")

        stock = matches[0]
        shutil.rmtree(stock.paths.path)
        del self.stocks[stock.name]
        if stock.name in self.subpools:
            del self.subpools[stock.name]

    def sync(self):
        """sync all non-subpool stocks"""
        for stock in self:
            stock.sync()

    def get_source_versions(self):
        """List all stock sources.
        Returns an array of (stock, relative_path/package, versions) tuples"""
        
        source_versions = []
        for stock in self:
            for path, versions in stock.source_versions.items():
                source_versions.append((stock, path, versions))
        return source_versions
    
    def get_source_path(self, name, version):
        """Return path of source package"""
        for stock, path, versions in self.get_source_versions():
            if basename(path) == name and version in versions:
                return join(stock.workdir, dirname(path))

        return None

    def exists_source_version(self, name, version=None):
        """Returns true if the package source exists in any of the stocks.
        If version is None (default), any version will match"""

        for stock in self:
            for path, versions in stock.source_versions.items():
                if basename(path) == name:
                    if version is None:
                        return True

                    if version in versions:
                        return True

        return False
    
    def get_subpools(self):
        return self.subpools.values()

class PoolPaths(Paths):
    files = [ "pkgcache", "stocks", "tmp", "build/root", "build/logs" ]
    def __init__(self, path=None):
        if path is None:
            path = os.getenv("POOL_DIR", os.getcwd())
        path = join(realpath(path), ".pool")
        Paths.__init__(self, path)

def sync(method):
    def wrapper(self, *args, **kws):
        self.sync()
        return method(self, *args, **kws)
    return wrapper

class Pool(object):
    """Class for creating and controlling a Pool.
    This class's public methods map roughly to the pool's cli interface"""
    class Subpools(object):
        def __get__(self, obj, type):
            return obj.stocks.get_subpools()

    subpools = Subpools()

    @classmethod
    def init_create(cls, buildroot, path=None):
        paths = PoolPaths(path)

        if not isdir(buildroot):
            raise Error("buildroot `%s' is not a directory" % buildroot)
        
        mkdir(paths.stocks)
        mkdir(paths.pkgcache)
        mkdir(paths.build)
        mkdir(paths.build.logs)
        os.symlink(buildroot, paths.build.root)

        return cls(path)
    
    def __init__(self, path=None, recursed_paths=[]):
        self.paths = PoolPaths(path)
        self.path = dirname(self.paths.path)
        if not exists(self.paths.path):
            raise Error("no pool found (POOL_DIR=%s)" % self.path)
        self.buildroot = os.readlink(self.paths.build.root)
        self.pkgcache = PackageCache(self.paths.pkgcache)
        self.stocks = Stocks(self.paths.stocks, self.pkgcache,
                             recursed_paths + [ self.path ])
        mkdir(self.paths.tmp)
    
    def register(self, stock):
        self.stocks.register(stock)
        
    def unregister(self, stock):
        self.stocks.unregister(stock)

    @sync
    def exists(self, package):
        """Check if package exists in pool -> Returns bool"""
        if self.pkgcache.exists(package):
            return True

        if self.stocks.exists_source_version(*parse_package_id(package)):
            return True
        
        for subpool in self.subpools:
            if subpool.exists(package):
                return True

        return False

    @sync
    def list(self, all_versions=False):
        """List packages in pool -> list of (name, version) tuples.

        If all_versions is True, returns all versions of packages,
        otherwise, returns only the newest versions.
        """
        packages = set()
        for subpool in self.subpools:
            packages |= set(subpool.list(all_versions))
            
        packages |= set(self.pkgcache.list())
        for stock, path, versions in self.stocks.get_source_versions():
            package = basename(path)
            packages |= set([ (package, version) for version in versions ])
        
        if all_versions:
            return list(packages)

        newest = {}
        for name, version in packages:
            if not newest.has_key(name) or \
               deb_cmp_versions(newest[name], version) < 0:
                newest[name] = version

        return newest.items()

    @sync
    def getpath(self, package):
        """Get path to package in pool if it exists or None if it doesn't"""
        if '=' not in package:
            raise Error("getpath requires explicit version for `%s'" % package)
        
        path = self.pkgcache.getpath(package)
        if path:
            return path

        for subpool in self.subpools:
            path = subpool.getpath(package)
            if path:
                return path

        package_name, package_version = parse_package_id(package)
        build_outputdir = tempfile.mkdtemp(dir=self.paths.tmp, prefix="%s-%s." % (package_name, package_version))

        source_path = self.stocks.get_source_path(package_name, package_version)
        if not source_path:
            return None

        print "### BUILDING PACKAGE: " + package
        print "###           SOURCE: " + source_path
        
        # seek to version, build the package, seek back
        verseek.seek(source_path, package_version)
        error = os.system("cd %s && deckdebuild %s %s" % mkargs(source_path, self.buildroot, build_outputdir))
        verseek.seek(source_path)
        
        if error:
            shutil.rmtree(build_outputdir)
            raise Error("package `%s' failed to build" % package)

        print

        # copy *.debs and build output from output dir
        for fname in os.listdir(build_outputdir):
            fpath = join(build_outputdir, fname)
            if fname.endswith(".deb"):
                self.pkgcache.add(fpath)
            elif fname.endswith(".build"):
                shutil.copyfile(fpath, join(self.paths.build.logs, fname))

        shutil.rmtree(build_outputdir)

        path = self.pkgcache.getpath(package)
        if not path:
            raise Error("recently built package `%s' missing from cache" % package)
    
        return path

    def sync(self):
        """synchronise pool with registered stocks"""
        self.stocks.sync()
