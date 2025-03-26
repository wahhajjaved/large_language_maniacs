#!/usr/bin/env python

from __future__ import print_function
import os, shutil
import os.path as P
import re, sys
from glob import glob
import subprocess
from BinaryBuilder import CMakePackage, GITPackage, Package, stage, warn, \
     PackageError, HelperError, SVNPackage, Apps, write_vw_config, write_asp_config
from BinaryDist import fix_install_paths

def strip_flag(flag, key, env):
    ret = []
    hit = None
    if not key in env:
        return
    for test in env[key].split():
        m = re.search(flag, test)
        if m:
            hit = m
        else:
            ret.append(test)
    if ret:
        env[key] = ' '.join(ret).strip()
    else:
        del env[key]
    return hit, env

class ccache(Package):
    src     = 'http://samba.org/ftp/ccache/ccache-3.1.9.tar.bz2'
    chksum  = 'e80a5cb7301e72f675097246d722505ae56e3cd3'

class m4(Package):
    src     = 'http://ftp.gnu.org/gnu/m4/m4-1.4.17.tar.gz'
    chksum  = '4f80aed6d8ae3dacf97a0cb6e989845269e342f0'
    
class libtool(Package):
    src     = 'http://ftpmirror.gnu.org/libtool/libtool-2.4.2.tar.gz'
    chksum  = '22b71a8b5ce3ad86e1094e7285981cae10e6ff88'

class autoconf(Package):
    src='http://ftp.gnu.org/gnu/autoconf/autoconf-2.69.tar.gz'
    chksum  = '562471cbcb0dd0fa42a76665acf0dbb68479b78a'

class automake(Package):
    src='ftp://ftp.gnu.org/gnu/automake/automake-1.14.1.tar.gz'
    chksum  = '0bb1714b78d70cab9907d2013082978a28f48a46'
    
class cmake(Package):
    src     = 'http://www.cmake.org/files/v2.8/cmake-2.8.11.2.tar.gz'
    chksum  = '31f217c9305add433e77eff49a6eac0047b9e929'
    # cmake pollutes the doc folder
    @stage
    def install(self):
        super(cmake, self).install()
        cmd = ['rm', '-vrf'] + glob(P.join( self.env['INSTALL_DIR'], 'doc', 'cmake*' ))
        self.helper(*cmd)

class chrpath(Package):
    src     = 'http://ftp.debian.org/debian/pool/main/c/chrpath/chrpath_0.13.orig.tar.gz'
    chksum  = '11ff3e3dda2acaf1e529475f394f74f2ef7a8204'
    # chrpath pollutes the doc folder
    @stage
    def install(self):
        super(chrpath, self).install()
        cmd = ['rm', '-vrf'] + glob(P.join( self.env['INSTALL_DIR'], 'doc', 'chrpath*' ))
        self.helper(*cmd)

class bzip2(Package):
    src     = 'http://www.bzip.org/1.0.6/bzip2-1.0.6.tar.gz'
    chksum  = '3f89f861209ce81a6bab1fd1998c0ef311712002'
    def configure(self): pass
    @stage
    def install(self):
        # Copy just the things we need.
        self.helper(*['mkdir','-p',P.join(self.env['INSTALL_DIR'],'include')]);
        self.helper(*['mkdir','-p',P.join(self.env['INSTALL_DIR'],'lib')]);
        self.helper(*['mkdir','-p',P.join(self.env['INSTALL_DIR'],'bin')]);
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, '*.h')) + \
              [P.join(self.env['INSTALL_DIR'], 'include')]
        self.helper(*cmd)
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, 'lib*')) + \
              [P.join(self.env['INSTALL_DIR'], 'lib')]
        self.helper(*cmd)
        cmd = ['cp', '-vf', P.join(self.workdir, 'bzip2'),
               P.join(self.env['INSTALL_DIR'], 'bin')]
        self.helper(*cmd)

class pbzip2(Package):
    src     = 'http://compression.ca/pbzip2/pbzip2-1.1.6.tar.gz'
    chksum  = '3b4d0ffa3ac362c3702793cc5d9e61664d468aeb'
    def configure(self): pass
    def compile(self):
        self.helper('sed','-ibak','-e','s# g++# %s#g' % self.env['CXX'],
                    'Makefile');
        cflags = 'CFLAGS = -I' + P.join(self.env['INSTALL_DIR'], 'include') + \
                 ' -L' + P.join(self.env['INSTALL_DIR'], 'lib') + ' '
        self.helper('sed','-ibak','-e','s#CFLAGS = #%s#g' % cflags, 'Makefile')
        super(pbzip2, self).compile()
    def install(self):
        # Copy just the things we need.
        cmd = ['cp', '-vf', P.join(self.workdir, 'pbzip2'),
               P.join(self.env['INSTALL_DIR'], 'bin')]
        self.helper(*cmd)

class parallel(Package):
    src     = 'http://ftp.gnu.org/gnu/parallel/parallel-20130722.tar.bz2'
    chksum  = 'd794ac9c2c0a73d430b9ae2ebbbd07e4eb2fcaf0'

    @stage
    def install(self):
        super(parallel, self).install()
        # Copy parallel to libexec, as we want it to be hidden there in
        # the released ASP distribution.
        libexec = P.join( self.env['INSTALL_DIR'], 'libexec' )
        self.helper('mkdir', '-p', libexec)
        cmd = ['cp', '-vf', P.join( self.env['INSTALL_DIR'], 'bin', 'parallel' ),
               libexec]
        self.helper(*cmd)

class tnt(Package):
    src     = 'http://math.nist.gov/tnt/tnt_126.zip'
    chksum  = '32f628d7e28a6e373ec2ff66c70c1cb25783b946'
    patches = 'patches/tnt'

    def __init__(self, env):
        super(tnt, self).__init__(env)
        # Our source doesn't unpack into a directory. So our work
        # directory is just the outer containing folder.
        self.workdir = P.join(self.env['BUILD_DIR'], self.pkgname)
    def configure(self): pass
    def compile(self): pass

    @stage
    def install(self):
        d = P.join('%(INSTALL_DIR)s' % self.env, 'include', 'tnt')
        self.helper('mkdir', '-p', d)
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, '*.h')) + [d]
        self.helper(*cmd)

class jama(Package):
    src     = 'http://math.nist.gov/tnt/jama125.zip'
    chksum  = '5ca8b154d0a0c30e2c50700ffe70567315ebcf2c'

    def __init__(self, env):
        super(jama, self).__init__(env)
        self.workdir = P.join(self.env['BUILD_DIR'], self.pkgname)
    def configure(self): pass
    def compile(self): pass

    @stage
    def install(self):
        d = P.join('%(INSTALL_DIR)s' % self.env, 'include', 'jama')
        self.helper('mkdir', '-p', d)
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, '*.h')) + [d]
        self.helper(*cmd)

class openjpeg2(CMakePackage):
    src     = 'http://openjpeg.googlecode.com/files/openjpeg-2.0.0.tar.gz'
    chksum  = '0af78ab2283b43421458f80373422d8029a9f7a7'

    @stage
    def configure(self):
        super(openjpeg2, self).configure(other=['-DBUILD_SHARED_LIBS=ON'])

class tiff(Package):
    src     = 'http://download.osgeo.org/libtiff/tiff-4.0.3.tar.gz'
    chksum  = '652e97b78f1444237a82cbcfe014310e776eb6f0'

    def configure(self):
        super(tiff, self).configure(
            with_ = ['jpeg', 'png', 'zlib'],
            without = ['x'],
            enable=('shared',),
            disable = ['static', 'lzma', 'cxx', 'logluv'])

class libgeotiff(CMakePackage):
    src='http://download.osgeo.org/geotiff/libgeotiff/libgeotiff-1.4.0.tar.gz'
    chksum='4c6f405869826bb7d9f35f1d69167e3b44a57ef0'
    def configure(self):
        super(libgeotiff, self).configure( other=['-DBUILD_SHARED_LIBS=ON',
                                                  '-DBUILD_STATIC_LIBS=OFF'] )
        
class gdal(Package):
    src     = 'http://download.osgeo.org/gdal/1.10.1/gdal-1.10.1.tar.gz'
    chksum  = 'b4df76e2c0854625d2bedce70cc1eaf4205594ae'
    patches = 'patches/gdal'

    @stage
    def configure(self):
        # Parts of GDAL will attempt to load libproj manual (something
        # we can't see or correct in the elf tables). This sed should
        # correct that problem.
        self.env['LDFLAGS'] += ' -Wl,-rpath -Wl,%(INSTALL_DIR)s/lib -ljpeg -lproj' % self.env
        self.helper('sed', '-ibak', '-e', 's/libproj./libproj.0./g', 'ogr/ogrct.cpp')

        w = ['threads', 'libtiff', 'geotiff=' + self.env['INSTALL_DIR'], 'jpeg=' + self.env['INSTALL_DIR'], 'png', 'zlib', 'pam','openjpeg=' + self.env['INSTALL_DIR']]
        wo = \
            '''bsb cfitsio curl dods-root dwg-plt dwgdirect ecw epsilon expat expat-inc expat-lib fme
             geos gif grass hdf4 hdf5 idb ingres jasper jp2mrsid kakadu libgrass
             macosx-framework mrsid msg mysql netcdf oci oci-include oci-lib odbc ogdi pcidsk
             pcraster perl pg php pymoddir python ruby sde sde-version spatialite sqlite3
             static-proj4 xerces xerces-inc xerces-lib libiconv-prefix libiconv xml2 pcre freexl'''.split()

        self.helper('./autogen.sh')
        super(gdal,self).configure(with_=w, without=wo, disable='static', enable='shared')

    @stage
    def install(self):
        super(gdal, self).install()
        # Copy gdal_translate and gdalinfo to libexec, as we want it
        # to be hidden there in the released ASP distribution.
        progs = ['gdalinfo', 'gdal_translate']
        libexec = P.join( self.env['INSTALL_DIR'], 'libexec' )
        self.helper('mkdir', '-p', libexec)
        for prog in progs:
            cmd = ['cp', '-vf', P.join( self.env['INSTALL_DIR'], 'bin',
                                        prog ), libexec]
            self.helper(*cmd)

class ilmbase(Package):
    src     = 'http://download.savannah.nongnu.org/releases/openexr/ilmbase-1.0.2.tar.gz'
    chksum  = 'fe6a910a90cde80137153e25e175e2b211beda36'
    patches = 'patches/ilmbase'

    @stage
    def configure(self):
        self.env['AUTOHEADER'] = 'true'
        # XCode in snow leopard removed this flag entirely (way to go, guys)
        self.helper('sed', '-ibak', '-e', 's/-Wno-long-double//g', 'configure.ac')
        self.helper('autoupdate', 'configure.ac')
        self.helper('autoreconf', '-fvi')
        super(ilmbase, self).configure(disable='static')

class openexr(Package):
    src     = 'http://download.savannah.nongnu.org/releases/openexr/openexr-1.7.0.tar.gz'
    chksum  = '91d0d4e69f06de956ec7e0710fc58ec0d4c4dc2b'
    patches = 'patches/openexr'

    @stage
    def configure(self):
        self.env['AUTOHEADER'] = 'true'
        # XCode in snow leopard removed this flag entirely (way to go, guys)
        self.helper('sed', '-ibak', '-e', 's/-Wno-long-double//g', 'configure.ac')
        self.helper('autoupdate', 'configure.ac')
        self.helper('autoreconf', '-fvi')
        super(openexr,self).configure(with_=('ilmbase-prefix=%(INSTALL_DIR)s' % self.env),
                                      disable=('ilmbasetest', 'imfexamples', 'static'))

class proj(Package):
    src     = 'http://download.osgeo.org/proj/proj-4.8.0.tar.gz'
    chksum  = '5c8d6769a791c390c873fef92134bf20bb20e82a'
    def install(self):
        super(proj, self).install()
        # Copy extra files which are needed by libgeotiff to compile.
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, 'src/*.h')) + \
              [P.join(self.env['INSTALL_DIR'], 'include')]
        self.helper(*cmd)

    @stage
    def configure(self):
        super(proj,self).configure(disable='static', without='jni')

class curl(Package):
    src     = 'http://curl.haxx.se/download/curl-7.33.0.tar.bz2'
    chksum  = 'b0dc79066f31a000190fd8a15277738e8c1940aa'

    @stage
    def configure(self):
        w = ['zlib=%(INSTALL_DIR)s' % self.env]
        wo = 'ssl libidn'.split()
        super(curl,self).configure(
            with_=w, without=wo, disable=['static','ldap','ldaps'])

class liblas(CMakePackage):
    src     = 'http://download.osgeo.org/liblas/libLAS-1.8.0.tar.bz2'
    chksum  = '73a29a97dfb8373d51c5e36bdf12a825c44fa398'

    @stage
    def configure(self):
        # Remove the pedantic flag. Latest boost is not compliant.
        self.helper('sed', '-ibak', '-e', 's/-pedantic//g', 'CMakeLists.txt')

        self.env['LDFLAGS'] += ' -Wl,-rpath -Wl,%(INSTALL_DIR)s/lib' % self.env

        super(liblas, self).configure(other=[
            '-DBoost_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include','boost-'+boost.version),
            '-DBoost_LIBRARY_DIRS=' + P.join(self.env['INSTALL_DIR'],'lib'),
            '-DWITH_LASZIP=true',
            '-DLASZIP_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include'),
            '-DWITH_GDAL=true',
            '-DGDAL_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include'),
            '-DWITH_GEOTIFF=true',
            '-DGEOTIFF_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include')
            ])
        
    @stage
    def install(self):
        super(liblas, self).install()
        # Copy lasinfo to libexec, as we want it
        # to be hidden there in the released ASP distribution.
        progs = ['lasinfo']
        libexec = P.join( self.env['INSTALL_DIR'], 'libexec' )
        self.helper('mkdir', '-p', libexec)
        for prog in progs:
            cmd = ['cp', '-vf', P.join( self.env['INSTALL_DIR'], 'bin',
                                        prog ), libexec]
            self.helper(*cmd)

class laszip(CMakePackage):
    src     = 'http://download.osgeo.org/laszip/laszip-2.1.0.tar.gz'
    chksum  = 'bbda26b8a760970ff3da3cfac97603dd0ec4f05f'

class geoid(Package):

    src     = 'https://byss.arc.nasa.gov/asp_packages/geoids.tgz'
    chksum  = 'e6e3961d6a84e10b4c49039b9a84098d57bd2206'

    @stage
    def configure(self): pass

    def compile(self):
        self.helper(self.env['F77'], '-c','-fPIC','interp_2p5min.f')
        if self.arch.os == 'osx':
            flag = '-dynamiclib'
        else:
            flag = '-shared'
        self.helper(self.env['F77'], flag, '-o', 'libegm2008.so', 'interp_2p5min.o')
            
    def install(self):
        cmd = ['cp'] + glob(P.join(self.workdir, 'libegm2008.*')) \
              + [P.join(self.env['INSTALL_DIR'], 'lib')]
        self.helper(*cmd)
        geoidDir = P.join(self.env['INSTALL_DIR'], 'share/geoids')
        self.helper('mkdir', '-p', geoidDir)
        cmd = ['cp'] + glob(P.join(self.workdir, '*tif')) \
        + glob(P.join(self.workdir, '*jp2')) + [geoidDir] 
        self.helper(*cmd)

# Due to legal reasons ... we are not going to download a modified
# version of ISIS from some NASA Ames server. Instead, we will
# download ISIS and then download the repo for editing ISIS. We apply
# the patch locally and then build away.
class isis(Package):
    def __init__(self, env):
        super(isis, self).__init__(env)
        self.isis_localcopy = P.join(env['DOWNLOAD_DIR'], 'rsync', self.pkgname)
        self.isisautotools_localcopy = P.join(env['DOWNLOAD_DIR'], 'git', 'AutotoolsForISIS')
        # We download the source code from the OSX branch, should be same code
        # as on the Linux side.
        self.isis_src = "isisdist.astrogeology.usgs.gov::x86-64_darwin_OSX10.8/isis/"
        self.isisautotools_src = "https://github.com/NeoGeographyToolkit/AutotoolsForISIS.git"

        # Fetch the ISIS version. We will rebuild it each time
        # the version changes.
        cmd = ['rsync', self.isis_src +'version']
        self.helper(*cmd)
        f = open('version','r')
        self.chksum = f.readline().strip()
        if self.chksum == "":
            raise PackageError(self, 'Could not find the ISIS version')
        
    @stage
    def fetch(self, skip=False):
        if not P.exists(self.isis_localcopy) or \
                not P.exists(self.isisautotools_localcopy):
            if skip: raise PackageError(self, 'Fetch is skipped and no src available')
            os.makedirs(self.isis_localcopy)
        if skip: return

        self.copytree(self.isis_src, self.isis_localcopy + '/', ['-zv', '--exclude', 'doc/*', '--exclude', '*/doc/*', '--exclude', 'bin/*', '--exclude', '3rdParty/*', '--exclude', 'lib/*'])
        if not P.exists(self.isisautotools_localcopy):
            self.helper('git', 'clone', '--mirror', self.isisautotools_src, self.isisautotools_localcopy)
        else:
            self.helper('git', '--git-dir', self.isisautotools_localcopy, 'fetch', 'origin')

    @stage
    def unpack(self):
        output_dir = P.join(self.env['BUILD_DIR'], self.pkgname)
        self.remove_build(output_dir)
        self.workdir = output_dir
        if P.exists(P.join(self.workdir, self.pkgname)):
            self.helper('rm','-rf',self.pkgname);
        if not P.exists(P.join(output_dir, 'isis_original')):
            os.makedirs(P.join(output_dir, 'isis_original'))
        self.copytree(self.isis_localcopy + '/', P.join(output_dir, 'isis_original'),
                      ['--link-dest=%s' % self.isis_localcopy])
        autotools_dir = P.join(output_dir, 'AutotoolsForISIS-git')
        os.mkdir(autotools_dir )
        self.helper('git', 'clone', self.isisautotools_localcopy, autotools_dir)

        # Delete the patch that applies to applications we are not building
        os.remove(os.path.join(autotools_dir, 'patches/00005-fix_variable_length_array.patch'))

        # Now we actually run commands that patch ISIS with a build system
        self.helper(sys.executable,"AutotoolsForISIS-git/reformat_isis.py","--destination",
                    self.pkgname,"--isisroot","isis_original","--dont-build-apps")
        self.workdir = P.join(output_dir,self.pkgname)

        self._apply_patches()

    @stage
    def configure(self):
        self.helper('./autogen')

        pkgs = 'arbitrary_qt qwt boost protobuf tnt jama xercesc spice geos gsl \
                lapack superlu gmm tiff z jpeg suitesparse amd colamd cholmod curl xercesc'.split()

        w = [i + '=%(INSTALL_DIR)s' % self.env for i in pkgs]
        includedir = P.join(self.env['INSTALL_DIR'], 'include')

        with file(P.join(self.workdir, 'config.options'), 'w') as config:
            for pkg in pkgs:
                ldflags = []
                ldflags.append('-L%s' % P.join(self.env['INSTALL_DIR'], 'lib'))
                if self.arch.os == 'osx':
                    ldflags.append('-F%s' % P.join(self.env['INSTALL_DIR'], 'lib'))
                print('PKG_%s_LDFLAGS="%s"' % (pkg.upper(), ' '.join(ldflags)), file=config)

            qt_pkgs = 'QtCore QtGui QtNetwork QtSql QtSvg QtXml QtXmlPatterns'
            print('QT_ARBITRARY_MODULES="%s"' % qt_pkgs, file=config)

            qt_cppflags=['-I%s' % includedir]
            qt_libs=['-L%s' % P.join(self.env['INSTALL_DIR'], 'lib')]

            for module in qt_pkgs.split():
                qt_cppflags.append('-I%s/%s' % (includedir, module))
                qt_libs.append('-l%s' % module)

            print('PKG_ARBITRARY_QT_CPPFLAGS="%s"' % ' '.join(qt_cppflags), file=config)
            print('PKG_ARBITRARY_QT_LIBS="%s"' %  ' '.join(qt_libs), file=config)
            print('PKG_ARBITRARY_QT_MORE_LIBS="-lpng -lz"', file=config)

            print('PROTOC=%s' % (P.join(self.env['INSTALL_DIR'], 'bin', 'protoc')), file=config)
            print('MOC=%s' % (P.join(self.env['INSTALL_DIR'], 'bin', 'moc')), file=config)
            print('HAVE_PKG_APPLE_QWT=no', file=config)
            print('HAVE_PKG_KAKADU=no', file=config)
            print('HAVE_PKG_GSL_HASBLAS=no', file=config)

        # Force the linker to do a thorough job at finding dependencies.
        # If older linkers don't like the provided flags, try again
        # without them.
        ldflag_attempts = []
        ldflag_attempts.append( self.env['LDFLAGS'] )
        if self.arch.os == 'linux':
            ld_flags1 = ' -Wl,--copy-dt-needed-entries  -Wl,--no-as-needed'
            ld_flags2 = ' -Wl,-rpath=%(INSTALL_DIR)s/lib -L%(INSTALL_DIR)s/lib -lblas -lQtXml' % self.env
            ldflag_attempts.append( ldflag_attempts[0] + ld_flags2 )
            ldflag_attempts.append( ldflag_attempts[0] + ld_flags1)
            ldflag_attempts.append( ldflag_attempts[0] )
            ldflag_attempts[0] = ldflag_attempts[0] + ld_flags1 + ld_flags2

        for ld_flags in ldflag_attempts:
            self.env['LDFLAGS'] = ld_flags
            try:
                super(isis, self).configure(
                    with_ = w,
                    without = ['clapack', 'slapack'],
                    disable = ['pkg_paths_default', 'static', 'qt-qmake'] )
                break
            except:
                print ("Unexpected error in attempt: ", ld_flags, sys.exc_info()[0])

class stereopipeline(GITPackage):
    src     = 'https://github.com/NeoGeographyToolkit/StereoPipeline.git'
    def configure(self):
        self.helper('./autogen')

        use_env_flags = True
        prefix        = self.env['INSTALL_DIR']
        installdir    = prefix
        vw_build      = prefix
        arch          = self.arch
        config_file   = P.join(self.workdir, 'config.options')
        write_asp_config(use_env_flags, prefix, installdir, vw_build,
                         arch, geoid, config_file)

        super(stereopipeline, self).configure(
            other   = ['docdir=%s/doc' % prefix],
            without = ['clapack', 'slapack', 'tcmalloc'],
            disable = ['pkg_paths_default', 'static', 'qt-qmake'],
            enable  = ['debug=ignore', 'optimize=ignore']
            )

    @stage
    def compile(self, cwd=None):
            
        super(stereopipeline, self).compile(cwd)
        if 'ISISROOT' in os.environ and 'ISIS3DATA' in os.environ and self.arch.os == 'osx':
            # Do 'make check' if ISIS was set up. Do it only on the Mac,
            # as in other places we are lacking all ISIS kernels.
            cmd = ('make', 'check')
            self.helper(*cmd)

class visionworkbench(GITPackage):
    src     = 'https://github.com/visionworkbench/visionworkbench.git'

    def __init__(self,env):
        super(visionworkbench,self).__init__(env)

    @stage
    def configure(self):
        self.helper('./autogen')

        arch         = self.arch
        installdir   = self.env['INSTALL_DIR']
        prefix       = installdir
        config_file  = P.join(self.workdir, 'config.options')
        write_vw_config(prefix, installdir, arch, config_file)
        fix_install_paths(installdir, arch) # this is needed for Mac for libgeotiff
        super(visionworkbench, self).configure()

    @stage
    def compile(self, cwd=None):
        super(visionworkbench, self).compile(cwd)
        cmd = ('make', 'check')
        self.helper(*cmd)

class lapack(CMakePackage):
    src     = 'http://www.netlib.org/lapack/lapack-3.5.0.tgz'
    chksum  = '5870081889bf5d15fd977993daab29cf3c5ea970'

    def configure(self):
        LDFLAGS_ORIG = self.env['LDFLAGS']
        LDFLAGS_CURR = []
        for i in self.env['LDFLAGS'].split(' '):
            if not i.startswith('-L'):
                LDFLAGS_CURR.append(i);
        self.env['LDFLAGS'] = ' '.join(LDFLAGS_CURR)
        super(lapack, self).configure( other=['-DBUILD_SHARED_LIBS=ON','-DBUILD_STATIC_LIBS=OFF','-DCMAKE_Fortran_FLAGS=-fPIC'] )
        self.env['LDFLAGS'] = LDFLAGS_ORIG

class boost(Package):
    version = '1_55' # variable is used in class liblas, libnabo, etc.
    src     = 'http://downloads.sourceforge.net/boost/boost_' + version + '_0.tar.bz2'
    chksum  = 'cef9a0cc7084b1d639e06cd3bc34e4251524c840'
    patches = 'patches/boost'

    def __init__(self, env):
        super(boost, self).__init__(env)
        self.env['NO_BZIP2'] = '1'
#        self.env['NO_ZLIB']  = '1'

    @stage
    def configure(self):
        with file(P.join(self.workdir, 'user-config.jam'), 'w') as f:
            if self.arch.os == 'linux':
                toolkit = 'gcc'
            elif self.arch.os == 'osx':
                toolkit = 'darwin'

            # print('variant myrelease : release : <optimization>none <debug-symbols>none ;', file=f)
            # print('variant mydebug : debug : <optimization>none ;', file=f)
            args = [toolkit] + list(self.env.get(i, ' ') for i in ('CXX', 'CXXFLAGS', 'LDFLAGS'))
            print('using %s : : %s : <cxxflags>"%s" <linkflags>"%s -ldl" ;' % tuple(args), file=f)
            print('using zlib : 1.2.8 : <include>%s <search>%s ;' %
                  (P.join(self.env['INSTALL_DIR'],'include'),P.join(self.env['INSTALL_DIR'],'lib')), file=f)
            print('option.set keep-going : false ;', file=f)

    # TODO: WRONG. There can be other things besides -j4 in MAKEOPTS
    @stage
    def compile(self):
        self.env['BOOST_ROOT'] = self.workdir

        self.helper('./bootstrap.sh')
        os.unlink(P.join(self.workdir, 'project-config.jam'))

        cmd = ['./bjam']
        if 'MAKEOPTS' in self.env:
            cmd += (self.env['MAKEOPTS'],)

        self.args = [
            '-q', '--user-config=%s/user-config.jam' % self.workdir,
            '--prefix=%(INSTALL_DIR)s' % self.env, '--layout=versioned',
            'threading=multi', 'variant=release', 'link=shared', 'runtime-link=shared',
            '--without-mpi', '--without-python', '--without-wave', '--without-log', 'stage',
            '-d+2' # Show commands as they are executed
            ]

        cmd += self.args
        self.helper(*cmd)

    # TODO: Might need some darwin path-munging with install_name_tool?
    @stage
    def install(self):
        self.env['BOOST_ROOT'] = self.workdir
        cmd = ['./bjam'] + self.args + ['install']
        self.helper(*cmd)

class HeaderPackage(Package):
    def configure(self, *args, **kw):
        kw['other'] = kw.get('other', []) + ['--prefix=%(NOINSTALL_DIR)s' % self.env,]
        super(HeaderPackage, self).configure(*args, **kw)

    @stage
    def compile(self): pass

    @stage
    def install(self):
        self.helper('make', 'install-data')

class gsl(Package):
    src = 'ftp://ftp.gnu.org/gnu/gsl/gsl-1.15.tar.gz',
    chksum = 'd914f84b39a5274b0a589d9b83a66f44cd17ca8e',

    def configure(self):
        super(gsl, self).configure(disable=('static'))

class geos(Package):
    src = 'http://download.osgeo.org/geos/geos-3.3.9.tar.bz2'
    chksum = '1523f000b69523dfbaf008c7407b98217470e7a3'

    def __init__(self, env):
        super(geos, self).__init__(env)
        if self.arch.os == 'linux':
            # Bugfix for SuSE, skip using ccache
            self.env['CXX']='g++'
            self.env['CC']='gcc'

    def configure(self):
        super(geos, self).configure(disable=('python', 'ruby', 'static'))

class superlu(Package):
    src    = ['http://sources.gentoo.org/cgi-bin/viewvc.cgi/gentoo-x86/sci-libs/superlu/files/superlu-4.3-autotools.patch','http://crd-legacy.lbl.gov/~xiaoye/SuperLU/superlu_4.3.tar.gz']
    chksum = ['c9cc1c9a7aceef81530c73eab7f599d652c1fddd','d2863610d8c545d250ffd020b8e74dc667d7cbdd']

    def __init__(self,env):
        super(superlu,self).__init__(env)
        self.patches = [P.join(env['DOWNLOAD_DIR'], 'superlu-4.3-autotools.patch'),
                        P.join(self.pkgdir,'patches','superlu','finish_autotools.patch')]

    @stage
    def configure(self):
        self.helper('mkdir', 'm4')
        self.helper('autoreconf', '-fvi')
        blas = ''
        if self.arch.os == "osx":
            blas = '"-framework vecLib"'
        else:
            blas = glob(P.join(self.env['INSTALL_DIR'],'lib','libblas.so*'))[0]
        super(superlu,self).configure(with_=('blas=%s') % blas,
                                      disable=('static'))

class gmm(Package):
    src     = 'http://download.gna.org/getfem/stable/gmm-4.2.tar.gz'
    chksum  = '3555d5a5abdd525fe6b86db33428604d74f6747c'
    patches = 'patches/gmm'

    @stage
    def configure(self):
        self.helper('autoreconf', '-fvi')
        blas = ''
        if self.arch.os == "osx":
            blas = '"-framework vecLib"'
        else:
            blas = glob(P.join(self.env['INSTALL_DIR'],'lib','libblas.so*'))[0]
        super(gmm,self).configure(with_=('blas=%s') % blas)

class xercesc(Package):
    src    = 'http://mirror.symnds.com/software/Apache//xerces/c/3/sources/xerces-c-3.1.1.tar.gz'
    chksum = '177ec838c5119df57ec77eddec9a29f7e754c8b2'

    @stage
    def configure(self):
        super(xercesc,self).configure(with_=['curl=%s' % glob(P.join(self.env['INSTALL_DIR'],'lib','libcurl.*'))[0],
                                             'icu=no'],
                                      disable = ['static', 'msgloader-iconv', 'msgloader-icu', 'network'])

class qt(Package):
    src     = 'http://download.qt-project.org/official_releases/qt/4.8/4.8.6/qt-everywhere-opensource-src-4.8.6.tar.gz'
    chksum  = 'ddf9c20ca8309a116e0466c42984238009525da6' #SHA-1 Hash
    patches = 'patches/qt'
    patch_level = '-p0'

    def __init__(self, env):
        super(qt, self).__init__(env)

        # Qt can only be built on OSX with an Apple Compiler. If the
        # user overwrote the compiler choice, we must revert here. The
        # problem is -fconstant-cfstrings. Macports also gives up in
        # this situation and blacks lists all Macport built compilers.
        if self.arch.os == 'osx':
            self.env['CXX']='c++'
            self.env['CC']='cc'

    @stage
    def configure(self):
        # The default confs override our compiler choices.
        self.helper('sed','-ibak','-e','s# g++# %s#g' % self.env['CXX'], '-e', 's# gcc# %s#g' % self.env['CC'], 'mkspecs/common/g++-base.conf')
        cmd = './configure -opensource -fast -confirm-license -nomake demos -nomake examples -nomake docs -nomake translations -no-webkit -prefix %(INSTALL_DIR)s -no-script -no-scripttools -no-openssl -no-libjpeg -no-libmng -no-libpng -no-libtiff -no-cups -no-nis -no-opengl -no-openvg -no-phonon -no-phonon-backend -no-sql-psql -no-dbus' % self.env
        args = cmd.split()
        if self.arch.os == 'osx':
            args.append('-no-framework')
            args.extend(['-arch',self.env['OSX_ARCH']])
        self.helper(*args)

    @stage
    def install(self):
        # Call the install itself afterward
        super(qt, self).install()

class qwt(Package):
    src     = 'http://downloads.sourceforge.net/qwt/qwt-6.1.0.tar.bz2',
    chksum  = '48a967038f7aa9a9c87c64bcb2eb07c5df375565',
    patches = 'patches/qwt'

    def configure(self):
        installDir = self.env['INSTALL_DIR']

        # Wipe old installation, otherwise qwt refuses to install
        cmd = ['rm', '-vf'] + glob(P.join(installDir, 'lib/', 'libqwt.*'))
        self.helper(*cmd)

        cmd = [installDir + '/bin/qmake','-spec']
        if self.arch.os == 'osx':
            cmd.append(P.join(installDir,'mkspecs','macx-g++'))
        else:
            cmd.append(P.join(installDir,'mkspecs','linux-g++'))
        self.helper(*cmd)

    # Qwt pollutes the doc folder
    @stage
    def install(self):
        super(qwt, self).install()
        cmd = ['rm', '-vrf', P.join( self.env['INSTALL_DIR'], 'doc', 'html' ) ]
        self.helper(*cmd)
        cmd = ['rm', '-vrf', P.join( self.env['INSTALL_DIR'], 'doc', 'man' ) ]
        self.helper(*cmd)

class zlib(Package):
    src     = 'http://downloads.sourceforge.net/libpng/zlib-1.2.8.tar.gz'
    chksum  = 'a4d316c404ff54ca545ea71a27af7dbc29817088'

    @stage
    def configure(self):
        super(zlib,self).configure(other=('--shared',))

    @stage
    def install(self):
        super(zlib, self).install()
        self.helper(*['rm', P.join(self.env['INSTALL_DIR'], 'lib', 'libz.a')])

class jpeg(Package):
    src     = 'http://www.ijg.org/files/jpegsrc.v8d.tar.gz'
    chksum  = 'f080b2fffc7581f7d19b968092ba9ebc234556ff'
    patches = 'patches/jpeg8'

    def configure(self):
        super(jpeg, self).configure(enable=('shared',), disable=('static',))

class png(Package):
    src    = 'http://downloads.sourceforge.net/libpng/libpng-1.6.7.tar.gz'
    chksum = '22fcd1aaab3d8f4b98f43e5b301cc4fd7cc15722'

    def configure(self):
        super(png,self).configure(disable='static')

class cspice(Package):
    # This will break when they release a new version BECAUSE THEY USE UNVERSIONED TARBALLS.
    PLATFORM = dict(
        linux64 = dict(
            src    = 'ftp://naif.jpl.nasa.gov/pub/naif/toolkit/C/PC_Linux_GCC_64bit/packages/cspice.tar.Z',
            chksum = '335a16141e3d4f5d2e596838285fc9f918c2f328', # N0065
            ),
        linux32 = dict(
            src    = 'ftp://naif.jpl.nasa.gov/pub/naif/toolkit/C/PC_Linux_GCC_32bit/packages/cspice.tar.Z',
            chksum = 'a875f47ac9811bdc22359ff77e1511a0376bd1bd', # N0065
            ),
        osx32   = dict(
            src    = 'ftp://naif.jpl.nasa.gov/pub/naif/toolkit/C/MacIntel_OSX_AppleC_32bit/packages/cspice.tar.Z',
            chksum = '45efcac7fb260401fcd2124dfe9d226d9f74211d', # N0065
            ),
        osx64   = dict(
            src    = 'ftp://naif.jpl.nasa.gov/pub/naif/toolkit//C/MacIntel_OSX_AppleC_64bit/packages/cspice.tar.Z',
            chksum = '1500a926f01a0bb04744ebe8af0149c7ae098a8f', # N0065
            ),
        )

    def __init__(self, env):
        super(cspice, self).__init__(env)
        self.pkgname += '_' + self.arch.osbits
        self.src    = self.PLATFORM[self.arch.osbits]['src']
        self.chksum = self.PLATFORM[self.arch.osbits]['chksum']
        if self.arch.os == "osx":
            self.patches = 'patches/cspice_osx'
        else:
            self.patches = 'patches/cspice_linux'
    def configure(self): pass

    @stage
    def compile(self):
        cmd = ['csh']
        self.args = ['./makeall.csh']
        cmd += self.args
        self.helper(*cmd)

    @stage
    def install(self):
        d = P.join('%(INSTALL_DIR)s' % self.env, 'include', 'naif')
        self.helper('mkdir', '-p', d)
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, 'include', '*.h')) + [d]
        self.helper(*cmd)

        d = P.join('%(INSTALL_DIR)s' % self.env, 'lib')
        self.helper('mkdir', '-p', d)
        # Wipe the static libraries
        cmd = ['rm' ] + glob(P.join(self.workdir,'lib', '*.a'))
        self.helper(*cmd)
        # Copy everything else, including the dynamic libraries
        cmd = ['cp', '-vf'] + glob(P.join(self.workdir, 'lib', '*')) + [d]
        self.helper(*cmd)

class protobuf(Package):
    src = 'http://protobuf.googlecode.com/files/protobuf-2.4.1.tar.bz2'
    chksum = 'df5867e37a4b51fb69f53a8baf5b994938691d6d'

    @stage
    def configure(self):
        self.helper('./autogen.sh')
        super(protobuf, self).configure(disable=('static'))

class suitesparse(Package):
    src = 'http://www.cise.ufl.edu/research/sparse/SuiteSparse/SuiteSparse-4.2.1.tar.gz'
    chksum = '2fec3bf93314bd14cbb7470c0a2c294988096ed6'

    # Note: Currently this is archive only. They don't have the option
    # of using shared (probably for performance reasons). If we want
    # shared, we'll have make then a build system.

    @stage
    def configure(self):
        pass

    @stage
    def install(self):
        inc = P.join(self.env['INSTALL_DIR'],'include')
        lib = P.join(self.env['INSTALL_DIR'],'lib')
        self.helper('make','install',
                    'INSTALL_INCLUDE=' + inc,
                    'INSTALL_LIB=' + lib
                    )

class osg3(CMakePackage):
    src = 'http://trac.openscenegraph.org/downloads/developer_releases/OpenSceneGraph-3.2.0.zip'
    chksum = 'c20891862b5876983d180fc4a3d3cfb2b4a3375c'
    patches = 'patches/osg3'

    def __init__(self, env):
        super(osg3, self).__init__(env)

        # Cocoa bindings can't be built unless using an apple provided
        # compiler. Using a homebrew or macports built GCC or hand
        # built clang will be missing the required 'blocks'
        # extension. The error will look something like "NSTask.h:
        # error: expected unqualified-id before '^' token".
        if self.arch.os == 'osx':
            self.env['CXX'] = 'c++'
            self.env['CC'] = 'cc'

    def configure(self):
        other_flags = ['-DBUILD_OSG_APPLICATIONS=ON', '-DCMAKE_VERBOSE_MAKEFILE=ON', '-DOSG_USE_QT=OFF', '-DBUILD_DOCUMENTATION=OFF']
        if self.arch.os == 'osx':
            other_flags.extend(['-DOSG_DEFAULT_IMAGE_PLUGIN_FOR_OSX=imageio','-DOSG_WINDOWING_SYSTEM=Cocoa'])
        super(osg3, self).configure(
            with_='GDAL GLUT JPEG OpenEXR PNG ZLIB CURL'.split(),
            without='QuickTime CoreVideo QTKit COLLADA FBX FFmpeg FLTK FOX FreeType GIFLIB Inventor ITK Jasper LibVNCServer OpenAL OpenVRML OurDCMTK Performer Qt3 Qt4 SDL TIFF wxWidgets Xine XUL RSVG NVTT DirectInput GtkGL Poppler-glib GTA'.split(),
            other=other_flags)

class flann(CMakePackage):
    src = 'http://people.cs.ubc.ca/~mariusm/uploads/FLANN/flann-1.8.4-src.zip'
    chksum = 'e03d9d458757f70f6af1d330ff453e3621550a4f'

    @stage
    def configure(self):
        super(flann, self).configure(other=['-DBUILD_C_BINDINGS=OFF','-DBUILD_MATLAB_BINDINGS=OFF','-DBUILD_PYTHON_BINDINGS=OFF','-DBUILD_CUDA_LIB=OFF','-DUSE_MPI=OFF','-DUSE_OPENMP=OFF'])

    @stage
    def install(self):
        super(flann, self).install()
        cmd = ['rm' ] +glob(P.join(self.env['INSTALL_DIR'], 'lib', 'libflann*.a'))
        self.helper(*cmd)

class yaml(CMakePackage):
    src = 'http://yaml-cpp.googlecode.com/files/yaml-cpp-0.3.0.tar.gz'
    chksum = '28766efa95f1b0f697c4b4a1580a9972be7c9c41'

    def configure(self):
        super(yaml, self).configure(other=[
            '-DBoost_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include','boost-'+boost.version),
            '-DBoost_LIBRARY_DIRS=' + P.join(self.env['INSTALL_DIR'],'lib'),
            '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
            '-DBUILD_SHARED_LIBS=ON'
            ])

class eigen(CMakePackage):
    src = 'http://bitbucket.org/eigen/eigen/get/3.1.3.tar.bz2'
    chksum = '07e248deaaa5d2a8822a0581a606151127fce450'

    def configure(self):
        super(eigen, self).configure(other=[
            '-DBoost_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include','boost-'+boost.version),
            '-DBoost_LIBRARY_DIRS=' + P.join(self.env['INSTALL_DIR'],'lib'),
            '-DCMAKE_BUILD_TYPE=RelWithDebInfo'
            ])

class glog(Package):
    src     = 'https://google-glog.googlecode.com/files/glog-0.3.3.tar.gz'
    chksum  = 'ed40c26ecffc5ad47c618684415799ebaaa30d65'
    def configure(self):
        if self.arch.os == 'osx':
            other_flags = ['CFLAGS=-m64', 'CXXFLAGS=-m64',]
        else:
            other_flags = []
            
        super(glog, self).configure(
            enable=['shared',],
            disable = ['static'],
            other = other_flags
            )
        
class ceres(CMakePackage):
    src = 'https://ceres-solver.googlecode.com/files/ceres-solver-1.8.0.tar.gz'
    chksum = '8a67268d995b8351bd5ee5acf1eebff910028e7e'

    def configure(self):
        # Remove warnings as errors. They don't pass newest compilers.
        self.helper('sed', '-ibak', '-e', 's/-Werror//g', 'CMakeLists.txt')
        super(ceres, self).configure(other=[
            '-DEIGEN_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include/eigen3'),
            '-DBoost_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include','boost-'+boost.version),
            '-DBoost_LIBRARY_DIRS=' + P.join(self.env['INSTALL_DIR'],'lib'),
            '-DCMAKE_VERBOSE_MAKEFILE=ON', '-DSHARED_LIBS=ON', '-DMINIGLOG=OFF',
            '-DSUITESPARSE=ON', '-DLAPACK=ON',
            '-DLIB_SUFFIX=', '-DBUILD_EXAMPLES=OFF', '-DBUILD_SHARED_LIBS=ON', '-DBUILD_TESTING=OFF'
            ])

class libnabo(GITPackage, CMakePackage):
    src = 'https://github.com/ethz-asl/libnabo.git'
    patches = 'patches/libnabo'
    commit = '4cda228'

    def configure(self):
        # Remove python bindings, tests, and examples
        self.helper('sed', '-ibak', '-e', 's/add_subdirectory(python)//g', '-e', 's/add_subdirectory(tests)//g', '-e', 's/add_subdirectory(examples)//g', 'CMakeLists.txt')
        super(libnabo, self).configure(other=[
            '-DCMAKE_CXX_FLAGS=-g -O3',
            '-DEIGEN_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include/eigen3'),
            '-DBoost_INCLUDE_DIR=' + P.join(self.env['INSTALL_DIR'],'include','boost-'+boost.version),
            '-DBoost_LIBRARY_DIRS=' + P.join(self.env['INSTALL_DIR'],'lib'),
            '-DBoost_DIR=' + P.join(self.env['INSTALL_DIR'],'lib'),
            '-DCMAKE_VERBOSE_MAKEFILE=ON',
            '-DSHARED_LIBS=ON'
            ])

class libpointmatcher(GITPackage, CMakePackage):
    # We are fetching a hacked version of this from GitHub. Need to upgdate
    # at some point to the master version.
    src   = 'https://github.com/oleg-alexandrov/libpointmatcher'
    chksum = '0e8e2a8'
    patches = 'patches/libpointmatcher'

    def configure(self):
        installDir = self.env['INSTALL_DIR']
        boost_include = P.join(installDir,'include','boost-'+boost.version)
        self.env['CXXFLAGS'] += ' -I="' + boost_include + '"' # bugfix for lunokhod2

        options = [
            '-DCMAKE_CXX_FLAGS=-g -O3 -I' + boost_include,
            '-DBoost_INCLUDE_DIR=' + boost_include,
            '-DBoost_LIBRARY_DIRS=' + P.join(installDir,'lib'),
            '-DEIGEN_INCLUDE_DIR=' + P.join(installDir,'include/eigen3'),
            '-DCMAKE_VERBOSE_MAKEFILE=ON',
            '-DCMAKE_PREFIX_PATH=' + installDir,
            '-DSHARED_LIBS=ON'
            ]
        # Bugfix for lunokhod2. This has problems on Mac OSX 10.6.
        if self.arch.os == 'linux':
            options += [
                '-DBoost_DIR=' + os.getcwd() + '/settings/boost',
                '-DMY_BOOST_VERSION=' + boost.version,
                '-DMY_BOOST_DIR=' + installDir
                ]
        super(libpointmatcher, self).configure(other=options)

# We would like to fetch this very source code. This is used
# in the nightly builds and regressions.
class binarybuilder(GITPackage):
    src     = 'https://github.com/NeoGeographyToolkit/BinaryBuilder.git'
    def configure(self): pass

    @stage
    def compile(self, cwd=None): pass
            
    @stage
    def install(self): pass
