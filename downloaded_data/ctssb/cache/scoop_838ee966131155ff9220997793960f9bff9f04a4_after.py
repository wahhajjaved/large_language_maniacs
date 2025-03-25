#!/usr/bin/env python
#
#    This file is part of Scalable COncurrent Operations in Python (SCOOP).
#
#    SCOOP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    SCOOP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with SCOOP. If not, see <http://www.gnu.org/licenses/>.
#
from threading import Thread
import subprocess
import logging
import sys
import os
import scoop
try:
    import psutil
except ImportError:
    psutil = None


class localBroker(object):
    def __init__(self, debug, nice=0, subbroker=False):
        """Starts a broker on random unoccupied ports"""
        from scoop.broker import Broker
        if nice:
            if not psutil:
                scoop.logger.error("'nice' used while psutil not installed.")
                raise ImportError("psutil is needed for nice functionnality.")
            p = psutil.Process(os.getpid())
            p.set_nice(nice)
        self.localBroker = Broker(debug=debug, subbroker=subbroker)
        self.brokerPort, self.infoPort = self.localBroker.getPorts()
        self.broker = Thread(target=self.localBroker.run)
        self.broker.daemon = True
        self.broker.start()
        logging.debug("Local broker launched on ports {0}, {1}"
                      ".".format(self.brokerPort, self.infoPort))

    def close(self):
        pass


class remoteBroker(object):
    BASE_SSH = ['ssh', '-x', '-n', '-oStrictHostKeyChecking=no']

    def __init__(self, hostname, pythonExecutable, nice=0, subbroker=False):
        """Starts a broker on the specified hostname on unoccupied ports"""
        brokerString = ("{pythonExec} -m scoop.broker.__main__ "
                        "--tPort {brokerPort} "
                        "--mPort {infoPort} "
                        "--echoGroup "
                        "--echoPorts ")
        if nice:
            brokerString += "--nice {nice} ".format(nice=nice)
        if subbroker:
            brokerString += "--subbroker "
        self.hostname = hostname
        for i in range(5000, 10000, 2):
            self.shell = subprocess.Popen(self.BASE_SSH
                + [hostname]
                + [brokerString.format(brokerPort=i,
                                       infoPort=i + 1,
                                       pythonExec=pythonExecutable,
                                      )],
                # stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # TODO: This condition is not doing what it's supposed
            if self.shell.poll() is not None:
                continue
            else:
                self.brokerPort, self.infoPort = i, i + 1
                break
        else:
            raise Exception("Could not successfully launch the remote broker.")

        # Get remote process group ID
        try:
            self.remoteProcessGID = int(self.shell.stdout.readline().strip())
        except ValueError:
            self.remoteProcessGID = None

        # Get remote ports
        try:
            self.remoteProcessGID = self.shell.stdout.readline().decode().strip().split(",")
        except ValueError:
            self.remoteProcessGID = None

        logging.debug("Foreign broker launched on ports {0}, {1} of host {2}"
                      ".".format(self.brokerPort,
                                 self.infoPort,
                                 hostname,
                                 )
                      )


    def isLocal(self):
        """Is the current broker on the localhost?"""
        # This exists for further fusion with localBroker
        return False
        # return self.hostname in utils.localHostnames

    def close(self):
        """Connection(s) cleanup."""
        # Ensure everything is cleaned up on exit
        logging.debug('Closing broker on host {0}.'.format(self.hostname))

        # Terminate subprocesses
        try:
            self.shell.terminate()
        except OSError:
            pass

        # Send termination signal to remaining workers
        if not self.isLocal() and self.remoteProcessGID is None:
                logging.info("Zombie process(es) possibly left on "
                             "host {0}!".format(self.hostname))
        elif not self.isLocal():
            command = "kill -9 -{0} &>/dev/null".format(self.remoteProcessGID)
            subprocess.Popen(self.BASE_SSH
                             + [self.hostname]
                             + [command],
                             shell=True,
            ).wait()

        sys.stdout.write(self.shell.stdout.read().decode("utf-8"))
        sys.stdout.flush()

        sys.stderr.write(self.shell.stderr.read().decode("utf-8"))
        sys.stderr.flush()
