import imp
import os
import shutil
import sys

from dataanalysis.caches import cache_core
from dataanalysis.core import DataAnalysis, DataFile
from dataanalysis.hashtools import *
from printhook import log


class find_module_standard(DataAnalysis):
    cached=False # never    
    input_module_name=None

    def main(self):
        log("find module",self.input_module_name)

        module_name=self.input_module_name.handle
        self.found=imp.find_module(module_name,["."]+sys.path)
        fp, pathname, description=self.found
        
        log("will search in",["."]+sys.path)

        log("found as",pathname)

        self.module_path=pathname

cm= cache_core.CacheModule()
#cmi=caches.CacheModuleIRODS()
#cm.parent=cmi

class find_module_cached(DataAnalysis):
    cached=True
    cache=cm

    allow_timespent_adjustment=False
    hard_timespent_checks=False

    input_module_name=None
    input_module_version=None

    def main(self):
        log("find module as ",self.input_module_name)

        pathname=self.input_module_name.handle+".py"

        if not os.path.exists(pathname):
            pathname=imp.find_module(self.input_module_name.handle)[1]
            print(pathname)

        hashedfn=self.input_module_name.handle+"."+self.get_version()+"."+hash_for_file(open(pathname))[:8]+".py"


        shutil.copyfile(pathname,hashedfn)

        log("found as",pathname)
        log("will store as",hashedfn)

        self.module_path=hashedfn
        self.module_file=DataFile(hashedfn)


class load_module(DataAnalysis):
    cached=False # never    
    input_module_path=None

    def main(self):
        log("load module",self.input_module_path.input_module_name.handle)
        log("load as",self.input_module_path.module_path)

#        self.module = __import__(self.input_module_path.module_path)
        if not os.path.exists(self.input_module_path.module_path):
            raise Exception("can not open: "+self.input_module_path.module_path)

        self.module=imp.load_source(self.input_module_path.input_module_name.handle,self.input_module_path.module_path)
        #self.module=imp.load_module(,*self.input_module_path.found)


def import_git_module(name,version,local_gitroot=None,remote_git_root=None):
    if remote_git_root == "any":
        return import_git_module(name, version, local_gitroot, ["volodymyrss-private","volodymyrss-public"])

    if isinstance(remote_git_root,list):
        exceptions=[]
        for try_remote_git_root in remote_git_root:
            try:
                log("try to import with",remote_git_root)
                return import_git_module(name, version, local_gitroot, try_remote_git_root)
            except Exception as e:
                log("failed to import",e)
                exceptions.append(e)

        raise Exception("failed to import from git",exceptions)


    if local_gitroot is None:
        local_gitroot=os.getcwd()

    gitroot=os.environ["GIT_ROOT"] if "GIT_ROOT" in os.environ else "git@github.com:volodymyrss"
    if remote_git_root is not None:
        if remote_git_root=="volodymyrss-public":
            gitroot="https://github.com/volodymyrss"
        elif remote_git_root == "volodymyrss-private":
            gitroot="git@github.com:volodymyrss"

    netgit=os.environ["GIT_COMMAND"] if "GIT_COMMAND" in os.environ else "git"

    local_module_dir=local_gitroot+"/dda-"+name

    print("local git clone:",local_module_dir)

    cmd=netgit+" clone "+gitroot+"/dda-"+name+".git "+local_module_dir
    print(cmd)
    os.system(cmd)
    cmd="cd " + local_module_dir + "; " + netgit + " pull; git checkout " + version
    print(cmd)
    os.system(cmd)
    print name,local_module_dir+"/"+name+".py"
    return imp.load_source(name,local_module_dir+"/"+name+".py")



def import_analysis_module(name,version):
    return load_module(input_module_path=find_module_cached(input_module_name=name,input_module_version=version)).get().module



def load_by_name(m, local_gitroot=None,remote_git_root='any'):
    log("requested to load by name:",m)
    if isinstance(m,list):
        if m[0]=="filesystem":
            if m[2] is not None:
                name=m[1]

                fullpath=m[2].replace(".pyc",".py")

                return imp.load_source(name, fullpath), name
            else:
                m=m[1]
                log("using generic load from filesystem:",m[1])
        else:
            m=m[0]+"://"+m[1]
            log("loading with provider:",m)

    if m.startswith("/"):
        log("will import modul from cache")
        ms=m[1:].split("/",1)
        if len(ms)==2:
            m0,m1=ms
        else:
            m0=ms[0]
            m1="master"

        log("as",m0,m1)
        result=import_analysis_module(m0,m1),m0
        result[0].__dda_module_global_name__= m#(m0,m1)
        result[0].__dda_module_origin__="global_cache"
        return result
    elif m.startswith("git://"):
        log("will import modul from cache")
        ms=m[len("git://"):].split("/")

        if len(ms)==2:
            m0,m1=ms
        else:
            m0=ms[0]
            m1="master"

        log("as",m0,m1)
        result=import_git_module(m0,m1,local_gitroot=local_gitroot,remote_git_root=remote_git_root),m0
        result[0].__dda_module_global_name__= m
        result[0].__dda_module_origin__ = "git"
        return result
    else:
        fp, pathname, description=imp.find_module(m,["."]+sys.path)
        log("found as",  fp, pathname, description)
        return imp.load_module(m,fp,pathname,description), m

    return load_module(input_module_path=find_module_standard(input_module_name=name)).get().module
