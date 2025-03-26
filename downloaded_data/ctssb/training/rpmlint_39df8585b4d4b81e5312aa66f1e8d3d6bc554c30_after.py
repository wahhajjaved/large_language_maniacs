#############################################################################
# File          : SpecCheck.py
# Package       : rpmlint
# Author        : Frederic Lepied
# Created on    : Thu Oct  7 17:06:14 1999
# Version       : $Id$
# Purpose       : check the spec file of a source rpm.
#############################################################################

from Filter import *
import AbstractCheck
from Pkg import is_utf8
import re
import sys
import rpm
import string
import Config

# Don't check for hardcoded library paths in biarch packages
DEFAULT_BIARCH_PACKAGES = '^(gcc|glibc)'

# Don't check for hardcoded library paths in packages which can have
# their noarch files in /usr/lib/<package>/*, or packages that can't
# be installed on biarch systems
DEFAULT_HARDCODED_LIB_PATH_EXCEPTIONS = '/lib/(modules|cpp|perl5|rpm|hotplug)($|[\s/,])'

spec_regex = re.compile(".spec$")
patch_regex = re.compile("^\s*Patch(.*?)\s*:\s*([^\s]+)")
applied_patch_regex = re.compile("^\s*%patch.*-P\s*([^\s]*)|^\s*%patch([^\s]*)\s")
source_dir_regex = re.compile("^[^#]*(\$RPM_SOURCE_DIR|%{?_sourcedir}?)")
obsolete_tags_regex = re.compile("^(Copyright|Serial)\s*:\s*([^\s]+)")
buildroot_regex = re.compile('Buildroot\s*:\s*([^\s]+)', re.IGNORECASE)
prefix_regex = re.compile('^Prefix\s*:\s*([^\s]+)', re.IGNORECASE)
packager_regex = re.compile('^Packager\s*:\s*([^\s]+)', re.IGNORECASE)
make_check_regexp = re.compile('make\s+(check|test)', re.IGNORECASE)
rm_regex = re.compile('(^|\s)((.*/)?rm|%{?__rm}?) ')
tmp_regex = re.compile('^/')
setup_regex = re.compile('^%setup')
section = {}
for sec in ['description', 'prep', 'build', 'install', 'clean', 'files', 'changelog', 'package', 'check']:
	section[sec] = {}
	section[sec]['re'] = re.compile('^%' + sec + '(?:\s|$)')
rpm_buildroot_regex = re.compile('\${?RPM_BUILD_ROOT}?|%{?buildroot}?')
configure_start_regex = re.compile('\./configure')
configure_libdir_spec_regex = re.compile('ln |\./configure[^#]*--libdir=([^\s]+)[^#]*')
lib_package_regex = re.compile('^%package.*\Wlib')
mklibname_regex = re.compile('%mklibname')
ifarch_regex = re.compile('%ifn?arch')
if_regex = re.compile('%if\s+')
endif_regex = re.compile('%endif')
biarch_package_regex = re.compile(DEFAULT_BIARCH_PACKAGES)
hardcoded_lib_path_exceptions_regex = re.compile(Config.getOption('HardcodedLibPathExceptions', DEFAULT_HARDCODED_LIB_PATH_EXCEPTIONS))
prereq_regex = re.compile('^PreReq:\s*(.+?)\s*$', re.IGNORECASE)
buildprereq_regex = re.compile('^BuildPreReq:\s*(.+?)\s*$', re.IGNORECASE)
use_utf8 = Config.getOption('UseUTF8', Config.USEUTF8_DEFAULT)
macro_regex = re.compile('(%+)[{(]?(\w+)')

# Only check for /lib, /usr/lib, /usr/X11R6/lib
# TODO: better handling of X libraries and modules.
hardcoded_library_paths = '(/lib|/usr/lib|/usr/X11R6/lib/(?!([^/]+/)+)[^/]*\\.([oa]|la|so[0-9.]*))'
hardcoded_library_path_regex = re.compile('^[^#]*((^|\s+|\.\./\.\.|\${?RPM_BUILD_ROOT}?|%{?buildroot}?|%{?_prefix}?)' + hardcoded_library_paths + '(?=[\s;/])([^\s,;]*))')

# Requires(pre,post) is broken in rpm
scriptlet_requires_regex = re.compile('Requires\([^\)]*,')

def file2string(file):
    fd = open(file, "r")
    content = fd.readlines()
    fd.close()
    return content

class SpecCheck(AbstractCheck.AbstractCheck):

    def __init__(self):
        AbstractCheck.AbstractCheck.__init__(self, "SpecCheck")

    def check(self, pkg):
        if not pkg.isSource():
            return

        # lookup spec file
        files = pkg.files()
        spec_file = None
        for f in files.keys():
            if spec_regex.search(f):
                spec_file = pkg.dirName() + "/" + f
                break
        if not spec_file:
            printError(pkg, "no-spec-file")
        else:
            if f != pkg[rpm.RPMTAG_NAME] + ".spec":
                printError(pkg, "invalid-spec-name", f)

            # check content of spec file
            spec = file2string(spec_file)
            patches = {}
            applied_patches = []
            applied_patches_ifarch = []
            source_dir = None
            buildroot = 0
            clean = 0
            configure = 0
            configure_cmdline = ""
            mklibname = 0
            lib = 0
            if_depth = 0
            ifarch_depth = -1
            current_section = 'package'       
            buildroot_clean={'clean':0 , 'install':0}

            if use_utf8 and not is_utf8(spec_file):
                printError(pkg, "non-utf8-spec-file", f)

            # gather info from spec lines
            for line in spec:
            
                for i in section.keys():
                    if section[i]['re'].search(line):
                        current_section = i
                        continue

                if current_section in ('prep', 'build'):
                    if rpm_buildroot_regex.search(line):
                        printWarning(pkg, 'rpm-buildroot-usage', '%' + current_section, line[:-1])

                if make_check_regexp.search(line) and current_section != 'check':
                    printWarning(pkg, 'make-check-outside-check-section', line[:-1])

                if current_section in buildroot_clean.keys():
                    if rpm_buildroot_regex.search(line) and rm_regex.search(line):
                        buildroot_clean[current_section] = 1

                if ifarch_regex.search(line):
                    if_depth = if_depth + 1
                    ifarch_depth = if_depth

                if if_regex.search(line):
                    if_depth = if_depth + 1

                if setup_regex.search(line):
                    if line.find(' -q') < 1:
                        printWarning(pkg, 'setup-not-quiet')
            
                if endif_regex.search(line):
                    if ifarch_depth == if_depth:
                        ifarch_depth = -1
                    if_depth = if_depth - 1

                res=patch_regex.search(line)
                if res:
                    patches[res.group(1)] = res.group(2)
                else:
                    res = applied_patch_regex.search(line)
                    if res:
                        applied_patches.append(res.group(1) or res.group(2))
                        if ifarch_depth > 0:
                            applied_patches_ifarch.append(res.group(1))
                    elif not source_dir:
                        res = source_dir_regex.search(line)
                        if res:
                            source_dir = 1
                            printError(pkg, "use-of-RPM_SOURCE_DIR")

                res=obsolete_tags_regex.search(line)
                if res:
                    printWarning(pkg, "obsolete-tag", res.group(1))

                if configure:
                    if configure_cmdline[-1] == "\\":
                        configure_cmdline=configure_cmdline[:-1] + string.strip(line)
                    else:
                        configure = 0
                        res = configure_libdir_spec_regex.search(configure_cmdline)
                        if not res:
                            printError(pkg, "configure-without-libdir-spec")
                        elif res.group(1):
                            res = re.match(hardcoded_library_paths, res.group(1))
                            if res:
                                printError(pkg, "hardcoded-library-path", res.group(1), "in configure options")

                if current_section != 'changelog' and configure_start_regex.search(line):
                    configure = 1
                    configure_cmdline = string.strip(line)

                res = hardcoded_library_path_regex.search(line)
                if current_section != 'changelog' and res and not (biarch_package_regex.match(pkg[rpm.RPMTAG_NAME]) or hardcoded_lib_path_exceptions_regex.search(string.lstrip(res.group(1)))):
                    printError(pkg, "hardcoded-library-path", "in", string.lstrip(res.group(1)))

                res = buildroot_regex.search(line)
                if res:
                    buildroot=1
                    if tmp_regex.search(res.group(1)):
                        printWarning(pkg, 'hardcoded-path-in-buildroot-tag', res.group(1))

                res = packager_regex.search(line)
                if res:
                    printWarning(pkg, 'hardcoded-packager-tag', res.group(1))
                res=prefix_regex.search(line)
                if res:
                    if res.group(1) == '%{_prefix}' or res.group(1) == '%_prefix':
                        printWarning(pkg, 'redundant-prefix-tag')
                    else:
                        printWarning(pkg, 'hardcoded-prefix-tag', res.group(1))

                if current_section =='clean':
                    clean = 1

                if mklibname_regex.search(line):
                    mklibname = 1

                if lib_package_regex.search(line):
                    lib = 1

                res = prereq_regex.search(line)
                if res:
                    printWarning(pkg, 'prereq-use', res.group(1))

                res = buildprereq_regex.search(line)
                if res:
                    printWarning(pkg, 'buildprereq-use', res.group(1))

                if scriptlet_requires_regex.search(line):
                    printError(pkg, 'broken-syntax-in-scriptlet-requires', string.strip(line))

                if current_section == 'changelog':
                    res = macro_regex.search(line)
                    if res and len(res.group(1)) % 2:
                        printWarning(pkg, 'macro-in-%changelog', res.group(2))

            if 0 in buildroot_clean.values():
                printError(pkg, 'no-cleaning-of-buildroot')

            if not buildroot:
                printError(pkg, 'no-buildroot-tag')

            if not clean:
                printError(pkg, 'no-%clean-section')

            if lib and not mklibname:
                printError(pkg, 'lib-package-without-%mklibname')

            # process gathered info
            for p in patches.keys():
                if p in applied_patches_ifarch:
                    printWarning(pkg, "%ifarch-applied-patch", "Patch" + p + ":", patches[p])
                if p not in applied_patches:
                    if p == "" and "0" in applied_patches:
                        continue
                    if p == "0" and "" in applied_patches:
                        continue
                    printWarning(pkg, "patch-not-applied", "Patch" + p + ":", patches[p])

# Create an object to enable the auto registration of the test
check = SpecCheck()

# Add information about checks
if Config.info:
    addDetails(
'no-spec-file',
'''No spec file was specified in your RPM building. Please specify a valid
SPEC file to build a valid RPM package.''',

'invalid-spec-name',
'''Your spec filename must end with '.spec'. If it's not the case, rename your
file and rebuild your package.''',

'non-utf8-spec-file',
'''The character encoding of the spec file is not UTF-8.  Convert it for
example using iconv(1).''',

'use-of-RPM_SOURCE_DIR',
'''You use $RPM_SOURCE_DIR or %{_sourcedir} in your spec file. If you have to
use a directory for building, use $RPM_BUILD_ROOT instead.''',

'patch-not-applied',
'''A patch is included in your package but was not applied. Refer to the patches
documentation to see what's wrong.''',

'obsolete-tag',
'''The following tags are obsolete: Copyright and Serial. They must
be replaced by License and Epoch respectively.''',

'no-buildroot-tag',
'''The BuildRoot tag isn't used in your spec. It must be used in order to
allow building the package as non root on some systems.''',

'hardcoded-path-in-buildroot-tag',
'''A path is hardcoded in your Buildroot tag. It should be replaced
by something like %{_tmppath}/%name-root.''',

'hardcoded-packager-tag',
'''The Packager tag is hardcoded in your spec file. It should be removed, so
as to use rebuilder's own defaults.''',

'hardcoded-prefix-tag',
'''The Prefix tag is hardcoded in your spec file. It should be removed, so as
to allow package relocation.''',

'redundant-prefix-tag',
'''The Prefix tag is uselessly defined as %{_prefix} in your spec file. It
should be removed, as it is redundant with rpm defaults.''',

'hardcoded-library-path',
'''A library path is hardcoded to one of the following paths: /lib,
/usr/lib. It should be replaced by something like /%{_lib} or %{_libdir}.''',

'configure-without-libdir-spec',
'''A configure script is run without specifying the libdir. configure
options must be augmented with something like --libdir=%{_libdir}.''',

'no-%clean-section',
'''The spec file doesn't contain a %clean section to remove the files installed
by the %install section.''',

'lib-package-without-%mklibname',
'''The package name must be built using %mklibname to allow lib64 and lib32
coexistence.''',

'%ifarch-applied-patch',
'''A patch is applied inside an %ifarch block. Patches must be applied
on all architectures and may contain necessary configure and/or code
patch to be effective only on a given arch.''',

'prereq-use',
'''The use of PreReq is deprecated. In the majority of cases, a plain Requires
is enough and the right thing to do. Sometimes Requires(pre), Requires(post),
Requires(preun) and/or Requires(postun) can also be used instead of PreReq.''',

'buildprereq-use',
'''The use of BuildPreReq is deprecated, build dependencies are always required
before a package can be built.  Use plain BuildRequires instead.''',

'broken-syntax-in-scriptlet-requires',
'''Requires(pre,post) is accepted by rpm but leads to strange behaviour.
You should use Requires(pre) and Requires(post) instead.''',

'setup-not-quiet',
'''You should use -q to have a quiet extraction of the source tarball, as this
generate useless lines of log ( for buildbot, for example )''',

'no-cleaning-of-buildroot',
'''You should clean $RPM_BUILD_ROOT in the %clean section and just after the
beginning of %install section. Use "rm -Rf $RPM_BUILD_ROOT".''',

'rpm-buildroot-usage',
'''$RPM_BUILD_ROOT should not be touched during %build or %prep stage, as it
will break short circuiting.''',

'make-check-outside-check-section',
'''Make check or other automated regression test should be run in %check, as
they can be disabled with a rpm macro for short circuiting purposes.''',

'macro-in-%changelog',
'''Macros are expanded in %changelog too, which can in unfortunate cases lead
to the package not building at all, or other subtle unexpected conditions that
affect the build.  Even when that doesn\'t happen, the expansion results in
possibly "rewriting history" on subsequent package revisions and generally
odd entries eg. in source rpms, which is rarely wanted.  Avoid use of macros
in %changelog altogether, or use two '%'s to escape them, like '%%foo'.''',
)

# SpecCheck.py ends here

# Local variables:
# indent-tabs-mode: nil
# py-indent-offset: 4
# End:
# ex: ts=4 sw=4 et
