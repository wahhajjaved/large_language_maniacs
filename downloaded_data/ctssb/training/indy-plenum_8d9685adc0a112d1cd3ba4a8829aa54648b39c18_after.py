import json
import os
import time
from binascii import unhexlify
from collections import deque, defaultdict
from contextlib import closing
from typing import Dict, Any, Mapping, Iterable, List, Optional, Set, Tuple

from intervaltree import IntervalTree

from ledger.compact_merkle_tree import CompactMerkleTree
from ledger.serializers.compact_serializer import CompactSerializer
from ledger.stores.file_hash_store import FileHashStore
from ledger.stores.hash_store import HashStore
from ledger.stores.memory_hash_store import MemoryHashStore
from ledger.util import F
from orderedset._orderedset import OrderedSet

from plenum.client.wallet import Wallet
from plenum.common.config_util import getConfig
from plenum.common.constants import TXN_TYPE, TXN_TIME, POOL_TXN_TYPES, \
    TARGET_NYM, ROLE, STEWARD, NYM, VERKEY, OP_FIELD_NAME, CLIENT_STACK_SUFFIX, \
    CLIENT_BLACKLISTER_SUFFIX, NODE_BLACKLISTER_SUFFIX, \
    NODE_PRIMARY_STORAGE_SUFFIX, NODE_HASH_STORE_SUFFIX, HS_FILE, DATA, ALIAS, \
    NODE_IP, HS_LEVELDB, POOL_LEDGER_ID, DOMAIN_LEDGER_ID, LedgerState, TRUSTEE
from plenum.common.exceptions import SuspiciousNode, SuspiciousClient, \
    MissingNodeOp, InvalidNodeOp, InvalidNodeMsg, InvalidClientMsgType, \
    InvalidClientOp, InvalidClientRequest, BaseExc, \
    InvalidClientMessageException, KeysNotFoundException as REx, BlowUp
from plenum.common.has_file_storage import HasFileStorage
from plenum.common.keygen_utils import areKeysSetup
from plenum.common.ledger import Ledger
from plenum.common.ledger_manager import LedgerManager
from plenum.common.message_processor import MessageProcessor
from plenum.common.motor import Motor
from plenum.common.plugin_helper import loadPlugins
from plenum.common.request import Request, SafeRequest
from plenum.common.roles import Roles
from plenum.common.signer_simple import SimpleSigner
from plenum.common.stacks import nodeStackClass, clientStackClass
from plenum.common.startable import Status, Mode
from plenum.common.throttler import Throttler
from plenum.common.txn_util import getTxnOrderedFields
from plenum.common.types import Propagate, \
    Reply, Nomination, TaggedTuples, Primary, \
    Reelection, PrePrepare, Prepare, Commit, \
    Ordered, RequestAck, InstanceChange, Batch, OPERATION, BlacklistMsg, f, \
    RequestNack, HA, LedgerStatus, ConsistencyProof, CatchupReq, CatchupRep, \
    PLUGIN_TYPE_VERIFICATION, PLUGIN_TYPE_PROCESSING, PoolLedgerTxns, \
    ConsProofRequest, ElectionType, ThreePhaseType, Checkpoint, ThreePCState, \
    Reject, ViewChangeDone, ReqLedgerStatus
from plenum.common.util import friendlyEx, getMaxFailures, pop_keys, \
    compare_3PC_keys
from plenum.common.verifier import DidVerifier
from plenum.persistence.leveldb_hash_store import LevelDbHashStore
from plenum.persistence.req_id_to_txn import ReqIdrToTxn

from plenum.persistence.storage import Storage, initStorage, initKeyValueStorage
from plenum.server.msg_filter import MessageFilterEngine
from plenum.server.primary_selector import PrimarySelector
from plenum.server import replica
from plenum.server.blacklister import Blacklister
from plenum.server.blacklister import SimpleBlacklister
from plenum.server.client_authn import ClientAuthNr, SimpleAuthNr
from plenum.server.domain_req_handler import DomainRequestHandler
from plenum.server.has_action_queue import HasActionQueue
from plenum.server.instances import Instances
from plenum.server.models import InstanceChanges
from plenum.server.monitor import Monitor
from plenum.server.notifier_plugin_manager import notifierPluginTriggerEvents, \
    PluginManager
from plenum.server.plugin.has_plugin_loader_helper import PluginLoaderHelper
from plenum.server.pool_manager import HasPoolManager, TxnPoolManager, \
    RegistryPoolManager
from plenum.server.primary_decider import PrimaryDecider
from plenum.server.propagator import Propagator
from plenum.server.router import Router
from plenum.server.suspicion_codes import Suspicions
from plenum.server.view_change.view_change_msg_filter import ViewChangeMessageFilter
from state.pruning_state import PruningState
from stp_core.common.log import getlogger
from stp_core.crypto.signer import Signer
from stp_core.network.exceptions import RemoteNotFound
from stp_core.network.network_interface import NetworkInterface
from stp_core.ratchet import Ratchet
from stp_zmq.zstack import ZStack

from state.state import State

pluginManager = PluginManager()
logger = getlogger()


class Node(HasActionQueue, Motor, Propagator, MessageProcessor, HasFileStorage,
           HasPoolManager, PluginLoaderHelper):
    """
    A node in a plenum system.
    """

    suspicions = {s.code: s.reason for s in Suspicions.get_list()}
    keygenScript = "init_plenum_keys"
    _client_request_class = SafeRequest

    def __init__(self,
                 name: str,
                 nodeRegistry: Dict[str, HA]=None,
                 clientAuthNr: ClientAuthNr=None,
                 ha: HA=None,
                 cliname: str=None,
                 cliha: HA=None,
                 basedirpath: str=None,
                 primaryDecider: PrimaryDecider = None,
                 pluginPaths: Iterable[str]=None,
                 storage: Storage=None,
                 config=None,
                 seed=None):

        """
        Create a new node.

        :param nodeRegistry: names and host addresses of all nodes in the pool
        :param clientAuthNr: client authenticator implementation to be used
        :param basedirpath: path to the base directory used by `nstack` and
            `cstack`
        :param primaryDecider: the mechanism to be used to decide the primary
        of a protocol instance
        """
        self.created = time.time()
        self.name = name
        self.config = config or getConfig()
        self.basedirpath = basedirpath or config.baseDir
        self.dataDir = self.config.nodeDataDir or "data/nodes"

        self._view_change_timeout = self.config.VIEW_CHANGE_TIMEOUT

        HasFileStorage.__init__(self, name, baseDir=self.basedirpath,
                                dataDir=self.dataDir)
        self.ensureKeysAreSetup()
        self.opVerifiers = self.getPluginsByType(pluginPaths,
                                                 PLUGIN_TYPE_VERIFICATION)
        self.reqProcessors = self.getPluginsByType(pluginPaths,
                                                   PLUGIN_TYPE_PROCESSING)

        self.requestExecuter = defaultdict(lambda: self.executeDomainTxns)

        Motor.__init__(self)

        self.hashStore = self.getHashStore(self.name)

        self.primaryStorage = storage or self.getPrimaryStorage()
        self.states = {}  # type: Dict[int, State]

        self.states[DOMAIN_LEDGER_ID] = self.loadDomainState()
        self.reqHandler = self.getDomainReqHandler()
        self.initDomainState()

        self.clientAuthNr = clientAuthNr or self.defaultAuthNr()

        self.addGenesisNyms()

        self.initPoolManager(nodeRegistry, ha, cliname, cliha)

        if isinstance(self.poolManager, RegistryPoolManager):
            self.mode = Mode.discovered
        else:
            self.mode = None  # type: Optional[Mode]

        self.nodeReg = self.poolManager.nodeReg

        kwargs = dict(stackParams=self.poolManager.nstack,
                      msgHandler=self.handleOneNodeMsg, registry=self.nodeReg)
        cls = self.nodeStackClass
        kwargs.update(seed=seed)
        # noinspection PyCallingNonCallable
        self.nodestack = cls(**kwargs)
        self.nodestack.onConnsChanged = self.onConnsChanged

        kwargs = dict(stackParams=self.poolManager.cstack,
                      msgHandler=self.handleOneClientMsg)
        cls = self.clientStackClass
        kwargs.update(seed=seed)

        # noinspection PyCallingNonCallable
        self.clientstack = cls(**kwargs)

        self.cliNodeReg = self.poolManager.cliNodeReg

        HasActionQueue.__init__(self)
        # Motor.__init__(self)
        Propagator.__init__(self)

        self.primaryDecider = primaryDecider

        self.nodeInBox = deque()
        self.clientInBox = deque()

        self.setF()

        self.clientBlacklister = SimpleBlacklister(
            self.name + CLIENT_BLACKLISTER_SUFFIX)  # type: Blacklister

        self.nodeBlacklister = SimpleBlacklister(
            self.name + NODE_BLACKLISTER_SUFFIX)  # type: Blacklister

        self.nodeInfo = {
            'data': {}
        }

        self._elector = None  # type: PrimaryDecider

        self.instances = Instances()
        # QUESTION: Why does the monitor need blacklister?
        self.monitor = Monitor(self.name,
                               Delta=self.config.DELTA,
                               Lambda=self.config.LAMBDA,
                               Omega=self.config.OMEGA,
                               instances=self.instances,
                               nodestack=self.nodestack,
                               blacklister=self.nodeBlacklister,
                               nodeInfo=self.nodeInfo,
                               notifierEventTriggeringConfig=self.
                               config.notifierEventTriggeringConfig,
                               pluginPaths=pluginPaths)

        self.replicas = []  # type: List[replica.Replica]
        # Requests that are to be given to the replicas by the node. Each
        # element of the list is a deque for the replica with number equal to
        # its index in the list and each element of the deque is a named tuple
        self.msgsToReplicas = []  # type: List[deque]

        # Any messages that are intended for protocol instances not created.
        # Helps in cases where a new protocol instance have been added by a
        # majority of nodes due to joining of a new node, but some slow nodes
        # are not aware of it. Key is instance id and value is a deque
        self.msgsForFutureReplicas = {}

        self.adjustReplicas()

        self.instanceChanges = InstanceChanges()

        self.viewNo = 0                             # type: int

        # Requests that are to be given to the elector by the node
        self.msgsToElector = deque()

        self.ledgerManager = self.getLedgerManager()
        self.init_ledger_manager()
        if self.poolLedger:
            self.states[POOL_LEDGER_ID] = self.poolManager.state

        self.__message_filter_engine = MessageFilterEngine()

        nodeRoutes = [(Propagate, self.processPropagate),
                      (InstanceChange, self.processInstanceChange)]

        nodeRoutes.extend((msgTyp, self.sendToReplica) for msgTyp in
                          [PrePrepare, Prepare, Commit, Checkpoint,
                           ThreePCState])

        self.perfCheckFreq = self.config.PerfCheckFreq
        self.nodeRequestSpikeMonitorData = {
            'value': 0,
            'cnt': 0,
            'accum': 0
        }

        self.startRepeating(self.checkPerformance, self.perfCheckFreq)

        self.startRepeating(self.checkNodeRequestSpike,
                            self.config
                            .notifierEventTriggeringConfig[
                                'nodeRequestSpike']['freq'])

        self.initInsChngThrottling()

        # BE CAREFUL HERE
        # This controls which message types are excluded from signature
        # verification. These are still subject to RAET's signature verification
        # but client signatures will not be checked on these. Expressly
        # prohibited from being in this is ClientRequest and Propagation,
        # which both require client signature verification
        self.authnWhitelist = (Nomination, Primary, Reelection,
                               Batch, ViewChangeDone,
                               PrePrepare, Prepare, Checkpoint,
                               Commit, InstanceChange, LedgerStatus,
                               ConsistencyProof, CatchupReq, CatchupRep,
                               ConsProofRequest, ThreePCState)

        # Map of request identifier, request id to client name. Used for
        # dispatching the processed requests to the correct client remote
        # TODO: This should be persisted in
        # case the node crashes before sending the reply to the client
        self.requestSender = {}     # Dict[Tuple[str, int], str]

        nodeRoutes.extend([
            (ReqLedgerStatus, self.processReqLedgerStatus),
            (LedgerStatus, self.ledgerManager.processLedgerStatus),
            (ConsistencyProof, self.ledgerManager.processConsistencyProof),
            (ConsProofRequest, self.ledgerManager.processConsistencyProofReq),
            (CatchupReq, self.ledgerManager.processCatchupReq),
            (CatchupRep, self.ledgerManager.processCatchupRep)
        ])

        self.nodeMsgRouter = Router(*nodeRoutes)

        self.clientMsgRouter = Router(
            (Request, self.processRequest),
            (LedgerStatus, self.ledgerManager.processLedgerStatus),
            (CatchupReq, self.ledgerManager.processCatchupReq),
        )

        # Ordered requests received from replicas while the node was not
        # participating
        self.stashedOrderedReqs = deque()

        # Set of (identifier, reqId) of all transactions that were received
        # while catching up. Used to detect overlap between stashed requests
        # and received replies while catching up.
        # self.reqsFromCatchupReplies = set()

        # Any messages that are intended for view numbers higher than the
        # current view.
        self.msgsForFutureViews = {}

        self._primary_replica_no = None

        # Need to keep track of the time when lost connection with primary,
        # help in voting for/against a view change.
        self.lost_primary_at = None

        tp = loadPlugins(self.basedirpath)
        logger.debug("total plugins loaded in node: {}".format(tp))
        # TODO: this is already happening in `start`, why here then?
        self.logNodeInfo()
        self._wallet = None
        self.seqNoDB = self.loadSeqNoDB()

        # Stores the 3 phase keys for last `ProcessedBatchMapsToKeep` batches,
        # the key is the ledger id and value is an interval tree with each
        # interval being the range of txns and value being the 3 phase key of
        # the batch in which those transactions were included. The txn range is
        # exclusive of last seq no so to store txns from 1 to 100 add a range
        # of `1:101`
        self.txn_seq_range_to_3phase_key = {}  # type: Dict[int, IntervalTree]
        self._view_change_in_progress = False

    @property
    def id(self):
        if isinstance(self.poolManager, TxnPoolManager):
            return self.poolManager.id
        return None

    @property
    def wallet(self):
        if not self._wallet:
            wallet = Wallet(self.name)
            signer = SimpleSigner(seed=unhexlify(self.nodestack.keyhex))
            wallet.addIdentifier(signer=signer)
            self._wallet = wallet
        return self._wallet

    @property
    def elector(self) -> PrimaryDecider:
        return self._elector

    @elector.setter
    def elector(self, value):
        # clear old routes
        if self._elector:
            self.nodeMsgRouter.remove(self._elector.supported_msg_types)
        self._elector = value
        # set up new routes
        if self._elector:
            self.nodeMsgRouter.extend(
                (msgTyp, self.sendToElector) for msgTyp in
                self._elector.supported_msg_types)

    @property
    def view_change_in_progress(self):
        return self._view_change_in_progress

    @view_change_in_progress.setter
    def view_change_in_progress(self, value):
        self._view_change_in_progress = value
        # if self._view_change_in_progress:
        #     # Question: Why 2 args, won't every filter have a name?
        #     self.__message_filter_engine.add_filter(ViewChangeMessageFilter.NAME,
        #                                             ViewChangeMessageFilter(self.viewNo))
        # else:
        #     self.__message_filter_engine.remove_filter(ViewChangeMessageFilter.NAME)

    def initPoolManager(self, nodeRegistry, ha, cliname, cliha):
        HasPoolManager.__init__(self, nodeRegistry, ha, cliname, cliha)

    def __repr__(self):
        return self.name

    def getDomainReqHandler(self):
        return DomainRequestHandler(self.domainLedger,
                                    self.states[DOMAIN_LEDGER_ID],
                                    self.reqProcessors)

    def loadSeqNoDB(self):
        return ReqIdrToTxn(
            initKeyValueStorage(
                self.config.reqIdToTxnStorage,
                self.dataLocation,
                self.config.seqNoDbName)
        )

    # noinspection PyAttributeOutsideInit
    def setF(self):
        nodeNames = set(self.nodeReg.keys())
        self.allNodeNames = nodeNames.union({self.name, })
        self.totalNodes = len(self.allNodeNames)
        self.f = getMaxFailures(self.totalNodes)
        self.requiredNumberOfInstances = self.f + 1  # per RBFT
        self.minimumNodes = (2 * self.f) + 1  # minimum for a functional pool

    @property
    def poolLedger(self):
        return self.poolManager.ledger \
            if isinstance(self.poolManager, TxnPoolManager) \
            else None

    @property
    def domainLedger(self):
        return self.primaryStorage

    def build_ledger_status(self, ledger_id):
        ledger = self.getLedger(ledger_id)
        ledger_size = ledger.size
        three_pc_key = self.three_phase_key_for_txn_seq_no(ledger_id,
                                                           ledger_size)
        v, p = three_pc_key if three_pc_key else (None, None)
        return LedgerStatus(ledger_id, ledger.size, v, p, ledger.root_hash)

    @property
    def poolLedgerStatus(self):
        if self.poolLedger:
            return self.build_ledger_status(POOL_LEDGER_ID)

    @property
    def domainLedgerStatus(self):
        return self.build_ledger_status(DOMAIN_LEDGER_ID)

    @property
    def ledger_ids(self):
        return [POOL_LEDGER_ID, DOMAIN_LEDGER_ID]

    def getLedgerRootHash(self, ledgerId, isCommitted=True):
        ledgerInfo = self.ledgerManager.getLedgerInfoByType(ledgerId)
        if not ledgerInfo:
            raise RuntimeError('Ledger with id {} does not exist')
        ledger = ledgerInfo.ledger
        if isCommitted:
            return ledger.root_hash
        return ledger.uncommittedRootHash or ledger.root_hash

    def stateRootHash(self, ledgerId, isCommitted=True):
        state = self.states.get(ledgerId)
        if not state:
            raise RuntimeError('State with id {} does not exist')
        return state.committedHeadHash if isCommitted else state.headHash

    @property
    def isParticipating(self):
        return self.mode == Mode.participating

    @property
    def nodeStackClass(self) -> NetworkInterface:
        return nodeStackClass

    @property
    def clientStackClass(self) -> NetworkInterface:
        return clientStackClass

    def getPrimaryStorage(self):
        """
        This is usually an implementation of Ledger
        """
        if self.config.primaryStorage is None:
            fields = getTxnOrderedFields()
            defaultTxnFile = os.path.join(self.config.baseDir,
                                       self.config.domainTransactionsFile)
            if not os.path.exists(defaultTxnFile):
                logger.debug("Not using default initialization file for "
                             "domain ledger, since it does not exist: {}"
                             .format(defaultTxnFile))
                defaultTxnFile = None

            return Ledger(CompactMerkleTree(hashStore=self.hashStore),
                          dataDir=self.dataLocation,
                          serializer=CompactSerializer(fields=fields),
                          fileName=self.config.domainTransactionsFile,
                          ensureDurability=self.config.EnsureLedgerDurability,
                          defaultFile=defaultTxnFile)
        else:
            # TODO: we need to rethink this functionality
            return initStorage(self.config.primaryStorage,
                               name=self.name+NODE_PRIMARY_STORAGE_SUFFIX,
                               dataDir=self.dataLocation,
                               config=self.config)

    def getHashStore(self, name) -> HashStore:
        """
        Create and return a hashStore implementation based on configuration
        """
        hsConfig = self.config.hashStore['type'].lower()
        if hsConfig == HS_FILE:
            return FileHashStore(dataDir=self.dataLocation,
                                 fileNamePrefix=NODE_HASH_STORE_SUFFIX)
        elif hsConfig == HS_LEVELDB:
            return LevelDbHashStore(dataDir=self.dataLocation)
        else:
            return MemoryHashStore()

    def getLedgerManager(self) -> LedgerManager:
        return LedgerManager(self, ownedByNode=True,
                             postAllLedgersCaughtUp=self.allLedgersCaughtUp,
                             preCatchupClbk=self.preLedgerCatchUp)

    def init_ledger_manager(self):
        # TODO: this and tons of akin stuff should be exterminated
        self.ledgerManager.addLedger(DOMAIN_LEDGER_ID,
                                     self.domainLedger,
                                     postCatchupCompleteClbk=self.postDomainLedgerCaughtUp,
                                     postTxnAddedToLedgerClbk=self.postTxnFromCatchupAddedToLedger)
        self.on_new_ledger_added(DOMAIN_LEDGER_ID)
        if isinstance(self.poolManager, TxnPoolManager):
            self.ledgerManager.addLedger(POOL_LEDGER_ID, self.poolLedger,
                postCatchupCompleteClbk=self.postPoolLedgerCaughtUp,
                postTxnAddedToLedgerClbk=self.postTxnFromCatchupAddedToLedger)
            self.on_new_ledger_added(POOL_LEDGER_ID)

    def on_new_ledger_added(self, ledger_id):
        for r in self.replicas:
            # If a ledger was added after a replica was created, add a queue
            # in the ledger to the replica
            if ledger_id not in r.requestQueues:
                r.requestQueues[ledger_id] = OrderedSet()

    def loadDomainState(self):
        return PruningState(
            initKeyValueStorage(
                self.config.domainStateStorage,
                self.dataLocation,
                self.config.domainStateDbName)
        )

    @classmethod
    def ledgerIdForRequest(cls, request: Request):
        assert request.operation[TXN_TYPE]
        typ = request.operation[TXN_TYPE]
        return cls.ledgerId(typ)

    def start(self, loop):
        oldstatus = self.status
        if oldstatus in Status.going():
            logger.info("{} is already {}, so start has no effect".
                        format(self, self.status.name))
        else:
            super().start(loop)
            self.primaryStorage.start(loop,
                                      ensureDurability=
                                      self.config.EnsureLedgerDurability)
            if self.hashStore.closed:
                self.hashStore = self.getHashStore(self.name)

            self.nodestack.start()
            self.clientstack.start()

            self.elector = self.newPrimaryDecider()

            # if first time running this node
            if not self.nodestack.remotes:
                logger.info("{} first time running..."
                            "".format(self), extra={"cli": "LOW_STATUS",
                                                    "tags": ["node-key-sharing"]})
            else:
                self.nodestack.maintainConnections(force=True)

            if isinstance(self.poolManager, RegistryPoolManager):
                # Node not using pool ledger so start syncing domain ledger
                self.mode = Mode.discovered
                self.ledgerManager.setLedgerCanSync(DOMAIN_LEDGER_ID, True)
            else:
                # Node using pool ledger so first sync pool ledger
                self.mode = Mode.starting
                self.ledgerManager.setLedgerCanSync(POOL_LEDGER_ID, True)

        self.logNodeInfo()

    @property
    def rank(self) -> int:
        return self.poolManager.rank

    def get_name_by_rank(self, rank):
        return self.poolManager.get_name_by_rank(rank)

    def newPrimaryDecider(self):
        if self.primaryDecider:
            return self.primaryDecider
        else:
            return PrimarySelector(self)

    @property
    def connectedNodeCount(self) -> int:
        """
        The plus one is for this node, for example, if this node has three
        connections, then there would be four total nodes
        :return: number of connected nodes this one
        """
        return len(self.nodestack.conns) + 1

    def onStopping(self):
        """
        Actions to be performed on stopping the node.

        - Close the UDP socket of the nodestack
        """
        # Log stats should happen before any kind of reset or clearing
        self.logstats()

        self.reset()

        # Stop the ledgers
        ledgers = [self.domainLedger]
        if self.poolLedger:
            ledgers.append(self.poolLedger)

        for ledger in ledgers:
            try:
                ledger.stop()
            except Exception as ex:
                logger.warning('{} got exception while stopping ledger: {}'.
                               format(self, ex))

        # Stop the hash stores
        hashStores = [self.hashStore]
        if self.poolLedger:
            ledgers.append(self.poolLedger)
        if self.hashStore:
            hashStores.append(self.hashStore)
        if isinstance(self.poolManager, TxnPoolManager) and self.poolManager.hashStore:
            hashStores.append(self.poolManager.hashStore)
        hashStores = [hs for hs in hashStores if
                      isinstance(hs, (FileHashStore, LevelDbHashStore))
                      and not hs.closed]
        for hs in hashStores:
            try:
                hs.close()
            except Exception as ex:
                logger.warning('{} got exception while closing hash store: {}'.
                               format(self, ex))

        self.nodestack.stop()
        self.clientstack.stop()

        self.closeAllKVStores()

        self.mode = None
        if isinstance(self.poolManager, TxnPoolManager):
            self.ledgerManager.setLedgerState(POOL_LEDGER_ID,
                                              LedgerState.not_synced)
        self.ledgerManager.setLedgerState(DOMAIN_LEDGER_ID,
                                          LedgerState.not_synced)

    def closeAllKVStores(self):
        # Clear leveldb lock files
        logger.info("{} closing level dbs".format(self), extra={"cli": False})
        for ledgerId in self.ledgerManager.ledgerRegistry:
            state = self.getState(ledgerId)
            if state:
                state.close()
        if self.seqNoDB:
            self.seqNoDB.close()

    def reset(self):
        logger.info("{} reseting...".format(self), extra={"cli": False})
        self.nodestack.nextCheck = 0
        logger.debug("{} clearing aqStash of size {}".format(self,
                                                             len(self.aqStash)))
        self.nodestack.conns.clear()
        # TODO: Should `self.clientstack.conns` be cleared too
        # self.clientstack.conns.clear()
        self.aqStash.clear()
        self.actionQueue.clear()
        self.elector = None

    async def prod(self, limit: int=None) -> int:
        """.opened
        This function is executed by the node each time it gets its share of
        CPU time from the event loop.

        :param limit: the number of items to be serviced in this attempt
        :return: total number of messages serviced by this node
        """
        c = 0
        if self.status is not Status.stopped:
            c += await self.serviceReplicas(limit)
            c += await self.serviceNodeMsgs(limit)
            c += await self.serviceClientMsgs(limit)
            c += self._serviceActions()
            c += self.ledgerManager.service()
            c += self.monitor._serviceActions()
            c += await self.serviceElector()
            self.nodestack.flushOutBoxes()
        if self.isGoing():
            self.nodestack.serviceLifecycle()
            self.clientstack.serviceClientStack()
        return c

    async def serviceReplicas(self, limit) -> int:
        """
        Execute `serviceReplicaMsgs`, `serviceReplicaOutBox` and
        `serviceReplicaInBox` with `limit` number of messages. See the
        respective functions for more information.

        :param limit: the maximum number of messages to process
        :return: the sum of messages successfully processed by
        serviceReplicaMsgs, serviceReplicaInBox and serviceReplicaOutBox
        """
        a = self.serviceReplicaMsgs(limit)
        b = await self.serviceReplicaOutBox(limit)
        c = self.serviceReplicaInBox(limit)
        return a + b + c

    async def serviceNodeMsgs(self, limit: int) -> int:
        """
        Process `limit` number of messages from the nodeInBox.

        :param limit: the maximum number of messages to process
        :return: the number of messages successfully processed
        """
        n = await self.nodestack.service(limit)
        await self.processNodeInBox()
        return n

    async def serviceClientMsgs(self, limit: int) -> int:
        """
        Process `limit` number of messages from the clientInBox.

        :param limit: the maximum number of messages to process
        :return: the number of messages successfully processed
        """
        c = await self.clientstack.service(limit)
        await self.processClientInBox()
        return c

    async def serviceElector(self) -> int:
        """
        Service the elector's inBox, outBox and action queues.

        :return: the number of messages successfully serviced
        """
        if not self.isReady():
            return 0
        o = self.serviceElectorOutBox()
        i = await self.serviceElectorInbox()
        # TODO: Why is protected method accessed here?
        a = self.elector._serviceActions()
        return o + i + a

    def onConnsChanged(self, joined: Set[str], left: Set[str]):
        """
        A series of operations to perform once a connection count has changed.

        - Set f to max number of failures this system can handle.
        - Set status to one of started, started_hungry or starting depending on
            the number of protocol instances.
        - Check protocol instances. See `checkInstances()`
        
        """
        if self.isGoing():
            if self.connectedNodeCount == self.totalNodes:
                self.status = Status.started
            elif self.connectedNodeCount >= self.minimumNodes:
                self.status = Status.started_hungry
            else:
                self.status = Status.starting
        self.elector.nodeCount = self.connectedNodeCount

        if self.master_primary_name in joined:
            self.lost_primary_at = None
        if self.master_primary_name in left:
            logger.debug('{} lost connection to primary of master'.format(self))
            self.lost_master_primary()
        if self.isReady():
            self.checkInstances()


            # TODO: Should we only send election messages when lagged or
            # otherwise too?
            # if isinstance(self.elector, PrimaryElector) and joined:
            #     msgs = self.elector.get_msgs_for_lagged_nodes()
            #     logger.debug("{} has msgs {} for new nodes {}".
            #                  format(self, msgs, joined))
            #     for joinedNode in joined:
            #         self.sendElectionMsgsToLaggingNode(joinedNode, msgs)
            #         # Communicate current view number if any view change
            #         # happened to the connected node
            #         if self.viewNo > 0:
            #             logger.debug("{} communicating view number {} to {}"
            #                          .format(self, self.viewNo-1, joinedNode))
            #             rid = self.nodestack.getRemote(joinedNode).uid
            #             self.send(
            #                 self._create_instance_change_msg(self.viewNo, 0),
            #                 rid)
            # TODO: Make sure newly joined nodes are able to select the
            # correct primary
            for n in joined:
                msgs = self.elector.get_msgs_for_lagged_nodes()
                self.sendElectionMsgsToLaggingNode(n, msgs)

        # Send ledger status whether ready (connected to enough nodes) or not
        for n in joined:
            self.send_ledger_status_to_newly_connected_node(n)

    def ask_for_ledger_status(self, node_name: str):

        def send_request_for_ledger_status(ledger_id):
            req = ReqLedgerStatus(ledger_id)
            rid = self.nodestack.getRemote(node_name).uid
            self.send(req, rid)
            logger.debug("{} asking {} for ledger status of ledger {}"
                         .format(self, node_name, ledger_id))

        for ledger in [POOL_LEDGER_ID, DOMAIN_LEDGER_ID]:
            self.ledgerManager.setLedgerCanSync(ledger, True)
            send_request_for_ledger_status(ledger)

    def processReqLedgerStatus(self, request: ReqLedgerStatus, frm: str):
        ledger = request.ledgerId
        send = {
            POOL_LEDGER_ID: self.sendPoolLedgerStatus,
            DOMAIN_LEDGER_ID: self.sendDomainLedgerStatus
        }.get(ledger)
        logger.debug("{} cannot send ledger status to {} for unknow ledger {}"
                     .format(self, frm, ledger))
        send(frm)

    def send_ledger_status_to_newly_connected_node(self, node_name):
        self.sendPoolLedgerStatus(node_name)
        # Send the domain ledger status only when it has discovered enough
        # peers otherwise very few peers will know that this node is lagging
        # behind and it will not receive sufficient consistency proofs to
        # verify the exact state of the ledger.
        if self.mode in (Mode.discovered, Mode.participating):
            self.sendDomainLedgerStatus(node_name)

    def newNodeJoined(self, txn):
        self.setF()
        new_replicas = self.adjustReplicas()
        if new_replicas > 0:
            self.elector.decidePrimaries()

    def nodeLeft(self, txn):
        self.setF()
        self.adjustReplicas()

    def sendPoolInfoToClients(self, txn):
        logger.debug("{} sending new node info {} to all clients".format(self,
                                                                         txn))
        msg = PoolLedgerTxns(txn)
        self.clientstack.transmitToClients(msg,
                                           list(self.clientstack.connectedClients))

    @property
    def clientStackName(self):
        return self.getClientStackNameOfNode(self.name)

    @staticmethod
    def getClientStackNameOfNode(nodeName: str):
        return nodeName + CLIENT_STACK_SUFFIX

    def getClientStackHaOfNode(self, nodeName: str) -> HA:
        return self.cliNodeReg.get(self.getClientStackNameOfNode(nodeName))

    def sendElectionMsgsToLaggingNode(self, nodeName: str, msgs: List[Any]):
        rid = self.nodestack.getRemote(nodeName).uid
        for msg in msgs:
            logger.debug("{} sending election message {} to lagged node {}".
                         format(self, msg, nodeName))
            self.send(msg, rid)

    def _statusChanged(self, old: Status, new: Status) -> None:
        """
        Perform some actions based on whether this node is ready or not.

        :param old: the previous status
        :param new: the current status
        """
        pass

    def checkInstances(self) -> None:
        # TODO: Is this method really needed?
        """
        Check if this node has the minimum required number of protocol
        instances, i.e. f+1. If not, add a replica. If no election is in
        progress, this node will try to nominate one of its replicas as primary.
        This method is called whenever a connection with a  new node is
        established.
        """
        logger.debug("{} choosing to start election on the basis of count {} "
                     "and nodes {}".format(self, self.connectedNodeCount,
                                           self.nodestack.conns))

    def adjustReplicas(self):
        """
        Add or remove replicas depending on `f`
        """
        newReplicas = 0
        while len(self.replicas) < self.requiredNumberOfInstances:
            self.addReplica()
            newReplicas += 1
            self.processStashedMsgsForReplica(len(self.replicas)-1)

        while len(self.replicas) > self.requiredNumberOfInstances:
            self.removeReplica()
            newReplicas -= 1

        pop_keys(self.msgsForFutureReplicas, lambda x: x < len(self.replicas))
        return newReplicas

    def _dispatch_stashed_msg(self, msg, frm):
        if isinstance(msg, (ElectionType, ViewChangeDone)):
            self.sendToElector(msg, frm)
            return True
        elif isinstance(msg, ThreePhaseType):
            self.sendToReplica(msg, frm)
            return True
        else:
            return False

    def processStashedMsgsForReplica(self, instId: int):
        if instId not in self.msgsForFutureReplicas:
            return
        i = 0
        while self.msgsForFutureReplicas[instId]:
            msg, frm = self.msgsForFutureReplicas[instId].popleft()
            if not self._dispatch_stashed_msg(msg, frm):
                self.discard(msg, reason="Unknown message type for replica id "
                                         "{}".format(instId),
                             logMethod=logger.warning)
            i += 1
        logger.debug("{} processed {} stashed msgs for replica {}".
                     format(self, i, instId))

    def processStashedMsgsForView(self, view_no: int):
        if view_no not in self.msgsForFutureViews:
            return
        i = 0
        while self.msgsForFutureViews[view_no]:
            msg, frm = self.msgsForFutureViews[view_no].popleft()
            if not self._dispatch_stashed_msg(msg, frm):
                self.discard(msg, reason="Unknown message type for view no "
                                         "{}".format(view_no),
                             logMethod=logger.warning)
            i += 1
        logger.debug("{} processed {} stashed msgs for view no {}".
                     format(self, i, view_no))

    def decidePrimaries(self):
        """
        Choose the primary replica for each protocol instance in the system
        using a PrimaryDecider.
        """
        self.elector.decidePrimaries()

    def _check_view_change_completed(self):
        """
        This thing checks whether new primary was elected.
        If it was not - starts view change again
        """

        if self.view_change_in_progress:
            next_view_no = self.viewNo + 1
            logger.debug("view change to view {} is not completed in time, "
                         "starting view change for view {}"
                         .format(self.viewNo, next_view_no))
            self.do_view_change_if_possible(next_view_no)

    def createReplica(self, instId: int, isMaster: bool) -> 'replica.Replica':
        """
        Create a new replica with the specified parameters.
        This is a convenience method used to create replicas from a node
        instead of passing in replicas in the Node's constructor.

        :param instId: protocol instance number
        :param isMaster: does this replica belong to the master protocol
            instance?
        :return: a new instance of Replica
        """
        return replica.Replica(self, instId, isMaster)

    def addReplica(self):
        """
        Create and add a new replica to this node.
        If this is the first replica on this node, it will belong to the Master
        protocol instance.
        """
        instId = len(self.replicas)
        if len(self.replicas) == 0:
            isMaster = True
            instDesc = "master"
        else:
            isMaster = False
            instDesc = "backup"
        replica = self.createReplica(instId, isMaster)
        self.replicas.append(replica)
        self.msgsToReplicas.append(deque())
        self.monitor.addInstance()
        logger.display("{} added replica {} to instance {} ({})".
                       format(self, replica, instId, instDesc),
                       extra={"tags": ["node-replica"]})
        return replica

    def removeReplica(self):
        replica = self.replicas[-1]
        self.replicas = self.replicas[:-1]
        self.msgsToReplicas = self.msgsToReplicas[:-1]
        self.monitor.addInstance()
        logger.display("{} removed replica {} from instance {}".
                       format(self, replica, replica.instId),
                       extra={"tags": ["node-replica"]})
        return replica

    def serviceReplicaMsgs(self, limit: int=None) -> int:
        """
        Process `limit` number of replica messages.
        Here processing means appending to replica inbox.

        :param limit: the maximum number of replica messages to process
        :return: the number of replica messages processed
        """
        msgCount = 0
        for idx, replicaMsgs in enumerate(self.msgsToReplicas):
            while replicaMsgs and (not limit or msgCount < limit):
                msgCount += 1
                msg = replicaMsgs.popleft()
                self.replicas[idx].inBox.append(msg)
        return msgCount

    async def serviceReplicaOutBox(self, limit: int=None) -> int:
        """
        Process `limit` number of replica messages.
        Here processing means appending to replica inbox.

        :param limit: the maximum number of replica messages to process
        :return: the number of replica messages processed
        """
        msgCount = 0
        for replica in self.replicas:
            while replica.outBox and (not limit or msgCount < limit):
                msgCount += 1
                msg = replica.outBox.popleft()
                if isinstance(msg, (PrePrepare,
                                    Prepare,
                                    Commit,
                                    Checkpoint)):
                    self.send(msg)
                elif isinstance(msg, Ordered):
                    if self.isParticipating:
                        self.processOrdered(msg)
                    else:
                        logger.debug("{} stashing {} since mode is {}".
                                     format(self, msg, self.mode))
                        self.stashedOrderedReqs.append(msg)
                elif isinstance(msg, Reject):
                    reqKey = (msg.identifier, msg.reqId)
                    reject = Reject(*reqKey,
                                    self.reasonForClientFromException(msg.reason))
                    self.transmitToClient(reject, self.requestSender[reqKey])
                    self.doneProcessingReq(*reqKey)
                elif isinstance(msg, Exception):
                    self.processEscalatedException(msg)
                else:
                    logger.error("Received msg {} and don't know how to handle "
                                 "it".format(msg))
        return msgCount

    def serviceReplicaInBox(self, limit: int=None):
        """
        Process `limit` number of messages in the replica inbox for each replica
        on this node.

        :param limit: the maximum number of replica messages to process
        :return: the number of replica messages processed successfully
        """
        msgCount = 0
        for replica in self.replicas:
            msgCount += replica.serviceQueues(limit)
        return msgCount

    def serviceElectorOutBox(self, limit: int=None) -> int:
        """
        Service at most `limit` number of messages from the elector's outBox.

        :return: the number of messages successfully serviced.
        """
        msgCount = 0
        while self.elector.outBox and (not limit or msgCount < limit):
            msgCount += 1
            msg = self.elector.outBox.popleft()
            if isinstance(msg, (ElectionType, ViewChangeDone)):
                self.send(msg)
            elif isinstance(msg, BlacklistMsg):
                nodeName = getattr(msg, f.NODE_NAME.nm)
                code = getattr(msg, f.SUSP_CODE.nm)
                self.reportSuspiciousNode(nodeName, code=code)
            else:
                logger.error("Received msg {} and don't know how to handle it".
                             format(msg))
        return msgCount

    async def serviceElectorInbox(self, limit: int=None) -> int:
        """
        Service at most `limit` number of messages from the elector's outBox.

        :return: the number of messages successfully serviced.
        """
        msgCount = 0
        while self.msgsToElector and (not limit or msgCount < limit):
            msgCount += 1
            msg = self.msgsToElector.popleft()
            self.elector.inBox.append(msg)
        await self.elector.serviceQueues(limit)
        return msgCount

    @property
    def hasPrimary(self) -> bool:
        """
        Does this node have a primary replica?

        :return: whether this node has a primary
        """
        return any(replica.isPrimary for replica in self.replicas)

    @property
    def primaryReplicaNo(self) -> Optional[int]:
        """
        Return the index of the primary or None if there's no primary among the
        replicas on this node.

        :return: index of the primary
        """
        if self._primary_replica_no is None:
            for idx, replica in enumerate(self.replicas):
                if replica.isPrimary:
                    self._primary_replica_no = idx
                    return idx
        return self._primary_replica_no

    @property
    def master_primary_name(self) -> Optional[str]:
        """
        Return the name of the primary node of the master instance
        """

        master_primary_name = self.master_replica.primaryName
        if master_primary_name:
            return self.master_replica.getNodeName(master_primary_name)
        return None

    @property
    def master_last_ordered_3PC(self) -> Tuple[int, int]:
        return self.master_replica.last_ordered_3pc

    @property
    def master_replica(self):
        return self.replicas[0]

    @staticmethod
    def is_valid_view_or_inst(n):
        return not(n is None or not isinstance(n, int) or n < 0)

    def msgHasAcceptableInstId(self, msg, frm) -> bool:
        """
        Return true if the instance id of message corresponds to a correct
        replica.

        :param msg: the node message to validate
        :return:
        """
        instId = getattr(msg, f.INST_ID.nm, None)
        if not self.is_valid_view_or_inst(instId):
            return False
        if instId >= len(self.msgsToReplicas):
            if instId not in self.msgsForFutureReplicas:
                self.msgsForFutureReplicas[instId] = deque()
            self.msgsForFutureReplicas[instId].append((msg, frm))
            logger.debug("{} queueing message {} for future protocol "
                         "instance {}".format(self, msg, instId))
            return False
        return True

    def msgHasAcceptableViewNo(self, msg, frm) -> bool:
        """
        Return true if the view no of message corresponds to the current view
        no or a view no in the future
        :param msg: the node message to validate
        :return:
        """
        viewNo = getattr(msg, f.VIEW_NO.nm, None)
        if not self.is_valid_view_or_inst(viewNo):
            return False
        if self.viewNo - viewNo > 1:
            self.discard(msg, "un-acceptable viewNo {}"
                         .format(viewNo), logMethod=logger.info)
        elif viewNo > self.viewNo:
            if viewNo not in self.msgsForFutureViews:
                self.msgsForFutureViews[viewNo] = deque()
            logger.debug('{} stashing a message for a future view: {}'.
                         format(self, msg))
            self.msgsForFutureViews[viewNo].append((msg, frm))
        else:
            return True
        return False

    def sendToReplica(self, msg, frm):
        """
        Send the message to the intended replica.

        :param msg: the message to send
        :param frm: the name of the node which sent this `msg`
        """
        if self.msgHasAcceptableInstId(msg, frm) and \
                self.msgHasAcceptableViewNo(msg, frm):
            self.msgsToReplicas[msg.instId].append((msg, frm))

    def sendToElector(self, msg, frm):
        """
        Send the message to the intended elector.

        :param msg: the message to send
        :param frm: the name of the node which sent this `msg`
        """
        if self.msgHasAcceptableInstId(msg, frm) and \
                self.msgHasAcceptableViewNo(msg, frm):
            logger.debug("{} sending message to elector: {}".
                         format(self, (msg, frm)))
            self.msgsToElector.append((msg, frm))

    def handleOneNodeMsg(self, wrappedMsg):
        """
        Validate and process one message from a node.

        :param wrappedMsg: Tuple of message and the name of the node that sent
        the message
        """
        try:
            vmsg = self.validateNodeMsg(wrappedMsg)
            if vmsg:
                logger.info("{} msg validated {}".format(self, wrappedMsg),
                            extra={"tags": ["node-msg-validation"]})
                self.unpackNodeMsg(*vmsg)
            else:
                logger.info("{} invalidated msg {}".format(self, wrappedMsg),
                            extra={"tags": ["node-msg-validation"]})
        except SuspiciousNode as ex:
            self.reportSuspiciousNodeEx(ex)
        except Exception as ex:
            msg, frm = wrappedMsg
            self.discard(msg, ex)

    def validateNodeMsg(self, wrappedMsg):
        """
        Validate another node's message sent to this node.

        :param wrappedMsg: Tuple of message and the name of the node that sent
        the message
        :return: Tuple of message from node and name of the node
        """
        msg, frm = wrappedMsg
        if self.isNodeBlacklisted(frm):
            self.discard(msg, "received from blacklisted node {}"
                         .format(frm), logger.info)
            return None

        op = msg.pop(OP_FIELD_NAME, None)
        if not op:
            raise MissingNodeOp
        cls = TaggedTuples.get(op, None)
        if not cls:
            raise InvalidNodeOp(op)
        try:
            cMsg = cls(**msg)
        except Exception as ex:
            raise InvalidNodeMsg(str(ex))
        try:
            self.verifySignature(cMsg)
        except BaseExc as ex:
            raise SuspiciousNode(frm, ex, cMsg) from ex
        logger.debug("{} received node message from {}: {}".
                     format(self, frm, cMsg),
                     extra={"cli": False})
        return cMsg, frm

    def unpackNodeMsg(self, msg, frm) -> None:
        """
        If the message is a batch message validate each message in the batch,
        otherwise add the message to the node's inbox.

        :param msg: a node message
        :param frm: the name of the node that sent this `msg`
        """
        if isinstance(msg, Batch):
            logger.debug("{} processing a batch {}".format(self, msg))
            for m in msg.messages:
                m = self.nodestack.deserializeMsg(m)
                self.handleOneNodeMsg((m, frm))
        else:
            self.postToNodeInBox(msg, frm)

    def postToNodeInBox(self, msg, frm):
        """
        Append the message to the node inbox

        :param msg: a node message
        :param frm: the name of the node that sent this `msg`
        """
        logger.debug("{} appending to nodeInbox {}".format(self, msg))
        self.nodeInBox.append((msg, frm))

    async def processNodeInBox(self):
        """
        Process the messages in the node inbox asynchronously.
        """
        while self.nodeInBox:
            m = self.nodeInBox.popleft()

            msg, frm = m
            # if self.__message_filter_engine.filter_node_to_node(msg):
            #     continue

            try:
                await self.nodeMsgRouter.handle(m)
            except SuspiciousNode as ex:
                self.reportSuspiciousNodeEx(ex)
                self.discard(m, ex)

    def handleOneClientMsg(self, wrappedMsg):
        """
        Validate and process a client message

        :param wrappedMsg: a message from a client
        """
        try:
            vmsg = self.validateClientMsg(wrappedMsg)
            if vmsg:
                self.unpackClientMsg(*vmsg)
        except BlowUp:
            raise
        except Exception as ex:
            msg, frm = wrappedMsg
            friendly = friendlyEx(ex)
            if isinstance(ex, SuspiciousClient):
                self.reportSuspiciousClient(frm, friendly)

            self.handleInvalidClientMsg(ex, wrappedMsg)

    def handleInvalidClientMsg(self, ex, wrappedMsg):
        msg, frm = wrappedMsg
        exc = ex.__cause__ if ex.__cause__ else ex
        friendly = friendlyEx(ex)
        reason = self.reasonForClientFromException(ex)
        if isinstance(msg, Request):
            msg = msg.__getstate__()
        identifier = msg.get(f.IDENTIFIER.nm)
        reqId = msg.get(f.REQ_ID.nm)
        if not reqId:
            reqId = getattr(exc, f.REQ_ID.nm, None)
            if not reqId:
                reqId = getattr(ex, f.REQ_ID.nm, None)
        self.transmitToClient(RequestNack(identifier, reqId, reason), frm)
        self.discard(wrappedMsg, friendly, logger.warning, cliOutput=True)

    def validateClientMsg(self, wrappedMsg):
        """
        Validate a message sent by a client.

        :param wrappedMsg: a message from a client
        :return: Tuple of clientMessage and client address
        """
        msg, frm = wrappedMsg
        if self.isClientBlacklisted(frm):
            self.discard(msg, "received from blacklisted client {}"
                         .format(frm), logger.info)
            return None

        if all(attr in msg.keys()
               for attr in [OPERATION, f.IDENTIFIER.nm, f.REQ_ID.nm]):
            self.doStaticValidation(msg[f.IDENTIFIER.nm],
                                    msg[f.REQ_ID.nm],
                                    msg[OPERATION])
            cls = self._client_request_class
        elif OP_FIELD_NAME in msg:
            op = msg.pop(OP_FIELD_NAME)
            cls = TaggedTuples.get(op, None)
            if not cls:
                raise InvalidClientOp(op, msg.get(f.REQ_ID.nm))
            if cls not in (Batch, LedgerStatus, CatchupReq):
                raise InvalidClientMsgType(cls, msg.get(f.REQ_ID.nm))
        else:
            raise InvalidClientRequest(msg.get(f.IDENTIFIER.nm),
                                       msg.get(f.REQ_ID.nm))
        try:
            cMsg = cls(**msg)
        except TypeError as ex:
            raise InvalidClientRequest(msg.get(f.IDENTIFIER.nm),
                                       msg.get(f.REQ_ID.nm),
                                       str(ex))
        except Exception as ex:
            raise InvalidClientRequest(msg.get(f.IDENTIFIER.nm),
                                       msg.get(f.REQ_ID.nm)) from ex

        if self.isSignatureVerificationNeeded(msg):
            self.verifySignature(cMsg)
            # Suspicions should only be raised when lot of sig failures are
            # observed
            # try:
            #     self.verifySignature(cMsg)
            # except UnknownIdentifier as ex:
            #     raise
            # except Exception as ex:
            #     raise SuspiciousClient from ex
        logger.trace("{} received CLIENT message: {}".
                     format(self.clientstack.name, cMsg))
        return cMsg, frm

    def unpackClientMsg(self, msg, frm):
        """
        If the message is a batch message validate each message in the batch,
        otherwise add the message to the node's clientInBox.

        :param msg: a client message
        :param frm: the name of the client that sent this `msg`
        """
        if isinstance(msg, Batch):
            for m in msg.messages:
                # This check is done since Client uses NodeStack (which can
                # send and receive BATCH) to talk to nodes but Node uses
                # ClientStack (which cannot send or receive BATCH).
                # TODO: The solution is to have both kind of stacks be able to
                # parse BATCH messages
                if m in (ZStack.pingMessage, ZStack.pongMessage):
                    continue
                m = self.clientstack.deserializeMsg(m)
                self.handleOneClientMsg((m, frm))
        else:
            self.postToClientInBox(msg, frm)

    def postToClientInBox(self, msg, frm):
        """
        Append the message to the node's clientInBox

        :param msg: a client message
        :param frm: the name of the node that sent this `msg`
        """
        self.clientInBox.append((msg, frm))

    async def processClientInBox(self):
        """
        Process the messages in the node's clientInBox asynchronously.
        All messages in the inBox have already been validated, including
        signature check.
        """
        while self.clientInBox:
            m = self.clientInBox.popleft()
            req, frm = m
            logger.display("{} processing {} request {}".
                           format(self.clientstack.name, frm, req),
                           extra={"cli": True,
                                  "tags": ["node-msg-processing"]})

            # filtered = self.__message_filter_engine.filter_client_to_node(req)
            # if filtered:
            #     self._reject_msg(req, frm, filtered)
            #     continue

            try:
                await self.clientMsgRouter.handle(m)
            except InvalidClientMessageException as ex:
                self.handleInvalidClientMsg(ex, m)

    def _reject_msg(self, msg, frm, reason):
        reqKey = (msg.identifier, msg.reqId)
        reject = Reject(*reqKey,
                        reason)
        self.transmitToClient(reject, frm)

    def postPoolLedgerCaughtUp(self, **kwargs):
        self.mode = Mode.discovered
        # The node might have discovered more nodes, so see if schedule
        # election if needed.
        if isinstance(self.poolManager, TxnPoolManager):
            self.checkInstances()

        # TODO: why we do it this way?
        # Initialising node id in case where node's information was not present
        # in pool ledger at the time of starting, happens when a non-genesis
        # node starts
        self.id
        self.catchup_next_ledger_after_pool()

    def catchup_next_ledger_after_pool(self):
        self.start_domain_ledger_sync()

    def start_domain_ledger_sync(self):
        self.ledgerManager.setLedgerCanSync(DOMAIN_LEDGER_ID, True)
        for nm in self.nodestack.connecteds:
            self.sendDomainLedgerStatus(nm)
        self.ledgerManager.processStashedLedgerStatuses(DOMAIN_LEDGER_ID)

    def postDomainLedgerCaughtUp(self, **kwargs):
        """
        Process any stashed ordered requests and set the mode to
        `participating`
        :return:
        """
        pass

    def preLedgerCatchUp(self, ledger_id):
        # make the node Syncing
        self.mode = Mode.syncing

        # revert uncommitted txns and state for unordered requests
        self.replicas[0].revert_unordered_batches(ledger_id)

    def postTxnFromCatchupAddedToLedger(self, ledgerId: int, txn: Any):
        rh = self.postRecvTxnFromCatchup(ledgerId, txn)
        if rh:
            rh.updateState([txn], isCommitted=True)
            state = self.getState(ledgerId)
            state.commit(rootHash=state.headHash)
        self.updateSeqNoMap([txn])

    def postRecvTxnFromCatchup(self, ledgerId: int, txn: Any):
        rh = None
        if ledgerId == POOL_LEDGER_ID:
            self.poolManager.onPoolMembershipChange(txn)
            rh = self.poolManager.reqHandler
        if ledgerId == DOMAIN_LEDGER_ID:
            self.post_txn_from_catchup_added_to_domain_ledger(txn)
            rh = self.reqHandler
        return rh

    # TODO: should be renamed to `post_all_ledgers_caughtup`
    def allLedgersCaughtUp(self):
        last_caught_up_3PC = self.ledgerManager.last_caught_up_3PC
        if compare_3PC_keys(self.master_last_ordered_3PC,
                            last_caught_up_3PC) > 0:
            self.master_replica.caught_up_till_3pc(last_caught_up_3PC)
            logger.debug('{} caught up till {}'.format(self,
                                                       last_caught_up_3PC))

        # TODO: Maybe a slight optimisation is to check result of
        # `self.num_txns_caught_up_in_last_catchup()`
        self.processStashedOrderedReqs()

        if self.is_catchup_needed():
            logger.debug('{} needs to catchup again'.format(self))
            self.start_catchup()
        else:
            logger.debug('{} does not need any more catchups'.format(self))
            self.no_more_catchups_needed()

    def is_catchup_needed(self) -> bool:
        """
        Check if received a quorum of view change done messages and if yes
        check if caught up till the
        Check if all requests ordered till last prepared certificate
        Check if last catchup resulted in no txns
        """
        if self.caught_up_for_current_view():
            logger.info('{} is caught up for the current view {}'.format(self, self.viewNo))
            return False
        logger.debug('{} is not caught up for the current view {}'.format(self, self.viewNo))
        if self.has_ordered_till_last_prepared_certificate() and \
                        self.num_txns_caught_up_in_last_catchup() == 0:
            return False

        return True

    def caught_up_for_current_view(self):
        if not self.elector._hasViewChangeQuorum(0):
            logger.debug('{} does not have view change quorum for view {}'.
                         format(self, self.viewNo))
            return False
        vc = self.elector.has_sufficient_same_view_change_done_messages(0)
        if not vc:
            logger.debug('{} does not have acceptable ViewChangeDone for '
                         'view {}'.format(self, self.viewNo))
            return False
        ledger_info = vc[1]
        for lid, size, root_hash in ledger_info:
            ledger = self.ledgerManager.ledgerRegistry[lid].ledger
            if size == 0:
                continue
            if ledger.size < size:
                return False
            if ledger.hashToStr(ledger.tree.merkle_tree_hash(0, size)) != root_hash:
                return False
        return True

    def has_ordered_till_last_prepared_certificate(self):
        lst = self.master_replica.last_prepared_before_view_change
        if lst is None:
            return True
        return compare_3PC_keys(lst, self.master_replica.last_ordered_3pc) >= 0

    def num_txns_caught_up_in_last_catchup(self):
        count = sum([l.num_txns_caught_up for l in
                    self.ledgerManager.ledgerRegistry.values()])
        logger.debug('{} caught up to {} txns in the last catchup'.format(self, count))
        return count

    def no_more_catchups_needed(self):
        # This method is called when no more catchups needed
        self.mode = Mode.participating
        # self.processStashedOrderedReqs()
        self.decidePrimaries()

    def getLedger(self, ledgerId):
        return self.ledgerManager.getLedgerInfoByType(ledgerId).ledger

    def getState(self, ledgerId):
        return self.states.get(ledgerId)

    def post_txn_from_catchup_added_to_domain_ledger(self, txn):
        if txn.get(TXN_TYPE) == NYM:
            self.addNewRole(txn)

    def sendPoolLedgerStatus(self, nodeName):
        self.sendLedgerStatus(nodeName, POOL_LEDGER_ID)

    def sendDomainLedgerStatus(self, nodeName):
        self.sendLedgerStatus(nodeName, DOMAIN_LEDGER_ID)

    def getLedgerStatus(self, ledgerId: int):
        if ledgerId == POOL_LEDGER_ID:
            return self.poolLedgerStatus
        if ledgerId == DOMAIN_LEDGER_ID:
            return self.domainLedgerStatus

    def sendLedgerStatus(self, nodeName: str, ledgerId: int):
        ledgerStatus = self.getLedgerStatus(ledgerId)
        if ledgerStatus:
            rid = self.nodestack.getRemote(nodeName).uid
            self.send(ledgerStatus, rid)
        else:
            logger.debug("{} not sending ledger {} status to {} as it is null"
                         .format(self, ledgerId, nodeName))

    def doStaticValidation(self, identifier, reqId, operation):
        if TXN_TYPE not in operation:
            raise InvalidClientRequest(identifier, reqId)

        if operation.get(TXN_TYPE) in POOL_TXN_TYPES:
            self.poolManager.doStaticValidation(identifier, reqId, operation)

        if self.opVerifiers:
            try:
                for v in self.opVerifiers:
                    v.verify(operation)
            except Exception as ex:
                raise InvalidClientRequest(identifier, reqId) from ex

    def doDynamicValidation(self, request: Request):
        """
        State based validation
        """
        if self.ledgerIdForRequest(request) == POOL_LEDGER_ID:
            self.poolManager.doDynamicValidation(request)
        else:
            self.domainDynamicValidation(request)

    def applyReq(self, request: Request):
        """
        Apply request to appropriate ledger and state
        """
        if self.ledgerIdForRequest(request) == POOL_LEDGER_ID:
            return self.poolManager.applyReq(request)
        else:
            return self.domainRequestApplication(request)

    def domainDynamicValidation(self, request: Request):
        self.reqHandler.validate(request, self.config)

    def domainRequestApplication(self, request: Request):
        return self.reqHandler.apply(request)

    def processRequest(self, request: Request, frm: str):
        """
        Handle a REQUEST from the client.
        If the request has already been executed, the node re-sends the reply to
        the client. Otherwise, the node acknowledges the client request, adds it
        to its list of client requests, and sends a PROPAGATE to the
        remaining nodes.

        :param request: the REQUEST from the client
        :param frm: the name of the client that sent this REQUEST
        """
        logger.debug("{} received client request: {} from {}".
                     format(self.name, request, frm))
        self.nodeRequestSpikeMonitorData['accum'] += 1

        # TODO: What if client sends requests with same request id quickly so
        # before reply for one is generated, the other comes. In that
        # case we need to keep track of what requests ids node has seen
        # in-memory and once request with a particular request id is processed,
        # it should be removed from that in-memory DS.

        # If request is already processed(there is a reply for the
        # request in
        # the node's transaction store then return the reply from the
        # transaction store)
        # TODO: What if the reply was a REQNACK? Its not gonna be found in the
        # replies.

        ledgerId = self.ledgerIdForRequest(request)
        ledger = self.getLedger(ledgerId)
        reply = self.getReplyFromLedger(ledger, request)
        if reply:
            logger.debug("{} returning REPLY from already processed "
                         "REQUEST: {}".format(self, request))
            self.transmitToClient(reply, frm)
        else:
            if not self.isProcessingReq(*request.key):
                self.startedProcessingReq(*request.key, frm)
            # If not already got the propagate request(PROPAGATE) for the
            # corresponding client request(REQUEST)
            self.recordAndPropagate(request, frm)
            self.transmitToClient(RequestAck(*request.key), frm)

    # noinspection PyUnusedLocal
    def processPropagate(self, msg: Propagate, frm):
        """
        Process one propagateRequest sent to this node asynchronously

        - If this propagateRequest hasn't been seen by this node, then broadcast
        it to all nodes after verifying the the signature.
        - Add the client to blacklist if its signature is invalid

        :param msg: the propagateRequest
        :param frm: the name of the node which sent this `msg`
        """
        logger.debug("Node {} received propagated request: {}".
                     format(self.name, msg))
        reqDict = msg.request
        request = SafeRequest(**reqDict)

        clientName = msg.senderClient

        if not self.isProcessingReq(*request.key):
            self.startedProcessingReq(*request.key, clientName)
        self.requests.addPropagate(request, frm)

        # # Only propagate if the node is participating in the consensus process
        # # which happens when the node has completed the catchup process
        self.propagate(request, clientName)
        self.tryForwarding(request)

    def startedProcessingReq(self, identifier, reqId, frm):
        self.requestSender[identifier, reqId] = frm

    def isProcessingReq(self, identifier, reqId) -> bool:
        return (identifier, reqId) in self.requestSender

    def doneProcessingReq(self, identifier, reqId):
        self.requestSender.pop((identifier, reqId))

    def processOrdered(self, ordered: Ordered):
        """
        Process and orderedRequest.

        Execute client request with retries if client request hasn't yet reached
        this node but corresponding PROPAGATE, PRE-PREPARE, PREPARE and
        COMMIT request did

        :param ordered: an orderedRequest
        :param retryNo: the retry number used in recursion
        :return: True if successful, None otherwise
        """

        inst_id, view_no, req_idrs, pp_seq_no, pp_time, ledger_id, \
            state_root, txn_root = tuple(ordered)

        # Only the request ordered by master protocol instance are executed by
        # the client
        r = None
        if inst_id == self.instances.masterId:
            reqs = [self.requests[i, r].finalised for (i, r) in req_idrs
                    if (i, r) in self.requests and self.requests[i, r].finalised]
            if len(reqs) == len(req_idrs):
                logger.debug("{} executing Ordered batch {} {} of {} requests".
                             format(self.name, view_no, pp_seq_no, len(req_idrs)))
                self.executeBatch(view_no, pp_seq_no, pp_time, reqs, ledger_id,
                                  state_root, txn_root)
                r = True
            else:
                logger.warning('{} did not find {} finalized requests, but '
                               'still ordered'.format(self, len(req_idrs) -
                                                      len(reqs)))
                return None
        else:
            logger.trace("{} got ordered requests from backup replica {}".
                         format(self, inst_id))
            r = False
        self.monitor.requestOrdered(req_idrs, inst_id, byMaster=r)
        return r

    def processEscalatedException(self, ex):
        """
        Process an exception escalated from a Replica
        """
        if isinstance(ex, SuspiciousNode):
            self.reportSuspiciousNodeEx(ex)
        else:
            raise RuntimeError("unhandled replica-escalated exception") from ex

    def processInstanceChange(self, instChg: InstanceChange, frm: str) -> None:
        """
        Validate and process an instance change request.

        :param instChg: the instance change request
        :param frm: the name of the node that sent this `msg`
        """
        logger.debug("{} received instance change request: {} from {}".
                     format(self, instChg, frm))

        # TODO: add sender to blacklist?
        if not isinstance(instChg.viewNo, int):
            self.discard(instChg, "field viewNo has incorrect type: {}".
                         format(type(instChg.viewNo)))
        elif instChg.viewNo <= self.viewNo:
            self.discard(instChg,
                         "Received instance change request with view no {} "
                         "which is not more than its view no {}".
                         format(instChg.viewNo, self.viewNo), logger.debug)
        else:
            # Record instance changes for views but send instance change
            # only when found master to be degraded. if quorum of view changes
            #  found then change view even if master not degraded
            if not self.instanceChanges.hasInstChngFrom(instChg.viewNo, frm):
                self._record_inst_change_msg(instChg, frm)

            if self.monitor.isMasterDegraded() and not \
                    self.instanceChanges.hasInstChngFrom(instChg.viewNo,
                                                         self.name):
                logger.info(
                    "{} found master degraded after receiving instance change "
                    "message from {}".format(self, frm))
                self.sendInstanceChange(instChg.viewNo)
            else:
                logger.debug(
                    "{} received instance change message {} but did not "
                    "find the master to be slow or has already sent an instance"
                    " change message".format(self, instChg))

    def do_view_change_if_possible(self, view_no):
        # TODO: Need to handle skewed distributions which can arise due to
        # malicious nodes sending messages early on
        can, whyNot = self.canViewChange(view_no)
        if can:
            logger.info("{} initiating a view change to {} from {}".
                        format(self, view_no, self.viewNo))
            self.startViewChange(view_no)
        else:
            logger.debug(whyNot)
        return can

    def checkPerformance(self):
        """
        Check if master instance is slow and send an instance change request.
        :returns True if master performance is OK, otherwise False
        """
        logger.trace("{} checking its performance".format(self))

        # Move ahead only if the node has synchronized its state with other
        # nodes
        if not self.isParticipating:
            return

        if self.instances.masterId is not None:
            self.sendNodeRequestSpike()
            if self.monitor.isMasterDegraded():
                self.sendInstanceChange(self.viewNo+1)
                logger.debug('{} sent view change since performance degraded '
                             'of master instance'.format(self))
                self.do_view_change_if_possible(self.viewNo+1)
                return False
            else:
                logger.debug("{}'s master has higher performance than backups".
                             format(self))
        return True

    def checkNodeRequestSpike(self):
        logger.debug("{} checking its request amount".format(self))

        if not self.isParticipating:
            return

        if self.instances.masterId is not None:
            self.sendNodeRequestSpike()

    def sendNodeRequestSpike(self):
        requests = self.nodeRequestSpikeMonitorData['accum']
        self.nodeRequestSpikeMonitorData['accum'] = 0
        return pluginManager.sendMessageUponSuspiciousSpike(
            notifierPluginTriggerEvents['nodeRequestSpike'],
            self.nodeRequestSpikeMonitorData,
            requests,
            self.config.notifierEventTriggeringConfig['nodeRequestSpike'],
            self.name
        )

    def _create_instance_change_msg(self, view_no, suspicion_code):
        return InstanceChange(view_no, suspicion_code)

    def _record_inst_change_msg(self, msg, frm):
        view_no = msg.viewNo
        self.instanceChanges.addVote(msg, frm)
        if msg.viewNo > self.viewNo:
            self.do_view_change_if_possible(view_no)

    def sendInstanceChange(self, view_no: int,
                           suspicion=Suspicions.PRIMARY_DEGRADED):
        """
        Broadcast an instance change request to all the remaining nodes

        :param view_no: the view number when the instance change is requested
        """

        # If not found any sent instance change messages in last
        # `ViewChangeWindowSize` seconds or the last sent instance change
        # message was sent long enough ago then instance change message can be
        # sent otherwise no.
        canSendInsChange, cooldown = self.insChngThrottler.acquire()

        if canSendInsChange:
            logger.info("{} sending an instance change with view_no {} since "
                        "{}".
                        format(self, view_no, suspicion.reason))
            logger.info("{} metrics for monitor: {}".
                        format(self, self.monitor.prettymetrics))
            msg = self._create_instance_change_msg(view_no, suspicion.code)
            self.send(msg)
            self._record_inst_change_msg(msg, self.name)
        else:
            logger.debug("{} cannot send instance change sooner then {} seconds"
                         .format(self, cooldown))

    # noinspection PyAttributeOutsideInit
    def initInsChngThrottling(self):
        windowSize = self.config.ViewChangeWindowSize
        ratchet = Ratchet(a=2, b=0.05, c=1, base=2, peak=windowSize)
        self.insChngThrottler = Throttler(windowSize, ratchet.get)

    @property
    def quorum(self) -> int:
        r"""
        Return the quorum of this RBFT system. Equal to :math:`2f + 1`.
        """
        return (2 * self.f) + 1

    def primary_found(self):
        # If the node has primary replica of master instance
        # TODO: 0 should be replaced with configurable constant
        self.monitor.hasMasterPrimary = self.primaryReplicaNo == 0
        if self.view_change_in_progress and self.all_instances_have_primary:
            self.on_view_change_complete(self.viewNo)

    @property
    def all_instances_have_primary(self):
        return all(r.primaryName is not None for r in self.replicas)

    def canViewChange(self, proposedViewNo: int) -> (bool, str):
        """
        Return whether there's quorum for view change for the proposed view
        number and its view is less than or equal to the proposed view
        """
        msg = None
        if not self.instanceChanges.hasQuorum(proposedViewNo, self.f):
            msg = '{} has no quorum for view {}'.format(self, proposedViewNo)
        elif not proposedViewNo > self.viewNo:
            msg = '{} is in higher view more than {}'.format(self, proposedViewNo)

        return not bool(msg), msg

    def propose_view_change(self):
        # Sends instance change message when primary has been
        # disconnected for long enough
        if self.lost_primary_at and \
                                time.perf_counter() - self.lost_primary_at \
                        >= self.config.ToleratePrimaryDisconnection:
            view_no = self.viewNo + 1
            self.sendInstanceChange(view_no,
                                    Suspicions.PRIMARY_DISCONNECTED)
            logger.debug('{} sent view change since was disconnected '
                         'from primary for too long'.format(self))
            self.do_view_change_if_possible(view_no)

    # TODO: consider moving this to pool manager
    def lost_master_primary(self):
        """
        Schedule an primary connection check which in turn can send a view
        change message
        :return: whether view change started
        """
        self.lost_primary_at = time.perf_counter()

        logger.debug('{} scheduling a view change in {} sec'.
                     format(self, self.config.ToleratePrimaryDisconnection))
        self._schedule(self.propose_view_change,
                       self.config.ToleratePrimaryDisconnection)

    def startViewChange(self, proposedViewNo: int):
        """
        Trigger the view change process.

        :param proposedViewNo: the new view number after view change.
        """
        # TODO: consider moving this to pool manager
        # TODO: view change is a special case, which can have different
        # implementations - we need to make this logic pluggable

        self.view_change_in_progress = True
        self._schedule(action=self._check_view_change_completed,
                       seconds=self._view_change_timeout)
        self.master_replica.on_view_change_start()
        self.viewNo = proposedViewNo
        logger.debug("{} resetting monitor stats after view change".
                     format(self))
        self.monitor.reset()
        self.processStashedMsgsForView(self.viewNo)
        # Now communicate the view change to the elector which will
        # contest primary elections across protocol all instances
        self.elector.view_change_started(self.viewNo)
        self._primary_replica_no = None
        pop_keys(self.msgsForFutureViews, lambda x: x <= self.viewNo)
        self.initInsChngThrottling()
        self.logNodeInfo()
        # Keep on doing catchup until >2f nodes LedgerStatus same on have a
        # prepared certificate the first PRE-PREPARE of the new view
        logger.info('{} changed to view {}, will start catchup now'.
                    format(self, self.viewNo))
        # TODO: Do not need to revert, keep the 3PC messages with
        # prepared certificate
        # self.master_replica.revert_unordered_batches()
        self.start_catchup()

    def on_view_change_complete(self, view_no):
        """
        View change completes for a replica when it has been decided which was
        the last ppSeqno and state and txn root for previous view
        """
        self.view_change_in_progress = False
        self.instanceChanges.pop(view_no-1, None)
        self.master_replica.on_view_change_done()

    def start_catchup(self):
        self.mode = Mode.starting
        self.ledgerManager.prepare_ledgers_for_sync()
        # TODO isinstance is not OK
        # if isinstance(self.poolManager, TxnPoolManager):
        #     status_sender = self.sendPoolLedgerStatus
        #     ledger_id = POOL_LEDGER_ID
        # else:
        #     status_sender = self.sendDomainLedgerStatus
        #     ledger_id = DOMAIN_LEDGER_ID

        for nm in self.nodeReg:
            try:
                self.ask_for_ledger_status(nm)
                # status_sender(nm)
            except RemoteNotFound:
                continue

    def ordered_prev_view_msgs(self, inst_id, pp_seqno):
        logger.debug('{} ordered previous view batch {} by instance {}'.
                     format(self, pp_seqno, inst_id))

    def verifySignature(self, msg):
        """
        Validate the signature of the request
        Note: Batch is whitelisted because the inner messages are checked

        :param msg: a message requiring signature verification
        :return: None; raises an exception if the signature is not valid
        """
        if isinstance(msg, self.authnWhitelist):
            return  # whitelisted message types rely on RAET for authn
        if isinstance(msg, Propagate):
            typ = 'propagate '
            req = msg.request
        else:
            typ = ''
            req = msg

        if not isinstance(req, Mapping):
            req = msg.as_dict

        identifier = self.authNr(req).authenticate(req)
        logger.info("{} authenticated {} signature on {} request {}".
                       format(self, identifier, typ, req['reqId']),
                       extra={"cli": True,
                              "tags": ["node-msg-processing"]})

    def authNr(self, req):
        return self.clientAuthNr

    def isSignatureVerificationNeeded(self, msg: Any):
        return True

    def three_phase_key_for_txn_seq_no(self, ledger_id, seq_no):
        if ledger_id in self.txn_seq_range_to_3phase_key:
            # point query in interval tree
            s = self.txn_seq_range_to_3phase_key[ledger_id][seq_no]
            if s:
                # There should not be more than one interval for any seq no in
                # the tree
                assert len(s) == 1
                return s.pop().data
        return None

    def executeBatch(self, view_no, pp_seq_no: int, pp_time: float,
                     reqs: List[Request], ledger_id, state_root,
                     txn_root) -> None:
        """
        Execute the REQUEST sent to this Node

        :param view_no: the view number (See glossary)
        :param pp_time: the time at which PRE-PREPARE was sent
        :param reqs: list of client REQUESTs
        """
        committedTxns = self.requestExecuter[ledger_id](pp_time, reqs,
                                                        state_root, txn_root)
        if committedTxns:
            first_txn_seq_no = committedTxns[0][F.seqNo.name]
            last_txn_seq_no = committedTxns[-1][F.seqNo.name]
            if ledger_id not in self.txn_seq_range_to_3phase_key:
                self.txn_seq_range_to_3phase_key[ledger_id] = IntervalTree()
            # adding one to end of range since its exclusive
            intrv_tree = self.txn_seq_range_to_3phase_key[ledger_id]
            intrv_tree[first_txn_seq_no:last_txn_seq_no+1] = (view_no, pp_seq_no)
            logger.debug('{} storing 3PC key {} for ledger {} range {}'.
                         format(self, (view_no, pp_seq_no), ledger_id,
                                (first_txn_seq_no, last_txn_seq_no)))
            if len(intrv_tree) > self.config.ProcessedBatchMapsToKeep:
                # Remove the first element from the interval tree
                old = intrv_tree[intrv_tree.begin()].pop()
                intrv_tree.remove(old)
                logger.debug('{} popped {} from txn to batch seqNo map'.
                             format(self, old))

    def updateSeqNoMap(self, committedTxns):
        self.seqNoDB.addBatch((txn[f.IDENTIFIER.nm], txn[f.REQ_ID.nm],
                               txn[F.seqNo.name]) for txn in committedTxns)

    def commitAndSendReplies(self, reqHandler, ppTime, reqs: List[Request],
                             stateRoot, txnRoot) -> List:
        committedTxns = reqHandler.commit(len(reqs), stateRoot, txnRoot)
        self.updateSeqNoMap(committedTxns)
        self.sendRepliesToClients(
            map(self.update_txn_with_extra_data, committedTxns),
            ppTime)
        return committedTxns

    def executeDomainTxns(self, ppTime, reqs: List[Request], stateRoot,
                          txnRoot) -> List:
        committedTxns = self.commitAndSendReplies(self.reqHandler, ppTime, reqs,
                                                  stateRoot, txnRoot)
        for txn in committedTxns:
            if txn[TXN_TYPE] == NYM:
                self.addNewRole(txn)
        return committedTxns

    def onBatchCreated(self, ledgerId, stateRoot):
        """
        A batch of requests has been created and has been applied but
        committed to ledger and state.
        :param ledgerId:
        :param stateRoot: state root after the batch creation
        :return:
        """
        if ledgerId == POOL_LEDGER_ID:
            if isinstance(self.poolManager, TxnPoolManager):
                self.poolManager.reqHandler.onBatchCreated(stateRoot)
        elif ledgerId == DOMAIN_LEDGER_ID:
            self.reqHandler.onBatchCreated(stateRoot)
        else:
            logger.debug('{} did not know how to handle for ledger {}'.
                         format(self, ledgerId))

    def onBatchRejected(self, ledgerId):
        """
        A batch of requests has been rejected, if stateRoot is None, reject
        the current batch.
        :param ledgerId:
        :param stateRoot: state root after the batch was created
        :return:
        """
        if ledgerId == POOL_LEDGER_ID:
            if isinstance(self.poolManager, TxnPoolManager):
                self.poolManager.reqHandler.onBatchRejected()
        elif ledgerId == DOMAIN_LEDGER_ID:
            self.reqHandler.onBatchRejected()
        else:
            logger.debug('{} did not know how to handle for ledger {}'.
                         format(self, ledgerId))

    @classmethod
    def ledgerId(cls, txnType: str):
        return POOL_LEDGER_ID if txnType in POOL_TXN_TYPES else DOMAIN_LEDGER_ID

    def sendRepliesToClients(self, committedTxns, ppTime):
        for txn in committedTxns:
            # TODO: Send txn and state proof to the client
            txn[TXN_TIME] = ppTime
            self.sendReplyToClient(Reply(txn), (txn[f.IDENTIFIER.nm],
                                                txn[f.REQ_ID.nm]))

    def sendReplyToClient(self, reply, reqKey):
        if self.isProcessingReq(*reqKey):
            logger.debug('{} sending reply for {} to client'.format(self, reqKey))
            self.transmitToClient(reply, self.requestSender[reqKey])
            self.doneProcessingReq(*reqKey)

    def addNewRole(self, txn):
        """
        Adds a new client or steward to this node based on transaction type.
        """
        # If the client authenticator is a simple authenticator then add verkey.
        #  For a custom authenticator, handle appropriately
        if isinstance(self.clientAuthNr, SimpleAuthNr):
            identifier = txn[TARGET_NYM]
            verkey = txn.get(VERKEY)
            v = DidVerifier(verkey, identifier=identifier)
            if identifier not in self.clientAuthNr.clients:
                role = txn.get(ROLE)
                if role not in (STEWARD, TRUSTEE, None):
                    logger.error("Role if present must be {} and not {}".
                                 format(Roles.STEWARD.name, role))
                    return
                self.clientAuthNr.addIdr(identifier,
                                         verkey=v.verkey,
                                         role=role)

    @staticmethod
    def initStateFromLedger(state: State, ledger: Ledger, reqHandler):
        # If the trie is empty then initialize it by applying
        # txns from ledger
        if state.isEmpty:
            txns = [_ for _ in ledger.getAllTxn().values()]
            reqHandler.updateState(txns, isCommitted=True)
            state.commit(rootHash=state.headHash)

    def initDomainState(self):
        self.initStateFromLedger(self.states[DOMAIN_LEDGER_ID],
                                 self.domainLedger, self.reqHandler)

    def addGenesisNyms(self):
        for _, txn in self.domainLedger.getAllTxn().items():
            if txn.get(TXN_TYPE) == NYM:
                self.addNewRole(txn)

    def defaultAuthNr(self):
        state = self.getState(DOMAIN_LEDGER_ID)
        return SimpleAuthNr(state=state)

    def processStashedOrderedReqs(self):
        i = 0
        while self.stashedOrderedReqs:
            msg = self.stashedOrderedReqs.popleft()
            if msg.instId == 0:
                if compare_3PC_keys((msg.viewNo, msg.ppSeqNo),
                                    self.ledgerManager.last_caught_up_3PC) >= 0:
                    logger.debug('{} ignoring stashed ordered msg {} since ledger '
                                 'manager has last_caught_up_3PC as {}'.
                                 format(self, msg,
                                        self.ledgerManager.last_caught_up_3PC))
                    continue
                logger.debug('{} applying stashed Ordered msg {}'.format(self, msg))
                # Since the PRE-PREPAREs ans PREPAREs corresponding to these
                # stashed ordered requests was not processed.
                for reqKey in msg.reqIdr:
                    req = self.requests[reqKey].finalised
                    self.applyReq(req)
                self.processOrdered(msg)
            else:
                self.processOrdered(msg)
            i += 1
        logger.debug("{} processed {} stashed ordered requests".format(self, i))
        # Resetting monitor after executing all stashed requests so no view
        # change can be proposed
        self.monitor.reset()
        return i

    def sync3PhaseState(self):
        for replica in self.replicas:
            self.send(replica.threePhaseState)

    def ensureKeysAreSetup(self):
        """
        Check whether the keys are setup in the local STP keep.
        Raises KeysNotFoundException if not found.
        """
        name, baseDir = self.name, self.basedirpath
        if not areKeysSetup(name, baseDir, self.config):
            raise REx(REx.reason.format(name) + self.keygenScript)

    @staticmethod
    def reasonForClientFromException(ex: Exception):
        friendly = friendlyEx(ex)
        reason = "client request invalid: {}".format(friendly)
        return reason

    def reportSuspiciousNodeEx(self, ex: SuspiciousNode):
        """
        Report suspicion on a node on the basis of an exception
        """
        self.reportSuspiciousNode(ex.node, ex.reason, ex.code, ex.offendingMsg)

    def reportSuspiciousNode(self,
                             nodeName: str,
                             reason=None,
                             code: int=None,
                             offendingMsg=None):
        """
        Report suspicion on a node and add it to this node's blacklist.

        :param nodeName: name of the node to report suspicion on
        :param reason: the reason for suspicion
        """
        logger.warning("{} raised suspicion on node {} for {}; suspicion code "
                       "is {}".format(self, nodeName, reason, code))
        # TODO need a more general solution here

        # TODO: Should not blacklist client on a single InvalidSignature.
        # Should track if a lot of requests with incorrect signatures have been
        # made in a short amount of time, only then blacklist client.
        # if code == InvalidSignature.code:
        #     self.blacklistNode(nodeName,
        #                        reason=InvalidSignature.reason,
        #                        code=InvalidSignature.code)

        # TODO: Consider blacklisting nodes again.
        # if code in self.suspicions:
        #     self.blacklistNode(nodeName,
        #                        reason=self.suspicions[code],
        #                        code=code)

        if code in (s.code for s in (Suspicions.PPR_DIGEST_WRONG,
                                     Suspicions.PPR_REJECT_WRONG,
                                     Suspicions.PPR_TXN_WRONG,
                                     Suspicions.PPR_STATE_WRONG)):
            self.sendInstanceChange(self.viewNo + 1, Suspicions.get_by_code(code))
            logger.info('{} sent instance change since suspicion code {}'
                        .format(self, code))

        if offendingMsg:
            self.discard(offendingMsg, reason, logger.warning)

    def reportSuspiciousClient(self, clientName: str, reason):
        """
        Report suspicion on a client and add it to this node's blacklist.

        :param clientName: name of the client to report suspicion on
        :param reason: the reason for suspicion
        """
        logger.warning("{} suspicion raised on client {} for {}; "
                       "doing nothing for now".
                       format(self, clientName, reason))
        self.blacklistClient(clientName)

    def isClientBlacklisted(self, clientName: str):
        """
        Check whether the given client is in this node's blacklist.

        :param clientName: the client to check for blacklisting
        :return: whether the client was blacklisted
        """
        return self.clientBlacklister.isBlacklisted(clientName)

    def blacklistClient(self, clientName: str, reason: str=None, code: int=None):
        """
        Add the client specified by `clientName` to this node's blacklist
        """
        msg = "{} blacklisting client {}".format(self, clientName)
        if reason:
            msg += " for reason {}".format(reason)
        logger.debug(msg)
        self.clientBlacklister.blacklist(clientName)

    def isNodeBlacklisted(self, nodeName: str) -> bool:
        """
        Check whether the given node is in this node's blacklist.

        :param nodeName: the node to check for blacklisting
        :return: whether the node was blacklisted
        """
        return self.nodeBlacklister.isBlacklisted(nodeName)

    def blacklistNode(self, nodeName: str, reason: str=None, code: int=None):
        """
        Add the node specified by `nodeName` to this node's blacklist
        """
        msg = "{} blacklisting node {}".format(self, nodeName)
        if reason:
            msg += " for reason {}".format(reason)
        if code:
            msg += " for code {}".format(code)
        logger.debug(msg)
        self.nodeBlacklister.blacklist(nodeName)

    @property
    def blacklistedNodes(self):
        return {nm for nm in self.nodeReg.keys() if
                self.nodeBlacklister.isBlacklisted(nm)}

    def transmitToClient(self, msg: Any, remoteName: str):
        self.clientstack.transmitToClient(msg, remoteName)

    def send(self, msg: Any, *rids: Iterable[int], signer: Signer = None):
        if rids:
            remoteNames = [self.nodestack.remotes[rid].name for rid in rids]
            recipientsNum = len(remoteNames)
        else:
            # so it is broadcast
            remoteNames = [remote.name for remote in
                           self.nodestack.remotes.values()]
            recipientsNum = 'all'

        logger.debug("{} sending message {} to {} recipients: {}"
                     .format(self, msg, recipientsNum, remoteNames))
        self.nodestack.send(msg, *rids, signer=signer)

    def getReplyFromLedger(self, ledger, request):
        # DoS attack vector, client requesting already processed request id
        # results in iterating over ledger (or its subset)
        seqNo = self.seqNoDB.get(request.identifier, request.reqId)
        if seqNo:
            txn = ledger.getBySeqNo(int(seqNo))
            if txn:
                txn.update(ledger.merkleInfo(txn.get(F.seqNo.name)))
                txn = self.update_txn_with_extra_data(txn)
                return Reply(txn)

    def update_txn_with_extra_data(self, txn):
        """
        All the data of the transaction might not be stored in ledger so the
        extra data that is omitted from ledger needs to be fetched from the
        appropriate data store
        :param txn:
        :return:
        """
        # All the data of any transaction is stored in the ledger
        return txn

    def transform_txn_for_ledger(self, txn):
        return self.reqHandler.transform_txn_for_ledger(txn)

    def __enter__(self):
        return self

    # noinspection PyUnusedLocal
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def logstats(self):
        """
        Print the node's current statistics to log.
        """
        lines = [
            "node {} current stats".format(self),
            "--------------------------------------------------------",
            "node inbox size         : {}".format(len(self.nodeInBox)),
            "client inbox size       : {}".format(len(self.clientInBox)),
            "age (seconds)           : {}".format(time.time() - self.created),
            "next check for reconnect: {}".format(time.perf_counter() -
                                                  self.nodestack.nextCheck),
            "node connections        : {}".format(self.nodestack.conns),
            "f                       : {}".format(self.f),
            "master instance         : {}".format(self.instances.masterId),
            "replicas                : {}".format(len(self.replicas)),
            "view no                 : {}".format(self.viewNo),
            "rank                    : {}".format(self.rank),
            "msgs to replicas        : {}".format(len(self.msgsToReplicas)),
            "msgs to elector         : {}".format(len(self.msgsToElector)),
            "action queue            : {} {}".format(len(self.actionQueue),
                                                     id(self.actionQueue)),
            "action queue stash      : {} {}".format(len(self.aqStash),
                                                     id(self.aqStash)),
        ]

        logger.info("\n".join(lines), extra={"cli": False})

    def collectNodeInfo(self):
        nodeAddress = None
        if self.poolLedger:
            txns = self.poolLedger.getAllTxn()
            for key, txn in txns.items():
                data = txn[DATA]
                if data[ALIAS] == self.name:
                    nodeAddress = data[NODE_IP]
                    break

        info = {
            'name': self.name,
            'rank': self.rank,
            'view': self.viewNo,
            'creationDate': self.created,
            'baseDir': self.basedirpath,
            'portN': self.nodestack.ha[1],
            'portC': self.clientstack.ha[1],
            'address': nodeAddress
        }
        return info

    def logNodeInfo(self):
        """
        Print the node's info to log for the REST backend to read.
        """
        self.nodeInfo['data'] = self.collectNodeInfo()

        with closing(open(os.path.join(self.config.baseDir, 'node_info'), 'w')) \
                as logNodeInfoFile:
            logNodeInfoFile.write(json.dumps(self.nodeInfo['data']))

