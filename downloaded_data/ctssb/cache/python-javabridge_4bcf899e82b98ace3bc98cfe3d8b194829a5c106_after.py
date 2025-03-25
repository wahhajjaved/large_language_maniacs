"""setup.py - build python-javabridge

python-javabridge is licensed under the BSD license.  See the
accompanying file LICENSE for details.

Copyright (c) 2003-2009 Massachusetts Institute of Technology
Copyright (c) 2009-2013 Broad Institute
All rights reserved.

"""

import errno
import glob
import os
import re
import sys
try:
    import sysconfig
except:
    import distutils.sysconfig as sysconfig
import subprocess
import traceback
import distutils.log
from distutils.errors import DistutilsSetupError, DistutilsExecError, LinkError
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext as _build_ext
from distutils.command.build_clib import build_clib
from distutils.ccompiler import CCompiler

try:
    from numpy import get_include
except ImportError:
    raise RuntimeError("""Numpy must be installed before installing javabridge.
It cannot be installed automatically when pip-installing javabridge.
See https://github.com/CellProfiler/python-javabridge/issues/30""")

# Hack to avoid importing the javabridge package
sys.path.append(os.path.join(os.path.dirname(__file__), 'javabridge'))
from locate import *

def in_cwd(basename):
    return os.path.join(os.path.dirname(__file__), basename)

def build_cython():
    """Compile the pyx files if we have them.
    
    The git repository has the .pyx files but not the .c files, and
    the source distributions that are uploaded to PyPI have the .c
    files and not the .pyx files. (The reason for the latter is that
    some versions of pip discovers the .pyx files and implicitly adds
    a dependency on Cython.) Therefore, if we have the .pyx files,
    compile them.

    """
    stems = ['_javabridge', '_javabridge_mac', '_javabridge_nomac']
    pyx_filenames = [in_cwd(s + '.pyx') for s in stems]
    c_filenames = [in_cwd(s + '.c') for s in stems]
    nc_pyx_filenames = [
        pyx for pyx, c in zip(pyx_filenames, c_filenames)
        if os.path.exists(pyx) and needs_compilation(c, pyx)]
    if len(nc_pyx_filenames) > 0:
        cmd = ['cython'] + nc_pyx_filenames
        subprocess.check_call(cmd)

def get_jvm_include_dirs():
    '''Return a sequence of paths to include directories for JVM defs'''
    jdk_home = find_jdk()
    java_home = find_javahome()
    include_dirs = []
    if is_win:
        if jdk_home is not None:
            jdk_include = os.path.join(jdk_home, "include")
            jdk_include_plat = os.path.join(jdk_include, sys.platform)
            include_dirs += [jdk_include, jdk_include_plat]
    elif is_mac:
        include_dirs += ['/System/Library/Frameworks/JavaVM.framework/Headers']
    elif is_linux:
        include_dirs += [os.path.join(java_home,'include'),
                         os.path.join(java_home,'include','linux')]
        
    return include_dirs
    
def ext_modules():
    extensions = []
    extra_link_args = None
    java_home = find_javahome()
    if java_home is None:
        raise JVMNotFoundError()
    jdk_home = find_jdk()
    include_dirs = [get_include()] + get_jvm_include_dirs()
    libraries = None
    library_dirs = None
    javabridge_sources = ['_javabridge.c']
    if is_mac:
        javabridge_sources += ['_javabridge_mac.c']
    else:
        javabridge_sources += ['_javabridge_nomac.c']
    if is_win:
        if is_mingw:
            #
            # Build libjvm from jvm.dll on Windows.
            # This assumes that we're using mingw32 for build
            #
            cmd = ["dlltool", "--dllname", 
                   os.path.join(jdk_home,"jre\\bin\\client\\jvm.dll"),
                   "--output-lib","libjvm.a",
                   "--input-def","jvm.def",
                   "--kill-at"]
            p = subprocess.Popen(cmd)
            p.communicate()
            library_dirs = [os.path.abspath(".")]
        else:
            #
            # Use the MSVC lib in the JDK
            #
            extra_link_args = ['/MANIFEST']
            jdk_lib = os.path.join(jdk_home, "lib")
            library_dirs = [jdk_lib]
            javabridge_sources.append("strtoull.c")

        libraries = ["jvm"]
    elif is_mac:
        javabridge_sources += [ "mac_javabridge_utils.c" ]
        extra_link_args = ['-framework', 'JavaVM']
    elif is_linux:
        library_dirs = [os.path.join(java_home,'jre','lib', arch, cs)
                        for arch in ['amd64', 'i386']
                        for cs in ['client', 'server']]
        libraries = ["jvm"]
    extension_kwargs = dict(
        name="javabridge._javabridge",
        sources=javabridge_sources,
        libraries=libraries,
        library_dirs=library_dirs,
        include_dirs=include_dirs,
        extra_link_args=extra_link_args)
    if not is_win:
        extension_kwargs["runtime_library_dirs"] =library_dirs

    extensions += [Extension(**extension_kwargs)]
    return extensions

SO = ".dll" if sys.platform == 'win32' \
    else ".jnilib" if sys.platform == 'darwin'\
    else sysconfig.get_config_var("SO")

def needs_compilation(target, *sources):
    try:
        target_date = os.path.getmtime(target)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise
        return True
    for source in sources:
        source_date = os.path.getmtime(source)
        if source_date > target_date:
            return True
    return False

def package_path(relpath):
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relpath))

class build_ext(_build_ext):
    def run(self, *args, **kwargs):
        self.build_java()
        build_cython()
        result = _build_ext.run(self, *args, **kwargs)
        self.build_java2cpython()
        return result

    def build_jar_from_single_source(self, jar, source):
        if sys.platform == 'win32':
            source = source.replace("/", os.path.sep)
        jar = self.get_ext_fullpath(jar)
        jar = os.path.splitext(jar)[0] + ".jar"
        if needs_compilation(jar, source):
            javac_loc = find_javac_cmd()
            javac_command = [javac_loc, "-source", "-6", "-target", "6", package_path(source)]
            self.spawn(javac_command)
            if not os.path.exists(os.path.dirname(jar)):
                os.mkdir(os.path.dirname(jar))
            jar_command = [find_jar_cmd(), 'cf', package_path(jar)]
            for klass in glob.glob(source[:source.rindex('.')] + '*.class'):
                java_klass_path = klass[klass.index(os.path.sep) + 1:].replace(os.path.sep, "/")
                jar_command.extend(['-C', package_path('java'), java_klass_path])
            self.spawn(jar_command)
            
    def build_java2cpython(self):
        sources = ["java/org_cellprofiler_javabridge_CPython.c"]
        distutils.log.info("building java2cpython library")
        

        # First, compile the source code to object files in the library
        # directory.  (This should probably change to putting object
        # files in a temporary build directory.)
        include_dirs = \
            [sysconfig.get_config_var("INCLUDEPY"), "java"] +\
            get_jvm_include_dirs()
        if is_win:
            python_lib_dir = os.path.join(
                sysconfig.get_config_var('platbase'),
                'LIBS')
            lib_name = "java2cpython" + SO
        else:
            python_lib_dir = sysconfig.get_config_var('LIBDIR')
            lib_name = "libjava2cpython" + SO
        library_dirs = [python_lib_dir]
        output_dir = os.path.splitext(self.get_ext_fullpath("javabridge.jars"))[0]
        export_symbols = ['Java_org_cellprofiler_javabridge_CPython_exec'] 
        objects = self.compiler.compile(sources,
                                        output_dir=self.build_temp,
                                        include_dirs=include_dirs,
                                        debug=self.debug)

        self.compiler.link(
            CCompiler.SHARED_OBJECT,
            objects, lib_name,
            output_dir=output_dir,
            debug=self.debug,
            library_dirs=library_dirs,
            export_symbols=export_symbols)
        if sys.platform == 'win32':
            temp_dir = os.path.dirname(objects[0])
            manifest_name = lib_name +".manifest"
            lib_path = os.path.join(output_dir, lib_name)
            manifest_file = os.path.join(temp_dir, manifest_name)
            lib_path = os.path.abspath(lib_path)
            manifest_file = os.path.abspath(manifest_file)
            out_arg = '-outputresource:%s;2' % lib_path
            try:
                self.compiler.spawn([
                    'mt.exe', '-nologo', '-manifest', manifest_file, 
                    out_arg])
            except DistutilsExecError, msg:
                raise LinkError(msg)
        

    def build_runnablequeue(self):
        jar = 'javabridge.jars.runnablequeue'
        source = 'java/org/cellprofiler/runnablequeue/RunnableQueue.java'
        self.build_jar_from_single_source(jar, source)
        
    def build_cpython(self):
        jar = 'javabridge.jars.cpython'
        source = 'java/org/cellprofiler/javabridge/CPython.java'
        self.build_jar_from_single_source(jar, source)
    
    def build_test(self):
        jar = 'javabridge.jars.test'
        source = 'java/org/cellprofiler/javabridge/test/RealRect.java'
        self.build_jar_from_single_source(jar, source)
    
    def build_java(self):
        self.build_runnablequeue()
        self.build_test()
        self.build_cpython()

    
def get_version():
    """Get version from git or file system.

    If this is a git repository, try to get the version number by
    running ``git describe``, then store it in
    javabridge/_version.py. Otherwise, try to load the version number
    from that file. If both methods fail, quietly return None.

    """
    git_version = None
    if os.path.exists(os.path.join(os.path.dirname(__file__), '.git')):
        import subprocess
        try:
            git_version = subprocess.Popen(['git', 'describe'], 
                                           stdout=subprocess.PIPE).communicate()[0].strip()
        except:
            pass

    version_file = os.path.join(os.path.dirname(__file__), 'javabridge', 
                                '_version.py')
    if os.path.exists(version_file):
        with open(version_file) as f:
            cached_version_line = f.read().strip()
        try:
            # From http://stackoverflow.com/a/3619714/17498
            cached_version = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", 
                                       cached_version_line, re.M).group(1)
        except:
            raise RuntimeError("Unable to find version in %s" % version_file)
    else:
        cached_version = None

    if git_version and git_version != cached_version:
        with open(version_file, 'w') as f:
            print >>f, '__version__ = "%s"' % git_version

    return git_version or cached_version


if __name__ == '__main__':
    if '/' in __file__:
        os.chdir(os.path.dirname(__file__))

    setup(name="javabridge",
          version=get_version(),
          description="Python wrapper for the Java Native Interface",
          long_description='''The python-javabridge package makes it easy to start a Java virtual
machine (JVM) from Python and interact with it. Python code can
interact with the JVM using a low-level API or a more convenient
high-level API. Python-javabridge was developed for and is used by the
cell image analysis software CellProfiler (cellprofiler.org).''',
          url="http://github.com/CellProfiler/python-javabridge/",
          packages=['javabridge'],
          classifiers=['Development Status :: 5 - Production/Stable',
                       'License :: OSI Approved :: BSD License',
                       'Programming Language :: Java',
                       'Programming Language :: Python :: 2 :: Only'
                       ],
          license='BSD License',
          install_requires=['numpy'],
          tests_require="nose",
          entry_points={'nose.plugins.0.10': [
                'javabridge = javabridge.noseplugin:JavabridgePlugin'
                ]},
          test_suite="nose.collector",
          package_data={"javabridge": [
              'jars/*.jar', 'jars/*%s' % SO, 'VERSION']},
          ext_modules=ext_modules(),
          cmdclass={'build_ext': build_ext})
