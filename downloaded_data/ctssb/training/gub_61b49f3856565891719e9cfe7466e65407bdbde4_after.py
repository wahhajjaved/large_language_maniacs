import os
#
import download
import misc
import targetpackage
from toolpackage import ToolBuildSpec


class Guile (targetpackage.TargetBuildSpec):
    def set_mirror(self):
        self.with (version='1.8.1', format='gz')
        self.so_version = '17'

    def license_file (self):
        return '%(srcdir)s/COPYING.LIB' 

    def get_subpackage_names (self):
        return ['doc', 'devel', 'runtime', '']

    def get_dependency_dict (self):
        return {
            '' : ['guile-runtime'],
            'runtime': ['gmp', 'gettext', 'libtool-runtime'],
            'devel': ['guile-runtime'],
            'doc': ['texinfo'],
            }

    def get_build_dependencies (self):
        return ['gmp-devel', 'libtool']
        
    def __init__ (self, settings):
        targetpackage.TargetBuildSpec.__init__ (self, settings)
        self.set_mirror ()

    # FIXME: C&P.
    def guile_version (self):
        return '.'.join (self.ball_version.split ('.')[0:2])

    def patch (self):
        self.system ('cd %(srcdir)s && patch -p0 < %(patchdir)s/guile-reloc.patch')
        self.autoupdate ()

    def configure_flags (self):
        return misc.join_lines ('''
--without-threads
--with-gnu-ld
--enable-deprecated
--enable-discouraged
--disable-error-on-warning
--enable-relocation
--disable-rpath
''')
        
    def configure_command (self):
        return (targetpackage.TargetBuildSpec.configure_command (self)
                + self.configure_flags ())

    def compile (self):

        ## Ugh : broken dependencies barf with make -jX
        self.system ('cd %(builddir)s/libguile && make scmconfig.h ')
        targetpackage.TargetBuildSpec.compile (self)

    def configure (self):
        targetpackage.TargetBuildSpec.configure (self)
        self.update_libtool ()

    def install (self):
        targetpackage.TargetBuildSpec.install (self)
        
        
        majmin_version = '.'.join (self.expand ('%(version)s').split ('.')[0:2])
        
        self.dump ("prependdir GUILE_LOAD_PATH=$INSTALLER_PREFIX/share/guile/%(majmin_version)s\n",
                   '%(install_root)s/usr/etc/relocate/guile.reloc',
                   env=locals())
        
        ## can't assume that /usr/bin/guile is the right one.
        version = self.read_pipe ('''\
GUILE_LOAD_PATH=%(install_prefix)s/share/guile/* guile -e main -s  %(install_prefix)s/bin/guile-config --version 2>&1\
''').split ()[-1]
	#FIXME: c&p linux.py
        self.dump ('''\
#! /bin/sh
test "$1" = "--version" && echo "%(target_architecture)s-guile-config - Guile version %(version)s"
#test "$1" = "compile" && echo "-I $%(system_root)s/usr/include"
#test "$1" = "link" && echo "-L%(system_root)s/usr/lib -lguile -lgmp"
prefix=$(dirname $(dirname $0))
test "$1" = "compile" && echo "-I$prefix/include"
test "$1" = "link" && echo "-L$prefix/lib -lguile -lgmp"
exit 0
''',
             '%(install_prefix)s/cross/bin/%(target_architecture)s-guile-config')
        os.chmod ('%(install_prefix)s/cross/bin/%(target_architecture)s-guile-config' % self.get_substitution_dict (), 0755)


    
class Guile__mingw (Guile):
    def __init__ (self, settings):
        Guile.__init__ (self, settings)
        # Configure (compile) without -mwindows for console
        self.target_gcc_flags = '-mms-bitfields'


    def get_build_dependencies (self):
        return Guile.get_build_dependencies (self) +  ['regex-devel']
        
    def get_dependency_dict (self):
        d = Guile.get_dependency_dict (self)
        d['runtime'].append ('regex')
        return d

# FIXME: ugh, C&P to Guile__freebsd, put in cross-Guile?
    def configure_command (self):
        # watch out for whitespace
        builddir = self.builddir ()
        srcdir = self.srcdir ()


# don't set PATH_SEPARATOR; it will fuckup tool searching for the
# build platform.

        return (Guile.configure_command (self)
           + misc.join_lines ('''
LDFLAGS=-L%(system_root)s/usr/lib
CC_FOR_BUILD="
C_INCLUDE_PATH=
CPPFLAGS=
LIBRARY_PATH=
LDFLAGS=
cc
-I%(builddir)s
-I%(srcdir)s
-I%(builddir)s/libguile
-I.
-I%(srcdir)s/libguile"
'''))

    def config_cache_overrides (self, str):
        return str + '''
guile_cv_func_usleep_declared=${guile_cv_func_usleep_declared=yes}
guile_cv_exeext=${guile_cv_exeext=}
libltdl_cv_sys_search_path=${libltdl_cv_sys_search_path="%(system_root)s/usr/lib"}
'''

    def configure (self):
        if 0: # using patch
            targetpackage.TargetBuildSpec.autoupdate (self)

        if 1:
            self.file_sub ([('''^#(LIBOBJS=".*fileblocks.*)''',
                    '\\1')],
                   '%(srcdir)s/configure')

        Guile.configure (self)

        ## probably not necessary, but just be sure.
        for el in self.locate_files ('%(builddir)s', "Makefile"):
            self.file_sub ([('PATH_SEPARATOR = .', 'PATH_SEPARATOR = ;'),
                            ], el)
            
        self.file_sub ([
            #('^(allow_undefined_flag=.*)unsupported', '\\1'),
            ('-mwindows', ''),
            ],
               '%(builddir)s/libtool')
        self.file_sub ([
            #('^(allow_undefined_flag=.*)unsupported', '\\1'),
            ('-mwindows', ''),
            ],
               '%(builddir)s/guile-readline/libtool')

    def install (self):
        Guile.install (self)
        # dlopen-able .la files go in BIN dir, BIN OR LIB package
        self.system ('''mv %(install_root)s/usr/lib/lib*[0-9].la %(install_root)s/usr/bin''')

class Guile__linux (Guile):
    def compile_command (self):
        # FIXME: when not x-building, guile runs guile without
        # setting the proper LD_LIBRARY_PATH.
        return ('export LD_LIBRARY_PATH=%(builddir)s/libguile/.libs:$LD_LIBRARY_PATH;'
                + Guile.compile_command (self))

class Guile__freebsd (Guile):
    def config_cache_settings (self):
        return Guile.config_cache_settings (self) + '\nac_cv_type_socklen_t=yes'

    def set_mirror(self):
        self.with (version='1.8.0', format='gz')
        self.so_version = '17'

    def configure_command (self):
        # watch out for whitespace
        builddir = self.builddir ()
        srcdir = self.srcdir ()
        return (
            ''' guile_cv_use_csqrt="no" '''
           + Guile.configure_command (self)
           + misc.join_lines ('''\
CC_FOR_BUILD="
C_INCLUDE_PATH=
CPPFLAGS=
LIBRARY_PATH=
cc
-I%(builddir)s
-I%(srcdir)s
-I%(builddir)s/libguile
-I.
-I%(srcdir)s/libguile"
'''))

class Guile__darwin (Guile):
    def install (self):
        Guile.install (self)
        pat = self.expand ('%(install_root)s/usr/lib/libguile-srfi*.dylib')
        import glob
        for f in glob.glob (pat):
            directory = os.path.split (f)[0]
            src = os.path.basename (f)
            dst = os.path.splitext (os.path.basename (f))[0] + '.so'

            self.system ('cd %(directory)s && ln -s %(src)s %(dst)s', locals())
 
class Guile__darwin__x86 (Guile__darwin):
    def configure (self):
        Guile__darwin.configure (self)
        self.file_sub ([('guile-readline', '')],
                       '%(builddir)s/Makefile')
        
class Guile__cygwin (Guile):
    def __init__ (self, settings):
        Guile.__init__ (self, settings)
        self.with (version='1.8.1',
                   mirror=download.gnu, format='gz')
        self.replace_ltdl = False
        self.static_ltdl = False

    def get_subpackage_definitions (self):
        d = dict (Guile.get_subpackage_definitions (self))
        # FIXME: we do this for all cygwin packages
        d['runtime'].append ('/usr/bin/cyg*dll')

        if self.replace_ltdl:
            # libtool fixups
            d['runtime'].append ('/etc/postinstall')
            d['runtime'].append ('/usr/bin/cyg*dll-fixed')
        return d

    # Using gub dependencies only would be nice, but
    # we need to a lot of gup.gub_to_distro_deps ().
    def GUB_get_dependency_dict (self):
        d = Guile.get_dependency_dict (self)
        d['runtime'].append ('cygwin')
        return d

    # Using gub dependencies only would be nice, but
    # we need to a lot of gup.gub_to_distro_deps ().
    def GUB_get_build_dependencies (self):
        return Guile.get_build_dependencies (self) + ['libiconv-devel']

    # FIXME: uses mixed gub/distro dependencies
    def get_dependency_dict (self):
        d = Guile.get_dependency_dict (self)
        d[''] += ['cygwin']
        d['devel'] += ['cygwin'] + ['bash']
        d['runtime'] += ['cygwin', 'crypt']
        return d
 
    # FIXME: uses mixed gub/distro dependencies
    def get_build_dependencies (self):
        return ['crypt', 'gmp', 'gettext-devel', 'libiconv', 'libtool']

    def config_cache_overrides (self, str):
        return str + '''
guile_cv_func_usleep_declared=${guile_cv_func_usleep_declared=yes}
guile_cv_exeext=${guile_cv_exeext=}
libltdl_cv_sys_search_path=${libltdl_cv_sys_search_path="%(system_root)s/usr/lib"}
'''
    def configure (self):
        if 1:
            self.file_sub ([('''^#(LIBOBJS=".*fileblocks.*)''', '\\1')],
                           '%(srcdir)s/configure')
        Guile.configure (self)

        ## ugh code dup. 
        ## probably not necessary, but just be sure.
        for i in self.locate_files ('%(builddir)s', "Makefile"):
            self.file_sub ([
                ('PATH_SEPARATOR = .', 'PATH_SEPARATOR = ;'),
                ], i)

        self.file_sub ([
            ('^(allow_undefined_flag=.*)unsupported', '\\1'),
            ],
               '%(builddir)s/libtool')
        self.file_sub ([
            ('^(allow_undefined_flag=.*)unsupported', '\\1'),
            ],
               '%(builddir)s/guile-readline/libtool')

    def patch (self):
        pass

    def compile (self):
        Guile.compile (self)
        if self.static_ltdl:
#            self.file_sub (
# URG
# libtool misinterprets `-shared -lfoo -lbar -static -lbaz', translating
# it to gcc .../system/lib/libfoo.a  .../lib/libbar.a  .../lib/libbaz.a
#                [(''' (-static )?-lltdl''', ' -static -lltdl')],

# URG2, libtool sees the .a library, and then refuses to link to other
# shared libraries.  It says:
#
# *** I have the capability to make that library automatically link in when
# *** you link to this library.  But I can only do this if you have a
# *** shared version of the library, which you do not appear to have
# *** because the file extensions .a of this argument makes me believe
# *** that it is just a static archive that I should not used here.
#
# And then replaces all -lFoo with .../libfoo.a
#
#                [(''' -lltdl''', ' %(system_root)s/usr/lib/libltdl.dll.a')],
#                       '%(builddir)s/config.status')
            self.dump ('''
# Hack to link only libltdl statically.  Link using gcc directly,
# avoiding libtool.
include Makefile

.PHONY: $(static-ltdl)

static-ltdl = .libs/cygguile-$(LIBGUILE_INTERFACE_CURRENT).dll

static-ltdl: $(static-ltdl)

ldflags = -Wl,-rpath $(libdir) -Wl,-export-dynamic -Wl,-no-undefined

$(static-ltdl): $(libguile_la_OBJECTS) $(libguile_la_DEPENDENCIES)
	$(CCLD) -shared -o $@ $(ldflags) $(libguile_la_OBJECTS:%%.lo=.libs/%%.o) $(libguile_la_LIBADD:%%.lo=.libs/%%.o) $(LIBS: -lltdl=%(system_root)s/usr/lib/libltdl.dll.a) -lintl
''',
                       '%(builddir)s/libguile/static-ltdl.make')
            self.system ('''
cd %(builddir)s/libguile && make -f static-ltdl.make static-ltdl
''')

    def install (self):
        # FIXME: we do this for all cygwin packages
        Guile.install (self)
        self.install_readmes ()

        if self.replace_ltdl:
            self.libtool_cygltdl3_fixup ()

    def libtool_cygltdl3_fixup (self):
        # The current (1.5.22-1) cygltdl-3.dll is broken.  Supply our
        # own.
        self.system ('''
cp -pv %(system_root)s/usr/bin/cygltdl-3.dll %(install_root)s/usr/bin/cygltdtl-3.dll-fixed''')

        name = 'guile-postinstall.sh'
        postinstall = '''#! /bin/sh
if ! test -e /usr/bin/cygltdl3.dll-broken; then
    mv /usr/bin/cygltdl-3.dll /usr/bin/cygltdl3.dll-broken
    cp -f /usr/bin/cygltdl-3.dll-fixed /usr/bin/cygltld3.dll
fi
'''
        self.dump (postinstall,
                   '%(install_root)s/etc/postinstall/%(name)s',
                   env=locals ())

    # FIXME: we do most of this for all cygwin packages
    def category_dict (self):
        return {'': 'interpreters',
                'runtime': 'libs',
                'devel': 'devel libs',
                'doc': 'doc'}

    def description_dict (self):
        return {
            '': """The GNU extension language and Scheme interpreter (executable
Guile, the GNU Ubiquitous Intelligent Language for Extension, is a scheme
implementation designed for real world programming, supporting a
rich Unix interface, a module system, and undergoing rapid development.

`guile' is a scheme interpreter that can execute scheme scripts (with a
#! line at the top of the file), or run as an inferior scheme
process inside Emacs.
""",
            'runtime': '''The GNU extension language and Scheme interpreter (runtime libraries)
Guile shared object libraries and the ice-9 scheme module.  Guile is
the GNU Ubiquitous Intelligent Language for Extension.
''',
            'devel': """Development headers and static libraries for Guile
`libguile.h' etc. C headers, aclocal macros, the `guile-snarf' and
`guile-config' utilities, and static `libguile.a' libraries for Guile,
the GNU Ubiquitous Intelligent Language for Extension.
""",
            'doc': """The GNU extension language and Scheme interpreter (documentation)
This package contains the documentation for guile, including both
a reference manual (via `info guile'), and a tutorial (via `info
guile-tut').
""",
    }

class Guile__local (ToolBuildSpec, Guile):
    def configure_command (self):
        return (ToolBuildSpec.configure_command (self)
                + self.configure_flags ())

    def configure (self):
        ToolBuildSpec.configure (self)
        self.update_libtool ()
        
    def install (self):
        ToolBuildSpec.install (self)

        ## don't want local GUILE headers to interfere with compile.
        self.system ("rm -rf %(install_root)s/%(packaging_suffix_dir)s/usr/include/ %(install_root)s/%(packaging_suffix_dir)s/usr/bin/guile-config ")

    def get_build_dependencies (self):
        return ToolBuildSpec.get_build_dependencies (self) + Guile.get_build_dependencies (self)
    
    def __init__ (self, settings):
        ToolBuildSpec.__init__ (self, settings)
        self.set_mirror ()
