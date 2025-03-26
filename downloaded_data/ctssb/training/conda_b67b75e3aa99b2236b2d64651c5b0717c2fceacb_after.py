"""
Tools for converting PyPI packages to conda recipes.
"""

from __future__ import print_function, division, absolute_import

import sys
from os import makedirs, listdir, getcwd, chdir
from os.path import join, isdir, exists, isfile
from tempfile import mkdtemp
from collections import defaultdict

if sys.version_info < (3,):
    from xmlrpclib import ServerProxy
else:
    from xmlrpc.client import ServerProxy

from conda.utils import human_bytes, hashsum_file
from conda.install import rm_rf
from conda.builder.utils import download, tar_xf, unzip
from conda.builder.source import SRC_CACHE

PYPI_META = """\
package:
  name: {packagename}
  version: {version}

source:
  fn: {filename}
  url: {pypiurl}
  {usemd5}md5: {md5}
#  patches:
   # List any patch files here
   # - fix.patch

{build_comment}build:
  {build_comment}entry_points:
    # Put any entry points (scripts to be generated automatically) here. The
    # syntax is module:function.  For example
    #
    # - {packagename} = {packagename}:main
    #
    # Would create an entry point called {packagename} that calls {packagename}.main()
{entry_points}

  # If this is a new build for the same version, increment the build
  # number. If you do not include this key, it defaults to 0.
  # number: 1

requirements:
  build:
    - python{build_depends}

  run:
    - python{run_depends}

test:
  # Python imports
  imports:
    - {orig_packagename}

  {build_comment}commands:
    # You can put test commands to be run here.  Use this to test that the
    # entry points work.
{test_commands}

  # You can also put a file called run_test.py in the recipe that will be run
  # at test time.

  # requires:
    # Put any test requirements here.  For example
    # - nose

about:
  home: {homeurl}
  license: {license}

# See
# http://docs.continuum.io/conda/build.html for
# more information about meta.yaml
"""

PYPI_BUILD_SH = """\
#!/bin/bash

$PYTHON setup.py install

# Add more build steps here, if they are necessary.

# See
# http://docs.continuum.io/conda/build.html
# for a list of environment variables that are set during the build process.
"""

PYPI_BLD_BAT = """\
"%PYTHON%" setup.py install
if errorlevel 1 exit 1

:: Add more build steps here, if they are necessary.

:: See
:: http://docs.continuum.io/conda/build.html
:: for a list of environment variables that are set during the build process.
"""

def main(args, parser):
    client = ServerProxy(args.pypi_url)
    package_dicts = {}
    [output_dir] = args.output_dir

    if len(args.packages) > 1 and args.download:
        # Because if a package's setup.py imports setuptools, it will make all
        # future packages look like they depend on distribute. Also, who knows
        # what kind of monkeypatching the setup.pys out there could be doing.
        print("WARNING: building more than one recipe at once without "
            "--no-download is not recommended")
    for package in args.packages:
        if exists(join(output_dir, package.lower())):
            raise RuntimeError("The directory %s already exists" % package.lower())
        d = package_dicts.setdefault(package, {'packagename':
            package.lower(), 'orig_packagename': package, 'run_depends':'',
            'build_depends':'', 'entry_points':'', 'build_comment':'# ',
            'test_commands':'', 'usemd5':''})
        if args.version:
            [version] = args.version
            versions = client.package_releases(package, True)
            if version not in versions:
                sys.exit("Error: Version %s of %s is not avalaiable on PyPI."
                    % (version, package))
            d['version'] = version
        else:
            versions = client.package_releases(package)
            if not versions:
                sys.exit("Error: Could not find any versions of package %s" % package)
            if len(versions) > 1:
                print("Warning, the following versions were found for %s" % package)
                for ver in versions:
                    print(ver)
                print("Using %s" % versions[0])
                print("Use --version to specify a different version.")
            d['version'] = versions[-1]

        data = client.release_data(package, d['version'])
        urls = client.release_urls(package, d['version'])
        if not args.all_urls:
            # Try to find source urls
            urls = [url for url in urls if url['python_version'] == 'source']
        if not urls:
            if 'download_url' in data:
                urls = [defaultdict(str, {'url': data['download_url']})]
                urls[0]['filename'] = urls[0]['url'].split('/')[-1]
                d['usemd5'] = '#'
            else:
                sys.exit("Error: No source urls found for %s" % package)
        if len(urls) > 1:
            print("More than one source version is available for %s:" % package)
            for i, url in enumerate(urls):
                print("%d: %s (%s) %s" % (i, url['url'],
                    human_bytes(url['size']), url['comment_text']))
            n = int(raw_input("Which version should I use? "))
        else:
            n = 0

        print("Using url %s (%s) for %s." % (urls[n]['url'], urls[n]['size'], package))

        d['pypiurl'] = urls[n]['url']
        d['md5'] = urls[n]['md5_digest']
        d['filename'] = urls[n]['filename']


        d['homeurl'] = data['home_page']
        license_classifier = "License :: OSI Approved ::"
        licenses = [classifier.lstrip(license_classifier) for classifier in
            data['classifiers'] if classifier.startswith(license_classifier)]
        if not licenses:
            if data['license']:
                # Some projects put the whole license text in this field
                print("This is the license for %s" % package)
                print()
                print(data['license'])
                print()
                license = raw_input("What license string should I use? ")
            else:
                license = raw_input("No license could be found for %s on PyPI. What license should I use? " % package)
        else:
            license = ' or '.join(licenses)
        d['license'] = license

        # Unfortunately, two important pieces of metadata are only stored in
        # the package itself: the dependencies, and the entry points (if the
        # package uses distribute).  Our strategy is to download the package
        # and "fake" distribute/setuptools's setup() function to get this
        # information from setup.py. If this sounds evil, keep in mind that
        # distribute itself already works by monkeypatching distutils.
        if args.download:
            import yaml
            print("Downloading %s (use --no-download to skip this step)" % package)
            tempdir = mkdtemp('conda_skeleton')
            indent = '\n    - '

            try:
                # Download it to the build source cache. That way, you have
                # it.
                download_path = join(SRC_CACHE, d['filename'])
                if not isfile(download_path) or hashsum_file(download_path,
                    'md5') != d['md5']:
                    download(d['pypiurl'], join(SRC_CACHE, d['filename']),
                        md5=d['md5'])
                else:
                    print("Using cached download")
                print("Unpacking %s..." % package)
                unpack(join(SRC_CACHE, d['filename']), tempdir)
                print("done")
                print("working in %s" % tempdir)
                src_dir = get_dir(tempdir)
                patch_distutils(tempdir)
                run_setuppy(src_dir)
                with open(join(tempdir, 'pkginfo.yaml')) as fn:
                    pkginfo = yaml.load(fn)

                uses_distribute = 'setuptools' in sys.modules

                if pkginfo['install_requires'] or uses_distribute:
                    deps = [remove_version_information(dep) for dep in pkginfo['install_requires']]
                    d['build_depends'] = indent.join([''] +
                        ['distribute']*uses_distribute + deps)
                    d['run_depends'] = indent.join([''] + deps)
                if pkginfo['entry_points']:
                    entry_list = pkginfo['entry_points']['console_scripts']
                    d['entry_points'] = indent.join([''] + entry_list)
                    d['build_comment'] = ''
                    d['test_commands'] = indent.join([''] + make_entry_tests(entry_list))
            finally:
                rm_rf(tempdir)


    for package in package_dicts:
        d = package_dicts[package]
        makedirs(join(output_dir, package.lower()))
        print("Writing recipe for %s" % package.lower())
        with open(join(output_dir, package.lower(), 'meta.yaml'),
            'w') as f:
            f.write(PYPI_META.format(**d))
        with open(join(output_dir, package.lower(), 'build.sh'), 'w') as f:
            f.write(PYPI_BUILD_SH.format(**d))
        with open(join(output_dir, package.lower(), 'bld.bat'), 'w') as f:
            f.write(PYPI_BLD_BAT.format(**d))

    print("Done")

def unpack(src_path, tempdir):
    if src_path.endswith(('.tar.gz', '.tar.bz2', '.tgz', '.tar.xz', '.tar')):
        tar_xf(src_path, tempdir)
    elif src_path.endswith('.zip'):
        unzip(src_path, tempdir)
    else:
        raise Exception("not a valid source")

def get_dir(tempdir):
    lst = [fn for fn in listdir(tempdir) if not fn.startswith('.') and
        isdir(join(tempdir, fn))]
    if len(lst) == 1:
        dir_path = join(tempdir, lst[0])
        if isdir(dir_path):
            return dir_path
    raise Exception("could not find unpacked source dir")

def patch_distutils(tempdir):
    # Note, distribute doesn't actually patch the setup function.
    import distutils.core
    import yaml

    def setup(*args, **kwargs):
        data = {}
        data['install_requires'] = kwargs.get('install_requires', [])
        data['entry_points'] = kwargs.get('entry_points', [])
        with open(join(tempdir, "pkginfo.yaml"), 'w') as fn:
            fn.write(yaml.dump(data))

    distutils.core.setup = setup

def run_setuppy(src_dir):
    import sys
    sys.argv = ['setup.py', 'install']
    sys.path.insert(0, src_dir)
    d = {'__file__': 'setup.py', '__name__': '__main__'}
    cwd = getcwd()
    chdir(src_dir)
    execfile(join(src_dir, 'setup.py'), d)
    chdir(cwd)

def remove_version_information(pkgstr):
    # TODO: Actually incorporate the version information into the meta.yaml
    # file.
    return pkgstr.partition(' ')[0].partition('<')[0].partition('!')[0].partition('>')[0].partition('=')[0]

def make_entry_tests(entry_list):
    tests = []
    for entry_point in entry_list:
        entry = entry_point.partition('=')[0].strip()
        tests.append(entry + " --help")
    return tests
