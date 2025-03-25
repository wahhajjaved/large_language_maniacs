import os.path
from ConfigParser import SafeConfigParser, NoOptionError, NoSectionError
from operator import add
from uuid import uuid4

from logger import logger
from ordereddict import OrderedDict


REPO = 'https://github.com/pavel-paulau/perfrunner'

BROKER_URL = 'amqp://couchbase:couchbase@ci.sc.couchbase.com:5672/perfrunner'

SF_STORAGE = {
    'host': 'showfast.sc.couchbase.com', 'port': 8091,
    'username': 'Administrator', 'password': 'password'
}


class CbAgentSettings(object):

    seriesly_host = 'cbmonitor.sc.couchbase.com'
    cbmonitor_host_port = 'cbmonitor.sc.couchbase.com'
    interval = 5
    update_metadata = True


def safe(method):
    def wrapper(*args, **kargs):
        try:
            return method(*args, **kargs)
        except (NoSectionError, NoOptionError), e:
            logger.warn('Failed to get option from config: {0}'.format(e))
    return wrapper


class Config(object):

    def parse(self, fname):
        logger.info('Reading configuration file: {0}'.format(fname))
        if not os.path.isfile(fname):
            logger.interrupt('File doesn\'t exist: {0}'.format(fname))
        self.config = SafeConfigParser()
        self.config.read(fname)

        basename = os.path.basename(fname)
        self.name = os.path.splitext(basename)[0]

    @safe
    def _get_options_as_dict(self, section):
        if section in self.config.sections():
            return dict((p, v) for p, v in self.config.items(section))
        else:
            return {}


class ClusterSpec(Config):

    @safe
    def get_clusters(self):
        clusters = OrderedDict()
        for cluster, servers in self.config.items('clusters'):
            cluster = '{0}_{1}'.format(cluster, uuid4().hex[:6])
            clusters[cluster] = servers.split()
        return clusters

    @safe
    def get_masters(self):
        masters = OrderedDict()
        for cluster, servers in self.get_clusters().items():
            masters[cluster] = servers[0].split(':')[0]
        return masters

    @safe
    def get_all_hosts(self):
        servers = reduce(add, self.get_clusters().values())
        split_host_port = lambda server: server.split(':')[0]
        return map(split_host_port, servers)

    @safe
    def get_workers(self):
        return tuple(
            worker.split()[0] for _, worker in self.config.items('workers')
        )

    @safe
    def get_paths(self):
        data_path = self.config.get('storage', 'data')
        index_path = self.config.get('storage', 'index')
        return data_path, index_path

    @safe
    def get_rest_credentials(self):
        return self.config.get('credentials', 'rest').split(':')

    @safe
    def get_ssh_credentials(self):
        return self.config.get('credentials', 'ssh').split(':')

    def get_parameters(self):
        return self._get_options_as_dict('parameters')


class TestConfig(Config):

    @safe
    def get_test_module(self):
        return self.config.get('test_case', 'module')

    @safe
    def get_test_class(self):
        return self.config.get('test_case', 'class')

    @safe
    def get_test_descr(self):
        return self.config.get('test_case', 'descr')

    def get_regression_criterion(self):
        return self.config.get('test_case', 'larger_is_better')

    @safe
    def get_mem_quota(self):
        return self.config.getint('cluster', 'mem_quota')

    @safe
    def get_initial_nodes(self):
        return self.config.getint('cluster', 'initial_nodes')

    @safe
    def get_num_buckets(self):
        return self.config.getint('cluster', 'num_buckets')

    @safe
    def get_mrw_threads_number(self):
        return self.config.getint('cluster', 'threads_number')

    def get_buckets(self):
        for i in xrange(self.get_num_buckets()):
            yield 'bucket-{0}'.format(i + 1)

    def get_compaction_settings(self):
        options = self._get_options_as_dict('compaction')
        return CompactionSettings(options)

    def get_load_settings(self):
        options = self._get_options_as_dict('load')
        return LoadSettings(options)

    def get_hot_load_settings(self):
        options = self._get_options_as_dict('hot_load')
        return HotLoadSettings(options)

    def get_xdcr_settings(self):
        options = self._get_options_as_dict('xdcr')
        return XDCRSettings(options)

    def get_index_settings(self):
        options = self._get_options_as_dict('index')
        return IndexSettings(options)

    def get_access_settings(self):
        options = self._get_options_as_dict('access')
        return AccessSettings(options)

    def get_rebalance_settings(self):
        options = self._get_options_as_dict('rebalance')
        return RebalanceSettings(options)


class CompactionSettings(object):

    DB_PERCENTAGE = 30
    VIEW_PERCENTAGE = 30
    PARALLEL = False

    def __init__(self, options):
        self.db_percentage = options.get('db_percentage', self.DB_PERCENTAGE)
        self.view_percentage = options.get('view_percentage', self.VIEW_PERCENTAGE)
        self.parallel = options.get('parallel', self.PARALLEL)

    def __str__(self):
        return str(self.__dict__)


class TargetSettings(object):

    def __init__(self, host_port, bucket, username, password, prefix):
        self.username = username
        self.password = password
        self.node = host_port
        self.bucket = bucket
        self.prefix = prefix


class RebalanceSettings(object):

    NODES_AFTER = 4
    START_AFTER = 1200
    STOP_AFTER = 1200

    def __init__(self, options):
        self.nodes_after = int(options.get('nodes_after', self.NODES_AFTER))
        self.start_after = int(options.get('start_after', self.START_AFTER))
        self.stop_after = int(options.get('stop_after', self.STOP_AFTER))


class PhaseSettings(object):

    CREATES = 0
    READS = 0
    UPDATES = 0
    DELETES = 0
    OPS = 0
    THROUGHPUT = float('inf')

    ITEMS = 0
    SIZE = 2048
    EXPIRATION = 0
    WORKING_SET = 100
    WORKING_SET_ACCESS = 100

    WORKERS = 12

    SEQ_READS = False

    def __init__(self, options):
        self.creates = int(options.get('creates', self.CREATES))
        self.reads = int(options.get('reads', self.READS))
        self.updates = int(options.get('updates', self.UPDATES))
        self.deletes = int(options.get('deletes', self.DELETES))
        self.ops = int(options.get('ops', self.OPS))
        self.throughput = float(options.get('throughput', self.THROUGHPUT))

        self.size = int(options.get('size', self.SIZE))
        self.items = int(options.get('items', self.ITEMS))
        self.expiration = int(options.get('expiration', self.EXPIRATION))
        self.working_set = int(options.get('working_set', self.WORKING_SET))
        self.working_set_access = int(options.get('working_set_access',
                                                  self.WORKING_SET_ACCESS))

        self.workers = int(options.get('workers', self.WORKERS))

        self.seq_reads = self.SEQ_READS

    def __str__(self):
        return str(self.__dict__)


class LoadSettings(PhaseSettings):

    CREATES = 100


class HotLoadSettings(PhaseSettings):

    SEQ_READS = True


class XDCRSettings(PhaseSettings):

    XDCR_REPLICATION_TYPE = 'bidir'

    def __init__(self, options):
        self.replication_type = options.get('replication_type',
                                            self.XDCR_REPLICATION_TYPE)


class IndexSettings(PhaseSettings):

    VIEWS = [1]
    DISABLED_UPDATES = False

    def __init__(self, options):
        self.views = eval(options.get('views', self.VIEWS))
        self.disabled_updates = bool(options.get('disabled_updates',
                                                 self.DISABLED_UPDATES))


class AccessSettings(PhaseSettings):

    READS = 100
