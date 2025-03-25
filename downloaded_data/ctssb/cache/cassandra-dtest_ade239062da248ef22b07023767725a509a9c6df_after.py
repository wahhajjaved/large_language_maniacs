import random, time
from dtest import Tester, debug
from tools import *
from assertions import *
from ccmlib.cluster import Cluster


class TestBootstrap(Tester):

    def __init__(self, *args, **kwargs):
        # Ignore these log patterns:
        self.ignore_log_patterns = [
            # This one occurs when trying to send the migration to a
            # node that hasn't started yet, and when it does, it gets
            # replayed and everything is fine.
            r'Can\'t send migration request: node.*is down',
        ]
        Tester.__init__(self, *args, **kwargs)

    def simple_bootstrap_test(self):
        cluster = self.cluster
        tokens = cluster.balanced_tokens(2)

        keys = 10000

        # Create a single node cluster
        cluster.populate(1, tokens=[tokens[0]]).start()
        node1 = cluster.nodes["node1"]

        time.sleep(.5)
        cursor = self.cql_connection(node1).cursor()
        self.create_ks(cursor, 'ks', 1)
        self.create_cf(cursor, 'cf', columns={ 'c1' : 'text', 'c2' : 'text' })

        for n in xrange(0, keys):
            insert_c1c2(cursor, n, "ONE")

        node1.flush()
        initial_size = node1.data_size()

        # Reads inserted data all during the boostrap process. We shouldn't
        # get any error
        reader = self.go(lambda _: query_c1c2(cursor, random.randint(0, keys-1), "ONE"))

        # Boostraping a new node
        node2 = new_node(cluster, token=tokens[1])
        node2.start()
        time.sleep(.5)

        reader.check()
        node1.cleanup()
        time.sleep(.5)
        reader.check()

        size1 = node1.data_size()
        size2 = node2.data_size()
        assert_almost_equal(size1, size2, error=0.3)
        assert_almost_equal(initial_size, 2 * size1)

    def read_from_bootstrapped_node_test(self):
        """Test bootstrapped node sees existing data, eg. CASSANDRA-6648"""
        cluster = self.cluster
        cluster.populate(3)
        version = cluster.version()
        cluster.start()
        
        node1 = cluster.nodes['node1']
        if version < "2.1":
            node1.stress(['-n', '10000'])
        else:
            node1.stress(['write', 'n=10000', '-rate', 'threads=8'])
        
        node4 = new_node(cluster)
        node4.start()

        cursor = self.patient_cql_connection(node4).cursor()
        cursor.execute('select * from "Keyspace1"."Standard1" limit 10')
        assert len(list(cursor)) == 10
