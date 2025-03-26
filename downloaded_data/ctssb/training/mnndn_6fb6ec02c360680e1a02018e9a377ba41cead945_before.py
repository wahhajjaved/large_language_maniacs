from mininet.link import TCIntf

class LinkFailure:
    """Allow failing and recovering links.
       To use this helper, Mininet must be created with `link=TCLink`."""

    def __init__(self, net, sched):
        """net: a Mininet instance
           sched: a sched.scheduler instance"""
        self.net = net
        self.sched = sched
        self.failedLinks = set()

    @staticmethod
    def __fail(intf):
        if not isinstance(intf, TCIntf):
            raise TypeError('interface is not TCIntf')
        intf.config(loss=100)

    @staticmethod
    def __recover(intf):
        if not isinstance(intf, TCIntf):
            raise TypeError('interface is not TCIntf')
        # loss=0 alone would be ignored, so we add bw=1000
        intf.config(bw=1000, loss=0)

    def __do(self, h1, h2, isFail, cb):
        h1 = h1 if not isinstance(h1, basestring) else self.net[h1]
        h2 = h2 if not isinstance(h2, basestring) else self.net[h2]
        if h1.name == h2.name:
            return
        if h1.name > h2.name:
            h1, h2 = h2, h1

        if isFail:
            act = self.__fail
            self.failedLinks.add((h1.name, h2.name))
        else:
            act = self.__recover
            try:
                self.failedLinks.remove((h1.name, h2.name))
            except KeyError:
                return

        connections = h1.connectionsTo(h2)
        for (intf1, intf2) in connections:
            act(intf1)
            act(intf2)
        if hasattr(cb, '__call__'):
            cb()

    def fail(self, h1, h2, t=None, cb=None):
        """Fail links between h1 and h2.
           h1, h2: mininet.node.Node, or node name
           t: if not None, schedule at a future time
           cb: if callable, call this function after failing link"""
        if t is None:
            self.__do(h1, h2, True, cb)
        else:
            if self.sched is None:
                raise TypeError('scheduler is unavailable')
            self.sched.enter(t, 0, self.__do, (h1, h2, True, cb))

    def recover(self, h1, h2, t=None, cb=None):
        """Recover links between h1 and h2.
           h1, h2: mininet.node.Node, or node name
           t: if not None, schedule at a future time
           cb: if callable, call this function after recovering link"""
        if t is None:
            self.__do(h1, h2, True, cb)
        else:
            if self.sched is None:
                raise TypeError('scheduler is unavailable')
            self.sched.enter(t, 0, self.__do, (h1, h2, False, cb))
