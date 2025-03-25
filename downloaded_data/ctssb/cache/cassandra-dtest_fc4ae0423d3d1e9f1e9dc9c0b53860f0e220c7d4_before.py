import Queue
import sys
import threading
import time
import traceback
from collections import OrderedDict
from copy import deepcopy

from cassandra import ConsistencyLevel
from cassandra.query import SimpleStatement

from assertions import assert_none, assert_unavailable
from dtest import DISABLE_VNODES, Tester, debug
from tools import (create_c1c2_table, insert_c1c2, insert_columns, query_c1c2,
                   rows_to_list)


class TestHelper(Tester):

    def __init__(self, *args, **kwargs):
        Tester.__init__(self, *args, **kwargs)
        self.lock = threading.Lock()

    def log(self, message):
        with self.lock:
            debug(message)

    def _name(self, cl):
        return {
            None: '-',
            ConsistencyLevel.ANY: 'ANY',
            ConsistencyLevel.ONE: 'ONE',
            ConsistencyLevel.TWO: 'TWO',
            ConsistencyLevel.THREE: 'THREE',
            ConsistencyLevel.QUORUM: 'QUORUM',
            ConsistencyLevel.ALL: 'ALL',
            ConsistencyLevel.LOCAL_QUORUM: 'LOCAL_QUORUM',
            ConsistencyLevel.EACH_QUORUM: 'EACH_QUORUM',
            ConsistencyLevel.SERIAL: 'SERIAL',
            ConsistencyLevel.LOCAL_SERIAL: 'LOCAL_SERIAL',
            ConsistencyLevel.LOCAL_ONE: 'LOCAL_ONE',
        }[cl]

    def _is_local(self, cl):
        return (cl == ConsistencyLevel.LOCAL_QUORUM or
                cl == ConsistencyLevel.LOCAL_ONE or
                cl == ConsistencyLevel.LOCAL_SERIAL)

    def _is_conditional(self, cl):
        return (cl == ConsistencyLevel.SERIAL or
                cl == ConsistencyLevel.LOCAL_SERIAL)

    def _required_nodes(self, cl, rf_factors, dc):
        """
        Return the number of nodes required by this consistency level
        in the current data center, specified by the dc parameter,
        given a list of replication factors, one per dc.
        """
        return {
            ConsistencyLevel.ANY: 1,
            ConsistencyLevel.ONE: 1,
            ConsistencyLevel.TWO: 2,
            ConsistencyLevel.THREE: 3,
            ConsistencyLevel.QUORUM: sum(rf_factors) / 2 + 1,
            ConsistencyLevel.ALL: sum(rf_factors),
            ConsistencyLevel.LOCAL_QUORUM: rf_factors[dc] / 2 + 1,
            ConsistencyLevel.EACH_QUORUM: rf_factors[dc] / 2 + 1,
            ConsistencyLevel.SERIAL: sum(rf_factors) / 2 + 1,
            ConsistencyLevel.LOCAL_SERIAL: rf_factors[dc] / 2 + 1,
            ConsistencyLevel.LOCAL_ONE: 1,
        }[cl]

    def _should_succeed(self, cl, rf_factors, num_nodes_alive, current):
        """
        Return true if the read or write operation should succeed based on
        the consistency level requested, the replication factors and the
        number of nodes alive in each data center.
        """
        if self._is_local(cl):
            return num_nodes_alive[current] >= self._required_nodes(cl, rf_factors, current)
        elif cl == ConsistencyLevel.EACH_QUORUM:
            for i in xrange(0, len(rf_factors)):
                if num_nodes_alive[i] < self._required_nodes(cl, rf_factors, i):
                    return False
            return True
        else:
            return sum(num_nodes_alive) >= self._required_nodes(cl, rf_factors, current)

    def _start_cluster(self, save_sessions=False):
        cluster = self.cluster
        nodes = self.nodes
        rf = self.rf

        cluster.set_configuration_options(values={'hinted_handoff_enabled': False})
        cluster.populate(nodes).start(wait_for_binary_proto=True, wait_other_notice=True)

        self.ksname = 'mytestks'
        session = self.patient_exclusive_cql_connection(cluster.nodelist()[0])

        self.create_ks(session, self.ksname, rf)
        self.create_tables(session)

        if save_sessions:
            self.sessions = []
            self.sessions.append(session)
            for node in cluster.nodelist()[1:]:
                self.sessions.append(self.patient_exclusive_cql_connection(node, self.ksname))

    def create_tables(self, session):
        self.create_users_table(session)
        self.create_counters_table(session)

    def truncate_tables(self, session):
        statement = SimpleStatement("TRUNCATE users", ConsistencyLevel.ALL)
        session.execute(statement)
        statement = SimpleStatement("TRUNCATE counters", ConsistencyLevel.ALL)
        session.execute(statement)

    def create_users_table(self, session):
        session.execute("""CREATE TABLE users (
                userid int PRIMARY KEY,
                firstname text,
                lastname text,
                age int
            ) WITH COMPACT STORAGE""")

    def insert_user(self, session, userid, age, consistency, serial_consistency=None):
        text = "INSERT INTO users (userid, firstname, lastname, age) VALUES (%d, 'first%d', 'last%d', %d) %s" \
            % (userid, userid, userid, age, "IF NOT EXISTS" if serial_consistency else "")
        statement = SimpleStatement(text, consistency_level=consistency, serial_consistency_level=serial_consistency)
        session.execute(statement)

    def update_user(self, session, userid, age, consistency, serial_consistency=None, prev_age=None):
        text = "UPDATE users SET age = %d WHERE userid = %d" % (age, userid)
        if serial_consistency and prev_age:
            text = text + " IF age = %d" % (prev_age)
        statement = SimpleStatement(text, consistency_level=consistency, serial_consistency_level=serial_consistency)
        session.execute(statement)

    def delete_user(self, session, userid, consistency):
        statement = SimpleStatement("DELETE FROM users where userid = %d" % (userid,), consistency_level=consistency)
        session.execute(statement)

    def query_user(self, session, userid, age, consistency, check_ret=True):
        statement = SimpleStatement("SELECT userid, age FROM users where userid = %d" % (userid,), consistency_level=consistency)
        res = session.execute(statement)
        expected = [[userid, age]] if age else []
        ret = rows_to_list(res) == expected
        if check_ret:
            assert ret, "Got %s from %s, expected %s at %s" % (res, session.cluster.contact_points, expected, self._name(consistency))
        return ret

    def create_counters_table(self, session):
        session.execute("""
            CREATE TABLE counters (
                id int PRIMARY KEY,
                c counter
            )
        """)

    def update_counter(self, session, id, consistency, serial_consistency=None):
        text = "UPDATE counters SET c = c + 1 WHERE id = %d" % (id,)
        statement = SimpleStatement(text, consistency_level=consistency, serial_consistency_level=serial_consistency)
        session.execute(statement)
        return statement

    def query_counter(self, session, id, val, consistency, check_ret=True):
        statement = SimpleStatement("SELECT * from counters WHERE id = %d" % (id,), consistency_level=consistency)
        res = session.execute(statement)
        expected = [[id, val]] if val else []
        ret = rows_to_list(res) == expected
        if check_ret:
            assert ret, "Got %s from %s, expected %s at %s" % (res, session.cluster.contact_points, expected, self._name(consistency))
        return ret

    def read_counter(self, session, id, consistency):
        """
        Return the current counter value. If we find no value we return zero
        because after the next update the counter will become one.
        """
        statement = SimpleStatement("SELECT c from counters WHERE id = %d" % (id,), consistency_level=consistency)
        res = rows_to_list(session.execute(statement))
        return res[0][0] if res else 0


class TestAvailability(TestHelper):
    """
    Test that we can read and write depending on the number of nodes that are alive and the consistency levels.
    """
    def _test_simple_strategy(self, combinations):
        """
        Helper test function for a single data center: invoke _test_insert_query_from_node() for each node
        and each combination, progressively stopping nodes.
        """
        cluster = self.cluster
        nodes = self.nodes
        rf = self.rf

        num_alive = nodes
        for node in xrange(nodes):
            debug('Testing node %d in single dc with %d nodes alive' % (node, num_alive,))
            session = self.patient_exclusive_cql_connection(cluster.nodelist()[node], self.ksname)
            for combination in combinations:
                self._test_insert_query_from_node(session, 0, [rf], [num_alive], *combination)

            self.cluster.nodelist()[node].stop()
            num_alive = num_alive - 1

    def _test_network_topology_strategy(self, combinations):
        """
        Helper test function for multiple data centers, invoke _test_insert_query_from_node() for each node
        in each dc and each combination, progressively stopping nodes.
        """
        cluster = self.cluster
        nodes = self.nodes
        rf = self.rf

        nodes_alive = deepcopy(nodes)
        rf_factors = rf.values()

        for i in xrange(0, len(nodes)):  # for each dc
            self.log('Testing dc %d with rf %d and %s nodes alive' % (i, rf_factors[i], nodes_alive))
            for n in xrange(nodes[i]):  # for each node in this dc
                self.log('Testing node %d in dc %d with %s nodes alive' % (n, i, nodes_alive))
                node = n + sum(nodes[:i])
                session = self.patient_exclusive_cql_connection(cluster.nodelist()[node], self.ksname)
                for combination in combinations:
                    self._test_insert_query_from_node(session, i, rf_factors, nodes_alive, *combination)

                self.cluster.nodelist()[node].stop(wait_other_notice=True)
                nodes_alive[i] = nodes_alive[i] - 1

    def _test_insert_query_from_node(self, session, dc_idx, rf_factors, num_nodes_alive, write_cl, read_cl, serial_cl=None, check_ret=True):
        """
        Test availability for read and write via the session passed in as a prameter.
        """
        cluster = self.cluster

        self.log("Connected to %s for %s/%s/%s" %
            (session.cluster.contact_points, self._name(write_cl), self._name(read_cl), self._name(serial_cl)))

        start = 0
        end = 100
        age = 30

        if self._should_succeed(write_cl, rf_factors, num_nodes_alive, dc_idx):
            for n in xrange(start, end):
                self.insert_user(session, n, age, write_cl, serial_cl)
        else:
            assert_unavailable(self.insert_user, session, end, age, write_cl, serial_cl)

        if self._should_succeed(read_cl, rf_factors, num_nodes_alive, dc_idx):
            for n in xrange(start, end):
                self.query_user(session, n, age, read_cl, check_ret)
        else:
            assert_unavailable(self.query_user, session, end, age, read_cl, check_ret)

    def test_simple_strategy(self):
        """
        Test for a single datacenter, using simple replication strategy.
        """
        self.nodes = 3
        self.rf = 3

        self._start_cluster()

        combinations = [
            (ConsistencyLevel.ALL, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.EACH_QUORUM, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.ONE, ConsistencyLevel.ONE, None, False),
            (ConsistencyLevel.ONE, ConsistencyLevel.ALL),
            (ConsistencyLevel.ALL, ConsistencyLevel.ONE),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.TWO),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.THREE),
            (ConsistencyLevel.TWO, ConsistencyLevel.TWO),
            (ConsistencyLevel.THREE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ANY, ConsistencyLevel.ONE, None, False),
            (ConsistencyLevel.LOCAL_ONE, ConsistencyLevel.LOCAL_ONE, None, False),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.LOCAL_SERIAL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.LOCAL_SERIAL),
        ]

        self._test_simple_strategy(combinations)

    def test_network_topology_strategy(self):
        """
        Test for multiple datacenters, using network topology replication strategy.
        """
        self.nodes = [3, 3, 3]
        self.rf = OrderedDict([('dc1', 3), ('dc2', 3), ('dc3', 3)])

        self._start_cluster()

        combinations = [
            (ConsistencyLevel.ALL, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.EACH_QUORUM, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.ONE, ConsistencyLevel.ONE, None, False),
            (ConsistencyLevel.ONE, ConsistencyLevel.ALL),
            (ConsistencyLevel.ALL, ConsistencyLevel.ONE),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.TWO),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.THREE),
            (ConsistencyLevel.TWO, ConsistencyLevel.TWO),
            (ConsistencyLevel.THREE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ANY, ConsistencyLevel.ONE, None, False),
            (ConsistencyLevel.LOCAL_ONE, ConsistencyLevel.LOCAL_ONE, None, False),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.LOCAL_SERIAL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.LOCAL_SERIAL),
        ]

        self._test_network_topology_strategy(combinations)


class TestAccuracy(TestHelper):
    """
    Test that we can consistently read back what we wrote depending on the write and read consitency levels.
    """

    class Validation:
        def __init__(self, outer, sessions, nodes, rf_factors, start, end, write_cl, read_cl, serial_cl=None):
            self.outer = outer
            self.sessions = sessions
            self.nodes = nodes
            self.rf_factors = rf_factors
            self.start = start
            self.end = end
            self.write_cl = write_cl
            self.read_cl = read_cl
            self.serial_cl = serial_cl

            outer.log('Testing accuracy for %s/%s/%s (keys : %d to %d)'
            % (outer._name(write_cl), outer._name(read_cl), outer._name(serial_cl), start, end))

        def get_num_nodes(self, idx):
            """
            Given a node index, identify to which data center we are connecting and return
            number of nodes we write to, read from and whether R + W > N
            """
            outer = self.outer
            nodes = self.nodes
            rf_factors = self.rf_factors
            write_cl = self.write_cl
            read_cl = self.read_cl

            dc = 0
            for i in xrange(1, len(nodes)):
                if idx < sum(nodes[:i]):
                    break
                dc = dc + 1

            if write_cl == ConsistencyLevel.EACH_QUORUM:
                write_nodes = sum([outer._required_nodes(write_cl, rf_factors, i) for i in range(0, len(nodes))])
            else:
                write_nodes = outer._required_nodes(write_cl, rf_factors, dc)

            read_nodes = outer._required_nodes(read_cl, rf_factors, dc)
            strong_consistency = read_nodes + write_nodes > sum(rf_factors)

            return write_nodes, read_nodes, strong_consistency

        def validate_users(self):
            """
            First validation function: update the users table sending different values to different sessions
            and check that when strong_consistency is true (R + W > N) we read back the latest value from all sessions.
            If strong_consistency is false we instead check that we read back the latest value from at least
            the number of nodes we wrote to.
            """
            outer = self.outer
            sessions = self.sessions
            start = self.start
            end = self.end
            write_cl = self.write_cl
            read_cl = self.read_cl
            serial_cl = self.serial_cl

            def check_all_sessions(idx, n, val):
                write_nodes, read_nodes, strong_consistency = self.get_num_nodes(idx)
                num = 0
                for s in sessions:
                    if outer.query_user(s, n, val, read_cl, check_ret=strong_consistency):
                        num = num + 1
                assert num >= write_nodes, \
                "Failed to read value from sufficient number of nodes, required %d but  got %d - [%d, %s]" \
                % (write_nodes, num, n, val)

            for n in xrange(start, end):
                age = 30
                for s in range(0, len(sessions)):
                    outer.insert_user(sessions[s], n, age, write_cl, serial_cl)
                    check_all_sessions(s, n, age)
                    if serial_cl is None:
                        age = age + 1
                for s in range(0, len(sessions)):
                    outer.update_user(sessions[s], n, age, write_cl, serial_cl, age - 1)
                    check_all_sessions(s, n, age)
                    age = age + 1
                outer.delete_user(sessions[0], n, write_cl)
                check_all_sessions(s, n, None)

        def validate_counters(self):
            """
            Second validation function: update the counters table sending different values to different sessions
            and check that when strong_consistency is true (R + W > N) we read back the latest value from all sessions.
            If strong_consistency is false we instead check that we read back the latest value from at least
            the number of nodes we wrote to.
            """
            outer = self.outer
            sessions = self.sessions
            start = self.start
            end = self.end
            write_cl = self.write_cl
            read_cl = self.read_cl
            serial_cl = self.serial_cl

            def check_all_sessions(idx, n, val):
                write_nodes, read_nodes, strong_consistency = self.get_num_nodes(idx)
                num = 0
                for s in sessions:
                    if outer.query_counter(s, n, val, read_cl, check_ret=strong_consistency):
                        num = num + 1
                assert num >= write_nodes, \
                "Failed to read value from sufficient number of nodes, required %d but got %d - [%d, %s]" \
                % (write_nodes, num, n, val)

            for n in xrange(start, end):
                c = outer.read_counter(sessions[0], n, ConsistencyLevel.ALL)
                for s in range(0, len(sessions)):
                    c = c + 1
                    outer.update_counter(sessions[s], n, write_cl, serial_cl)
                    check_all_sessions(s, n, c)

    def _run_test_function_in_parallel(self, valid_fcn, nodes, rf_factors, combinations):
        """
        Run a test function in parallel.
        """
        self._start_cluster(save_sessions=True)

        input_queue = Queue.Queue()
        exceptions_queue = Queue.Queue()

        def run():
            while not input_queue.empty():
                try:
                    v = TestAccuracy.Validation(self, self.sessions, nodes, rf_factors, *input_queue.get(block=False))
                    valid_fcn(v)
                except Queue.Empty:
                    pass
                except:
                    exceptions_queue.put(sys.exc_info())

        start = 0
        num_keys = 50
        for combination in combinations:
            input_queue.put((start, start + num_keys) + combination)
            start = start + num_keys

        threads = []
        for n in range(0, 8):
            t = threading.Thread(target=run)
            t.setDaemon(True)
            t.start()
            threads.append(t)

        self.log("Waiting for workers to complete")
        while exceptions_queue.empty():
            time.sleep(0.1)
            if len(filter(lambda t: t.isAlive(), threads)) == 0:
                break

        if not exceptions_queue.empty():
            traceback.print_exception(*exceptions_queue.get())
            assert False, "Look for an exception above"

    def test_simple_strategy_users(self):
        """
        Test for a single datacenter, users table.
        """
        self.nodes = 5
        self.rf = 3

        combinations = [
            (ConsistencyLevel.ALL, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.ALL, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.TWO, ConsistencyLevel.TWO),
            (ConsistencyLevel.ONE, ConsistencyLevel.THREE),
            (ConsistencyLevel.THREE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ANY, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.TWO),
            (ConsistencyLevel.TWO, ConsistencyLevel.ONE),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.SERIAL),
        ]

        self.log("Testing single dc, users")
        self._run_test_function_in_parallel(TestAccuracy.Validation.validate_users, [self.nodes], [self.rf], combinations)

    def test_network_topology_strategy_users(self):
        """
        Test for multiple datacenters, users table.
        """
        self.nodes = [3, 3]
        self.rf = OrderedDict([('dc1', 3), ('dc2', 3)])

        combinations = [
            (ConsistencyLevel.ALL, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.ALL, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.EACH_QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.TWO, ConsistencyLevel.TWO),
            (ConsistencyLevel.ONE, ConsistencyLevel.THREE),
            (ConsistencyLevel.THREE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ANY, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.TWO),
            (ConsistencyLevel.TWO, ConsistencyLevel.ONE),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.LOCAL_SERIAL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.LOCAL_SERIAL, ConsistencyLevel.SERIAL),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.SERIAL, ConsistencyLevel.LOCAL_SERIAL),
        ]

        self.log("Testing multiple dcs, users")
        self._run_test_function_in_parallel(TestAccuracy.Validation.validate_users, self.nodes, self.rf.values(), combinations),

    def test_simple_strategy_counters(self):
        """
        Test for a single datacenter, counters table.
        """
        self.nodes = 3
        self.rf = 3

        combinations = [
            (ConsistencyLevel.ALL, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.ALL, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.TWO, ConsistencyLevel.TWO),
            (ConsistencyLevel.ONE, ConsistencyLevel.THREE),
            (ConsistencyLevel.THREE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.TWO),
            (ConsistencyLevel.TWO, ConsistencyLevel.ONE),
        ]

        self.log("Testing single dc, counters")
        self._run_test_function_in_parallel(TestAccuracy.Validation.validate_counters, [self.nodes], [self.rf], combinations)

    def test_network_topology_strategy_counters(self):
        """
        Test for multiple datacenters, counters table.
        """
        self.nodes = [3, 3]
        self.rf = OrderedDict([('dc1', 3), ('dc2', 3)])

        combinations = [
            (ConsistencyLevel.ALL, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.ALL, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ALL),
            (ConsistencyLevel.QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.QUORUM),
            (ConsistencyLevel.LOCAL_QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.LOCAL_QUORUM),
            (ConsistencyLevel.EACH_QUORUM, ConsistencyLevel.ONE),
            (ConsistencyLevel.TWO, ConsistencyLevel.TWO),
            (ConsistencyLevel.ONE, ConsistencyLevel.THREE),
            (ConsistencyLevel.THREE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.ONE),
            (ConsistencyLevel.ONE, ConsistencyLevel.TWO),
            (ConsistencyLevel.TWO, ConsistencyLevel.ONE),
        ]

        self.log("Testing multiple dcs, counters")
        self._run_test_function_in_parallel(TestAccuracy.Validation.validate_counters, self.nodes, self.rf.values(), combinations),


class TestConsistency(Tester):

    def short_read_test(self):
        cluster = self.cluster

        # Disable hinted handoff and set batch commit log so this doesn't
        # interfer with the test
        cluster.set_configuration_options(values={'hinted_handoff_enabled': False}, batch_commitlog=True)

        cluster.populate(3).start(wait_other_notice=True)
        node1, node2, node3 = cluster.nodelist()

        session = self.patient_cql_connection(node1)
        self.create_ks(session, 'ks', 3)
        self.create_cf(session, 'cf', read_repair=0.0)

        # Repeat this test 10 times to make it more easy to spot a null pointer exception caused by a race, see CASSANDRA-9460
        for k in xrange(10):
            # insert 9 columns in one row
            insert_columns(self, session, 0, 9)

            # Deleting 3 first columns with a different node dead each time
            self.stop_delete_and_restart(1, 0)
            self.stop_delete_and_restart(2, 1)
            self.stop_delete_and_restart(3, 2)

            # Query 3 firsts columns
            session = self.patient_cql_connection(node1, 'ks')
            query = SimpleStatement('SELECT c, v FROM cf WHERE key=\'k0\' LIMIT 3', consistency_level=ConsistencyLevel.QUORUM)
            rows = session.execute(query)
            res = rows
            assert len(res) == 3, 'Expecting 3 values, got %d (%s)' % (len(res), str(res))
            # value 0, 1 and 2 have been deleted
            for i in xrange(1, 4):
                assert res[i-1][1] == 'value%d' % (i+2), 'Expecting value%d, got %s (%s)' % (i+2, res[i-1][1], str(res))

            truncate_statement = SimpleStatement('TRUNCATE cf', consistency_level=ConsistencyLevel.QUORUM)
            session.execute(truncate_statement)

    def short_read_delete_test(self):
        """ Test short reads ultimately leaving no columns alive [#4000] """
        cluster = self.cluster

        # Disable hinted handoff and set batch commit log so this doesn't
        # interfer with the test
        cluster.set_configuration_options(values={'hinted_handoff_enabled': False}, batch_commitlog=True)

        cluster.populate(2).start(wait_other_notice=True)
        node1, node2 = cluster.nodelist()

        session = self.patient_cql_connection(node1)
        self.create_ks(session, 'ks', 3)
        self.create_cf(session, 'cf', read_repair=0.0)
        # insert 2 columns in one row
        insert_columns(self, session, 0, 2)

        # Delete the row while first node is dead
        node1.flush()
        node1.stop(wait_other_notice=True)
        session = self.patient_cql_connection(node2, 'ks')

        query = SimpleStatement('DELETE FROM cf WHERE key=\'k0\'', consistency_level=ConsistencyLevel.ONE)
        session.execute(query)

        node1.start(wait_other_notice=True)

        # Query first column
        session = self.patient_cql_connection(node1, 'ks')

        query = SimpleStatement('SELECT c, v FROM cf WHERE key=\'k0\' LIMIT 1', consistency_level=ConsistencyLevel.QUORUM)
        res = session.execute(query)
        assert len(res) == 0, res

    def short_read_quorum_delete_test(self):
        """Test CASSANDRA-8933"""
        cluster = self.cluster
        # Consider however 3 nodes A, B, C (RF=3), and following sequence of operations (all done at QUORUM):

        # Disable hinted handoff and set batch commit log so this doesn't
        # interfere with the test
        cluster.set_configuration_options(values={'hinted_handoff_enabled': False}, batch_commitlog=True)

        cluster.populate(3).start(wait_other_notice=True)
        node1, node2, node3 = cluster.nodelist()

        session = self.patient_cql_connection(node1)
        self.create_ks(session, 'ks', 3)

        session.execute("CREATE TABLE t (id int, v int, PRIMARY KEY(id, v)) WITH read_repair_chance = 0.0")
        # we write 1 and 2 in a partition: all nodes get it.
        session.execute(SimpleStatement("INSERT INTO t (id, v) VALUES (0, 1)", consistency_level=ConsistencyLevel.ALL))
        session.execute(SimpleStatement("INSERT INTO t (id, v) VALUES (0, 2)", consistency_level=ConsistencyLevel.ALL))

        # we delete 1: only A and C get it.
        node2.flush()
        node2.stop(wait_other_notice=True)
        session.execute(SimpleStatement("DELETE FROM t WHERE id = 0 AND v = 1", consistency_level=ConsistencyLevel.QUORUM))
        node2.start(wait_other_notice=True)

        # we delete 2: only B and C get it.
        node1.flush()
        node1.stop(wait_other_notice=True)
        session = self.patient_cql_connection(node2, 'ks')
        session.execute(SimpleStatement("DELETE FROM t WHERE id = 0 AND v = 2", consistency_level=ConsistencyLevel.QUORUM))
        node1.start(wait_other_notice=True)
        session = self.patient_cql_connection(node1, 'ks')

        # we read the first row in the partition (so with a LIMIT 1) and A and B answer first.
        node3.flush()
        node3.stop(wait_other_notice=True)
        assert_none(session, "SELECT * FROM t WHERE id = 0 LIMIT 1", cl=ConsistencyLevel.QUORUM)

    def readrepair_test(self):
        cluster = self.cluster
        cluster.set_configuration_options(values={'hinted_handoff_enabled': False})

        if DISABLE_VNODES:
            cluster.populate(2).start()
        else:
            tokens = cluster.balanced_tokens(2)
            cluster.populate(2, tokens=tokens).start()
        node1, node2 = cluster.nodelist()

        session = self.patient_cql_connection(node1)
        self.create_ks(session, 'ks', 2)
        create_c1c2_table(self, session, read_repair=1.0)

        node2.stop(wait_other_notice=True)

        insert_c1c2(session, n=10000, consistency=ConsistencyLevel.ONE)

        node2.start(wait_other_notice=True)

        # query everything to cause RR
        for n in xrange(0, 10000):
            query_c1c2(session, n, ConsistencyLevel.QUORUM)

        node1.stop(wait_other_notice=True)

        # Check node2 for all the keys that should have been repaired
        session = self.patient_cql_connection(node2, keyspace='ks')
        for n in xrange(0, 10000):
            query_c1c2(session, n, ConsistencyLevel.ONE)

    def short_read_reversed_test(self):
        cluster = self.cluster

        # Disable hinted handoff and set batch commit log so this doesn't
        # interfere with the test
        cluster.set_configuration_options(values={'hinted_handoff_enabled': False}, batch_commitlog=True)

        cluster.populate(3).start(wait_other_notice=True)
        node1, node2, node3 = cluster.nodelist()

        session = self.patient_cql_connection(node1)
        self.create_ks(session, 'ks', 3)
        self.create_cf(session, 'cf', read_repair=0.0)

        # Repeat this test 10 times to make it more easy to spot a null pointer exception caused by a race, see CASSANDRA-9460
        for k in xrange(10):
            # insert 9 columns in one row
            insert_columns(self, session, 0, 9)

            # Deleting 3 last columns with a different node dead each time
            self.stop_delete_and_restart(1, 6)
            self.stop_delete_and_restart(2, 7)
            self.stop_delete_and_restart(3, 8)

            # Query 3 firsts columns
            session = self.patient_cql_connection(node1, 'ks')
            query = SimpleStatement('SELECT c, v FROM cf WHERE key=\'k0\' ORDER BY c DESC LIMIT 3', consistency_level=ConsistencyLevel.QUORUM)
            rows = session.execute(query)
            res = rows
            assert len(res) == 3, 'Expecting 3 values, got %d (%s)' % (len(res), str(res))
            # value 6, 7 and 8 have been deleted
            for i in xrange(0, 3):
                assert res[i][1] == 'value%d' % (5-i), 'Expecting value%d, got %s (%s)' % (5-i, res[i][1], str(res))

            truncate_statement = SimpleStatement('TRUNCATE cf', consistency_level=ConsistencyLevel.QUORUM)
            session.execute(truncate_statement)

    def quorum_available_during_failure_test(self):
        CL = ConsistencyLevel.QUORUM
        RF = 3

        debug("Creating a ring")
        cluster = self.cluster
        if DISABLE_VNODES:
            cluster.populate(3).start()
        else:
            tokens = cluster.balanced_tokens(3)
            cluster.populate(3, tokens=tokens).start()
        node1, node2, node3 = cluster.nodelist()
        cluster.start()

        debug("Set to talk to node 2")
        session = self.patient_cql_connection(node2)
        self.create_ks(session, 'ks', RF)
        create_c1c2_table(self, session)

        debug("Generating some data")
        insert_c1c2(session, n=100, consistency=CL)

        debug("Taking down node1")
        node1.stop(wait_other_notice=True)

        debug("Reading back data.")
        for n in xrange(100):
            query_c1c2(session, n, CL)

    def stop_delete_and_restart(self, node_number, column):
        to_stop = self.cluster.nodes["node%d" % node_number]
        next_node = self.cluster.nodes["node%d" % (((node_number + 1) % 3) + 1)]
        to_stop.flush()
        to_stop.stop(wait_other_notice=True)
        session = self.patient_cql_connection(next_node, 'ks')
        query = 'BEGIN BATCH '
        query = query + 'DELETE FROM cf WHERE key=\'k0\' AND c=\'c%06d\'; ' % column
        query = query + 'DELETE FROM cf WHERE key=\'k0\' AND c=\'c2\'; '
        query = query + 'APPLY BATCH;'
        simple_query = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM)
        session.execute(simple_query)

        to_stop.start(wait_other_notice=True)
