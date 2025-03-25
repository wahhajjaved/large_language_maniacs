#!/usr/bin/python
#
# Copyright (c) 2015 Michael Scherer <mscherer@redhat.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# This script trigger a middleman rebuild if upstream git or any submodule did change


import yaml
import sys
import os
import subprocess
import datetime
import atexit


#TODO use real options
debug = False
def debug_print(message):
    if debug:
        print message

def refresh_checkout(checkout_dir):
    os.chdir(checkout_dir)
    subprocess.call(['git', 'fetch', '-q'])

def get_last_commit(checkout_dir):
    os.chdir(checkout_dir)
    r = subprocess.check_output(['git','ls-remote','-q', '.', 'refs/remotes/origin/HEAD'])
    return r.split()[0]


def get_last_commit_submodule(checkout_dir, submodule):
    os.chdir("{}/{}/".format(checkout_dir, submodule))
    r = subprocess.check_output(['git','ls-remote','-q', '.', 'refs/remotes/origin/HEAD'])
    return r.split()[0]
     
def get_submodules_checkout(checkout_dir):
    os.chdir(checkout_dir)
    result = []
    submodule_status = subprocess.check_output(['git','submodule','status'])
    for s in submodule_status.split('\n'):
        # there is a empty line at the end...
        if s:
            result.append(s.split()[1])
    return result
    

def load_config(config_file):

    if not os.path.exists(config_file):
        print "Error %s, do not exist" % config_file
        sys.exit(1)
    if not os.path.isfile(config_file):
        print "Error %s is not a file" % config_file
        sys.exit(1)
         
    with open(config_file) as f:
        config = yaml.safe_load(f)

    return config

def has_submodules(checkout_dir):
    os.chdir(checkout_dir)
    r = subprocess.check_output(['git','submodule','status'])
    return len(r) > 0

# TODO complete that
def notify_error(error):
    pass


if len(sys.argv) != 2:
    print "This script take only 1 single argument, the config file"
    sys.exit(1)

config = load_config(sys.argv[1])

if not 'name' in config:
    print "Incorrect config file: {}".format(sys.argv[1])
    sys.exit(1)


name = config['name']


#TODO place it on a tmpfs, so it get wiped on reboot
lock_file = os.path.expanduser('~/lock_%s' % name)
if os.path.exists(lock_file):
    #TODO verify if the PID in the file still exist
    print "Builder already running, exiting"
    sys.exit(2)

# TODO try/except, show a better error message
fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
os.write(fd, str(os.getpid()))
os.close(fd)
atexit.register(os.unlink, lock_file)




status_file = os.path.expanduser('~/status_%s.yml' % name) 
status = {}
if os.path.exists(status_file):
    with open(status_file) as f:
        status = yaml.safe_load(f)


checkout_dir = os.path.expanduser("~/%s" % name)
if not os.path.isdir(checkout_dir):
    os.unlink(lock_file)
    print "Checkout not existing, exiting"
    sys.exit(2)

    

refresh_checkout(checkout_dir)

start_build = False

last_build = datetime.datetime.fromtimestamp(int(status.get("last_build", "0")))
if 'regular_rebuild_interval' in config and datetime.datetime.now() - last_build > datetime.timedelta(hours=config['regular_rebuild_interval']):
    start_build = True 

current_commit = get_last_commit(checkout_dir)
if current_commit != status.get('last_build_commit', ''):
    start_build = True

submodule_commits = status.get('submodule_commits', {})
current_submodule_commits = {}
for submodule in get_submodules_checkout(checkout_dir):
    debug_print('Looking for %s' % submodule)
    current_submodule_commits[submodule] = get_last_commit_submodule(checkout_dir, submodule) 
    
    if current_submodule_commits[submodule] != submodule_commits.get(submodule, ''):
        start_build = True

if not start_build:
    debug_print("Nothing to build")
    sys.exit(0)

os.chdir(checkout_dir)
if config.get('force_checkout', False):
    subprocess.call(['git','checkout', '-f'])
else:
    subprocess.call(['git', 'pull', '--rebase'])

if has_submodules(checkout_dir):
    subprocess.call(['git', 'submodule', 'init'])
    subprocess.call(['git', 'submodule', 'sync'])
    
if config.get('update_submodule_head', False):
    subprocess.call(['git', 'submodule', 'foreach', '"git pull -qf origin master"'])

os.environ['PATH'] = "/usr/local/bin:/srv/builder/bin:" + os.environ['PATH'] 
try:
    result = subprocess.check_output(['bundle','install'])
except subprocess.CalledProcessError, C:
    notify_error(C.output)

try:
    result = subprocess.check_output(['bundle','exec', 'middleman', 'build', '--verbose'])
except subprocess.CalledProcessError, C:
    notify_error(C.output)



if config['remote']:
    subprocess.call(['rsync', '-e', 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i ~/.ssh/{}_id.rsa'.format(name), '--delete-after', '-rqavz', '%s/build/' % checkout_dir, config['remote']])
else:
    subprocess.call(['bundle','exec', 'middleman', 'deploy'])

status = {}
status['last_build_commit'] = current_commit
status['last_build'] = datetime.datetime.now().strftime("%s")
status['submodule_commits'] = current_submodule_commits

with open(status_file, 'w+') as f:
    f.write(yaml.dump(status, default_flow_style=False))

 
