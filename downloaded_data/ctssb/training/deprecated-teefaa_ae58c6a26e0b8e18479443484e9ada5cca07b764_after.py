#!/usr/bin/env python

import os
import time
import argparse
import subprocess
from fabric.api import local, execute, task, hide

from .libexec.common import read_config

class TeefaaSsh(object):

    def __init__(self):

        config = read_config()
        self.ssh_config = config['ssh_config']
        self.hostname = config['host_config']['hostname']
        try:
            self.ssh_key = os.path.abspath(config['ssh_key'])
        except:
            self.ssh_key = None

    def setup(self, parser):

        ssh = parser.add_parser(
                'ssh', 
                help="ssh to destination host")
        ssh.set_defaults(func=self.do_ssh)

    def do_ssh(self, args):

        print("\nssh to machine '{0}'...\n".format(self.hostname))
        self.check_ssh()
        cmd = ['ssh', '-F', self.ssh_config, self.hostname]
        if self.ssh_key: cmd.append('-i' + self.ssh_key)
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            print("SSH is disconnected...")

    def check_ssh(self):

        count = 1
        limit = 50
        FNULL = open(os.devnull, 'w')
        cmd = ['ssh', '-o', 'ConnectTimeout=5', '-F', self.ssh_config]
        if self.ssh_key: cmd.append('-i' + self.ssh_key)
        cmd.append(self.hostname)
        cmd.append('hostname')
        while count < limit:
            try:
                subprocess.check_call(cmd, stdout=FNULL, stderr=subprocess.STDOUT)
                break
            except subprocess.CalledProcessError:
                print ("'{h}' is offline. Wait and retry ssh ({c}/{l})...".format(
                    h=self.hostname,c=count,l=limit))
                count += 1
                time.sleep(10)


def check_ssh():
    ts = TeefaaSsh()
    ts.check_ssh()
