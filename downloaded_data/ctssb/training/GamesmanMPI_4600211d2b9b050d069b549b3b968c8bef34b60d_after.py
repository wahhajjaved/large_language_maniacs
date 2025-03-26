from mpi4py import MPI
from .game_state import GameState
from .job import Job
from .utils import negate, PRIMITIVE_REMOTENESS, WIN, LOSS, \
                   TIE, DRAW, to_str, reduce_singleton
from .cache_dict import CacheDict
from queue import PriorityQueue


class Process:
    """
    Class that defines the behavior what each process should do
    """

    __slots__ = ['rank', 'root', 'initial_pos', 'resolved',
                 'world_size', 'comm', 'send', 'recv', 'abort',
                 'work', 'received', 'remote', '_id', '_counter',
                 '_pending']
    IS_FINISHED = False

    def dispatch(self, job):
        """
        Given a particular kind of job, decide what to do with
        it, this can range from lookup, to distributing, to
        checking for recieving.
        """
        _dispatch_table = (
            self.finished,
            self.lookup,
            self.resolve,
            self.send_back,
            self.distribute,
            self.check_for_updates
        )
        return _dispatch_table[job.job_type](job)

    def run(self):
        """
        Main loop for each process
        """
        while not Process.IS_FINISHED:
            if (
                self.rank == self.root and
                self.initial_pos.pos in self.resolved
               ):
                Process.IS_FINISHED = True
                print(
                    to_str(self.resolved[self.initial_pos.pos]) +
                    " in " +
                    str(self.remote[self.initial_pos.pos]) +
                    " moves"
                )
                self.abort()
            if self.work.empty():
                self.add_job(Job(Job.CHECK_FOR_UPDATES))
            job = self.work.get()
            result = self.dispatch(job)
            if result is None:  # Check for updates returns nothing.
                continue
            self.add_job(result)

    def __init__(self, rank, world_size, comm,
                 send, recv, abort, stats_dir=''):
        self.rank = rank
        self.world_size = world_size
        self.comm = comm

        self.send = send
        self.recv = recv
        self.abort = abort

        self.initial_pos = GameState(GameState.INITIAL_POS)
        self.root = self.initial_pos.get_hash(self.world_size)

        self.work = PriorityQueue()
        self.resolved = CacheDict("resolved", stats_dir, self.rank)
        self.remote = CacheDict("remote", stats_dir, self.rank)
        # As for recieving, should test them when appropriate
        # in the run loop.
        self.received = []
        # Keep a dictionary of "distributed tasks"
        # Should contain an id associated with the length of task.
        # For example, you distributed rank 0 has 4, you wish to
        # distribute 3, 2. Give it an id, like 1 and associate it
        # with length 2. Then once all the results have been received
        # you can compare the length, and then reduce the results.
        # solving this particular distributed task.

        # Job id tracker.
        self._id = 0
        # A job_id -> Number of results remaining.
        self._counter = CacheDict("counter", stats_dir, self.rank, t="work")
        # job_id -> [ Job, GameStates, ... ]
        self._pending = CacheDict("pending", stats_dir, self.rank, t="work")

    def add_job(self, job):
        """
        Adds a job to the priority queue so it may be worked on at an
        appropriate time
        """
        self.work.put(job)

    def finished(self, job):
        """
        Occurs when the root node has detected that the game has been solved
        """
        self.IS_FINISHED = True

    def lookup(self, job):
        """
        Takes a GameState object and determines if it is in the
        resolved list. Returns the result if this is the case, None
        otherwise.
        """
        try:
            job.game_state.state = self.resolved[job.game_state.pos]
            job.game_state.remoteness = self.remote[job.game_state.pos]
            return Job(Job.SEND_BACK, job.game_state, job.parent, job.job_id)
        except KeyError:  # Not in dictionary
            # Try to see if it is_primitive:
            if job.game_state.is_primitive():
                self.remote[job.game_state.pos] = PRIMITIVE_REMOTENESS
                job.game_state.remoteness = PRIMITIVE_REMOTENESS
                self.resolved[job.game_state.pos] = job.game_state.primitive
                return Job(
                    Job.SEND_BACK,
                    job.game_state,
                    job.parent,
                    job.job_id
                )
            # Not a primitive.
            return Job(Job.DISTRIBUTE, job.game_state, job.parent, job.job_id)

    def _add_pending_state(self, job, children):
        # Refer to lines 179-187 for an explanation of why this
        # is done.
        self._pending[self._id] = [job]
        self._counter[self._id] = len(list(children))

    def _update_id(self):
        """
        Changes the id so there is no collision.
        """
        self._id += 1

    def distribute(self, job):
        """
        Given a gamestate distributes the results to the appropriate
        children.
        """
        children = list(job.game_state.expand())
        # Add new pending state information.
        self._add_pending_state(job, children)
        # Keep a list of the requests made by isend. Something may
        # fail, so we will need to worry about error checking at
        # some point.
        for child in children:
            new_job = Job(Job.LOOK_UP, child, self.rank, self._id)

            self.send(new_job, dest=child.get_hash(self.world_size))

        self._update_id()

    def check_for_updates(self, job):
        """
        Checks if there is new data from other Processes that needs to
        be received and prepares to recieve it if there is any new data.
        Returns True if there is new data to be recieved.
        Returns None if there is nothing to be recieved.
        """
        # Probe for any sources
        if self.comm.probe(source=MPI.ANY_SOURCE):
            # If there are sources recieve them.
            self.received.append(self.recv(source=MPI.ANY_SOURCE))
            for job in self.received:
                self.add_job(job)
        del self.received[:]

    def send_back(self, job):
        """
        Send the job back to the node who asked for the computation
        to be done.
        """
        resolve_job = Job(Job.RESOLVE, job.game_state, job.parent, job.job_id)
        self.send(resolve_job, dest=resolve_job.parent)

    def _res_red(self, res1, res2):
        """
        Private method that helps reduce in resolve.
        """
        nums = (0, 3, 2, 1)
        states = (WIN, DRAW, TIE, LOSS)

        if res2 is None:
            return negate(res1)
        max_num = max(nums[res1], nums[res2])
        return negate(states[max_num])

    def _remote_red(self, rem1, rem2):
        """
        Private method that helps reduce remoteness.
        Takes in two (state, remotness) tuples, and returns a Job with with an
        appropriate remoteness.
        """
        # TODO: Make cleaner.
        if rem2 is None:
            return (rem1[0], rem1[1])

        if rem1[0] == LOSS or rem2[0] == LOSS:
            if rem1[0] == LOSS and rem2[0] == WIN:
                return (LOSS, rem1[1])
            elif rem1[0] == WIN and rem2[0] == LOSS:
                return (LOSS, rem2[1])
            else:
                return (LOSS, min(rem1[1], rem2[1]))
        elif rem2[0] == WIN and rem1[0] == WIN:
            return (WIN, max(rem1[1], rem2[1]))
        else:
            # Use rem1's state by default, but rem2's state should work too.
            return (rem1[0], max(rem1[1], rem2[1]))

    def _cleanup(self, job):
        del self._pending[job.job_id][:]
        del self._pending[job.job_id]
        del self._counter[job.job_id]

    def resolve(self, job):
        """
        Given a list of WIN, LOSS, TIE, (DRAW, well maybe for later)
        determine whether this position in the game tree is a WIN,
        LOSS, TIE, or DRAW.
        """
        self._counter[job.job_id] -= 1
        # [Job, GameState, ... ]
        self._pending[job.job_id].append(job.game_state)
        # Resolve _pending
        if self._counter[job.job_id] == 0:
            # [Job, GameState, ...] -> Job
            to_resolve = self._pending[job.job_id][0]
            if to_resolve.game_state.is_primitive():
                self.resolved[to_resolve.game_state.pos] = \
                    to_resolve.game_state.primitive
                self.remote[to_resolve.game_state.pos] = 0
            else:
                # Convert [Job, GameState, GameState, ...] ->
                # [GameState, GameState, ... ]
                tail = self._pending[job.job_id][1:]
                # [(state, remote), (state, remote), ...]
                resolve_data = [g.to_remote_tuple for g in tail]
                # [state, state, ...]
                state_red = [gs[0] for gs in resolve_data]
                self.resolved[to_resolve.game_state.pos] = \
                    reduce_singleton(self._res_red, state_red)
                self.remote[to_resolve.game_state.pos] = \
                    reduce_singleton(self._remote_red, resolve_data)[1] + 1
                job.game_state.state = self.resolved[to_resolve.game_state.pos]
                job.game_state.remoteness = \
                    self.remote[to_resolve.game_state.pos]
            to = Job(
                Job.SEND_BACK,
                job.game_state,
                to_resolve.parent,
                to_resolve.job_id
            )
            self.add_job(to)
            # Dealloc unneeded _pending and counter data.
            self._cleanup(job)
