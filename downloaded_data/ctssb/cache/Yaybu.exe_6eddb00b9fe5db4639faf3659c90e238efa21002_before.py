import os
from setuptools import setup
import py2exe
import py2exe.build_exe
import pkg_resources
import ctypes.util
import importlib
import glob


# Patch py2exe.build_exe.LOADER so that it doesn't choke on gevent.os etc
py2exe.build_exe.LOADER = """
def __load():
    imp = __import__("imp")
    os = __import__("os")
    sys = __import__("sys")
    try:
        dirname = os.path.dirname(__loader__.archive)
    except NameError:
        dirname = sys.prefix
    path = os.path.join(dirname, '%s')
    #print "py2exe extension module", __name__, "->", path
    mod = imp.load_dynamic(__name__, path)
    mod.frozen = 1
__load()
del __load
"""


class BuildExe(py2exe.build_exe.py2exe):

    def _copy_assets(self, package, globs):
        src = os.path.join(os.path.dirname(importlib.import_module(package).__file__))
        dst = os.path.join(self.collect_dir, *package.split("."))

        for g in globs:
            for f in glob.glob(os.path.join(src, g)):
                basename = os.path.relpath(f, src)
                destination = os.path.join(dst, basename)
                destination_dir = os.path.dirname(destination)
                destination_rel = os.path.relpath(destination, self.collection_dir)

                if not os.path.exists(destination_dir):
                    self.mkpath(destination_dir)

                self.copy_file(f, destination)
                self.compiled_files.append(destination_rel)

    def copy_extensions(self, extensions):
        py2exe.build_exe.py2exe.copy_extensions(self, extensions)

        print "*** injecting non-code assets into library.zip ***"
        self._copy_assets("yaybu.tests", ["*.json"])        

    def create_binaries(self, py_files, extensions, dlls):
        py2exe.build_exe.py2exe.create_binaries(self, py_files, extensions, dlls)

        print "*** generate fake egg metadata ***"

        eggs = pkg_resources.require("Yaybu")
        for egg in eggs:
            print '%s == %s' % (egg.project_name, egg.version)
            path = os.path.join(self.exe_dir, '%s.egg-info' % egg.project_name)
            with open(path, "w") as fp:
                fp.write("Metadata-Version: 1.0\n")
                fp.write("Name: %s\n" % egg.project_name)
                fp.write("Version: %s\n" % egg.version)

        print "*** bundling cacert.pem ***"
        self.copy_file(
            os.path.join(os.getcwd(), "cacert.pem"),
            os.path.join(self.exe_dir, "cacert.pem"),
            )

        print "*** bundling python dll ***"
        self.copy_file(
            ctypes.util.find_library('python27.dll'),
            os.path.join(self.exe_dir, 'python27.dll'),
            )


setup(
    console=['YaybuShell.py'],
    cmdclass = {
            'py2exe': BuildExe,
    },
    options = {
        "py2exe": {
            "includes": [
                'pkg_resources',
                #'email.image',
                ],
            },
        },
    )
