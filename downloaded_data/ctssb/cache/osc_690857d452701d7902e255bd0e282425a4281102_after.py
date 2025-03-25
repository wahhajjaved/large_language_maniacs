# Copyright (C) 2006 Novell Inc.  All rights reserved.
# This program is free software; it may be used, copied, modified
# and distributed under the terms of the GNU General Public Licence,
# either version 2, or (at your option) any later version.



import os
import re
import sys
from tempfile import NamedTemporaryFile
from shutil import rmtree
from osc.fetch import *
from osc.core import get_buildinfo, store_read_apiurl, store_read_project, store_read_package, meta_exists, quote_plus, get_buildconfig
import osc.conf
import oscerr
import subprocess
try:
    from xml.etree import cElementTree as ET
except ImportError:
    import cElementTree as ET

from conf import config, cookiejar

change_personality = {
            'i686':  'linux32',
            'i586':  'linux32',
            'i386':  'linux32',
            'ppc':   'powerpc32',
            's390':  's390',
        }

can_also_build = { 
             'armv4l': [                                         'armv4l'                                 ],
             'armv5el':[                                         'armv4l', 'armv5el'                      ],
             'armv6l' :[                                         'armv4l', 'armv5el'                      ],
             'armv7el':[                                         'armv4l', 'armv5el', 'armv7el'           ],
             'armv7l' :[                                         'armv4l', 'armv5el', 'armv7el'           ],
             's390x':  ['s390'                                                                            ],
             'ppc64':  [                        'ppc', 'ppc64',                                           ],
             'i386':   [        'i586',                          'armv4l', 'armv5el', 'armv7el',    'sh4' ],
             'i586':   [                'i386',                  'armv4l', 'armv5el', 'armv7el',    'sh4' ],
             'i686':   [        'i586',                          'armv4l', 'armv5el', 'armv7el',    'sh4' ],
             'x86_64': ['i686', 'i586', 'i386',                  'armv4l', 'armv5el', 'armv7el',    'sh4' ],
             }

# real arch of this machine
hostarch = os.uname()[4]
if hostarch == 'i686': # FIXME
    hostarch = 'i586'


class Buildinfo:
    """represent the contents of a buildinfo file"""

    def __init__(self, filename, apiurl, buildtype = 'spec'):

        try:
            tree = ET.parse(filename)
        except:
            print >>sys.stderr, 'could not parse the buildinfo:'
            print >>sys.stderr, open(filename).read()
            sys.exit(1)

        root = tree.getroot()

        if root.find('error') != None:
            sys.stderr.write('buildinfo is broken... it says:\n')
            error = root.find('error').text
            sys.stderr.write(error + '\n')
            sys.exit(1)

        if not (apiurl.startswith('https://') or apiurl.startswith('http://')):
            raise urllib2.URLError('invalid protocol for the apiurl: \'%s\'' % apiurl)

        self.buildtype = buildtype

        # are we building .rpm or .deb?
        # XXX: shouldn't we deliver the type via the buildinfo?
        self.pacsuffix = 'rpm'
        if self.buildtype == 'dsc':
            self.pacsuffix = 'deb'

        self.buildarch = root.find('arch').text
        self.downloadurl = root.get('downloadurl')
        self.debuginfo = 0
        if root.find('debuginfo') != None:
            try:
                self.debuginfo = int(root.find('debuginfo').text)
            except ValueError:
                pass

        self.deps = []
        for node in root.findall('bdep'):
            p = Pac(node,
                    self.buildarch,       # buildarch is used only for the URL to access the full tree...
                    self.pacsuffix,
                    apiurl)
                    
            self.deps.append(p)

        self.vminstall_list = [ dep.name for dep in self.deps if dep.vminstall ]
        self.preinstall_list = [ dep.name for dep in self.deps if dep.preinstall ]
        self.runscripts_list = [ dep.name for dep in self.deps if dep.runscripts ]


    def has_dep(self, name):
        for i in self.deps:
            if i.name == name:
                return True
        return False

    def remove_dep(self, name):
        for i in self.deps:
            if i.name == name:
                self.deps.remove(i)
                return True
        return False


class Pac:
    """represent a package to be downloaded

    We build a map that's later used to fill our URL templates
    """
    def __init__(self, node, buildarch, pacsuffix, apiurl):

        self.mp = {}
        for i in ['name', 'package', 
                  'version', 'release', 
                  'project', 'repository', 
                  'preinstall', 'vminstall', 'noinstall', 'runscripts',
                 ]:
            self.mp[i] = node.get(i)

        self.mp['buildarch']  = buildarch
        self.mp['pacsuffix']  = pacsuffix

        self.mp['arch'] = node.get('arch') or self.mp['buildarch']

        self.mp['extproject'] = node.get('project').replace(':', ':/')
        self.mp['extrepository'] = node.get('repository').replace(':', ':/')
        self.mp['repopackage'] = node.get('package') or '_repository'
        self.mp['repoarch'] = node.get('repoarch') or self.mp['arch']

        if pacsuffix == 'deb' and not (self.mp['name'] and self.mp['arch'] and self.mp['version']):
            raise oscerr.APIError(
                "buildinfo for package %s/%s/%s is incomplete" 
                    % (self.mp['name'], self.mp['arch'], self.mp['version']))

        self.mp['apiurl'] = apiurl

        self.filename = '%(name)s-%(version)s-%(release)s.%(arch)s.%(pacsuffix)s' % self.mp
        self.partname = '%s.part' % self.filename

        self.mp['filename'] = self.filename
        if self.mp['repopackage'] == '_repository':
	        self.mp['repofilename'] = self.mp['name']
        else:
            self.mp['repofilename'] = self.mp['filename']

        # make the content of the dictionary accessible as class attributes
        self.__dict__.update(self.mp)


    def makeurls(self, cachedir, urllist):

        self.urllist = []

        # build up local URL
        # by using the urlgrabber with local urls, we basically build up a cache.
        # the cache has no validation, since the package servers don't support etags,
        # or if-modified-since, so the caching is simply name-based (on the assumption
        # that the filename is suitable as identifier)
        self.localdir = '%s/%s/%s/%s' % (cachedir, self.project, self.repository, self.arch)
        self.fullfilename = os.path.join(self.localdir, self.filename)
        self.fullpartname = os.path.join(self.localdir, self.partname)
        self.url_local = 'file://%s/' % self.fullfilename

        # first, add the local URL 
        self.urllist.append(self.url_local)

        # remote URLs
        for url in urllist:
            self.urllist.append(url % self.mp)

    def __str__(self):
        return self.name

    def __repr__(self):
        return "%s" % self.name



def get_built_files(pacdir, pactype):
    if pactype == 'rpm':
        b_built = subprocess.Popen(['find', os.path.join(pacdir, 'RPMS'), 
                                    '-name', '*.rpm'],
                                   stdout=subprocess.PIPE).stdout.read().strip()
        s_built = subprocess.Popen(['find', os.path.join(pacdir, 'SRPMS'), 
                                    '-name', '*.rpm'],
                                   stdout=subprocess.PIPE).stdout.read().strip()
    elif pactype == 'kiwi':
        b_built = subprocess.Popen(['find', os.path.join(pacdir, 'KIWI'), 
                                    '-type', 'f'],
                                   stdout=subprocess.PIPE).stdout.read().strip()
    else:
        b_built = subprocess.Popen(['find', os.path.join(pacdir, 'DEBS'),
                                    '-name', '*.deb'],
                                   stdout=subprocess.PIPE).stdout.read().strip()
        s_built = subprocess.Popen(['find', os.path.join(pacdir, 'SOURCES.DEB'), 
                                    '-type', 'f'],
                                   stdout=subprocess.PIPE).stdout.read().strip()
    return s_built, b_built


def get_prefer_pkgs(dirs, wanted_arch):
    # XXX learn how to do the same for Debian packages
    import glob
    paths = []
    for dir in dirs:
        paths += glob.glob(os.path.join(os.path.abspath(dir), '*.rpm'))
    prefer_pkgs = []

    for path in paths:
        if path.endswith('src.rpm'):
            continue
        if path.find('-debuginfo-') > 0:
            continue
        arch, name = subprocess.Popen(['rpm', '-qp', 
                                      '--nosignature', '--nodigest', 
                                      '--qf', '%{arch} %{name}\n', path], 
                                      stdout=subprocess.PIPE).stdout.read().split()
        # instead of thip assumption, we should probably rather take the
        # requested arch for this package from buildinfo
        # also, it will ignore i686 packages, how to handle those?
        if arch == wanted_arch or arch == 'noarch':
            prefer_pkgs.append((name, path))

    return dict(prefer_pkgs)


def main(opts, argv):

    repo = argv[0]
    arch = argv[1]
    build_descr = argv[2]
    xp = []

    build_type = os.path.splitext(build_descr)[1][1:]
    if build_type not in ['spec', 'dsc', 'kiwi']:
        raise oscerr.WrongArgs(
                "Unknown build type: '%s'. Build description should end in .spec, .dsc or .kiwi." \
                        % build_type)

    buildargs = []
    if not opts.userootforbuild:
        buildargs.append('--norootforbuild')
    if opts.clean:
        buildargs.append('--clean')
    if opts.noinit:
        buildargs.append('--noinit')
    if opts.nochecks:
        buildargs.append('--no-checks')
    if not opts.no_changelog:
        buildargs.append('--changelog')
    if opts.jobs:
        buildargs.append('--jobs %s' % opts.jobs)
    if opts.icecream:
        buildargs.append('--icecream %s' % opts.icecream)
        xp.append('icecream')
        xp.append('gcc-c++')
    if opts.ccache:
        buildargs.append('--ccache')
        xp.append('ccache')
    if opts.baselibs:
        buildargs.append('--baselibs')
    if opts.debuginfo:
        buildargs.append('--debug')
    if opts._with:
        buildargs.append('--with %s' % opts._with)
    if opts.without:
        buildargs.append('--without %s' % opts.without)
# FIXME: quoting
#    if opts.define:
#        buildargs.append('--define "%s"' % opts.define)

    if opts.alternative_project:
        prj = opts.alternative_project
        pac = '_repository'
        apiurl = config['apiurl']
    else:
        prj = store_read_project(os.curdir)
        if opts.local_package:
            pac = '_repository'
        else:
            pac = store_read_package(os.curdir)
        apiurl = store_read_apiurl(os.curdir)

    if not os.path.exists(build_descr):
        print >>sys.stderr, 'Error: build description named \'%s\' does not exist.' % build_descr
        return 1

    # make it possible to override configuration of the rc file
    for var in ['OSC_PACKAGECACHEDIR', 'OSC_SU_WRAPPER', 'OSC_BUILD_ROOT']: 
        val = os.getenv(var)
        if val:
            if var.startswith('OSC_'): var = var[4:]
            var = var.lower().replace('_', '-')
            if config.has_key(var):
                print 'Overriding config value for %s=\'%s\' with \'%s\'' % (var, config[var], val)
            config[var] = val

    config['build-root'] = config['build-root'] % { 'repo': repo, 'arch': arch,
                                                    'project' : prj, 'package' : pac
                                                  }

    if not opts.extra_pkgs:
        extra_pkgs = config['extra-pkgs']
    elif opts.extra_pkgs == ['']:
        extra_pkgs = None
    else:
        extra_pkgs = opts.extra_pkgs

    if xp:
        extra_pkgs += xp


    print 'Getting buildinfo from server'
    tempdir = '/tmp'
    if sys.platform[:3] == 'win':
        tempdir = os.getenv('TEMP')
    bi_file = NamedTemporaryFile(suffix='.xml', prefix='buildinfo.', dir = tempdir)
    try:
        bi_text = ''.join(get_buildinfo(apiurl, 
                                        prj,
                                        pac,
                                        repo, 
                                        arch, 
                                        specfile=open(build_descr).read(), 
                                        addlist=extra_pkgs))
    except urllib2.HTTPError, e:
        if e.code == 404:
        # check what caused the 404
            if meta_exists(metatype='prj', path_args=(quote_plus(prj), ),
                           template_args=None, create_new=False):
                if pac == '_repository' or meta_exists(metatype='pkg', path_args=(quote_plus(prj), quote_plus(pac)),
                                                       template_args=None, create_new=False):
                    print >>sys.stderr, 'wrong repo/arch?'
                    sys.exit(1)
                else:
                    print >>sys.stderr, 'The package \'%s\' does not exists - please ' \
                                        'rerun with \'--local-package\'' % pac
                    sys.exit(1)
            else:
                print >>sys.stderr, 'The project \'%s\' does not exists - please ' \
                                    'rerun with \'--alternative-project <alternative_project>\'' % prj
                sys.exit(1)
        else:
            raise
    bi_file.write(bi_text)
    bi_file.flush()

    bi = Buildinfo(bi_file.name, apiurl, build_type)
    if bi.debuginfo and not opts.disable_debuginfo:
        buildargs.append('--debug')
    buildargs = ' '.join(set(buildargs))

    # real arch of this machine 
    # vs.
    # arch we are supposed to build for
    if hostarch != bi.buildarch:
        if not bi.buildarch in can_also_build.get(hostarch, []):
            print >>sys.stderr, 'Error: hostarch \'%s\' cannot build \'%s\'.' % (hostarch, bi.buildarch)
            return 1

    rpmlist_prefers = []
    if opts.prefer_pkgs:
        print 'Evaluating preferred packages'
        # the resulting dict will also contain packages which are not on the install list
        # but they won't be installed
        prefer_pkgs = get_prefer_pkgs(opts.prefer_pkgs, bi.buildarch)

        for name, path in prefer_pkgs.iteritems():
            if bi.has_dep(name):
                # We remove a preferred package from the buildinfo, so that the
                # fetcher doesn't take care about them.
                # Instead, we put it in a list which is appended to the rpmlist later.
                # At the same time, this will make sure that these packages are
                # not verified.
                bi.remove_dep(name)
                rpmlist_prefers.append((name, path))
                print ' - %s (%s)' % (name, path)
                continue

    print 'Updating cache of required packages'

    urllist = []

    # transform 'url1, url2, url3' form into a list
    if 'urllist' in config:
        if type(config['urllist']) == str:
	    re_clist = re.compile('[, ]+')
            urllist = [ i.strip() for i in re_clist.split(config['urllist'].strip()) ]
        else:
            urllist = config['urllist']

    # OBS 1.5 and before has no downloadurl defined in buildinfo
    if bi.downloadurl:
        urllist.append(bi.downloadurl + '/%(extproject)s/%(extrepository)s/%(arch)s/%(filename)s')
    urllist.append( '%(apiurl)s/build/%(project)s/%(repository)s/%(repoarch)s/%(repopackage)s/%(repofilename)s' )

    fetcher = Fetcher(cachedir = config['packagecachedir'], 
                      urllist = urllist,
                      api_host_options = config['api_host_options'],
                      http_debug = config['http_debug'],
                      cookiejar=cookiejar)

    # now update the package cache
    fetcher.run(bi)

    # Make packages from buildinfo available as repos for kiwi
    if build_type == 'kiwi':
        if not os.path.exists('repos'):
            os.mkdir('repos')
        else:
            rmtree('repos')
            os.mkdir('repos')
        for i in bi.deps:
            # project
            pdir = str(i.extproject).replace(':/', ':')
            # repo
            rdir = str(i.extrepository).replace(':/', ':')
            # arch
            adir = i.repoarch
            # project/repo
            prdir = "repos/"+pdir+"/"+rdir
            # project/repo/arch
            pradir = prdir+"/"+adir
            # source fullfilename
            sffn = i.fullfilename
            print "Using package: "+sffn
            # target fullfilename
            tffn = pradir+"/"+sffn.split("/")[-1]
            if not os.path.exists(os.path.join(pradir)):
                os.makedirs(os.path.join(pradir))
            if not os.path.exists(tffn):
                os.symlink(sffn, tffn)

    if bi.pacsuffix == 'rpm':
        """don't know how to verify .deb packages. They are verified on install
        anyway, I assume... verifying package now saves time though, since we don't
        even try to set up the buildroot if it wouldn't work."""

        if config['build-type'] == "xen" or config['build-type'] == "kvm":
            print 'Skipping verification of package signatures due to secure VM build'
        elif opts.no_verify:
            print 'Skipping verification of package signatures'
        else:
            print 'Verifying integrity of cached packages'
            verify_pacs([ i.fullfilename for i in bi.deps ])

    print 'Writing build configuration'

    rpmlist = [ '%s %s\n' % (i.name, i.fullfilename) for i in bi.deps if not i.noinstall ]
    rpmlist += [ '%s %s\n' % (i[0], i[1]) for i in rpmlist_prefers ]

    rpmlist.append('preinstall: ' + ' '.join(bi.preinstall_list) + '\n')
    rpmlist.append('vminstall: ' + ' '.join(bi.vminstall_list) + '\n')
    rpmlist.append('runscripts: ' + ' '.join(bi.runscripts_list) + '\n')

    tempdir = '/tmp'
    if sys.platform[:3] == 'win':
        tempdir = os.getenv('TEMP')
    rpmlist_file = NamedTemporaryFile(prefix='rpmlist.', dir = tempdir)
    rpmlist_file.writelines(rpmlist)
    rpmlist_file.flush()
    os.fsync(rpmlist_file)



    print 'Getting buildconfig from server'
    tempdir = '/tmp'
    if sys.platform[:3] == 'win':
        tempdir = os.getenv('TEMP')
    bc_file = NamedTemporaryFile(prefix='buildconfig.', dir = tempdir)
    bc_file.write(get_buildconfig(apiurl, prj, pac, repo, arch))
    bc_file.flush()

    vm_options=""
    if config['build-device'] and config['build-memory'] and config['build-type']:
       if config['build-type'] == "kvm":
          vm_options="--kvm " + config['build-device']
       elif config['build-type'] == "xen":
          vm_options="--xen " + config['build-device']
       else:
          print "ERROR: unknown VM is set ! (" + config['build-type'] + ")"
          sys.exit(1)
       if config['build-swap']:
          vm_options+=" --swap " + config['build-swap']
       if config['build-memory']:
          vm_options+=" --memory " + config['build-memory']
    
    print 'Running build'
    cmd = '%s --root=%s --rpmlist=%s --dist=%s --arch=%s %s %s %s' \
                 % (config['build-cmd'],
                    config['build-root'],
                    rpmlist_file.name, 
                    bc_file.name, 
                    bi.buildarch,
                    vm_options,
                    build_descr, 
                    buildargs)

    if config['su-wrapper'].startswith('su '):
        tmpl = '%s \'%s\''
    else:
        tmpl = '%s %s'

    # change personality, if needed
    cmd = tmpl % (config['su-wrapper'], cmd)
    if hostarch != bi.buildarch:
        cmd = (change_personality.get(bi.buildarch, '') + ' ' + cmd).strip()

    rc = subprocess.call(cmd, shell=True)
    if rc: 
        print
        print 'The buildroot was:', config['build-root']
        sys.exit(rc)

    pacdir = os.path.join(config['build-root'], '.build.packages')
    if os.path.islink(pacdir):
        pacdir = os.readlink(pacdir)
        pacdir = os.path.join(config['build-root'], pacdir)

    if os.path.exists(pacdir):
        (s_built, b_built) = get_built_files(pacdir, bi.pacsuffix)
        
        print
        if s_built: print s_built
        print
        print b_built

        if opts.keep_pkgs:
            for i in b_built.splitlines() + s_built.splitlines():
                import shutil
                shutil.copy2(i, os.path.join(opts.keep_pkgs, os.path.basename(i)))


