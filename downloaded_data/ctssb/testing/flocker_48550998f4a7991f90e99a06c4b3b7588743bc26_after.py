# Copyright ClusterHQ Inc.  See LICENSE file for details.
from datetime import timedelta
import sys
from ipaddr import IPAddress
from uuid import uuid4
from bitmath import GiB

from twisted.internet.defer import succeed
from twisted.internet.task import LoopingCall
from twisted.python.filepath import FilePath
from twisted.python import usage

from eliot import add_destination, start_action, write_failure, Message
from eliot.twisted import DeferredContext

from flocker.common import gather_deferreds
from flocker.control.httpapi import REST_API_PORT
from flocker.control import DockerImage
from flocker.apiclient import FlockerClient, MountedDataset

from benchmark._flocker import create_container


DEFAULT_TIMEOUT = 3600

MESSAGE_FORMATS = {
    'flocker.benchmark.container_setup:start':
        'Starting %(containers_per_node)s containers per node '
        'on %(total_nodes)s nodes...\n',
    'flocker.benchmark.container_setup:finish':
        'Started %(container_count)s containers with %(error_count)s '
        'failures.\n',
    'flocker.benchmark.container_setup:progress':
        'Created %(container_count)s / %(total_containers)s containers '
        '(%(error_count)s failures)\n',
}
ACTION_START_FORMATS = {
}


def eliot_output(message):
    """
    Write pretty versions of eliot log messages to stdout.
    """
    message_type = message.get('message_type')
    action_type = message.get('action_type')
    action_status = message.get('action_status')

    format = ''
    if message_type is not None:
        if message_type == 'twisted:log' and message.get('error'):
            format = '%(message)s'
        else:
            format = MESSAGE_FORMATS.get(message_type, '')
    elif action_type is not None:
        if action_status == 'started':
            format = ACTION_START_FORMATS.get('action_type', '')
        # We don't consider other status, since we
        # have no meaningful messages to write.
    sys.stdout.write(format % message)
    sys.stdout.flush()


class ContainerOptions(usage.Options):
    """
    Parses the options passed as an argument to the create container script.
    """
    description = "Set up containers in a Flocker cluster."

    optParameters = [
        ['apps-per-node', None, 1, 'Number of application containers per node',
         int],
        ['image', None, None,
         'Docker image to deploy'],
        ['mountpoint', None, None,
         'Location of the mountpoint of the datasets'],
        ['control-node', None, None,
         'Public IP address of the control node'],
        ['cert-directory', None, None,
         'Location of the user and control certificates and user key'],
        ['max-size', None, 1,
         'Size of the volume, in gigabytes.'],
        ['wait', None, DEFAULT_TIMEOUT,
         "The timeout in seconds for waiting until the operation is complete."
         ],
    ]

    synopsis = ('Usage: setup-cluster-containers --app-per-node <containers '
                'per node> --image<DockerImage> '
                '--mountpoint <path to the mountpoint> '
                '--control-node <IPAddress> '
                '--cert-directory <path where all the certificates are> '
                '[--max-size <volume size in GB>] '
                '[--wait <total seconds to wait>]'
                )

    def postOptions(self):
        # Mandatory parameters
        # Validate image
        if self['image'] is None:
            raise usage.UsageError(
                "image parameter must be provided"
            )
        # Validate mountpoint
        if self['mountpoint'] is None:
            raise usage.UsageError("mountpoint is a mandatory parameter")
        else:
            try:
                FilePath(self['mountpoint'])
            except ValueError:
                raise usage.UsageError("mountpoint has to be an absolute path")
        # Validate app per node
        if self['apps-per-node'] is None:
            raise usage.UsageError("apps-per-node is a mandatory parameter")
        else:
            try:
                self['apps-per-node'] = int(self['apps-per-node'])
            except ValueError:
                raise usage.UsageError("apps-per-node has to be an integer")
        # Validate control node
        if self['control-node'] is None:
            raise usage.UsageError("control-node is a mandatory parameter")
        else:
            try:
                IPAddress(self['control-node'])
            except ValueError:
                raise usage.UsageError("control-node has to be an IP address")
        # Validate certificate directory
        if self['cert-directory'] is None:
            raise usage.UsageError("cert-directory is a mandatory parameter")

        # Validate optional parameters
        # Note that we don't check if those parameters are None, because
        # all of them have default value and can't be none. If they are,
        # and exception will be raised
        try:
            self['max-size'] = int(self['max-size'])
        except ValueError:
            raise usage.UsageError(
                "The max-size timeout must be an integer.")

        try:
            self['wait'] = timedelta(seconds=int(self['wait']))
        except ValueError:
            raise usage.UsageError("The wait timeout must be an integer.")


def main(reactor, argv, environ):
    # Setup eliot to print better human-readable output to standard
    # output
    add_destination(eliot_output)

    try:
        options = ContainerOptions()
        options.parseOptions(argv[1:])
    except usage.UsageError as e:
        sys.stderr.write(e.args[0])
        sys.stderr.write('\n\n')
        sys.stderr.write(options.getSynopsis())
        sys.stderr.write('\n')
        sys.stderr.write(options.getUsage())
        raise SystemExit(1)

    container_deployment = ClusterContainerDeployment.from_options(reactor,
                                                                   options)

    return container_deployment.deploy(options['apps-per-node'])


class ClusterContainerDeployment(object):
    """
    Class that contains all the methods needed to deploy a new config in a
    cluster.

    :ivar image: ``DockerImage`` for the containers.
    :ivar max_size: maximum volume (dataset) size in bytes.
    :ivar mountpoint: unicode string containing the absolute path of the
        mountpoint.
    :ivar control_node_address: public ip address of the control node.
    :ivar timeout: total time to wait for the containers and datasets
        to be created.
    :ivar cluster_cert: ``FilePath`` of the cluster certificate.
    :ivar user_cert: ``FilePath`` of the user certificate.
    :ivar user_key: ``FilePath`` of the user key.
    :ivar client: ``FlockerClient`` conected to the cluster.
    :ivar reactor: ``Reactor`` used by the client.
    """
    def __init__(
        self, reactor, image, max_size, mountpoint, control_node_address,
        timeout, cluster_cert, user_cert, user_key, client
    ):
        """
        ``ClusterContainerDeployment`` constructor.
        It is not meant to be called directly. See ``from_options`` if you
        want to instantiate a ``ClusterContainerDeployment`` object.

        """
        self.image = image
        self.max_size = max_size
        self.mountpoint = mountpoint
        self.control_node_address = control_node_address
        self.timeout = timeout

        self.cluster_cert = cluster_cert
        self.user_cert = user_cert
        self.user_key = user_key
        self.client = client
        self.reactor = reactor
        self.container_count = 0
        self.error_count = 0

    @classmethod
    def from_options(cls, reactor, options):
        """
        Create a cluster container deployment object from the
        options given through command line.

        :param reactor: reactor
        :param options: ``ContainerOptions`` container the parsed
            options given to the script.
        """
        try:
            image = DockerImage(repository=options['image'])
            max_size = int(GiB(options['max-size']).to_Byte().value)
            mountpoint = unicode(options['mountpoint'])
            control_node_address = options['control-node']
            timeout = options['wait']
        except Exception as e:
            sys.stderr.write("%s: %s\n" % ("Missing or wrong arguments", e))
            sys.stderr.write(e.args[0])
            sys.stderr.write('\n\n')
            sys.stderr.write(options.getSynopsis())
            sys.stderr.write('\n')
            sys.stderr.write(options.getUsage())
            raise SystemExit(1)

        certificates_path = FilePath(options['cert-directory'])
        cluster_cert = certificates_path.child(b"cluster.crt")
        user_cert = certificates_path.child(b"user.crt")
        user_key = certificates_path.child(b"user.key")

        # Initialise client
        client = FlockerClient(
            reactor,
            control_node_address,
            REST_API_PORT,
            cluster_cert,
            user_cert,
            user_key
        )

        return cls(
            reactor, image, max_size, mountpoint, control_node_address,
            timeout, cluster_cert, user_cert, user_key, client
        )

    def _dataset_to_volume(self, dataset):
        """
        Given a ``Dataset``, returns a ``MountedDataset`` populated with
        the information from the dataset and the mountpoint.

        :param dataset: ``Dataset`` containing the dataset_id of an
            existent dataset.

        :return MountedDataset: with the datset id and the mountpoint
            populated.
        """
        if dataset is not None:
            return MountedDataset(dataset_id=dataset.dataset_id,
                                  mountpoint=self.mountpoint)
        else:
            return None

    def create_stateful_container(self, node, count):
        """
        Configure a stateful container to mount a new dataset, and wait for
        it to be running.
        """
        with start_action(
            action_type=u'flocker:benchmark:create_stateful_container',
            node=unicode(node.uuid),
            count=count
        ):
            d = DeferredContext(
                self.client.create_dataset(
                    primary=node.uuid,
                    maximum_size=self.max_size,
                )
            )

            def start_container(dataset):
                volume = MountedDataset(
                    dataset_id=dataset.dataset_id,
                    mountpoint=self.mountpoint
                )
                d = create_container(
                    self.reactor,
                    control_service=self.client,
                    node_uuid=node.uuid,
                    name=unicode(uuid4()),
                    image=self.image,
                    volumes=[volume],
                    timeout=self.timeout)

                # If container creation fails, delete dataset as well
                def delete_dataset(failure):
                    d = self.client.delete_dataset(dataset.dataset_id)
                    d.addErrback(write_failure)
                    d.addBoth(lambda _ignore: failure)
                    return d
                d.addErrback(delete_dataset)

                return d
            d.addCallback(start_container)

            def update_container_count(container):
                self.container_count += 1

            def update_error_count(failure):
                self.error_count += 1
                failure.printTraceback(sys.stderr)
                write_failure(failure)

            d.addCallbacks(update_container_count, update_error_count)

            return d.addActionFinish()

    def deploy(self, per_node):
        """
        Create ``per_node`` containers and datasets in each node of the
        cluster.

        :return Deferred: once all the requests to create the datasets and
            containers are made.
        """
        d = self.client.list_nodes()

        def start_containers(nodes):

            Message.log(
                message_type='flocker.benchmark.container_setup:start',
                containers_per_node=per_node,
                total_nodes=len(nodes)
            )
            total = per_node * len(nodes)

            def log_progress():
                Message.log(
                    message_type='flocker.benchmark.container_setup:progress',
                    container_count=self.container_count,
                    error_count=self.error_count,
                    total_containers=total
                )
            loop = LoopingCall(log_progress)
            loop.start(10, now=False)

            deferred_list = []
            for node in nodes:
                d = succeed(None)
                for i in range(per_node):
                    d.addCallback(
                        lambda _ignore, node=node, i=i:
                            self.create_stateful_container(node, i)
                    )
                deferred_list.append(d)

            d = gather_deferreds(deferred_list)

            def stop_loop(result):
                loop.stop()
                return result
            d.addBoth(stop_loop)

            return d

        d.addCallback(start_containers)

        def log_totals(result):
            Message.log(
                message_type='flocker.benchmark.container_setup:finish',
                container_count=self.container_count,
                error_count=self.error_count
            )
            return result
        d.addBoth(log_totals)

        return d
