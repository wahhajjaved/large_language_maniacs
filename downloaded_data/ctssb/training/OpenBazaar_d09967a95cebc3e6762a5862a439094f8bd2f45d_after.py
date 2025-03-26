import hashlib
import json
import logging
import os
import time
import functools
from threading import RLock

from node import constants, datastore, routingtable
from node.protocol import proto_store

class DHT(object):
    def __init__(self, transport, market_id, settings, db_connection):

        self.log = logging.getLogger(
            '[%s] %s' % (market_id, self.__class__.__name__)
        )
        self.settings = settings
        self.known_nodes = []
        self.searches = []
        self.active_peers = []
        self.transport = transport
        self.market_id = market_id

        # Routing table
        self.routing_table = routingtable.OptimizedTreeRoutingTable(
            self.settings['guid'], market_id)
        self.data_store = datastore.SqliteDataStore(db_connection)

        self._lock = RLock()

    # pylint: disable=no-self-argument
    # pylint: disable=not-callable
    def _synchronized(f):
        """Decorator for synchronizing access to DHT attributes."""
        @functools.wraps(f)
        def synced_f(self, *args, **kwargs):
            with self._lock:
                return f(self, *args, **kwargs)
        return synced_f

    @_synchronized
    def get_active_peers(self):
        return self.active_peers

    @_synchronized
    def start(self, seed_peer):
        """ This method executes only when the server is starting up for the
            first time and add the seed peer(s) to known node list and
            active peer list. It then executes a findNode against the network
            for itself to refresh buckets.

        :param seed_peer: (CryptoPeerConnection) for seed peer
        """
        ip_address = seed_peer.ip
        port = seed_peer.port
        self._add_known_node(('tcp://%s:%s' % (ip_address, port), seed_peer.guid, seed_peer.nickname))

        self.log.debug('Starting Seed Peer: %s', seed_peer.nickname)
        self.add_peer(seed_peer.address,
                      seed_peer.pub,
                      seed_peer.guid,
                      seed_peer.nickname)

        self.iterative_find(self.settings['guid'], self.known_nodes,
                            'findNode')

    def remove_peer(self, guid):
        for i, x in enumerate(self.active_peers):
            if x.guid == guid:
                self.log.debug('Remove Node: %s', guid)
                del self.active_peers[i]
        self.routing_table.remove_contact(guid)

    @_synchronized
    def add_peer(self, hostname, port, pubkey=None, guid=None, nickname=None, dump=False):
        """ This takes a tuple (pubkey, hostname, port, guid) and adds it to the active
        peers list if it doesn't already reside there.

        TODO: Refactor to just pass a peer object. evil tuples.
        """

        # peer_tuple = (hostname, port, pubkey, guid, nickname)
        # found_peer = False

        # activePeers
        for peer in self.active_peers:
            if peer.guid == guid:

                # Check if hostname/port combo changed
                if hostname != peer.hostname or port != peer.port:
                    peer.hostname = hostname
                    peer.port = port
                    peer.init_packetsender()
                    peer.setup_emitters()
                    self.routing_table.add_contact(peer)

                peer.nickname = nickname
                peer.pub = pubkey

                # DHT contacts
                # self.routingTable.removeContact(guid)
                #self.routingTable.addContact(peer)

                return peer

        new_peer = self.transport.get_crypto_peer(guid, hostname, port, pubkey, nickname)

        if new_peer:
            #if new_peer.guid:
            #self.activePeers[:] = [x for x in self.active_peers if x.guid != guid]

            self.active_peers.append(new_peer)
            self.log.debug('Active peers after adding new one: %s', self.active_peers)
            self.routing_table.add_contact(new_peer)
            return new_peer
        else:
            self.log.error('Could not create a new peer.')
            return None

            # self.log.debug('Sending hello message')


            # if not new_peer.hello:
            # new_peer.send_raw(
            #     json.dumps({
            #         'type': 'hello',
            #         'pubkey': self.transport.pubkey,
            #         'senderGUID': self.transport.guid,
            #         'hostname': self.transport.hostname,
            #         'port': self.transport.port,
            #         'senderNick': self.transport.nickname,
            #         'v': constants.VERSION
            #     })
            # )
            # new_peer.hello = True

    @_synchronized
    def _add_known_node(self, node):
        """ Accept a peer tuple and add it to known nodes list
        :param node: (tuple)
        :return: N/A
        """
        self.log.debug('Adding known node: %s', node)
        if node not in self.known_nodes and node[1] is not None:
            self.known_nodes.append(node)

    @_synchronized
    def on_find_node(self, msg):
        """ When a findNode message is received it will be of several types:
        - findValue: Looking for a specific key-value
        - findNode: Looking for a node with a key

        If you find the key-value pair you send back the value in the foundKey
        field.

        If you find the node then send back the exact node and if you don't
        send back a list of k closest nodes in the foundNodes field.

        :param msg: Incoming message from other node with findNode request
        :return: N/A
        """

        self.log.debug('Received a findNode request: %s', msg)

        guid = msg['senderGUID']
        key = msg['key']
        find_id = msg['findID']
        pubkey = msg['pubkey']

        assert guid is not None and guid != self.transport.guid
        assert key is not None
        assert find_id is not None
        assert pubkey is not None

        querying_peer = self.routing_table.get_contact(guid)
        self.log.debug('got contact %s', querying_peer)

        if querying_peer is not None:

            response_msg = {"type": "findNodeResponse",
                            "senderGUID": self.transport.guid,
                            "hostname": self.transport.hostname,
                            "port": self.transport.port,
                            "pubkey": self.transport.pubkey,
                            "senderNick": self.transport.nickname,
                            "findID": find_id}

            if msg['findValue']:
                if key in self.data_store and self.data_store[key] is not None:
                    # Found key in local data store
                    response_msg["foundKey"] = self.data_store[key]
                    self.log.info('Found a key: %s', key)

                querying_peer.send(response_msg)
            else:

                # Return close nodes to the key
                close_nodes = self.close_nodes(key, guid)
                self.log.debug('Found Close Nodes: %s', close_nodes)

                response_msg['foundNodes'] = close_nodes
                querying_peer.send(response_msg)

    @_synchronized
    def close_nodes(self, key, guid=None):
        contacts = self.routing_table.find_close_nodes(key, constants.K, guid)
        contact_list = []
        for contact in contacts:
            self.log.debug('Contact: %s', contact)
            contact_list.append((contact.guid, contact.hostname, contact.port, contact.pub, contact.nickname))

        return self.dedupe(contact_list)

    @_synchronized
    def on_find_node_response(self, msg):

        # Update existing peer's pubkey if active peer
        for idx, peer in enumerate(self.active_peers):
            if peer.guid == msg['senderGUID']:
                peer.nickname = msg['senderNick']
                peer.pub = msg['pubkey']

        # If key was found by this node then
        if 'foundKey' in msg.keys():
            self.log.debug('Found the key-value pair. Executing callback.')

            for idx, search in enumerate(self.searches):
                if search.find_id == msg['findID']:
                    search.callback(msg['foundKey'])
                    if idx in self.searches:
                        del self.searches[idx]

        else:

            if 'foundNode' in msg.keys():
                found_node = msg['foundNodes']

                # Add foundNode to active peers list and routing table
                if found_node[0] != self.transport.guid:
                    self.log.debug('Found a tuple %s', found_node)
                    if len(found_node) == 3:
                        found_node.append('')
                    self.add_peer(found_node[1], found_node[2], found_node[3], found_node[0], found_node[4])

                for idx, search in enumerate(self.searches):
                    if search.find_id == msg['findID']:

                        # Execute callback
                        if search.callback is not None:
                            search.callback((found_node[2], found_node[1], found_node[0], found_node[3]))

                        # Clear search
                        del self.searches[idx]

            else:
                found_search = False
                search = None
                find_id = msg['findID']
                for ser in self.searches:
                    if ser.find_id == find_id:
                        search = ser
                        found_search = True

                if not found_search:
                    self.log.info('No search found')
                    return
                else:

                    # Get current shortlist length
                    shortlist_length = len(search.shortlist)

                    nodes_to_extend = []

                    # Extends shortlist if necessary
                    for node in msg['foundNodes']:
                        if node[0] != self.transport.guid and node[3] != self.transport.pubkey \
                                and not (node[1] == self.transport.hostname) \
                                or not node[2] == self.transport.port:

                            self.log.debug('Adding a findNode peer')
                            new_node = self.add_peer(node[1], node[2], node[3], node[0], node[4])
                            new_node.send_raw(
                                json.dumps({
                                    'type': 'hello',
                                    'pubkey': self.transport.pubkey,
                                    'senderGUID': self.transport.guid,
                                    'hostname': self.transport.hostname,
                                    'port': self.transport.port,
                                    'senderNick': self.transport.nickname,
                                    'v': constants.VERSION
                                })
                            )
                            nodes_to_extend.append(node)

                    self.extend_shortlist(msg['findID'], nodes_to_extend)

                    # Remove active probe to this node for this findID
                    search_ip = msg['hostname']
                    search_port = msg['port']
                    search_guid = msg['senderGUID']
                    search_tuple = (search_ip, search_port, search_guid)

                    for idx, probe in enumerate(search.active_probes):
                        if probe == search_tuple:
                            del search.active_probes[idx]
                    self.log.datadump(
                        'Find Node Response - Active Probes After: %s',
                        search.active_probes
                    )

                    # Add this to already contacted list
                    if search_tuple not in search.already_contacted:
                        search.already_contacted.append(search_tuple)
                    self.log.datadump(
                        'Already Contacted: %s',
                        search.already_contacted
                    )

                    # If we added more to shortlist then keep searching
                    if len(search.shortlist) > shortlist_length:
                        self.log.info('Lets keep searching')
                        self._search_iteration(search)
                    else:
                        self.log.info('Shortlist is empty')
                        if search.callback is not None:
                            search.callback(search.shortlist)

    @_synchronized
    def _refresh_node(self):
        """ Periodically called to perform k-bucket refreshes and data
        replication/republishing as necessary """
        self._refresh_routing_table()
        self._republish_data()

    @_synchronized
    def _refresh_routing_table(self):
        self.log.info('Started Refreshing Routing Table')

        # Get Random ID from every KBucket
        node_ids = self.routing_table.get_refresh_list(0, False)

        def search_for_next_node_id():
            if len(node_ids) > 0:
                search_id = node_ids.pop()
                self.iterative_find_node(search_id)
                search_for_next_node_id()
            else:
                # If this is reached, we have finished refreshing the routing table
                return

        # Start the refreshing cycle
        search_for_next_node_id()

    @_synchronized
    def _republish_data(self, *args):
        self._threaded_republish_data()

    @_synchronized
    def _threaded_republish_data(self, *args):
        """ Republishes and expires any stored data (i.e. stored
        C{(key, value pairs)} that need to be republished/expired

        This method should run in a deferred thread
        """
        self.log.debug('Republishing Data')
        expired_keys = []

        for key in self.data_store.keys():

            # Filter internal variables stored in the data store
            if key == 'nodeState':
                continue

            now = int(time.time())
            key = key.encode('hex')
            original_publisher_id = self.data_store.get_original_publisher_id(key)
            age = now - self.data_store.get_original_publish_time(key) + 500000

            if original_publisher_id == self.settings['guid']:
                # This node is the original publisher; it has to republish
                # the data before it expires (24 hours in basic Kademlia)
                if age >= constants.DATE_EXPIRE_TIMEOUT:
                    self.iterative_store(key, self.data_store[key])

            else:
                # This node needs to replicate the data at set intervals,
                # until it expires, without changing the metadata associated with it
                # First, check if the data has expired
                if age >= constants.DATE_EXPIRE_TIMEOUT:
                    # This key/value pair has expired and has not been
                    # republished by the original publishing node,
                    # so remove it.
                    expired_keys.append(key)
                elif now - self.data_store.get_last_published(key) >= constants.REPLICATE_INTERVAL:
                    self.iterative_store(key, self.data_store[key], original_publisher_id, age)

        for key in expired_keys:
            del self.data_store[key]

    @_synchronized
    def extend_shortlist(self, find_id, found_nodes):

        self.log.datadump('found_nodes: %s', found_nodes)

        found_search = False
        for ser in self.searches:
            if ser.find_id == find_id:
                search = ser
                found_search = True

        if not found_search:
            self.log.error('There was no search found for this ID')
            return

        self.log.datadump('Short list before: %s', search.shortlist)

        for node in found_nodes:

            node_guid, node_hostname, node_port, node_pubkey, node_nick = node

            # Add to shortlist
            if (node_hostname, node_port, node_guid, node_nick) not in search.shortlist:
                search.add_to_shortlist([(node_hostname, node_port, node_guid, node_pubkey, node_nick)])

            # Skip ourselves if returned
            if node_guid == self.settings['guid']:
                continue

            for peer in self.active_peers:
                if node_guid == peer.guid:
                    # Already an active peer or it's myself
                    continue

            if node_guid != self.settings['guid']:
                self.log.debug('Adding new peer to active peers list: %s', node)
                self.add_peer(node_hostname, node_port, node_pubkey, node_guid, node_nick)

        self.log.datadump('Short list after: %s', search.shortlist)

    @_synchronized
    def find_listings(self, key, listing_filter=None, callback=None):
        """
        Send a get product listings call to the node in question and
        then cache those listings locally.
        TODO: Ideally we would want to send an array of listing IDs that
        we have locally and then the node would send back the missing or
        updated listings. This would save on queries for listings we
        already have.
        """

        peer = self.routing_table.get_contact(key)

        if peer:
            peer.send({'type': 'query_listings', 'key': key})
        else:
            self.log.error('Peer is not available for listings.')

        # TODO: Fix DHT listings search
        # Check cache in DHT if peer not available
        # listing_index_key = hashlib.sha1('contracts-%s' % key).hexdigest()
        # hashvalue = hashlib.new('ripemd160')
        # hashvalue.update(listing_index_key)
        # listing_index_key = hashvalue.hexdigest()
        #
        # self.log.info('Finding contracts for store: %s', listing_index_key)
        #
        # self.iterative_find_value(listing_index_key, callback)

    @_synchronized
    def find_listings_by_keyword(self, keyword, listing_filter=None, callback=None):

        hashvalue = hashlib.new('ripemd160')
        keyword_key = 'keyword-%s' % keyword
        hashvalue.update(keyword_key.encode('utf-8'))
        listing_index_key = hashvalue.hexdigest()

        self.log.info('Finding contracts for keyword: %s', keyword)

        self.iterative_find_value(listing_index_key, callback)

    @_synchronized
    def iterative_store(self, key, value_to_store=None, original_publisher_id=None, age=0):
        """ The Kademlia store operation

        Call this to store/republish data in the DHT.

        @param key: The hashtable key of the data
        @type key: str
        @param original_publisher_id: The node ID of the node that is the
                                      B{original} publisher of the data
        @type original_publisher_id: str
        @param age: The relative age of the data (time in seconds since it was
                    originally published). Note that the original publish time
                    isn't actually given, to compensate for clock skew between
                    different nodes.
        @type age: int
        """
        if original_publisher_id is None:
            original_publisher_id = self.transport.guid

        # Find appropriate storage nodes and save key value
        if value_to_store:
            self.log.info('Storing key to DHT: %s', key)
            self.log.datadump('Value to store: %s', value_to_store)
            self.iterative_find_node(
                key,
                lambda msg, findKey=key, value=value_to_store,
                       original_publisher_id=original_publisher_id, age=age:
                self.store_key_value(msg, findKey, value, original_publisher_id, age)
            )

    @_synchronized
    def store_key_value(self, nodes, key, value, original_publisher_id, age):

        self.log.datadump('Store Key Value: (%s, %s %s)', nodes, key, type(value))

        try:

            value_json = json.loads(value)

            # Add Notary GUID to index
            if 'notary_index_add' in value_json:
                existing_index = self.data_store[key]
                if existing_index is not None:
                    if not value_json['notary_index_add'] in existing_index['notaries']:
                        existing_index['notaries'].append(value_json['notary_index_add'])
                    value = existing_index
                else:
                    value = {'notaries': [value_json['notary_index_add']]}
                self.log.info('Notaries: %s', existing_index)

            if 'notary_index_remove' in value_json:
                existing_index = self.data_store[key]
                if existing_index is not None:
                    if value_json['notary_index_remove'] in existing_index['notaries']:
                        existing_index['notaries'].remove(value_json['notary_index_remove'])
                        value = existing_index
                    else:
                        return
                else:
                    return

            # Add listing to keyword index
            if 'keyword_index_add' in value_json:
                existing_index = self.data_store[key]

                if existing_index is not None:
                    if not value_json['keyword_index_add'] in existing_index['listings']:
                        existing_index['listings'].append(value_json['keyword_index_add'])
                    value = existing_index
                else:
                    value = {'listings': [value_json['keyword_index_add']]}

                self.log.info('Keyword Index: %s', value)

            if 'keyword_index_remove' in value_json:

                existing_index = self.data_store[key]

                if existing_index is not None:

                    if value_json['keyword_index_remove'] in existing_index['listings']:
                        existing_index['listings'].remove(value_json['keyword_index_remove'])
                        value = existing_index
                    else:
                        return

                else:
                    # Not in keyword index anyways
                    return

        except Exception as exc:
            self.log.debug('Value is not a JSON array: %s', exc)

        now = int(time.time())
        originally_published = now - age

        # Store it in your own node
        self.data_store.set_item(
            key, value, now, originally_published, original_publisher_id, market_id=self.market_id
        )

        for node in nodes:
            self.log.debug('Sending data to store in DHT: %s', node)
            #uri = network_util.get_peer_url(node[0], node[1])
            guid = node[2]
            peer = self.routing_table.get_contact(guid)

            if guid == self.transport.guid:
                break

            if not peer:
                peer = self.transport.get_crypto_peer(guid, node[0], node[1])
                peer.start_handshake()

            peer.send(proto_store(key, value, original_publisher_id, age))

    @_synchronized
    def _on_store_value(self, msg):

        key = msg['key']
        value = msg['value']
        original_publisher_id = msg['originalPublisherID']
        age = msg['age']

        self.log.info('Storing key %s for %s', key, original_publisher_id)
        self.log.datadump('Value: %s', value)

        now = int(time.time())
        originally_published = now - age

        if value:
            self.data_store.set_item(key, value, now, originally_published, original_publisher_id, self.market_id)
        else:
            self.log.error('No value to store')

    @_synchronized
    def store(self, key, value, original_publisher_id=None, age=0, **kwargs):
        """ Store the received data in this node's local hash table

        @param key: The hashtable key of the data
        @type key: str
        @param value: The actual data (the value associated with C{key})
        @type value: str
        @param original_publisher_id: The node ID of the node that is the
                                      B{original} publisher of the data
        @type original_publisher_id: str
        @param age: The relative age of the data (time in seconds since it was
                    originally published). Note that the original publish time
                    isn't actually given, to compensate for clock skew between
                    different nodes.
        @type age: int

        @rtype: str

        @todo: Since the data (value) may be large, passing it around as a buffer
               (which is the case currently) might not be a good idea... will have
               to fix this (perhaps use a stream from the Protocol class?)
        """
        # Get the sender's ID (if any)
        if '_rpcNodeID' in kwargs:
            rpc_sender_id = kwargs['_rpcNodeID']
        else:
            rpc_sender_id = None

        if original_publisher_id is None:
            if rpc_sender_id is not None:
                original_publisher_id = rpc_sender_id
            else:
                raise TypeError(
                    'No publisher specifed, and RPC caller ID not available.'
                    'Data requires an original publisher.'
                )

        now = int(time.time())
        originally_published = now - age
        self.data_store.set_item(
            key, value, now, originally_published, original_publisher_id, market_id=self.market_id
        )
        return 'OK'

    @_synchronized
    def iterative_find_node(self, key, callback=None):
        """ The basic Kademlia node lookup operation

        Call this to find a remote node in the P2P overlay network.

        @param key: the 160-bit key (i.e. the node or value ID) to search for
        @type key: str
        """
        self.log.info('Looking for node at: %s', key)
        self.iterative_find(key, [], callback=callback)

    @_synchronized
    def iterative_find(self, key, startup_shortlist=None, call='findNode', callback=None):
        """
        - Create a new DHTSearch object and add the key and call back to it
        - Add the search to our search queue (self.searches)
        - Find out if we're looking for a value or for a node
        -

        """
        # Create a new search object
        self.log.debug('Startup short list: %s', startup_shortlist)

        for i, x in enumerate(startup_shortlist):
            if not x[2]:
                del startup_shortlist[i]

        new_search = DHTSearch(self.market_id, key, call, callback=callback)
        self.searches.append(new_search)

        # Determine if we're looking for a node or a key
        find_value = call != 'findNode'

        if startup_shortlist == [] or startup_shortlist is None:

            # Retrieve closest nodes and add them to the shortlist for the search
            close_nodes = self.routing_table.find_close_nodes(key, constants.ALPHA, self.settings['guid'])
            shortlist = []

            for closeNode in close_nodes:
                shortlist.append((closeNode.hostname, closeNode.port, closeNode.guid))

            if len(shortlist) > 0:
                new_search.add_to_shortlist(shortlist)

            # Refresh the KBucket for this key
            if key != self.settings['guid']:
                self.routing_table.touch_kbucket(key)

            # Abandon the search if the shortlist has no nodes
            if len(new_search.shortlist) == 0:
                self.log.info('Search Finished')
                if callback is not None:
                    callback([])
                else:
                    return []

        else:
            new_search.shortlist = startup_shortlist

        self._search_iteration(new_search, find_value=find_value)

    @_synchronized
    def _search_iteration(self, new_search, find_value=False):

        # Update slow nodes count
        new_search.slow_node_count[0] = len(new_search.active_probes)

        # Sort shortlist from closest to farthest
        self.active_peers.sort(lambda firstNode, secondNode, targetKey=new_search.key: cmp(
            self.routing_table.distance(firstNode.guid, targetKey),
            self.routing_table.distance(secondNode.guid, targetKey)))

        # TODO: Put this in the callback
        # if new_search.key in new_search.find_value_result:
        # return new_search.find_value_result
        # elif len(new_search.shortlist) and find_value is False:
        #
        # # If you have more k amount of nodes in your shortlist then stop
        # # or ...
        # if (len(new_search.shortlist) >= constants.K) or (
        # new_search.shortlist[0] == new_search.previous_closest_node and len(
        # new_search.active_probes) ==
        # new_search.slow_node_count[0]):
        # if new_search.callback is not None:
        # new_search.callback(new_search.shortlist)
        # return

        # Update closest node
        if len(self.active_peers):
            closestPeer = self.active_peers[0]
            new_search.previous_closest_node = (closestPeer.hostname, closestPeer.port, closestPeer.guid)

        # Sort short list again
        if len(new_search.shortlist) > 1:

            # Remove dupes
            new_search.shortlist = self.dedupe(new_search.shortlist)
            self.log.datadump('Deduped Shortlist: %s', new_search.shortlist)

            new_search.shortlist.sort(lambda firstNode, secondNode, targetKey=new_search.key: cmp(
                self.routing_table.distance(firstNode[2], targetKey),
                self.routing_table.distance(secondNode[2], targetKey)))

            new_search.prev_shortlist_length = len(new_search.shortlist)

        # See if search was cancelled
        if not self.active_search_exists(new_search.find_id):
            self.log.info('Active search does not exist')
            return

        # Send findNodes out to all nodes in the shortlist
        for node in new_search.shortlist:
            if node not in new_search.already_contacted:
                if node[2] is not None and node[2] != self.transport.guid:

                    new_search.active_probes.append(node)
                    new_search.already_contacted.append(node)

                    contact = self.routing_table.get_contact(node[2])

                    if contact:

                        msg = {"type": "findNode",
                               "hostname": self.transport.hostname,
                               "port": self.transport.port,
                               "senderGUID": self.transport.guid,
                               "key": new_search.key,
                               "findValue": find_value,
                               "senderNick": self.transport.nickname,
                               "findID": new_search.find_id,
                               "pubkey": contact.transport.pubkey}
                        self.log.debug('Sending findNode to: %s %s', contact.hostname, msg)

                        contact.send(msg)
                        new_search.contacted_now += 1

                    else:
                        self.log.error('No contact was found for this guid: %s', node[2])

    @_synchronized
    def active_search_exists(self, find_id):

        active_search_exists = False
        for search in self.searches:
            if find_id == search.find_id:
                return True
        if not active_search_exists:
            return False

    @_synchronized
    def iterative_find_value(self, key, callback=None):
        self._iterativeFind(key, call='findValue', callback=callback)

    @staticmethod
    def dedupe(lst):
        seen = set()
        result = []
        for item in lst:
            frozenitem = frozenset(item)
            if frozenitem not in seen:
                result.append(item)
                seen.add(frozenitem)
        return result


class DHTSearch(object):
    def __init__(self, market_id, key, call="findNode", callback=None):
        self.key = key  # Key to search for
        self.call = call  # Either findNode or findValue depending on search
        self.callback = callback  # Callback for when search finishes
        self.shortlist = []  # List of nodes that are being searched against
        self.active_probes = []  #
        self.already_contacted = []  # Nodes are added to this list when they've been sent a findXXX action
        self.previous_closest_node = None  # This is updated to be the closest node found during search
        self.find_value_result = {}  # If a find_value search is found this is the value
        self.slow_node_count = [0]  #
        self.contacted_now = 0  # Counter for how many nodes have been contacted
        self.prev_shortlist_length = 0

        self.log = logging.getLogger(
            '[%s] %s' % (market_id, self.__class__.__name__)
        )

        # Create a unique ID (SHA1) for this iterative_find request to support parallel searches
        self.find_id = hashlib.sha1(os.urandom(128)).hexdigest()

    def add_to_shortlist(self, additions):

        self.log.debug('Additions: %s', additions)
        for item in additions:
            if item not in self.shortlist:
                self.shortlist.append(item)

        self.log.datadump('Updated short list: %s', self.shortlist)
