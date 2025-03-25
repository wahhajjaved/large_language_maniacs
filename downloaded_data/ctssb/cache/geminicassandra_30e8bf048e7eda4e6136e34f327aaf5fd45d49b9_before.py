"""Perform in-place updates of geminicassandra and databases when installed into virtualenv.
"""
import os
import shutil
import subprocess
import sys

import geminicassandra.config

def release(parser, args):
    """Update geminicassandra to the latest release, along with associated data files.
    """
    url = "https://github.com/bgossele/geminicassandra/master/requirements.txt"
    repo = "https://github.com/bgossele/geminicassandra"
    cbl_repo = "https://github.com/chapmanb/cloudbiolinux.git"
    # update locally isolated python
    base = os.path.dirname(os.path.realpath(sys.executable))
    gemini_cmd = os.path.join(base, "geminicassandra")
    pip_bin = os.path.join(base, "pip")
    fab_cmd = os.path.join(base, "fab")
    activate_bin = os.path.join(base, "activate")
    conda_bin = os.path.join(base, "conda")
    if not args.dataonly:
        if os.path.exists(conda_bin):
            pkgs = ["bx-python", "conda", "cython", "ipython", "jinja2", "nose", "numpy",
                    "pip", "pycrypto", "pyparsing", "pysam", "pyyaml",
                    "pyzmq", "pandas", "scipy", "cassandra-driver", "blist"]
            channels = ["-c", "https://conda.binstar.org/bcbio"]
            subprocess.check_call([conda_bin, "install", "--yes", "numpy"])
            subprocess.check_call([conda_bin, "install", "--yes"] + channels + pkgs)
        elif os.path.exists(activate_bin):
            pass
        else:
            raise NotImplementedError("Can only upgrade geminicassandra installed in anaconda or virtualenv")
        # allow downloads excluded in recent pip (1.5 or greater) versions
        try:
            p = subprocess.Popen([pip_bin, "--version"], stdout=subprocess.PIPE)
            pip_version = p.communicate()[0].split()[1]
        except:
            pip_version = ""
        pip_compat = []
        if pip_version >= "1.5":
            for req in ["python-graph-core", "python-graph-dot"]:
                pip_compat += ["--allow-external", req, "--allow-unverified", req]
        # update libraries
        subprocess.check_call([pip_bin, "install"] + pip_compat + ["-r", url])
        if args.devel:
            print("Installing latest GEMINI development version")
            subprocess.check_call([pip_bin, "install", "--upgrade", "--no-deps",
                                   "git+%s" % repo])
        print "Gemini upgraded to latest version"
    if args.tooldir:
        print "Upgrading associated tools..."
        cbl = get_cloudbiolinux(cbl_repo)
        fabricrc = write_fabricrc(cbl["fabricrc"], args.tooldir, args.sudo)
        install_tools(fab_cmd, cbl["tool_fabfile"], fabricrc)
    # update datafiles
    config = geminicassandra.config.read_gemini_config(args=args)
    extra_args = ["--extra=%s" % x for x in args.extra]
    subprocess.check_call([sys.executable, _get_install_script(), config["annotation_dir"]] + extra_args)
    print "Gemini data files updated"
    # update tests
    if not args.dataonly:
        test_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(pip_bin))),
                                "geminicassandra")
        if not os.path.exists(test_dir) or os.path.isdir(test_dir):
            _update_testbase(test_dir, repo, gemini_cmd)
            print "Run test suite with: cd %s && bash master-test.sh" % test_dir

def _get_install_script():
    try:
        import pkg_resources
        return pkg_resources.resource_filename(__name__, "install-data.py")
    except ImportError:
        return os.path.join(os.path.dirname(__file__), "install-data.py")

def _update_testbase(repo_dir, repo, gemini_cmd):
    cur_dir = os.getcwd()
    needs_git = True
    if os.path.exists(repo_dir):
        os.chdir(repo_dir)
        try:
            subprocess.check_call(["git", "pull", "origin", "master", "--tags"])
            needs_git = False
        except:
            os.chdir(cur_dir)
            shutil.rmtree(repo_dir)
    if needs_git:
        os.chdir(os.path.split(repo_dir)[0])
        subprocess.check_call(["git", "clone", repo])
    os.chdir(repo_dir)
    _update_testdir_revision(gemini_cmd)
    os.chdir(cur_dir)

def _update_testdir_revision(gemini_cmd):
    """Update test directory to be in sync with a tagged installed version or development.
    """
    try:
        p = subprocess.Popen([gemini_cmd, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        gversion = p.communicate()[0].split()[1]
    except:
        gversion = ""
    tag = ""
    if gversion:
        try:
            p = subprocess.Popen("git tag -l | grep %s" % gversion, stdout=subprocess.PIPE, shell=True)
            tag = p.communicate()[0].strip()
        except:
            tag = ""
    if tag:
        subprocess.check_call(["git", "checkout", "tags/%s" % tag])
        pass
    else:
        subprocess.check_call(["git", "reset", "--hard", "HEAD"])

# ## Tools

def get_cloudbiolinux(repo):
    base_dir = os.path.join(os.getcwd(), "cloudbiolinux")
    if not os.path.exists(base_dir):
        subprocess.check_call(["git", "clone", repo])
    return {"fabricrc": os.path.join(base_dir, "config", "fabricrc.txt"),
            "tool_fabfile": os.path.join(base_dir, "fabfile.py")}

def write_fabricrc(base_file, tooldir, use_sudo):
    out_file = os.path.join(os.getcwd(), os.path.basename(base_file))
    with open(base_file) as in_handle:
        with open(out_file, "w") as out_handle:
            for line in in_handle:
                if line.startswith("system_install"):
                    line = "system_install = %s\n" % tooldir
                elif line.startswith("local_install"):
                    line = "local_install = %s/install\n" % tooldir
                elif line.startswith("use_sudo"):
                    line = "use_sudo = %s\n" % use_sudo
                elif line.startswith("edition"):
                    line = "edition = minimal\n"
                out_handle.write(line)
    return out_file

def install_tools(fab_cmd, fabfile, fabricrc):
    """Install 3rd party tools used by Gemini using a custom CloudBioLinux flavor.
    """
    tools = ["tabix", "grabix", "samtools", "bedtools"]
    flavor_dir = os.path.join(os.getcwd(), "geminicassandra-flavor")
    if not os.path.exists(flavor_dir):
        os.makedirs(flavor_dir)
    with open(os.path.join(flavor_dir, "main.yaml"), "w") as out_handle:
        out_handle.write("packages:\n")
        out_handle.write("  - bio_nextgen\n")
        out_handle.write("libraries:\n")
    with open(os.path.join(flavor_dir, "custom.yaml"), "w") as out_handle:
        out_handle.write("bio_nextgen:\n")
        for tool in tools:
            out_handle.write("  - %s\n" % tool)
    cmd = [fab_cmd, "-f", fabfile, "-H", "localhost", "-c", fabricrc,
           "install_biolinux:target=custom,flavor=%s" % flavor_dir]
    subprocess.check_call(cmd)
