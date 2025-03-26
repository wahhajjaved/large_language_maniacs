"""Module for conveniently managing a Hyperopt cluster. https://github.com/hyperopt/hyperopt
"""

import time
import warnings
from typing import List, Union, Optional

from subprocess import Popen

from lazycluster import RuntimeTask, Runtime, RuntimeGroup
from lazycluster.cluster import MasterWorkerCluster, MasterLauncher, WorkerLauncher
from lazycluster import _utils
from lazycluster.cluster.exceptions import MasterStartError
from lazycluster.exceptions import PortInUseError


class LocalMongoLauncher(MasterLauncher):
    """Concrete implementation of the `MasterLauncher` interface.

    This class implements the logic for starting a MongoDB instance on localhost. Hence, we simply treat the MongoDB
    instance as master node.
    """

    def __init__(self, runtime_group: RuntimeGroup):
        """Initialization method.

        Args:
            runtime_group: The group where the workers will be started.
        """
        super().__init__(runtime_group)
        self._dbpath = None

    def start(self, ports: Union[List[int], int], timeout: int = 3) -> List[int]:
        """Launch a master instance.

        Args:
            ports: Port where the DB should be started. If a list is given then the first port that is free in the
                   `RuntimeGroup` will be used. The actual chosen port can be requested via the property `port`.
            timeout: Timeout (s) after which an MasterStartError is raised if DB instance not started yet.

        Returns:
            List[int]: In case a port list was given the updated port list will be returned. Otherwise an empty list.

        Raises:
            PortInUseError: If a single port is given and it is not free in the `RuntimeGroup`.
            NoPortsLeftError: If a port list was given and none of the ports is actually free in the `RuntimeGroup`.
            MasterStartError: If master was not started after the specified `timeout`.
        """

        if not isinstance(ports, list):
            if _utils.localhost_has_free_port(ports) and \
               self._group.has_free_port(ports, exclude_hosts=Runtime.LOCALHOST):
                master_port = ports
            else:
                raise PortInUseError(ports, self._group)

        else:
            master_port = self._group.get_free_port(ports)  # Raises NoPortsLeftError
            ports = _utils.get_remaining_ports(ports, master_port)

        self.log.debug(f'Starting MongoDB on localhost on port {str(master_port)} with dbpath `{self._dbpath}`.')
        #self._process = Popen(['mongod', '--dbpath', self._dbpath, '--port', str(master_port)])
        self._process = Popen(['mongod'])

        time.sleep(timeout)  # Needed for being able to check the port

        if not _utils.localhost_has_free_port(master_port):
            self._port = master_port
            self.log.info('MongoDB started on localhost on port ' + str(self._port))
        else:
            self.log.debug('MongoDB could NOT be started succesfully on port ' + str(self._port))
            raise MasterStartError('localhost', master_port)

        # Sets up ssh tunnel for scheduler such that all communication is routed over the
        # local machine and all entities can talk to each the scheduler on localhost.
        self.log.debug(f'Expose the MongoDB port in the RuntimeGroup.')
        self._group.expose_port_to_runtimes(self._port)

        return ports


class RoundRobinLauncher(WorkerLauncher):
    """WorkerLauncher implementation for launching hyperopt workers in a round robin manner.
    """

    def __init__(self, runtime_group: RuntimeGroup):
        """Initialization method.

        Args:
            runtime_group: The group where the workers will be started.
        """
        super().__init__(runtime_group)
        self._ports = None

        self.log.debug('RoundRobinLauncher initialized.')

    def start(self, worker_count: int, master_port: int, ports: List[int] = None) -> List[int]:
        """Launches the worker instances in the `RuntimeGroup`.

        Args:
            worker_count: The number of worker instances to be started in the group.
            master_port:  The port of the master instance.
            ports: Without use here. Only here because we need to adhere to the interface defined by the
                   WorkerLauncher class.
        Returns:
            List[int]: The updated port list after starting the workers, i.e. the used ones were removed.
        """
        self._ports = ports
        hosts = self._group.hosts
        runtimes = self._group.runtimes

        # Launch each desired worker one by one
        for worker_index in range(worker_count):
            # Determine the runtime where the next worker will be started in
            runtime_index = (self._group.runtime_count + worker_index) % self._group.runtime_count
            # Get the actual host corresponding to the index
            host = hosts[runtime_index]
            # working_dir = runtimes[runtime_index].working_directory
            assert host == runtimes[runtime_index].host

            self.log.debug(f'Launch Hyperopt worker with index {worker_index} on Runtime {host}')

            self._launch_single_worker(host, worker_index, master_port)

        return self._ports

    def _launch_single_worker(self, host: str, worker_index: int, master_port: int):
        """Launch a single worker instance in a `Runtime` in the `RuntimeGroup`.
        """
        # 2. Start the worker on this port
        task = RuntimeTask('launch-hyperopt-worker-' + str(worker_index), needs_explicit_termination=True)
        task.run_command(self._get_launch_command(master_port))
        self._group.execute_task(task, host)

    @classmethod
    def _get_launch_command(cls, master_port: int, db: str = 'hyperopt', poll_intervall: float = 0.1) -> str:
        """Get the shell command for starting a worker instance.

        Returns:
             str: The launch command.
        """
        return f'hyperopt-mongo-worker --mongo=localhost:{str(master_port)}/{db} --poll-interval={str(0.1)}'


class HyperoptCluster(MasterWorkerCluster):
    """Convenient class for launching a Hyperopt cluster in a `RuntimeGroup`.

    The number of hyperopt workers defaults to the number of `Runtimes` in the used `RuntimeGroup`. This number can be
    adjusted so that more or less workers than available `Runtimes` can be used. Per default the desired number of
    workers is started in a round robin way as implemented in `RoundRobinLauncher`. Consequently, this leads to an
    equal distribution of hyperopt workers in the `RuntimeGroup`. You can provide a custom implementation inheriting
    from the `WorkerLauncher` class in order to execute a different strategy how workers should be started. The
    master instance (i.e. the mongoDB) will always be started on localhost as implemented in `LocalMasterLauncher`. This
    behavior can also be changed by providing a custom implementation inheriting from the `MasterLauncher`.
    """

    DEFAULT_MASTER_PORT = 27017
    ENV_NAME_MONGO_URL = 'MONGO_CONNECTION_URL'

    def __init__(self, runtime_group: RuntimeGroup,
                 master_launcher: Optional[MasterLauncher] = None,
                 worker_launcher: Optional[WorkerLauncher] = None,
                 dbpath: str = '/data/db',
                 dbname: str = 'hyperopt'):
        """Initialization method.

        Args:
            runtime_group: The `RuntimeGroup` contains all `Runtimes` which can be used for starting the entities.
            master_launcher: Optionally, an instance implementing the `MasterLauncher` interface can be given, which
                             implements the strategy for launching the master instances in the cluster. If None, then
                             `LocalMasterLauncher` is used.
            worker_launcher: Optionally, an instance implementing the `WorkerLauncher` interface can be given, which
                             implements the strategy for launching the worker instances. If None, then
                             `RoundRobinLauncher` is used.
            dbpath: The directory where the db files will be kept. Defaults to /data/db.
            dbname: The name of the database to be used for experiments. See MongoTrials url scheme in hyperopt
                    documentation for more details.
        """
        super().__init__(runtime_group)

        self._master_launcher = master_launcher if master_launcher else LocalMongoLauncher(runtime_group)
        self._master_launcher._dbpath = dbpath
        self._dbname = dbname

        self._worker_launcher = worker_launcher if worker_launcher else RoundRobinLauncher(runtime_group)

        self.log.debug('HyperoptCluster initialized.')

    @property
    def mongo_url(self) -> str:
        """The MongoDB url indicating what mongod process and which database to use.

        Returns:
            str: URL string.
        """
        if not self.master_port:
            warnings.warn('HyperoptCluster.mongo_url was requested although the master_port is not yet set.')

        return f'mongo://localhost:{self.master_port}/{self.dbname}/jobs'

    @property
    def dbname(self):
        """The name of the MongoDB database to be used for experiments.
        """
        return self._dbname

    def start_master(self, master_port: Optional[int] = None, timeout: int = 3):
        """Start the master instance.

        Note:
            How the master is actually started is determined by the the actual `MasterLauncher` implementation. Another
            implementation adhering to the `MasterLauncher` interface can be provided in the constructor of the cluster
            class.

        Args:
            master_port: Port of the master instance. Defaults to self.DEFAULT_MASTER_PORT, but another one is chosen if
                         the port is not free within the group. The actual chosen port can be requested via
                         self.master_port.
            timeout: Timeout (s) after which an MasterStartError is raised if master instance not started yet.

        Raises:
            PortInUseError: If a single port is given and it is not free in the `RuntimeGroup`.
            NoPortsLeftError: If there are no free ports left in the port list for instantiating the master.
            MasterStartError: If master was not started after the specified `timeout`.
        """
        super().start_master(master_port, timeout)
        self._group.set_env_variables({self.ENV_NAME_MONGO_URL: self.mongo_url})
