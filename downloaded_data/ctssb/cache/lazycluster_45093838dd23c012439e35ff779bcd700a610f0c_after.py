"""Runtime management module. This module contains convenient classes for working with `Runtimes` and `RuntimeTasks`."""

from typing import Optional, List, Dict, Generator, Union
from storm import Storm
from multiprocessing import Process
import warnings
import logging
import atexit
from copy import deepcopy

from lazycluster import RuntimeTask, Runtime
from lazycluster import _utils
from lazycluster import PortInUseError, InvalidRuntimeError, NoPortsLeftError, NoRuntimesDetectedError


class RuntimeGroup(object):
    """A group of logically related `Runtimes`.

    The `RuntimeGroup` provides a simplified interface for executing tasks in multiple `Runtimes` or exposing ports
    within a `RuntimeGroup`.

    Examples:
            Execute a `RuntimeTask` in a `RuntimGroup`
            ```python
            # Create instances
            group = RuntimeGroup([Runtime('host-1'), Runtime('host-2')])
            # group = RuntimeGroup(hosts=['host-1', 'host-2'])
            my_task = RuntimeTask('group-demo').run_command('echo Hello Group!')

            # Execute a RuntimeTask in a single Runtime
            single_task = group.execute_task(my_task)
            print(single_task.execution_log[0])

            # Execute a RuntimeTask in the whole RuntimGroup
            task_list = group.execute_task(my_task, broadcast=True)

            # Execute RuntimeTask via RuntimGroup either on a single Runtime
            my_task = RuntimeTask('group-demo').run_command('echo Hello Group!')
            task = group.execute_task(my_task)
            ```
            A DB is running on localhost on port `local_port` and the DB is only accessible
            from localhost. But you also want to access the service on the other `Runtimes` on port
            `runtime_port`. Then you can use this method to expose the service which is running on the
            local machine to the remote machines.
            ```python
            # Expose a port to all Runtimes contained in the Runtime. If a port list is given the next free port is
            # chosen and returned.
            group_port = group.expose_port_to_runtimes(local_port=60000, runtime_port=list(range(60000,60010)))
            print('Local port 60000 is now exposed to port ' + str(group_port) + ' in the RuntimeGroup!')
            ```
            A DB is running on a remote host on port `runtime_port` and the DB is only accessible from the remote
            machine itself. But you also want to access the service to other `Runtimes` in the group. Then you can use
            this method to expose the service which is running on one `Runtime` to the whole group.
            ```python
            # Expose a port from a Runtime to all other ones in the RuntimeGroup. If a port list is given the next
            # free port is chosen and returned.
            group_port = group.expose_port_from_runtime_to_group(host='host-1', runtime_port=60000,
                                                                 group_port=list(range(60000,60010)))
            print('Port 60000 of `host-1` is now exposed to port ' + str(group_port) + ' in the RuntimeGroup!')
            ```
    """

    _INTERNAL_PORT_MIN = 5800
    _INTERNAL_PORT_MAX = 5999
    _internal_port_range = range(_INTERNAL_PORT_MIN, _INTERNAL_PORT_MAX)

    def __init__(self, runtimes: Optional[List[Runtime]] = None, hosts: Optional[List[str]] = None):
        """ Initialization method.
        
        Args:
            runtimes: List of `Runtimes`. If not given, then `hosts` must be supplied.
            hosts: List of hosts, which will be used to instantiate `Runtime` objects. If not given, then `runtimes`
                   must be supplied.
        Raises:
            ValueError: Either `runtimes` or `hosts` must be supplied. Not both or none.
            InvalidRuntimeError: If a runtime cannot be instantiated via host.
        """
        if not runtimes and not hosts or runtimes and hosts:
            raise ValueError("Either `runtimes` or `hosts` must be supplied. Not both or none.")

        # Create the Logger
        self.log = logging.getLogger(__name__)

        if runtimes:
            self._runtimes = {runtime.host: runtime for runtime in runtimes}
        elif hosts:
            self._runtimes = {host: Runtime(host) for host in hosts}  # Throws InvalidRuntimeError
        self._proc_keys = []
        self._tasks = []
        # Cleanup will be done atexit since usage of destructor may lead to exceptions
        atexit.register(self.cleanup)

        self.log.debug(f'RuntimeGroup initialized.')

    def __repr__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)

    def __str__(self):
        hosts_str = ''
        for runtime in self.runtimes:
            if not hosts_str:
                hosts_str += str(runtime)
            else:
                hosts_str += ', ' + str(runtime)
        return type(self).__name__ + ': ' + hosts_str

    @property
    def hosts(self) -> List[str]:
        """Contained hosts in the group.
        
        Returns:
            List[str]: List with hosts of all `Runtimes`.
        """
        return list(self._runtimes)

    @property
    def runtimes(self) -> List[Runtime]:
        """Contained Runtimes in the group.

        Returns:
            List[Runtime]: List with all `Runtimes`.
        """
        return list(self._runtimes.values())

    @property
    def runtime_count(self) -> int:
        """The count of runtimes contained in the group.

        Returns:
            int: The count.
        """
        return len(self.hosts)

    @property
    def task_processes(self) -> List[Process]:
        """Processes from all contained `Runtimes` which were started to execute a `RuntimeTask`.

        Returns:
             List[Process]: Process list.
        """
        processes = []
        for runtime in self._runtimes.values():
            processes.extend(runtime.task_processes)
        return processes

    @property
    def function_returns(self) -> Generator[object, None, None]:
        """Function return data. Blocks thread until a `RuntimeTasks` finished executing and gives back the return data
        of the remotely executed python functions. The data is returned in the same order as the Tasks were started.

        Note:
            Only function returns from `RuntimeTasks` that were started via the `RuntimeGroup` will be returned. If a
            contained `Runtime` executed further tasks directly, then those data will only be returned when querying the
            respective task directly.

        Returns:
            Generator[object, None, None]: The unpickled return data.
        """
        self.log.debug(f'Start generating function returns for RuntimeGroup.')
        for task in self._tasks:
            for return_data in task.function_returns:
                yield return_data

    def set_env_variables(self, env_variables: Dict):
        """Set environment variables used when executing a task.

        Note:
            This is a convenient wrapper and internally calls Runtime.set_env_variables().

        Args:
            env_variables: The env variables as dictionary.
        """
        for runtime in self._runtimes.values():
            runtime.set_env_variables(env_variables)

    def print_hosts(self):
        """Print the hosts of the group.
        """
        print('\n')
        if not self.hosts:
            print('The group is empty!')
            return
        else:
            print('\u001b[1mRuntimes contained in Group:\u001b[0m')
        for hostname in self.hosts:
            print(self.get_runtime(hostname).class_name + ': ' + hostname)

    def print_runtime_info(self):
        """Print information of contained `Runtimes`.
        """
        for runtime in self.runtimes:
            runtime.print_info()

    def add_runtime(self, host: Optional[str] = None, runtime: Optional[Runtime] = None):
        """Add a `Runtime` to the group either by host or as a `Runtime` object.
        
        Args:
            host: The host of the runtime. Defaults to None.
            runtime: The `Runtime` object to be added to the group. Defaults to None.

        Raises:
            ValueError: If the same host is already contained. Or if both host and runtime is given. We refuse
                        the temptation to guess. Also if no argument is supplied.
        """
        if host and runtime:
            raise ValueError('Only host or runtime must be supplied. We refuse the temptation to guess.')
        elif not host and not runtime:
            raise ValueError('Hostname or runtime must be supplied.')
        elif runtime and self.contains_runtime(runtime.host):
            raise ValueError('Runtime with the same host is already contained in the group.')
        elif host and self.contains_runtime(host):
            raise ValueError('Runtime with the same host is already contained in the group.')
        elif host:
            rt = Runtime(host)
        else:
            rt = runtime
        self._runtimes[rt.host] = rt
        self.log.info(rt.host + ' added as ' + rt.class_name + ' to the group.')

    def remove_runtime(self, host: str):
        """Remove a runtime from the group by host.
        
        Args:
            host: The host of the `Runtime` to be removed from the group.
        """
        if not self.contains_runtime(host):
            warnings.warn('Runtime ' + host + ' is  not contained in the group!')
            return
        else:
            del self._runtimes[host]
            self.log.info(f'Runtime {host} removed from RuntimeGroup')

    def expose_port_to_runtimes(self, local_port: int, runtime_port: Union[int, List[int], None] = None,
                                exclude_hosts: Union[str, List[str], None] = None) -> int:
        """ Expose a port from localhost to all Runtimes beside the excluded ones so that all traffic on the
        `runtime_port` is forwarded to the `local_port` on the local machine. This corresponds to remote
        port forwarding in ssh tunneling terms. Additionally, all relevant runtimes will be checked if the port is
        actually free.
        
        Args:
            local_port: The port on the local machine.
            runtime_port: The port on the runtimes where the `local_port` shall be exposed to. May raise PortInUseError
                          if a single port is given. If a list is used to automatically find a free port then a
                          NoPortsLeftError may be raised. Defaults to `local_port`.
            exclude_hosts: List with hosts where the port should not be exposed to. Defaults to None. Consequently, all
                           `Runtimes` will be considered.

        Returns:
            int: The port which was actually exposed to the `Runtimes`.

        Raises:
            PortInUseError: If `runtime_port` is already in use on at least one Runtime.
            ValueError: Only hosts or `exclude_hosts` must be provided or host is not contained in the group.
        """

        self.log.info(f'Start exposing the local port {str(local_port)} in the RuntimeGroup.')

        # 1. Determine a free runtime port
        if not runtime_port or not isinstance(runtime_port, list):
            if not runtime_port:
                runtime_port = local_port
            if not self.has_free_port(runtime_port):
                raise PortInUseError(runtime_port, self)

        elif isinstance(runtime_port, list):
            runtime_port = self.get_free_port(runtime_port)  # Raises NoPortsLeftError

        # Ensure that we work with a list and not a single value
        exclude_hosts = _utils.create_list_from_parameter_value(exclude_hosts)

        if not self.has_free_port(runtime_port, exclude_hosts=exclude_hosts + [Runtime.LOCALHOST]):
            raise PortInUseError(runtime_port, self)

        for runtime in self.get_runtimes(exclude_hosts=exclude_hosts).values():  # Raises ValueError
            process_key = runtime.expose_port_to_runtime(local_port, runtime_port)
            if process_key:
                self._proc_keys.append(process_key)

        self.log.debug(f'Port {str(runtime_port)} used as runtime_port.')
        return runtime_port

    def expose_port_from_runtime_to_group(self, host: str, runtime_port: int,
                                          group_port: Union[int, List[int], None] = None) -> int:
        """Expose a port from a `Runtime` to all other `Runtimes` in the `RuntimeGroup` so that all traffic to the
        `group_port` is forwarded to the `runtime_port` of the runtime.
        
        Args:
            host: The host of the `Runtime`.
            runtime_port: The port on the runtime.
            group_port: The port on the other runtimes where the `runtime_port` shall be exposed to. May raise
                        PortInUseError if a single port is given. If a list is used to automatically find a free port
                        then a NoPortsLeftError may be raised. Defaults to runtime_port.

        Returns:
            int: The `group_port` that was eventually used.

        Raises:
            ValueError: If host is not contained.
            PortInUseError: If `group_port` is occupied on the local machine.
            NoPortsLeftError: If `group_ports` was given and none of the ports was free.
        """
        if not self.contains_runtime(host):
            raise ValueError('Runtime ' + host + ' is not contained in the group.')

        self.log.info(f'Start exposing the port {str(runtime_port)} from Runtime {host} in the RuntimeGroup.')

        # 1. Determine a free group port
        if not group_port or not isinstance(group_port, list):
            if not group_port:
                group_port = runtime_port
            if not self.has_free_port(group_port, exclude_hosts=[host]):
                raise PortInUseError(group_port, self)

        elif isinstance(group_port, list):
            group_port = self.get_free_port(group_port)

        # 2. Determine a free port on localhost, since all traffic is tunneled over the local machine
        local_port = None
        if _utils.localhost_has_free_port(group_port):
            local_port = group_port
        else:
            # Get the first free port from the local port range
            for current_port in self._internal_port_range:
                if not _utils.localhost_has_free_port(current_port):
                    continue
                else:
                    local_port = current_port
                    self._internal_port_range = range(current_port + 1, self._INTERNAL_PORT_MAX)

        if not local_port:
            # self._internal_port_range = None <- does this makes sense? not sure!
            raise NoPortsLeftError()

        # 3. Finally expose the ports
        for runtime in self._runtimes.values():
            if runtime.host == host:
                process_key = runtime.expose_port_from_runtime(runtime_port, local_port)
            else:
                process_key = runtime.expose_port_to_runtime(local_port, group_port)
            if process_key:
                self._proc_keys.append(process_key)
        self.log.debug(f'Port {str(group_port)} used as group_port.')
        return group_port

    def execute_task(self, task: RuntimeTask, host: Optional[str] = None, broadcast: bool = False,
                     execute_async: bool = True, debug: bool = False) -> RuntimeTask or List[RuntimeTask]:
        """Execute a `RuntimeTask` in the whole group or in a single `Runtime`.

        Note:
            When broadcasting a task in the group then actually deep copies of the RuntimeTask are created (by using
            its custom __deepcopy__ implementation), since each task holds state related to its own execution. Thus,
            multiple tasks will be returned in this case.
        
        Args:
            task: The task to be executed.
            host: If task should be executed in one Runtime. Optionally, the host could be set in order to ensure
                  the execution in a specific Runtime. Defaults to None. Consequently, the least busy `Runtime` will be
                  chosen.
            broadcast: True, if the task will be executed on all `Runtimes`. Defaults to False.
            execute_async: True, if execution will take place async. Defaults to True.
            debug: If `True`, stdout/stderr from the runtime will be printed to stdout of localhost. If, `False` then
                   the stdout/stderr will be added to python logger with level debug after each task step. Defaults to
                   `False`.

        Returns:
            RuntimeTask or List[RuntimeTask]: Either a single `RuntimeTask` object in case the execution took place
                                              in a single `Runtime` or a list of `RuntimeTasks` if executed in all.

        Raises:
            ValueError: If `host` is given and not contained as `Runtime` in the group.
            TaskExecutionError: If an executed task step can't be executed successfully.
        """
        if not broadcast:
            self.log.info(f'Start executing task {task.name} in RuntimeGroup (no broadcasting).')
        else:
            self.log.info(f'Start broadcasting task {task.name} in RuntimeGroup.')

        if broadcast:
            tasks = []
            needs_to_create_copy = False

            for runtime in self.get_runtimes().values():  # Raises ValueError

                if not needs_to_create_copy:
                    current_task = task
                else:
                    # Create a deep copy to prevent reference errors especially for the task log.
                    # Each task will will contain its own log produced on its executing host.
                    current_task = deepcopy(task)

                runtime.execute_task(current_task, execute_async, debug)

                tasks.append(current_task)
                self._tasks.append(current_task)

            return tasks

        else:
            if host:
                if host not in self._runtimes:
                    raise ValueError('The host ' + host + ' is not a valid runtime.')
                self.get_runtime(host).execute_task(task, execute_async, debug)
            else:
                self._get_least_busy_runtime().execute_task(task, execute_async, debug)
            self._tasks.append(task)
            return task

    def send_file(self, local_path: str, remote_path: Optional[str] = None, execute_async: Optional[bool] = True):
        """Send either a single file or a folder from localhost to all Runtimes of the group.

        Note:
            This method is a convenient wrapper around the Runtime's send file functionality. See Runtime.send_file()
            for further details.

        Args:
            local_path: Path to file on local machine.
            remote_path: Path on the Runtime. Defaults to the Runtime.working_directory. See
                         `RuntimeTask.execute()` docs for further details.
            execute_async: Each individual sending will be done in a separate process if True. Defaults to True.

        Returns:
            RuntimeTask: self.

        Raises:
            ValueError: If local_path is emtpy.
            TaskExecutionError: If an executed task step can't be executed successfully.
        """
        for runtime in self._runtimes.values():
            runtime.send_file(local_path, remote_path, execute_async)

    def join(self):
        """Blocks until `RuntimeTasks` which were started via the `group.execute_task()` method terminated.
        """
        self.log.info('Joining all processes executing a task that were started via the RuntimeGroup')
        for task in self._tasks:
            task.join()

    def print_log(self):
        """Print the execution logs of each `RuntimeTask` that were executed in the group.
        """
        i = 0
        for task in self._tasks:
            if i > 0:
                print('\n')
                i += 1
            task.print_log()

    def get_free_port(self, ports: List[int], enforce_check_on_localhost: bool = False) -> int:
        """Return the first port from the list which is currently not in use in the whole group.

        Args:
             ports: The list of ports that will be used to find a free port in the group.
             enforce_check_on_localhost: If true the port check will be executed on localhost as well, although
                                         localhost might not be a `Runtime` instance contained in the `RuntimeGroup`.

        Returns:
            int: The first port from the list which is not yet used within the whole group.

        Raises:
            NoPortsLeftError: If the port list is empty and no free port was found yet.
        """
        localhost_not_in_group = True if Runtime.LOCALHOST not in self._runtimes else False

        for port in ports:

            if enforce_check_on_localhost and localhost_not_in_group and not _utils.localhost_has_free_port(port):
                continue

            if not self.has_free_port(port):
                continue

            self.log.debug(f'Port {str(port)} is retrieved as free port in the RuntimeGroup.')
            return port

        raise NoPortsLeftError()

    def has_free_port(self, port: int, exclude_hosts: Union[List[str], str, None] = None) -> bool:
        """Check if a given port is free on `Runtimes` contained in the group. The check can be restricted to a
        specific subset of contained `Runtimes` by excluding some hosts.

        Args:
            port: The port to be checked in the group.
            exclude_hosts: If supplied, the check will be omitted in these `Runtimes`. Defaults to None, i.e. not
                           restricted.

        Returns:
            bool: True if port is free on all `Runtimes`, else False.

        Raises:
            ValueError: Only hosts or exclude_hosts must be provided or Hostname is
                        not contained in the group.                     
        """
        is_free = True

        for runtime in self.get_runtimes(exclude_hosts=exclude_hosts).values():  # Raises ValueError
            if not runtime.has_free_port(port):
                self.log.debug(f'The port {str(port)} is currently in use on {runtime.class_name} {runtime.host}')
                is_free = False

        return is_free

    def contains_runtime(self, host: str) -> bool:
        """Check if the group contains a `Runtime` identified by host.

        Args:
            host: The `Runtime` to be looked for.

        Returns:
            bool: True if runtime is contained in the group, else False.
        """
        return True if host in self.hosts else False

    def clear_tasks(self):
        """Clears all internal state related to `RuntimeTasks`.
        """
        self.log.info(f'Clear all tasks and kill related processes in the RuntimeGroup.')
        # 1: Clean up all state on group level
        self._tasks = []
        self._proc_keys = [proc_key for proc_key in self._proc_keys if not Runtime.is_runtime_task_process(proc_key)]
        # 2: Clean up state in contained `Runtimes`
        for runtime in self._runtimes.values():
            runtime.clear_tasks()

    def get_runtime(self, host: Optional[str] = None) -> Runtime:
        """Returns a runtime identified by the `host` or 'the least busy one' will be returned if not host is given,
        i.e. the one with the fewest alive processes executing a `RuntimeTask`.

        Note:
            The current behavior of the 'least busy runtime' is intended to be changed to a smarter approach as soon as
            there will be the concrete need. So feel free to reach out to us or provide an alternative approach as PR.

        Args:
            host: The host which identifies the runtime.

        Returns:
            Runtime: Runtime object.

        Raises:
            ValueError: Hostname is not contained in the group.
        """
        if host and host not in self.hosts:
            raise ValueError('Hostname not contained in the RuntimeGroup')
        elif host:
            return self._runtimes[host]
        else:
            self._get_least_busy_runtime()

    def get_runtimes(self, include_hosts: Union[str, List[str], None] = None,
                           exclude_hosts: Union[str, List[str], None] = None) -> Dict[str, Runtime]:
        """Convenient methods for getting relevant `Runtimes` contained in the group.

        Args:
            include_hosts: If supplied, only the specified `Runtimes` will be
                                                                 returned. Defaults to None, i.e. not restricted.
            exclude_hosts: If supplied, all `Runtimes` beside the here specified ones will be returned. Defaults to an
                           empty list, i.e. not restricted.
        Raises:
            ValueError: If include_hosts and exclude_hosts is provided or if a host from `include_host` is not contained
                        in the group.
        """
        runtimes = {}

        if include_hosts and exclude_hosts:
            raise ValueError('Only include_hosts or exclude_hosts must be provided. Not both.')

        elif not include_hosts and not exclude_hosts:
            # => Return all runtimes
            return self._runtimes

        elif include_hosts:
            # => Only the ones specified in hosts
            include_hosts = _utils.create_list_from_parameter_value(include_hosts)  # Ensure it's a list
            for hostname in include_hosts:
                if hostname not in self._runtimes:
                    raise ValueError(hostname + ' is not contained in the RuntimeGroup.')
                runtimes.update({hostname: self._runtimes[hostname]})

        elif exclude_hosts:
            # => All but without the ones specified in excluded_hosts
            exclude_hosts = _utils.create_list_from_parameter_value(exclude_hosts)  # Ensure it's a list
            for hostname in self.hosts:
                if hostname not in exclude_hosts:
                    runtimes.update({hostname: self._runtimes[hostname]})

        return runtimes

    def cleanup(self):
        """Release all acquired resources and terminate all processes by calling the cleanup method on all contained
        `Runtimes`.
        """
        self.log.info(f'Start cleanup of RuntimeGroup.')
        for runtime in self.get_runtimes().values():
            runtime.cleanup()

    def _get_least_busy_runtime(self) -> Runtime:
        """Get the least busiest runtime in terms of alive `RuntimeTask` processes.
        """
        final_rt = None

        for runtime in self.get_runtimes().values():
            if not final_rt:
                final_rt = runtime
            elif runtime.alive_task_process_count < final_rt.alive_task_process_count:
                final_rt = runtime
        return final_rt


class RuntimeManager(object):
    """The `RuntimeManager` can be used for a simplified resource management, since it aims to automatically detect
    valid `Runtimes` based on the ssh configuration. It can be used to create a `RuntimeGroup` based on the
    automatically detected instances and possibly based on further filters such as GPU availability.
    """

    def __init__(self):
        """Initialization method.

        Raises:
            NoRuntimeDetectedError: If no `Runtime` could be automatically detected.
        """
        # Create the Logger
        self.log = logging.getLogger(__name__)

        runtimes = {}

        # Iterate over ssh configuration entries and look for valid RemoteRuntimes
        ssh_util = Storm()
        self.log.debug('RuntimeManager starts looking for Runtimes based on ssh configuration.')

        for ssh_entry in ssh_util.list_entries(only_servers=True):
            if ssh_entry['host'] in runtimes:
                continue
            if (ssh_entry['host'] == 'localhost' and '127.0.0.1' in runtimes) or (ssh_entry['host'] == '127.0.0.1'
                                                                                  and 'localhost' in runtimes):
                continue
            try:
                self.log.debug(f'RuntimeManager tries to instantiate host {ssh_entry["host"]} as Runtime.')
                runtime = Runtime(ssh_entry['host'])
            except InvalidRuntimeError:
                self.log.debug(f'RuntimeManager detected host config for {ssh_entry["host"]}, that could NOT be '
                               f'instantiated  as a valid Runtime.')
                continue
            runtimes.update({runtime.host: runtime})
            self.log.info(runtime.host + ' detected as valid Runtime by the RuntimeManager.')

        try:
            self._group = RuntimeGroup(list(runtimes.values()))
            self.log.info(f'RuntimeManager detected {len(runtimes)} valid Runtime(s).')
        except ValueError as err:
            raise NoRuntimesDetectedError(err)

        self.log.debug('RuntimeManager initialized.')

    def __repr__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)

    def __str__(self):
        runtimes_str = ''
        for runtime in self._group.runtimes:
            runtimes_str += ', ' + str(runtime)
        return type(self).__name__ + ' detected: ' + runtimes_str

    def create_group(self,
                     include_hosts: Union[str, List[str], None] = None,
                     exclude_hosts: Union[str, List[str], None] = None,
                     gpu_required: bool = False,
                     min_memory: Optional[int] = None,
                     min_cpu_cores: Optional[int] = None,
                     installed_executables: Union[str, List[str], None] = None,
                     filter_commands: Union[str, List[str], None] = None,
                     working_dir: Optional[str] = None) -> RuntimeGroup:
        """Create a runtime group with either all detected `Runtimes` or with a subset thereof.
        
        Args:
            include_hosts: Only these hosts will be included in the `RuntimeGroup`. Defaults to None, i.e. not
                           restricted.
            exclude_hosts: If supplied, all detected `Runtimes` beside the here specified ones will be included in the
                           group. Defaults to None, i.e. not restricted.
            gpu_required): True, if gpu availability is required. Defaults to False.
            min_memory: The minimal amount of memory in MB. Defaults to None, i.e. not restricted.
            min_cpu_cores: The minimum number of cpu cores required. Defaults to None, i.e. not restricted.
            installed_executables: Possibility to only include `Runtimes` that have an specific executables installed.
            filter_commands: Shell commands that can be used for generic filtering.
            working_dir: The directory which shall act as working one. Defaults to None. See the `Runtime` docs for
                         further details.

        Note:
            The filter criteria are passed through the `check_filter()` method of the `Runtime` class. See its
            documentation for further details and examples.

        Returns:
            RuntimeGroup: The created `RuntimeGroup`.
        
        Raises:
            ValueError: Only hosts or excluded_hosts must be provided or Hostname is not contained in the group.
            NoRuntimesError: If no `Runtime` matches the filter criteria.
        """
        runtimes_dict = self._group.get_runtimes(include_hosts, exclude_hosts)  # Raises ValueError

        final_runtimes = []

        for runtime in runtimes_dict.values():
            if runtime.check_filter(gpu_required, min_memory, min_cpu_cores, installed_executables, filter_commands):
                runtime._working_dir = working_dir
                final_runtimes.append(runtime)

        try:
            group = RuntimeGroup(final_runtimes)
            self.log.debug('RuntimeGroup created by RuntimeManager')
        except ValueError as e:
            raise NoRuntimesDetectedError(e)

        self.log.debug(f'RuntimeManager created RuntimeGroup with {str(group.runtime_count)} Runtime(s).')
        return group

    def print_runtime_info(self):
        """Print information of detected `Runtimes`.

        Note:
            This function is a wrapper for `RuntimeGroup.print_runtime_info()`, since the detected `Runtimes` are
            internally kept as a 'RuntimeGroup`.
        """
        self._group.print_runtime_info()