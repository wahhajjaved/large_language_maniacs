from mpi4py import MPI
import hashlib
import sys
import inspect
from Queue import PriorityQueue
import logging

# Set up our logging system
logging.basicConfig(filename='solver_log.log', filemode='w', level=logging.DEBUG)

# Import game definition from file specified in command line
game_module = __import__(sys.argv[1].replace('.py', ''))

# Make sure the game is properly defined
assert(hasattr(game_module, 'initial_position'))
assert(hasattr(game_module, 'do_move'))
assert(hasattr(game_module, 'gen_moves'))
assert(hasattr(game_module, 'primitive'))
assert(inspect.isfunction(game_module.do_move))
assert(inspect.isfunction(game_module.gen_moves))
assert(inspect.isfunction(game_module.primitive))

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

class GameState:
    """
    Wrapper for the idea of a GameState, not needed
    by the user, just makes things easier for the
    framework.
    """
    def __init__(self, pos):
        self.pos = pos

    def get_hash(self):
        """
        Returns the appropriate hash of a given GameState object.
        Based off of the value of it's position.
        """
        return int(hashlib.md5(str(self.pos).encode('utf-8')).hexdigest(), 16) % size

    def expand(self):
        """
        Takes the current position and generates the
        children positions.
        """
        # Raw, in other words, not a GameState object.
        raw_states = map(lambda m: game_module.do_move(self.pos, m), game_module.gen_moves(self.pos))
        # Wrapped, in other words, a GameState object.
        wrapped_states = map(lambda m: GameState(m), raw_states)
        return wrapped_states

    @property
    def state(self):
        """
        Determines whether the state is a:
        WIN, LOSS, TIE, DRAW or UNDECIDED
        """
        return game_module.primitive(self.pos)

    def is_primitive(self):
        """
        Determines the difference between
        WLTD and UNDECIDED
        """
        # TODO: Don't violate abstraction barrier...
        # Notably: ("WIN", "LOSS", "TIE", "DRAW")
        return self.state in ("WIN", "LOSS", "TIE", "DRAW")

class Job:
    """
    A job has a game state, parent, type, and also has a priority for placing
    jobs in a queue for the processes to work on.
    """
    # A list of possible job types.
    LOOK_UP           = "lookup"
    DISTRIBUTE        = "distribute"
    CHECK_FOR_UPDATES = "check_for_updates"
    SEND_BACK         = "send_back"
    FINISHED          = "finished"
    RESOLVE           = "resolve"

    _priority_table = {
            FINISHED          : 0,
            LOOK_UP           : 1,
            RESOLVE           : 2,
            SEND_BACK         : 3,
            DISTRIBUTE        : 4,
            CHECK_FOR_UPDATES : 5
    }

    # Keep a special variable for the initial job!
    # This way you can check if the job you finished was
    # the initial job. In this case we are done!
    INITIAL_JOB_ID = -1

    def _assign_priority(self):
        self.priority = self._priority_table[self.job_type]

    def __init__(self, job_type, game_state=None, parent=None, job_id=None):
        self.job_type   = job_type
        self.game_state = game_state
        self.parent     = parent
        self.job_id     = job_id
        self._assign_priority()

    def __lt__(self, other):
        """
        Compares two Job objects based off the priority
        they have.
        """
        return self.priority < other.priority

class Process:
    """
    Class that defines the behavior what each process should do
    """
    ROOT = 0
    IS_FINISHED = False

    INITIAL_POS = GameState(game_module.initial_position)

    def dispatch(self, job):
        """
        Given a particular kind of job, decide what to do with
        it, this can range from lookup, to distributing, to
        checking for recieving.
        """
        _dispatch_table = {
                Job.FINISHED          : self.finished,
                Job.LOOK_UP           : self.lookup,
                Job.RESOLVE           : self.resolve,
                Job.DISTRIBUTE        : self.distribute,
                Job.SEND_BACK         : self.send_back,
                Job.CHECK_FOR_UPDATES : self.check_for_updates
        }
        return _dispatch_table[job.job_type](job)

    def _queue_to_str(self, q):
        """
        For debugging purposes.
        Prints the job type for each job in the job queue.
        """
        return ', '.join([str(j.job_type) for j in q.queue])

    def run(self):
        """
        Main loop for each process
        """
        # TODO
        while not Process.IS_FINISHED:
            logging.info("Machine " + str(self.rank) + " has " + self._queue_to_str(self.work) + " lined up to work on")
            if self.work.qsize() == 0:
                if self.rank == 0 and Process.INITIAL_POS in self.resolved:
                    logging.info('Finished')
                    for rnk in range(size):
                        comm.isend(Job(Job.FINISHED), dest = rnk)
                else:
                    self.add_job(Job(Job.CHECK_FOR_UPDATES))
            job = self.work.get()
            result = self.dispatch(job)
            if result is None: # Check for updates returns nothing.
                continue
            self.add_job(result)

    def __init__(self, rank):
        self.rank = rank
        self.work = PriorityQueue()
        self.resolved = {}
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
        self._counter = {}        # A job_id -> Number of results
                                  # remaining.
        self._id_to_resolved = {} # A job_id -> a gamestate that
                                  # needs resolution.
        self._id = 0              # The id of the job.
        self._pending = {}        # game state -> list of 
                                  # children game states.
                                  # Needed to resolve a pending
                                  # state.
        self._gamestate_dep = {}  # When a node cannot be resolved 
                                  # immediately back got parent,
                                  # information about the parent is
                                  # lost as a new parent is assigned
                                  # This keeps track of the parents
                                  # that need a particular game
                                  # state.
        # Main process will terminate everyone by bcasting the value of
        # finished to True.
        self.finished = False

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
        IS_FINISHED = True

    def lookup(self, job):
        """
        Takes a GameState object and determines if it is in the
        resolved list. Returns the result if this is the case, None
        otherwise.
        """
        logging.info("Machine " + str(rank) + " looking up " + str(job.game_state.pos))
        try:
            res = self.resolved[job.game_state.pos]
            logging.info("Positition " + str(job.game_state.pos) + " has been resolved")
            return Job(Job.SEND_BACK, res, job.parent, job.job_id)
        except KeyError: # Not in dictionary.
            # Try to see if it is_primitive:
            if job.game_state.is_primitive():
                logging.info("Position " + str(job.game_state.pos) + " is primitive")
                self.resolved[job.game_state.pos] = job.game_state.state
                return Job(Job.SEND_BACK, job.game_state.state, job.parent, job.job_id)
            return Job(Job.DISTRIBUTE, job.game_state, job.parent, self._id)

    def _add_pending_state(self, job, children):
        # Refer to lines 179-187 for an explanation of why this 
        # is done.
        try:
            self._gamestate_dep[job.game_state.pos].append((job.parent, job.job_id))
        except KeyError:
            self._gamestate_dep[job.game_state.pos] = []
            self._gamestate_dep[job.game_state.pos].append((job.parent, job.job_id))
        self._pending[job.game_state.pos] = []
        self._counter[self._id] = len(children)
        self._id_to_resolved[self._id] = job.game_state.pos

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
        children = job.game_state.expand()
        # Add new pending state information.
        self._add_pending_state(job, children)
        # Keep a list of the requests made by isend. Something may
        # fail, so we will need to worry about error checking at
        # some point.
        for child in children:
            job = Job(Job.LOOK_UP, child, self.rank, self._id)
            logging.info("Machine " + str(rank) 
                       + " found child " + str(job.game_state.pos)
                       + ", sending to " + str(child.get_hash())) 

            comm.isend(job,  dest = child.get_hash())

        self._update_id()

    def check_for_updates(self, job):
        """
        Checks if there is new data from other Processes that needs to
        be received and prepares to recieve it if there is any new data.
        Returns True if there is new data to be recieved.
        Returns None if there is nothing to be recieved.
        """
        # Probe for any sources
        if comm.iprobe(source=MPI.ANY_SOURCE):
            # If there are sources recieve them.
            self.received.append(comm.recv(source=MPI.ANY_SOURCE))
            for job in self.received:
                self.add_job(job)

            self.recieved = [] # Clear recieved.

    def send_back(self, job):
        """
        Send the job back to the node who asked for the computation
        to be done.
        """
        logging.info("Machine " + str(rank) + " is sending back " + str(job.game_state) + " to " + str(job.parent))
        resolve_job = Job(Job.RESOLVE, job.game_state, job.parent, job.job_id)
        comm.send(resolve_job, dest=resolve_job.parent)

    def _res_red(self, res1, res2):
        """
        Private method that helps reduce in resolve.
        """
        # Probably can be done in a "cleaner" way.
        if res1 == "LOSS" and res2 == "LOSS":
            return "LOSS"
        elif res1.pos == "WIN" or res2 == "WIN":
            return "WIN"
        elif res1 == "TIE" or res2 == "TIE":
            return "TIE"
        elif res1 == "DRAW" or res2 == "DRAW":
            return "DRAW"

    def resolve(self, job):
        """
        Given a list of WIN, LOSS, TIE, (DRAW, well maybe for later)
        determine whether this position in the game tree is a WIN,
        LOSS, TIE, or DRAW.
        """
        self._counter[job.job_id] -= 1
        self._pending[self._id_to_resolved[job.job_id]].append(job.game_state)
        if self._counter[job.job_id] == 0:
            resolved_state = self._id_to_resolved[job.job_id]
            self.resolved[resolved_state] = reduce(self._res_red, self._pending[resolved_state])
            logging.info("Position " + str(resolved_state) + " has been resolved.")
            for p_data in self._gamestate_dep[resolved_state]:
                to = Job(Job.SEND_BACK, self.resolved[resolved_state], p_data[0], p_data[1])
                self.add_job(to)

process = Process(rank)
if process.rank == Process.ROOT:
    initial_gamestate = GameState(game_module.initial_position)
    initial_job = Job(Job.LOOK_UP, initial_gamestate, process.rank, Job.INITIAL_JOB_ID)
    process.add_job(initial_job)

process.run()

comm.Barrier()
