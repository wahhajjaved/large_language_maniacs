"""Classes and functions useful for parsing and representing collections
of BroRecords as a DAG, with each node's successor being the page that
lead to a given page, and its children being the pages visted next."""

import networkx as nx
import logging
import re
from .records import bro_records
from .chains import BroRecordChain

try:
    import cPickle as pickle
except ImportError:
    import pickle

FILE_TS_PATTERN = re.compile('[0-9]{10}')
def _timestamp_for_filename(filename):
    """Collections of BroRecordGraphs are are saved with filenames like
    http-requests.1388592000.log.pickles, which refer to the lower bound of the
    request time of the earliest BroRecord contained in the graph.

    This function returns the earliest possible time that a BroRecord
    was sent in the collection of graphs in the given file.

    Args:
        filename -- A filename, as a string in a format, such as
                    http-requests.1388592000.log.pickles

    Return:
        None if no date could be returned, otherwise an integer unix timestamp
    """
    match = FILE_TS_PATTERN.search(filename)
    if not match:
        return None
    return int(match.group())

def _graphs_from_file(filename):
    """Creates an iterator that returns completed graphs that are read out
    of the given filename.

    Args:
        filename -- a filename, or filepath, to a file on disk containing
                    pickled graphs
    """
    log = logging.getLogger("brorecords")
    index = 0
    with open(filename, 'r') as h:
        while True:
            try:
                index += 1
                if index % 10000 == 0:
                    log.info(" * Completed graph: {0}".format(index))
                yield pickle.load(h)
            except EOFError:
                break
            except:
                log.info(" * Pickle error, skipping: {0}".format(filename))
                pass

def merge(filelist, time=10):
    """Attempts to merge BroRecordGraph that represent one logical graph /
    browsing session, but where the log divisions cause the single session
    to be split across multiple different graphs.

    Args:
        filelist -- a list of filenames, in the format
                    http-requests.1388592000.log.pickles. This list should be
                    sorted by the timestamps in the filenames

    Keyword Args:
        time  -- the maximum amount of time that can have passed in
                 a browsing session before the graph is closed and yielded
        state -- if set, the iterator also yields back the state of the
                 generator.  Only really useful for debugging

    Return:
        Yields pairs of values.  The first value is a BroRecordGraph, and
        the second value is a boolean description of whether the graph has been
        changed (ie if it has absorbed another graph)
    """
    log = logging.getLogger("brorecords")

    state = {
        # A collection of graphs, keyed by a client specific hash.  Keys
        # are the client hashes, and values are a set of graph, path pairs
        "potential_mergers_by_client": {},
        "graphs_for_client": {},
        # Keep track of which graphs were altered by having child graphs
        # merged into them
        "changed": set()
    }

    log_timestamps = [_timestamp_for_filename(f) for f in filelist]
    log_merge_ranges = [(t - time, t, t + time) for t in log_timestamps]

    def _client_hash(graph):
        return graph.ip + "|" + graph.user_agent

    def _could_be_merger(graph):
        """Checks to see if the given graph could be a graph that should
        receive other child graphs which represent the same logical browsing
        session, but which were stored in a different graph because of how
        the logs are segmented by time.

        Args:
            graph -- a BroRecordGraph object

        Return:
            A boolean description of whether the graph could possibly have
            child graphs in another file.
        """
        latest_ts = graph.latest_ts

        for start, mid, end in log_merge_ranges:
            # If the current range is strictly later than all records in the
            # graph, then it means that all possible range comparisons will
            # be false, so we can stop looking any further
            if start > latest_ts and end > latest_ts:
                return False

            if latest_ts >= start and latest_ts <= mid:
                return True
        return False

    def _yield_back_merger(graph, path):
        try:
            state['changed'].remove(graph)
            is_changed = True
        except KeyError:
            is_changed = False
        return path, graph, is_changed

    def _all_potential_mergers():
        """Returns an iterator for all remaining, potential merger graphs
        still in the collection, to make sure that we return the held over
        graphs even after we've finished considering all the graphs in
        all of the files in the workset.

        Return:
            An iterator that returns pairs of BroRecordGraph objects
            and filepath strings that the graph came from
        """
        for key in state['potential_mergers_by_client']:
            for record in state['potential_mergers_by_client'][key]:
                yield record

    def _add_graph_as_potential_merger(graph, path):
        """Records the given graph and path pair as potential mergers that
        should be checked as possible parents of graphs found in future
        files.

        Args:
            graph -- a BroRecordGraph
            path  -- the file path that this graph was extracted from
        """
        client_key = _client_hash(graph)
        record = (graph, path)
        try:
            state['potential_mergers_by_client'][client_key].add(record)
        except KeyError:
            state['potential_mergers_by_client'][client_key] = set()
            state['potential_mergers_by_client'][client_key].add(record)

    def _parent_merge_graph(graph):
        """Checks to see if the give graph should be merged with a parent
        graph, and if so does the actual merge.

        Args:
            graph -- a BroRecordGraph object

        Return:
            None if the given graph cannot be merged into a parent graph,
            and otherwise the BroRecordGraph object the given graph was
            merged into.
        """
        client_key = _client_hash(graph)
        try:
            client_records = state['potential_mergers_by_client'][client_key]
            for old_graph, old_path in client_records:
                if old_graph.add_graph(graph):
                    state['changed'].add(old_graph)
                    return old_graph
        except KeyError:
            pass
        return None

    def _prune_mergers(graph):
        """Removes potential merger graphs that are too old to still possibly
        be merged with anything.

        Args:
            graph -- a BroRecordGraph object, which must always be the most
                     recent graph (by start date) observed so far

        Return:
            A list of zero or more graphs that were pruned out of the collection
        """
        start = graph.earliest_ts
        client_key = _client_hash(graph)
        removed_graphs = []

        try:
            client_records = state['potential_mergers_by_client'][client_key]
        except KeyError:
            return removed_graphs

        # Common case, where there are no possible mergeable graphs
        # for the client
        if len(client_records) == 0:
            return removed_graphs

        for record in client_records:
            old_graph, old_path = record
            if old_graph.latest_ts + time < start:
                removed_graphs.append(record)

        for ex_record in removed_graphs:
            client_records.remove(record)
        return removed_graphs

    def _could_be_mergee(graph):
        """Checks to see if the graph could possibly be a child of a graph
        stored in an earlier file, such that both graphs represent the same
        logical browsing session, but the underlying BroRecords were split
        into two or more graphs because of log partition.

        Args:
            graph -- a BroRecordGraph object

        Returns:
            A boolean description of whether a graph could be merged into
            a parent graph.
        """
        earliest_ts = graph.earliest_ts
        latest_ts = graph.latest_ts

        for start, mid, end in log_merge_ranges:
            # If the current range is strictly later than all records in the
            # graph, then it means that all possible range comparisons will
            # be false, so we can stop looking any further
            if start > latest_ts and end > latest_ts:
                return False

            if earliest_ts >= mid and earliest_ts <= end:
                return True
        return False

    # Everything above is just creating closures to ease managing the merging
    # -tracking-data-structures.  Actual code / usage / action starts here...
    for path in filelist:
        for graph in _graphs_from_file(path):

            # First check to see if its possible for this graph to
            # be merged into another one (either as a parent or a child).
            # If not, which is the common case, we can just immediatly
            # yield the value back as being unchanged from its source file
            possible_merger = _could_be_merger(graph)
            possible_mergee = _could_be_mergee(graph)
            if not possible_merger and not possible_mergee:
                yield path, graph, False
                continue

            # Since at this point we start interacting with the collection
            # of previous graphs that could potentially merge with the
            # new graph, we prune out any graphs from the previous potential
            # mergers and yield them back.
            #
            # Note that by doing so here, we keep these checks out of the
            # common path, though it means we'll disrupt the order a bit since
            # some of these graphs will be very old at this point.  However,
            # since the yielded back graphs were already going to be
            # semi out of order, they'd need to be sorted anyway, so no
            # biggie
            pruned_merger_graphs = _prune_mergers(graph)
            for old_graph, old_path in pruned_merger_graphs:
                yield _yield_back_merger(old_graph, old_path)

            # Next, we check to see if the graph under consideration
            # occurs late enough in its log to be possibly the parent
            # of a graph in a subsequent file.  If so, then don't deal with
            # the graph now, but add it to a hanging set of graphs that we'll
            # deal with later, when its no longer possible for them to
            # be parents of future graphs.
            if possible_merger:
                _add_graph_as_potential_merger(graph, path)
                continue

            # The only remaining option then is that the graph under
            # consideration potentially could be merged into a graph from a
            # previous file.
            parent_graph = _parent_merge_graph(graph)
            if parent_graph:
                # If we're able to find a parent graph, then no need to
                # consider this (now-child) graph any further, as its
                # records are now accounted for by a parent
                log.info(" * Found merge: {0}".format(graph._root.url))
                continue

            # Otherwise, if we're not able to find a parent graph,
            # then we can just yield back this graph, unchanged
            yield path, graph, False
            continue

    for old_graph, old_path in _all_potential_mergers():
        yield _yield_back_merger(old_graph, old_path)

def graphs(handle, time=10, record_filter=None):
    """A generator function yields BroRecordGraph objects that represent
    pages visited in a browsing session.

    Args:
        handle -- a file handle like object to read lines of bro data off of.

    Keyword Args:
        time          -- the maximum amount of time that can have passed in
                         a browsing session before the graph is closed and
                         yielded
        record_filter -- an optional function that, if provided, should take two
                         arguments of bro records, and should provide True if
                         they should be included in the same chain or not.  Note
                         that this is in addition to the filtering / matching
                         already performed by the BroRecordChain.add_record
                         function

    Return:
        An iterator returns BroRecordGraph objects
    """
    # To avoid needing to iterate over all the graphs, keys in this collection
    # are a simple concatination of IP and user agent, and the values
    # are all the currently active graphs being tracked for that client
    all_client_graphs = {}
    for r in bro_records(handle, record_filter=record_filter):
        hash_key = r.id_orig_h + "|" + r.user_agent

        # By default, assume that we've seen a request by this client
        # before, so start looking for a graph we can add this record to
        # to in the list of all graphs currently tracked for the client
        try:
            graphs = all_client_graphs[hash_key]
            found_graph_for_record = False
            dirty_graphs = []
            for g in graphs:
                # First make sure that our graphs are not too old.  If they
                # are, yield them and then remove them from our considered
                # set
                if (r.ts - g.latest_ts) > time:
                    yield g
                    dirty_graphs.append(g)
                    continue

                # If the current graph is not too old to represent a valid
                # browsing session then, see if it is valid for the given
                # bro record.  If so, then we don't need to consider any other
                # graphs on this iteration
                if g.add_node(r):
                    found_graph_for_record = True
                    break

            # Last, if we haven't found a graph to add the current record to,
            # create a new graph and add the record to it
            if not found_graph_for_record:
                graphs.append(BroRecordGraph(r))

            for dg in dirty_graphs:
                graphs.remove(dg)

        # If we've never seen any requests for this client, then
        # there is no way the request could be part of any graph we're tracking,
        # so create a new collection of graphs to search
        except KeyError:
            all_client_graphs[hash_key] = [BroRecordGraph(r)]

    # Last, if we've considered every bro record in the collection, we need to
    # yield the remaining graphs to the caller, to make sure they see
    # ever relevant record
    for graphs in all_client_graphs.values():
        for g in graphs:
            yield g


class BroRecordGraph(object):

    def __init__(self, br):
        self._g = nx.DiGraph()
        self.ip = br.id_orig_h
        self.user_agent = br.user_agent

        # The root element of the graph can either be the referrer of the given
        # bro record, if it exists, or otherwise the record itself.
        self._g.add_node(br)
        self._root = br

        # Keep track of what range of time this graph represents
        self.earliest_ts = br.ts
        self.latest_ts = br.ts

        # Since we expect that we'll see nodes in a sorted order (ie
        # each examined node will be the lastest-one-seen-yet)
        # we can make date comparisons of nodes faster by
        # keeping a seperate set of references to them, from earliest to
        # latest
        self._nodes_sorted = [br]

        # To make searching for referrers faster, we also keep a referrence
        # to each node by its url.  Here, each record's url is the key
        # and the corresponding value is a list of all records requesting
        # that url
        self._nodes_by_url = {}
        self._nodes_by_url[br.url] = [br]

        # Finally, also keep a reference to all nodes by host, where keys
        # are domains, and the values are a list of all records in the
        # graph to that domain
        self._nodes_by_host = {}
        self._nodes_by_host[br.host] = [br]

    def __str__(self):
        return self.summary()

    def __len__(self):
        return len(self._nodes_sorted)

    def summary(self, detailed=True):
        """Returns a string description of the current graph.

        Keyword Args:
            detailed -- boolean, if true, the returned summary includes the
                        client's IP and the date of the inital request

        Returns:
            A string, describing the requests contained in this graph, and
            optionally information about the client and time the initial
            request was made.
        """
        def _print_sub_tree(node, parent=None, level=0):
            response = ("  " * level)
            if parent:
                dif = node.ts - parent.ts
                response += "|-" + str(round(dif, 2)) + "-> "
            response += node.url + "\n"

            children = self.children_of_node(node)
            for c in children:
                response += _print_sub_tree(c, parent=node, level=(level + 1))
            return response

        if detailed:
            output = self.ip + "\n" + self._root.date_str + "\n"
            if self._root.name:
                output += self._root.name + "\n"
            output += "-----\n"
        else:
            output = ""
        return output + _print_sub_tree(self._root)

    def referrer_record(self, candidate_record):
        """Returns the BroRecord that could be the referrer of the given
        record, if one exists, and otherwise returns None.  If there
        are multiple BroRecords in this graph that could be the referrer of
        the given record, the most recent candidate is returned.

        Args:
            candidate_record -- a BroRecord object

        Returns:
            The most recent candidate BroRecord that could be the referrer of
            the passed BroRecord, or None if there are no possible matches.
        """
        # We can special case situations where the IP addresses don't match,
        # in order to save ourselves having to walk the entire line of nodes
        # again in a clear miss situation
        if candidate_record.id_orig_h != self.ip:
            return None

        # Similarly, we can special case situations where user agents
        # don't match.  Since all records in a single graph will have
        # the same user agent, we can quick reject any records that have
        # a user agent other than the first user agent seen in the graph.
        if candidate_record.user_agent != self.user_agent:
            return None

        try:
            for n in self._nodes_by_url[candidate_record.referrer]:
                if n.ts < candidate_record.ts:
                    return n
        except KeyError:
            return None

    def add_node(self, br):
        """Attempts to add the given BroRecord as a child (successor) of its
        referrer in the graph.

        Args:
            br -- a BroRecord object

        Returns:
            True if a referrer of the the BroRecord could be found and the given
            record was added as its child / successor.  Otherwise, False is
            returned, indicating no changes were made."""
        referrer_node = self.referrer_record(br)
        if not referrer_node:
            return False

        time_difference = br.ts - referrer_node.ts
        self._g.add_weighted_edges_from([(referrer_node, br, time_difference)])
        self.latest_ts = max(br.ts, self.latest_ts)
        self._nodes_sorted.append(br)
        self._nodes_sorted.sort(key=lambda x: x.ts)

        try:
            self._nodes_by_url[br.url].append(br)
        except KeyError:
            self._nodes_by_url[br.url] = [br]

        try:
            self._nodes_by_host[br.host].append(br)
        except KeyError:
            self._nodes_by_host[br.host] = [br]

        return True

    def add_graph(self, child_graph):
        """Attempts to merge in a child group into the current graph.
        This is done by seeing if the head of the child graph can find any
        referrer in the parent graph.

        Args:
            child_graph -- a BroRecordGraph instance

        Return:
            True if the child graph could be added to / merged into the current
            graph, otherwise False.
        """
        child_head = child_graph._root
        referrer_node = self.referrer_record(child_head)
        if not referrer_node:
            return False

        for n in child_graph.nodes():
            self.add_node(n)

        return True

    def nodes(self):
        """Returns an list of BroRecords, from oldest to newest, that are in
        the graph.

        Return:
            A list of zero or more BroRecords
        """
        return self._nodes_sorted

    def hosts(self):
        """Returns a list of all of the hosts represented in the graph.

        Return:
            A list of zero or more strings
        """
        return self._nodes_by_host.keys()

    def nodes_for_host(self, host):
        """Returns a list of all nodes in the graph that are requests to
        a given host.

        Args:
            host -- a string describing a host / domain

        Return:
            A list of zero or more BroRecords all requesting the given
            host.
        """
        try:
            return self._nodes_by_host[host]
        except KeyError:
            return []

    def nodes_for_hosts(self, *args):
        """Returns a list of all nodes in the graph that are requests to
        any of the given hosts.

        Args:
            args -- one or more host names, as strings

        Return:
            A list of zero or more BroRecords, that were made to one of the
            given hosts.
        """
        nodes = []
        for host in args:
            nodes_for_host = self.nodes_for_host(host)
            if nodes_for_host:
                nodes += nodes_for_host
        return nodes

    def leaves(self):
        """Returns a iterator of BroRecords, each of which are leaves in t
        graph (meaining record nodes that are there referrer for no other node).

        Returns:
            An iterator of BroRecord nodes"""
        g = self._g
        return (n for n in g.nodes_iter() if not g.successors(n))

    def node_domains(self):
        """Returns a dict representing a mapping from domain to a list of all
        nodes in the collection that are requests against that domain.

        Return:
            A dict with keys being domains (as strings), and values being
            lists of one or more BroRecord objects
        """
        mapping = {}
        for n in self._g.nodes_iter():
            try:
                mapping[n.host].append(n)
            except KeyError:
                mapping[n.host] = [n]
        return mapping

    def nodes_for_domain(self, domain):
        """Returns a list of nodes in the collection where the requested host
        matches the provided domain.

        Args:
            domain -- a valid domain, such as example.org

        Return:
            A list of zero or more nodes in the current collection that
            represent requests to the given domain
        """
        g = self._g
        return [n for n in g.nodes_iter() if n.host == domain]

    def graph(self):
        """Returns the underlying graph representation for the BroRecords

        Returns:
            The underlying graph representation, a networkx.DiGraph object
        """
        return self._g

    def remaining_child_time(self, br):
        """Returns the amount of time that the browsing session - captured
        by this graph - continued under the given node.  This is the same
        thing, and computed as, the max of times between the given node
        and all nodes below it.

        Args:
            br -- a BroRecord

        Return:
            A float, describing a number of seconds, or None if the given
            node is not in the graph.
        """
        g = self._g

        if not g.has_node(br):
            return None

        def _time_below(node, parent=None):
            if parent:
                cur_time = node.ts - parent.ts
            else:
                cur_time = 0
            cs = self.children_of_node(node)

            if len(cs) == 0:
                return cur_time

            try:
                max_time = max([_time_below(n, parent=node) for n in cs])
                return cur_time + max_time
            except RuntimeError:
                msg = ("Infinite recursive loop in `remaining_child_time`\n" +
                      "\n" +
                      "Node:\n" +
                      str(node) + "\n\n" +
                      "Graph:\n" +
                      str(self))
                raise(Exception(msg))

        return _time_below(self._root)

    def max_child_depth(self, br):
        """Returns the count of the longest path from the given node to a leaf
        under the node.  If the given node has no children, the returned value
        will be 0.  If the given node is not in the graph, None is returned.

        Args:
            br -- a BroRecord

        Returns:
            None if the given record is not in the graph, and otherwise returns
            an integer.
        """
        g = self._g

        if not g.has_node(br):
            return None

        def _max_depth(node, count=0):
            children = g.successors(node)
            if len(children) == 0:
                return count
            # Occasionally there is a recursion depth error here,
            # which is baffling at the moment.  So, for now, just escape
            # our way out of it
            try:
                return max([_max_depth(c, (count + 1)) for c in children])
            except RuntimeError:
                return count + 1

        return _max_depth(br)

    def children_of_node(self, br):
        """Returns a list of BroRecord objects that were directed to from
        the record represented by the given BroRecord.

        Args:
            br -- a BroRecord

        Return:
            A list of zero or more BroRecords, or None if the given BroRecord
            is not in the current graph.
        """
        g = self._g
        if not g.has_node(br):
            return None
        return g.successors(br)

    def parent_of_node(self, br):
        """Returns a BroRecord object that is the referrer of the given record
        in the graph, if available.

        Args:
            br -- a BroRecord

        Return:
            Either a BroRecord if the passed BroRecord is in the graph and
            has a parent, or None if the given BroRecord either isn't in
            the graph or has no parent.
        """
        g = self._g
        if not g.has_node(br):
            return None
        parents = g.predecessors(br)
        if len(parents) != 1:
            return None
        else:
            return parents[0]

    def chain_from_node(self, br):
        """Returns a BroRecordChain object, describing the chain of requests
        that lead to the given BroRecord.

        Args:
            br -- a BroRecord

        Return:
            None if the given BroRecord is not in the give BroRecordGraph,
            otherwise a BroRecordChain object describing how the record br
            was arrived at from the root of the graph / DAG.
        """
        g = self._g
        if not g.has_node(br):
            return None

        path = [br]
        node = br
        while True:
            parents = g.predecessors(node)
            if not len(parents):
                break
            node = parents[0]
            path.append(node)

        chain = BroRecordChain(path[-1])
        for r in path[1::-1]:
            chain.add_record(r)
        return chain
