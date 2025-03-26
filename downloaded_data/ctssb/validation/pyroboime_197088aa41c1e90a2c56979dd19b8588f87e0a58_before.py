from multiprocessing import Process, Event
from . import updater
from . import commander
from . import filter
from ..config import config


def _update_loop(queue, updater):
    while True:
        queue.put(updater.receive())


def _command_loop(queue, commander):
    latest_actions = None
    while True:
        while not queue.empty():
            latest_actions = queue.get()
        if latest_actions is not None:
            commander.send(latest_actions)


class Interface(Process):
    """ This class is used to manage a single interface channel

    More specifically, this class will instantiate a set of updaters,
    commanders and filters, and orchestrate them to interact with an
    instace of a World.
    """

    def __init__(self, world, updaters=[], commanders=[], filters=[], callback=lambda: None):
        """
        The callback function will be called whenever an update arrives,
        after the world is updated.
        """
        super(Interface, self).__init__()
        #self.updates = []
        #self.commands = []
        self.world = world
        self.updaters = updaters
        self.commanders = commanders
        self.filters = filters
        self.callback = callback
        self._exit = Event()

    def start(self):
        #super(Interface, self).start()
        for p in self.processes():
            p.start()

    def stop(self):
        for p in self.processes():
            p.stop()

    #def run(self):
    #    while not self._exit.is_set():
    #        for up in self.updaters:
    #            if not up.queue.empty():
    #                uu = up.queue.get()
    #                for fi in reversed(self.filters):
    #                    _uu = fi.filter_updates(uu)
    #                    if _uu is not None:
    #                        uu = _uu
    #                self.updates = uu

    #        for co in self.commanders:
    #            if self.actions is not None:
    #                co.send(self.actions)
    #            #co.send(actions)

    def step(self):
        #print "I'm stepping the interface."
        # updates injection phase
        for up in self.updaters:
            if not up.queue.empty():
                #uu = up.queue.get_nowait()
                for _ in xrange(15):
                    uu = up.queue.get()
                    if up.queue.empty():
                        break
                for fi in reversed(self.filters):
                    _uu = fi.filter_updates(uu)
                    if _uu is not None:
                        uu = _uu
                for u in uu:
                    u.apply(self.world)

            ##with up.queue_lock:
            ##    print 'Queue size: ', up.queue.qsize()
            #while not up.queue.empty() and count < 7:
            #    uu = up.queue.get()
            #    for fi in reversed(self.filters):
            #        _uu = fi.filter_updates(uu)
            #        if _uu is not None:
            #            uu = _uu
            #    for u in uu:
            #        u.apply(self.world)
            #    count += 1

            #if count > 0:
            #    self.callback()

        # actions extraction phase
        # TODO filtering
        for co in self.commanders:
            actions = []
            for r in co.team:
                if r.action is not None:
                    actions.append(r.action)
            for fi in self.filters:
                _actions = fi.filter_commands(actions)
                if _actions is not None:
                    actions = _actions

            #co.queue.put(actions)
            co.send(actions)

    def processes(self):
        for up in self.updaters:
            yield up
        #for co in self.commanders:
        #    yield co


class TxInterface(Interface):

    def __init__(self, world, filters=[], mapping_yellow=None, mapping_blue=None, kick_mapping_yellow=None, kick_mapping_blue=None, **kwargs):
        debug = config['interface']['debug']
        vision_address = (config['interface']['tx']['vision-addr'], config['interface']['tx']['vision-port'])
        referee_address = (config['interface']['tx']['referee-addr'], config['interface']['tx']['referee-port'])
        super(TxInterface, self).__init__(
            world,
            updaters=[
                updater.VisionUpdater(vision_address),
                updater.RealRefereeUpdater(referee_address),
            ],
            commanders=[
                commander.Tx2013Commander(world.blue_team, mapping_dict=mapping_blue, kicking_power_dict=kick_mapping_blue, verbose=debug),
                commander.Tx2013Commander(world.yellow_team, mapping_dict=mapping_yellow, kicking_power_dict=kick_mapping_yellow, verbose=debug),
            ],
            filters=filters + [
                filter.DeactivateInactives(),
                filter.Acceleration(),
                filter.Speed(), # second speed is more precise due to Kalman, size=2
                filter.Kalman(),
                filter.Speed(3), # first speed used to predict speed for Kalman
                filter.Scale(),
            ],
            **kwargs
        )


class SimulationInterface(Interface):

    def __init__(self, world, filters=[], **kwargs):
        #debug = config['interface']['debug']
        vision_address = (config['interface']['sim']['vision-addr'], config['interface']['sim']['vision-port'])
        referee_address = (config['interface']['sim']['referee-addr'], config['interface']['sim']['referee-port'])
        grsim_address = (config['interface']['sim']['grsim-addr'], config['interface']['sim']['grsim-port'])
        super(SimulationInterface, self).__init__(
            world,
            updaters=[
                updater.VisionUpdater(vision_address),
                updater.RefereeUpdater(referee_address),
            ],
            commanders=[
                commander.SimCommander(world.blue_team, grsim_address),
                commander.SimCommander(world.yellow_team, grsim_address),
            ],
            filters=filters + [
                #filter.PositionLog(options.position_log_filename), #should be last, to have all data available
                filter.DeactivateInactives(),
                filter.Acceleration(),
                filter.Speed(), # second speed is more precise due to Kalman, size=2
                #filter.CommandUpdateLog(options.cmdupd_filename),
                filter.Kalman(),
                filter.Speed(3), # first speed used to predict speed for Kalman
                #Noise should be enabled during simulation, to allow real noise simulation
                #filter.Noise(options.noise_var_x,options.noise_var_y,options.noise_var_angle),
                filter.RegisterPosition("input"),
                filter.Scale(),
            ],
            **kwargs
        )

    #def start()
