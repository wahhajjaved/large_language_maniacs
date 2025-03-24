from __future__ import division
from random import Random
from vector import Vector
import operator


class Particle(object):
    """Particle for Particle Swarm Optimization.
    
    The particle assumes that the position and velocity are Vectors so it
    doesn't have to coerce them.

    We create a simple particle with unspecified value.  Note that the empty
    value, pbestval, and nbestval are represented as empty fields.

    >>> p = Particle(42, Vector((1.0, 2.0)), Vector((3.0, 4.0)))
    >>> repr(p)
    'p:42;0;0;1.0,2.0;3.0,4.0;;1.0,2.0;;1.0,2.0;'
    >>>

    Adding more detailed state to the particle shows what the full particle
    representation looks like.

    >>> p.batches = 100
    >>> p.iters = 200
    >>> p.pbestpos = Vector((6.0, 7.0))
    >>> p.nbestpos = Vector((8.0, 9.0))
    >>> p.value = -10.0
    >>> p.pbestval = -11.0
    >>> p.nbestval = -12.0
    >>> repr(p)
    'p:42;100;200;1.0,2.0;3.0,4.0;-10.0;6.0,7.0;-11.0;8.0,9.0;-12.0'
    >>>

    A new particle is created by unpacking a repr string.  The repr string
    of the new particle is identical to the repr string of the old particle.
    >>> q = unpack(repr(p))
    >>> repr(q) == repr(p)
    True
    >>>

    Comparisons are based on the pbestval of the particle, not the id.

    >>> p = Particle(42, Vector((1.0, 2.0)), Vector((3.0, 4.0)))
    >>> p.pbestval = 0.0
    >>> q = Particle(7, p.pos, p.vel)
    >>> q.pbestval = p.pbestval
    >>> p == q
    True
    >>> p > q
    False
    >>> p > q
    False
    >>> q.pbestval = p.pbestval - 1
    >>> p < q
    False
    >>> q < p
    True
    >>> p > q
    True
    >>>
    """
    CLASS_ID = 'p'

    def __init__(self, id, pos, vel, value=None):
        self.id = id
        self.batches = 0
        self.iters = 0

        self.pos = pos
        self.vel = vel
        self.value = value
        self.pbestpos = pos
        self.pbestval = value
        self.nbestpos = pos
        self.nbestval = value

        self.rand = None

    def copy(self):
        """Performs a deep copy and returns the new Particle.
        """
        p = Particle(self.id, self.pos, self.vel, self.value)
        p.pbestpos = self.pbestpos
        p.pbestval = self.pbestval
        p.nbestpos = self.nbestpos
        p.nbestval = self.nbestval
        p.batches = self.batches
        p.iters = self.iters
        return p

    def make_message(self, transitive_best, comparator):
        """Creates a pseudo-particle which will be sent to a neighbor.

        This is used only in the Mrs PSO implementation.

        The `transitive_best` option determines whether the nbest should be
        sent instead of the pbest.
        """
        if (transitive_best
                and self.isbetter(self.nbestval, self.pbestval, comparator)):
            value = self.nbestval
            pos = self.nbestpos
        else:
            value = self.pbestval
            pos = self.pbestpos
        return Message(self.id, pos, value)

    def make_message_particle(self):
        m = MessageParticle(self)
        return m

    def update(self, newpos, newvel, newval, comparator):
        """Uses the given pos, vel, and value, and considers a new pbest."""
        self.pos = newpos
        self.vel = newvel
        self.value = newval
        self.iters += 1
        if self.isbetter(newval, self.pbestval, comparator):
            self.pbestval = newval
            self.pbestpos = newpos

    def update_value(self, newval, comparator):
        """Updates the value of the particle, considers a new pbest"""
        self.value = newval
        if self.isbetter(newval, self.pbestval, comparator):
            self.pbestval = newval
            self.pbestpos = self.pos

    def update_pos(self, newpos, newvel, comparator):
        """Updates the position and velocity and iterations."""
        self.pos = newpos
        self.vel = newvel
        self.iters += 1

    def nbest_cand(self, potential_pos, potential_val, comparator):
        """Update nbest if the given value is better than the current nbest.
        
        >>> p = Particle(42, Vector((1.0, 2.0)), Vector((3.0, 4.0)))
        >>> p.nbestval = -12.0
        >>> p.nbestpos
        1.0,2.0
        >>> p.nbest_cand(Vector((1.0,1.0)),-10.0,operator.lt)
        >>> p.nbestval
        -12.0
        >>> p.nbestpos
        1.0,2.0
        >>> p.nbest_cand(Vector((2.0,2.0)),-15,operator.lt)
        >>> p.nbestval
        -15
        >>> p.nbestpos
        2.0,2.0
        >>> 
        """
        if self.isbetter(potential_val, self.nbestval, comparator):
            self.nbestpos = potential_pos
            self.nbestval = potential_val
            return True
        return False

    @staticmethod
    def isbetter(potential, old, comparator):
        """Finds whether the potential value is better than the old value.

        >>> Particle.isbetter(4,3,operator.lt)
        False
        >>> Particle.isbetter(3,4,operator.lt)
        True
        >>>

        Unlike using the comparator directly, None values are shunned:

        >>> Particle.isbetter(None,4,operator.lt)
        False
        >>> Particle.isbetter(None,None,operator.lt)
        False
        >>> Particle.isbetter(4,None,operator.lt)
        True
        >>> Particle.isbetter(4,None,operator.gt)
        True
        >>> 
        """
        if potential is None:
            return False
        elif old is None:
            return True
        elif comparator(potential, old):
            return True
        else:
            return False

    def reset(self, pos, vel, value):
        self.pos = pos
        self.vel = vel
        self.value = value
        self.pbestpos = pos
        self.pbestval = value
        self.nbestpos = pos
        self.nbestval = value

    def __str__(self):
        return "pos: %r; vel: %r; value: %r; pbestpos: %r; pbestval: %r" % (
                self.pos, self.vel, self.value, self.pbestpos, self.pbestval)

    def __repr__(self):
        fields = (self.id, self.batches, self.iters, self.pos, self.vel,
                self.value, self.pbestpos, self.pbestval, self.nbestpos,
                self.nbestval)
        strings = ((repr(x) if x is not None else '') for x in fields)
        return '%s:%s' % (self.CLASS_ID, ';'.join(strings))

    @classmethod
    def unpack(cls, state):
        """Unpacks a state string, returning a new Particle.

        The state string would have been created with repr(particle).
        """
        prefix = cls.CLASS_ID + ':'
        assert state.startswith(prefix)
        state = state[len(prefix):]
        (id, batches, iters, pos, vel, value, pbestpos, pbestval,
                nbestpos, nbestval) = state.split(';')
        id = int(id)
        pos = Vector.unpack(pos)
        vel = Vector.unpack(vel)
        if value:
            value = float(value)
        else:
            value = None
        p = cls(id, pos, vel, value)
        p.batches = int(batches)
        p.iters = int(iters)
        p.pbestpos = Vector.unpack(pbestpos)
        if pbestval:
            p.pbestval = float(pbestval)
        else:
            p.pbestval = None
        p.nbestpos = Vector.unpack(nbestpos)
        if nbestval:
            p.nbestval = float(nbestval)
        else:
            p.nbestval = None
        return p

    def __lt__(self, other):
        if isinstance(other, Particle):
            return self.pbestval < other.pbestval
        else:
            return NotImplemented

    def __gt__(self, other):
        if isinstance(other, Particle):
            return self.pbestval > other.pbestval
        else:
            return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Particle):
            return self.pbestval == other.pbestval
        else:
            return NotImplemented


class Message(object):
    """Message used to update bests in Mrs PSO.

    >>> m = Message(128, Vector((1.0, 2.0)), -5.0)
    >>> repr(m)
    'm:128;1.0,2.0;-5.0'
    >>>

    Empty values should still work, too.

    >>> m = Message(128, Vector((1.0, 2.0)), None)
    >>> repr(m)
    'm:128;1.0,2.0;'
    >>>

    Comparisons are based on the value of the message, not the id.

    >>> m = Message(128, Vector((1.0, 2.0)), -5.0)
    >>> n = Message(42, m.position, m.value)
    >>> m == n
    True
    >>> m > n
    False
    >>> m > n
    False
    >>> n.value = m.value - 1
    >>> m < n
    False
    >>> n < m
    True
    >>> m > n
    True
    >>>

    Attributes:
        sender: ID of the sending particle.
        position: Position of the particle.
        value: Value of the particle at `position`.
    """
    CLASS_ID = 'm'

    def __init__(self, sender, position, value):
        self.sender = sender
        self.position = position
        self.value = value

    @classmethod
    def unpack(cls, state):
        """Unpacks a state string, returning a new Message.

        The state string would have been created with repr(message).
        """
        prefix = cls.CLASS_ID + ':'
        assert state.startswith(prefix)
        state = state[len(prefix):]
        sender, pos, value = state.split(';')
        sender = int(sender)
        pos = Vector.unpack(pos)
        value = float(value)
        return cls(sender, pos, value)

    def __repr__(self):
        fields = (self.sender, self.position, self.value)
        strings = ((repr(x) if x is not None else '') for x in fields)
        return '%s:%s' % (self.CLASS_ID, ';'.join(strings))

    def __lt__(self, other):
        if isinstance(other, Message):
            return self.value < other.value
        else:
            return NotImplemented

    def __gt__(self, other):
        if isinstance(other, Message):
            return self.value > other.value
        else:
            return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Message):
            return self.value == other.value
        else:
            return NotImplemented


class SEParticle(Particle):
    """An extension to Particle that adds fields for speculative execution:

    specpbest - boolean flag telling whether or not this SEParticle came from
        assuming an updated pbest or not

    specnbestid - int that holds the id of the particle this SEParticle guessed
        was the new nbest.  -1 means there was no new nbest.

    We'll redo some doctests here, as repr and unpack have changed.

    >>> p = Particle(42, Vector((1.0, 2.0)), Vector((3.0, 4.0)))
    >>> p = SEParticle(p, False, 4)
    >>> repr(p)
    'sep:42;0;0;1.0,2.0;3.0,4.0;;1.0,2.0;;1.0,2.0;;False;4'
    >>> p.batches = 100
    >>> p.iters = 200
    >>> p.pbestpos = Vector((6.0, 7.0))
    >>> p.nbestpos = Vector((8.0, 9.0))
    >>> p.value = -10.0
    >>> p.pbestval = -11.0
    >>> p.nbestval = -12.0
    >>> repr(p)
    'sep:42;100;200;1.0,2.0;3.0,4.0;-10.0;6.0,7.0;-11.0;8.0,9.0;-12.0;False;4'
    >>> q = unpack(repr(p))
    >>> repr(q) == repr(p)
    True
    >>>
    """
    CLASS_ID = 'sep'

    def __init__(self, p, specpbest=False, specnbestid=-1):
        self.id = p.id
        self.pos = p.pos
        self.vel = p.vel
        self.value = p.value
        self.pbestpos = p.pbestpos
        self.pbestval = p.pbestval
        self.nbestpos = p.nbestpos
        self.nbestval = p.nbestval
        self.batches = p.batches
        self.iters = p.iters

        self.specpbest = specpbest
        self.specnbestid = specnbestid

    @classmethod
    def unpack(cls, state):
        """Unpacks a state string, returning a new SEParticle.

        The state string would have been created with repr(separticle).
        """
        prefix = cls.CLASS_ID + ':'
        assert state.startswith(prefix)
        state = state[len(prefix):]
        (id, batches, iters, pos, vel, value, pbestpos, pbestval,
                nbestpos, nbestval, specpbest, specnbestid) = state.split(';')
        id = int(id)
        pos = Vector.unpack(pos)
        vel = Vector.unpack(vel)
        if value:
            value = float(value)
        else:
            value = None
        p = Particle(id, pos, vel, value)
        p.batches = int(batches)
        p.iters = int(iters)
        p.pbestpos = Vector.unpack(pbestpos)
        if pbestval:
            p.pbestval = float(pbestval)
        else:
            p.pbestval = None
        p.nbestpos = Vector.unpack(nbestpos)
        if nbestval:
            p.nbestval = float(nbestval)
        else:
            p.nbestval = None
        if specpbest == 'False':
            specpbest = False
        else:
            specpbest = True
        sep = cls(p, specpbest, int(specnbestid))
        return sep

    def make_message_particle(self):
        m = SEMessageParticle(self)
        return m

    def make_real_particle(self):
        p = Particle(self.id, self.pos, self.vel, self.value)
        p.pbestpos = self.pbestpos
        p.pbestval = self.pbestval
        p.nbestpos = self.nbestpos
        p.nbestval = self.nbestval
        p.iters = self.iters
        p.rand = None
        return p

    def __str__(self):
        return "pos: %r; vel: %r; value: %r; pbestpos: %r; pbestval: %r; "\
               "specpbest: %r; specnbestid: %r"% (
                self.pos, self.vel, self.value, self.pbestpos, self.pbestval,
                self.specpbest, self.specnbestid)

    def __repr__(self):
        fields = (self.id, self.batches, self.iters, self.pos, self.vel,
                self.value, self.pbestpos, self.pbestval, self.nbestpos,
                self.nbestval, self.specpbest, self.specnbestid)
        strings = ((repr(x) if x is not None else '') for x in fields)
        return '%s:%s' % (self.CLASS_ID, ';'.join(strings))

    def copy(self):
        """Performs a deep copy and returns the new Particle.
        """
        p = Particle(self.id, self.pos, self.vel, self.value)
        p.pbestpos = self.pbestpos
        p.pbestval = self.pbestval
        p.nbestpos = self.nbestpos
        p.nbestval = self.nbestval
        p.batches = self.batches
        p.iters = self.iters
        sep = SEParticle(p, self.specpbest, self.specnbestid)
        return sep

class Dummy(Particle):
    """A dummy particle that just has an id and a rand, for use with SpecEx."""
    CLASS_ID = 'd'

    def __init__(self, id, iters, batches):
        self.id = id
        self.iters = iters
        self.batches = batches
        self.rand = None


class MessageParticle(Particle):
    """A complete particle that is actually a message."""
    CLASS_ID = 'mp'

    def __init__(self, p):
        self.id = p.id
        self.pos = p.pos
        self.vel = p.vel
        self.value = p.value
        self.pbestpos = p.pbestpos
        self.pbestval = p.pbestval
        self.nbestpos = p.nbestpos
        self.nbestval = p.nbestval
        self.batches = p.batches
        self.iters = p.iters

    @classmethod
    def unpack(cls, state):
        """Unpacks a state string, returning a new SEParticle.

        The state string would have been created with repr(separticle).
        """
        prefix = cls.CLASS_ID + ':'
        assert state.startswith(prefix)
        state = state[len(prefix):]
        (id, batches, iters, pos, vel, value, pbestpos, pbestval,
                nbestpos, nbestval) = state.split(';')
        id = int(id)
        pos = Vector.unpack(pos)
        vel = Vector.unpack(vel)
        if value:
            value = float(value)
        else:
            value = None
        p = Particle(id, pos, vel, value)
        p.batches = int(batches)
        p.iters = int(iters)
        p.pbestpos = Vector.unpack(pbestpos)
        if pbestval:
            p.pbestval = float(pbestval)
        else:
            p.pbestval = None
        p.nbestpos = Vector.unpack(nbestpos)
        if nbestval:
            p.nbestval = float(nbestval)
        else:
            p.nbestval = None
        m = cls(p)
        return m

    def copy(self):
        """Performs a deep copy and returns the new Particle.
        """
        p = Particle(self.id, self.pos, self.vel, self.value)
        p.pbestpos = self.pbestpos
        p.pbestval = self.pbestval
        p.nbestpos = self.nbestpos
        p.nbestval = self.nbestval
        p.batches = self.batches
        p.iters = self.iters
        mp = MessageParticle(p)
        return mp
    

class SEMessageParticle(SEParticle):
    """A complete particle that is actually a message."""
    CLASS_ID = 'semp'

    def __init__(self, p):
        self.id = p.id
        self.pos = p.pos
        self.vel = p.vel
        self.value = p.value
        self.pbestpos = p.pbestpos
        self.pbestval = p.pbestval
        self.nbestpos = p.nbestpos
        self.nbestval = p.nbestval
        self.batches = p.batches
        self.iters = p.iters
        self.specpbest = p.specpbest
        self.specnbestid = p.specnbestid

    @classmethod
    def unpack(cls, state):
        """Unpacks a state string, returning a new SEParticle.

        The state string would have been created with repr(separticle).
        """
        prefix = cls.CLASS_ID + ':'
        assert state.startswith(prefix)
        state = state[len(prefix):]
        (id, batches, iters, pos, vel, value, pbestpos, pbestval,
                nbestpos, nbestval, specpbest, specnbestid) = state.split(';')
        id = int(id)
        pos = Vector.unpack(pos)
        vel = Vector.unpack(vel)
        if value:
            value = float(value)
        else:
            value = None
        p = Particle(id, pos, vel, value)
        p.batches = int(batches)
        p.iters = int(iters)
        p.pbestpos = Vector.unpack(pbestpos)
        if pbestval:
            p.pbestval = float(pbestval)
        else:
            p.pbestval = None
        p.nbestpos = Vector.unpack(nbestpos)
        if nbestval:
            p.nbestval = float(nbestval)
        else:
            p.nbestval = None
        if specpbest == 'False':
            specpbest = False
        else:
            specpbest = True
        sep = SEParticle(p, specpbest, int(specnbestid))
        sem = cls(sep)
        return sem

    def copy(self):
        """Performs a deep copy and returns the new Particle.
        """
        p = Particle(self.id, self.pos, self.vel, self.value)
        p.pbestpos = self.pbestpos
        p.pbestval = self.pbestval
        p.nbestpos = self.nbestpos
        p.nbestval = self.nbestval
        p.batches = self.batches
        p.iters = self.iters
        sep = SEParticle(p, self.specpbest, self.specnbestid)
        semp = SEMessageParticle(sep)
        return semp


class Swarm(object):
    """A set of particles.

    >>> particles = [Particle(42, 1.0, 2.0), Particle(41, 3.0, 4.0)]
    >>> s = Swarm(17, particles)
    >>> repr(s)
    's:17&p:42;0;0;1.0;2.0;;1.0;;1.0;&p:41;0;0;3.0;4.0;;3.0;;3.0;'
    >>>

    Test of round trip:
    >>> t = unpack(repr(s))
    >>> repr(t) == repr(s)
    True
    >>>
    """
    CLASS_ID = 's'

    def __init__(self, sid, particles):
        self.id = sid
        self.particles = list(particles)

        self.rand = None

    def __len__(self):
        return len(self.particles)

    def __getitem__(self, item):
        return self.particles[item]

    def __iter__(self):
        return iter(self.particles)

    def iters(self):
        return self.particles[0].iters

    def batches(self):
        return self.particles[0].batches

    @classmethod
    def unpack(cls, state):
        """Unpacks a state string, returning a new Swarm.

        The state string would have been created with repr(swarm).
        """
        strings = state.split('&')
        start = strings[0]
        prefix = cls.CLASS_ID + ':'
        assert start.startswith(prefix)
        sid = int(start[len(prefix):])
        particles = [Particle.unpack(s) for s in strings[1:]]
        return cls(sid, particles)

    def __repr__(self):
        strings = ['%s:%s' % (self.CLASS_ID, self.id)]
        strings += [repr(p) for p in self.particles]
        return '&'.join(strings)


def unpack(state):
    """Unpacks a state string, returning a Particle or Message."""
    start, _ = state.split(':', 1)
    try:
        cls = CLASS_IDS[start]
    except KeyError:
        raise ValueError('Cannot unpack a state string of class "%s".' % start)
    return cls.unpack(state)


# Valid class identifiers and their corresponding classes.
CLASSES = (Particle, Message, SEParticle, Swarm, Dummy, MessageParticle,
        SEMessageParticle)
CLASS_IDS = dict((cls.CLASS_ID, cls) for cls in CLASSES)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
