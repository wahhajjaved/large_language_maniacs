__id__ = "$Id"

from atoms import *
from pieces import *

class GameHist:
    """The game history.  There intended to keep patches (see 'board' module) here."""
    
    # supported chess variants
    variants = 'ortodox', 'hybrids'

    # tags requered by PGN standard
    required_tags = 'Event', 'Site', 'Date', 'Round', 'White', 'Black', 'Result'
    
    def __init__(self, **tags):
        try:
            import time
            date = time.strftime()
        except:
            date = '????.??.??'
        
        # all _requred_ tags
        self.tags = {'Event': '?', 'Site': '?', 'Date': date, 'Round': '-',
                     'White': '-', 'Black': '-', 'Result': '*'}
        for tag in tags.keys():
            # tags may be overwritten
            self.tags[tag] = tags[tag]

        # 'Variant' is an optional tag, 'ortodox' by default
        if not self.tags.has_key('Variant'):
            variant = 'ortodox'
        else:
            variant = self.tags['Variant']
            if variant == 'ortodox':
                del self.tags['Variant']
        
        if not variant in GameHist.variants:
            raise Exception, ("variant '%s' is not supported" % variant)
        
        self.variant = variant
        self.setup()

    def setup(self):
        self.history = []
        # semimove counter
        self.currPly = 0
        self.lastPly = 0
    
    def next(self):
        assert self.currPly <= self.lastPly
        if self.currPly < self.lastPly:
            self.currPly += 1
            return self.history[self.currPly-1]
        raise Exception, "it's the last position"
    
    def prev(self):
        assert self.currPly >= 0
        if self.currPly > 0:
            self.currPly -= 1
            return self.history[self.currPly]
        raise Exception, "it's the first position"
    
    def apply(self, move):
        "destructively updates the history; the tail is removed"
        self.history[self.currPly:] = [move]
        self.currPly += 1

    def commit(self):
        self.lastPly = self.currPly

class GameHist_PGN(GameHist):
    """Move_PGN are to kept here."""

    def load(str):
        # not implemented
        pass

    load = staticmethod(load)

    def save(self, fname):
        fo = open(fname, 'w')
        fo.write(str(self))
        fo.close()
    
    def __str__(self):
        # FIXME: format
        res = ''
        res += self.str_tags()
        res += '\n'
        for ply in range(len(self.history)):
            if not ply%2:
                res += (' ' + str(ply/2+1) + '.')
            res += (' ' + self.history[ply])

        res += ('\n' + self.tags['Result'] + '\n')
        return res

    def str_tag(tag, value):
        return '[' + tag + ' "' + value + '"]\n'

    str_tag = staticmethod(str_tag)

    def str_tags(self):
        res = ''
        # required first...
        for tag in GameHist.required_tags:
            res += GameHist.str_tag(tag, self.tags[tag])
        # ...then optional tags
        for tag in self.tags.keys():
            if not tag in GameHist.required_tags:
                res += GameHist.str_tag(tag, self.tags[tag])
        return res


class Move_PGN:

    """This class describes the information about a move as it written in PGN without
    understanding the current position.
    """

    # pass_sign should not be used (?)
    capture_sign, join_sign, pass_sign = 'x', '^', '-'
    check_sign, mate_sign = '+', '#'

    def __init__(self, actor, src, dst, **ops):
        """
        'actor' is the piece moving from 'src' to 'dst'.
        'src' must be either None, ('file', file), ('rank', rank), ('loc', loc).
        The options are: 'promote' (None either PrimePiece), 'movesign' (None, 'x', '^', '-'),
        'check' (None, '+', '#').
        """
        assert isinstance(actor, Piece)
        assert src.__class__ is types.StringType and len(src) == 2
        assert dst is None or len(dst) == 2 # dst may be a tupple
        
        self.actor = actor
        self.src = src
        self.dst = dst

        self.promote = ops.get('promote')
        self.movesign = ops.get('movesign')
        self.check = ops.get('check')

    def __str__(self):
        res = ''
        if not isinstance(self.actor, PawnPiece):
            res += self.actor.sym
        if src:
            res += src[1]
        # movesign
        res += dst
        if self.promote:
            assert isinstance(self.promote, PrimePiece)
            res += ('=' + self.promote.sym)
        if self.check:
            res += self.check
        return res
