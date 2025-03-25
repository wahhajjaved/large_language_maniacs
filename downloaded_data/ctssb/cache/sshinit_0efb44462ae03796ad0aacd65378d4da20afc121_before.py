#!/usr/bin/python3

# This software is covered under the GNU GPLv3 
# https://www.gnu.org/licenses/gpl.txt
# Contact the author at mudbungie@gmail.com
# Copyright 2016 mudbungie

# Program to initialize an SSH configuration with a host. Makes a new SSH key, 
# copies that to the host, appends the use of that key to the local 
# ~/.ssh/config. If the -r option is invoked, it will also su into the host's
# root user, and copy the ssh key there.

# Usage: 
#   ssh-init [-r] user@host

from sys import argv
import subprocess
import re
from os import environ, chmod, makedirs

class InputError(Exception):
    pass

# Goes through the list of arguments passed, and returns the target system's
# user, host, whether or not we're providing root access, and an intermediate
# hop, if any.
def handle_args(argv):
    # Default settings:
    settings = {}
    argv = argv[1:] # Discard the name of the program.
    for index, arg in enumerate(argv):
        print(index, arg)
        if arg == '-r':
            settings['root'] = True
        elif arg == '-h':
            try:
                settings['hostname'] = argv.pop(index + 1)
            except IndexError:
                raise InputError('-p takes a positional argument.')
        elif arg.startswith('-'):
            raise InputError('Unkown option ' + arg)
        # First positional is host.
        elif not 'host' in settings:
            # Check for the presence of a user.
            target = arg.split('@')
            if len(target) == 1:
                target = target[0]
            elif len(target) == 2:
                settings['user'] = target[0]
                target = target[1]
            else:
                raise InputError('Multiple @ symbols in connection string.')
            target = target.split(':')
            settings['host'] = target[0]
            if len(target) == 2:
                settings['port'] = target[1]
            elif len(target) > 2:
                raise InputError('Multiple : symbols in connection string.')
        # Second positional is bastion.
        elif not 'bastion' in settings:
            settings['bastion'] = arg
        else:
            raise InputError('Too many arguments')
    # Set defaults.
    if not 'hostname' in settings:
        settings['hostname'] = settings['host']
    if not 'port' in settings:
        settings['port'] = 22
    return settings

# Makes an SSH key, and puts it into $HOME/.ssh/auto/[target]
def createKey(settings):
    # Construct the strings that we'll use.
    keydir = environ['HOME'] + '/.ssh/auto/'
    target = settings['hostname']
    if 'user' in settings:
        target = settings['user'] + '@' + target
    if 'port' in settings:
        target = target + ':' + settings['port']

    # Make sure that we can insert keys...
    makedirs(keydir, exist_ok=True)
    chmod(keydir, 0o700)

    # Actually make it.
    keypath = keydir + target
    subprocess.call(['ssh-keygen' , '-t' , 'ed25519' , '-f' , keypath , '-C',
        'auto' , '-N' , ''])
    print('Keypair created in', keypath)
    return keypath

# Checks the ~/.ssh/config file for existing configuration. Returns line range
# or none.
def findHostLine(config, host):
    return len(config)

def confregex(key, value=False):
    if not value:
        return re.compile(r'^\s*' + key + '\s.*$')
    else:
        return re.compile(r'^s*' + key + '\s*' + value + '\s*$')

# Make the config file have a valid entry for this host.
def updateConfig(settings):
    # Just get the config file.
    conffilename = environ['HOME'] + '/.ssh/config'
    try:
        with open(conffilename, 'r') as conffile:
            config = conffile.readlines()
    except FileNotFoundError:
        config = []

    # Go through the config, and comment out lines starting with the one
    # that names this host, and going until the next line that names a host. 
    hostline = confregex('Host', value=settings['hostname'])
    anyhostline = confregex('Host')
    conflines = [confregex('user'), confregex('ProxyCommand'), 
        confregex('IdentityFile'), confregex('hostname'), confregex('Port')]
    start = False
    terminus = len(config)
    for index, line in enumerate(config):
        if start:
            if anyhostline.match(line):
                start = False
                terminus = index
        elif hostline.match(line):
            print('Configuration matched at line', index)
            start = True
            config[index] = '#' + config[index]
        if start:
            print(start)
            for confline in conflines:
                if confline.match(line):
                    print('Commenting line', index)
                    config[index] = '#' + config[index]
    
    # Add the relevant lines for the config.
    config.insert(terminus, '\n')
    config.insert(terminus, '    hostname ' + settings['host'] + '\n')
    config.insert(terminus, '    IdentityFile ' + settings['keypath'] + '\n')
    config.insert(terminus, '    Port ' + settings['port'] + '\n')
    if 'user' in settings:
        config.insert(terminus, '    user ' + settings['user'] + '\n')
    if 'bastion' in settings:
        config.insert(terminus, '    ProxyCommand ssh ' +\
            settings['bastion'] + ' -W ' + settings['host'] + ':%p\n')
    # Hostline is last, because we're inserting at the top of the section.
    config.insert(terminus, 'Host ' + settings['hostname'] + '\n')

    # Replace the current config with the modified config.
    with open(conffilename, 'w') as conffile:
        conffile.writelines(config)

def insertKey(settings):
    target = settings['hostname']
    if 'user' in settings:
        target = settings['user'] + '@' + target

    remoteCommand = 'mkdir .ssh 2> /dev/null; cat >> .ssh/authorized_keys'
    with open(settings['keypath'] + '.pub') as pubkey:
        #FIXME Add actual bastion parameters.
        a = subprocess.call(['ssh', target, '-p', settings['port'], remoteCommand],
            stdin=pubkey)
        if a == 0:
            print('Key installed.')
        else:
            print('Key installation failed.')

if __name__ == '__main__':
    try:
        settings = handle_args(argv)
        settings['keypath'] = createKey(settings)
        updateConfig(settings)
        insertKey(settings)
    except InputError:
        #print("usage: ssh-init [-r] [-p pseudonym] TARGET [HOP]")
        raise
        
