from numpy import sin, cos, pi, sign
import os
import sys
cpath = sys.path[0]


def pathjoin(path): return os.path.join(cpath, path)


class piece:
    def __init__(self, typ, clr):
        self.PTYPE = ptype(typ)
        self.MOVES = moves(self.PTYPE, color(clr))
        self.COLOR = color(clr)
        self.TUP = (self.PTYPE, self.COLOR)
        if self.MOVES.PMOVES is None:
            self.prom = None
            self.PROMOTABLE = False
        else:
            self.prom = False
            self.PROMOTABLE = True

    def __str__(self):
        return str(self.PTYPE)+str(self.COLOR)

    def __eq__(self, other): return self.TUP == other.TUP

    def __bool__(self): return not isinstance(self, nopiece)

    def __hash__(self): return hash(self.TUP)

    def __repr__(self): return f"{repr(self.PTYPE)} {repr(self.COLOR)}"

    def promote(self):
        if self.prom is None:
            raise NotPromotableException
        elif self.prom:
            raise PromotedException
        else:
            self.PTYPE = self.PTYPE.prom()
            self.MOVES = self.MOVES.prom()
            self.prom = True

    def demote(self):
        if not self.prom:
            raise DemotedException
        else:
            self.PTYPE = self.PTYPE.dem()
            self.MOVES = self.MOVES.dem()

    def flipsides(self):
        self.COLOR = color(self.COLOR.OTHER)

    def canmove(self, relloc): return self.MOVES.canmove(relloc)


class nopiece(piece):
    def __init__(self):
        super().__init__('-', '-')


class moves:
    with open(pathjoin('shogimoves.txt')) as movef:
        movelist = movef.readlines()
        movedict = {}
        for n, line in enumerate(movelist):
            line = line.strip()
            var = line.split(' ')
            movelist[n] = var
            movedict[line[0]] = tuple(var[1:])

    def __init__(self, piecenm, clr):
        piecenm = str(piecenm)
        pcmvlist = list(self.movedict[piecenm])
        if clr == color(1):
            for y, var in enumerate(pcmvlist):
                pcmvlist[y] = var[4:]+var[:4]
        mvlist = pcmvlist[0]
        self.DMOVES = {direction(x): mvlist[x] for x in range(8)}
        self.DMOVES[direction(8)] = '-'
        mvlist = pcmvlist[1]
        if mvlist in ('None', 'enoN'):
            self.PMOVES = None
        else:
            self.PMOVES = {direction(x): mvlist[x] for x in range(8)}
            self.PMOVES[direction(8)] = '-'
        self.MOVES = [self.DMOVES, self.PMOVES]
        self.ispromoted = False
        self.CMOVES = self.MOVES[self.ispromoted]

    def __getitem__(self, attr): return self.CMOVES[attr]

    def __iter__(self): yield from self.CMOVES

    def canmove(self, relloc):  # Takes coord object
        vec = direction(relloc)
        dist = max(abs(relloc))
        magicvar = self[vec]
        if magicvar == '-':
            return False
        elif magicvar == '1':
            return dist == 1
        elif magicvar == '+':
            return True
        elif magicvar == 'T':
            return abs(relloc.x) == 1 and relloc.y == 2

    def prom(self):
        self.ispromoted = True
        self.CMOVES = self.MOVES[self.ispromoted]

    def dem(self):
        self.ispromoted = False
        self.CMOVES = self.MOVES[self.ispromoted]


class color:
    def __init__(self, turnnum):
        if isinstance(turnnum, int):
            self.INT = turnnum
            self.NAME = 'wb'[self.INT]
        elif isinstance(turnnum, str):
            if turnnum == '-':
                self.NAME = turnnum
                self.INT = -1
            else:
                self.NAME = turnnum
                self.INT = 'wb'.index(turnnum)
        elif isinstance(turnnum, color):
            self.INT = turnnum.INT
            self.NAME = 'wb'[self.INT]
        else:
            raise TypeError
        self.OTHER = 'bw'[self.INT]
        self.FULLNM = ['White', 'Black'][self.INT]

    def __str__(self): return self.NAME

    def __repr__(self): return self.FULLNM

    def __int__(self): return self.INT

    def __eq__(self, other): return self.INT == other.INT

    def __hash__(self): return hash((self.INT, self.NAME))

    def flip(self): return color(int(not self.INT))

    def other(self): return color(self.OTHER)


class ptype:
    with open(pathjoin('shoginames.txt')) as namtxt:
        namelist = namtxt.readlines()
        for x, y in enumerate(namelist):
            namelist[x] = y.strip().split(': ')
        namedict = {x[0]: x[1] for x in namelist}

    def __init__(self, typ):
        typ = str(typ)
        self.TYP = typ.lower()
        self.NAME = self.namedict[self.TYP]

    def __str__(self): return self.TYP

    def __repr__(self): return self.NAME

    def __eq__(self, other): return repr(self) == repr(other)

    def __hash__(self): return hash((self.TYP, self.NAME))

    def prom(self):
        self.TYP = self.TYP.upper()
        self.NAME = '+'+self.NAME

    def dem(self):
        self.TYP = self.TYP.lower()
        self.NAME = self.NAME.replace('+', '')


class coord:
    def __init__(self, xy):
        if isinstance(xy, str):
            self.x = '987654321'.index(xy[1])
            self.y = 'abcdefghi'.index(xy[0])
        elif isinstance(xy, int) and abs(xy) in range(9):
            self.x = xy
            self.y = xy
        elif all(abs(x) in range(9) for x in xy):
            self.x = int(xy[0])
            self.y = int(xy[1])
        else:
            raise ValueError(xy)
        self.TUP = (self.x, self.y)
        self.XSTR = '987654321'[abs(self.x)]
        self.YSTR = 'abcdefghi'[abs(self.y)]

    def __str__(self): return self.YSTR+self.XSTR

    def __eq__(self, other): return hash(self) == hash(other)

    def __iter__(self): yield from self.TUP

    def __getitem__(self, index): return self.TUP[index]

    def __add__(self, other): return coord((self.x+other.x, self.y+other.y))

    def __sub__(self, other): return coord((self.x-other.x, self.y-other.y))

    def __mul__(self, other): return coord((self.x*other.x, self.y*other.y))

    def __hash__(self): return hash(self.TUP)

    def __abs__(self): return coord((abs(self.x), abs(self.y)))

    def __repr__(self): return f"coord('{self}')"


class direction(coord):
    lis = {(round(sin(pi*x/4)), -round(cos(pi*x/4))): x for x in range(8)}
    invlis = [(round(sin(pi*x/4)), -round(cos(pi*x/4))) for x in range(8)]

    def __init__(self, direction):
        if direction == (0, 0):
            self.DIR = 8
        elif isinstance(direction, coord):
            self.DIR = self.make(direction.x, direction.y)
        elif isinstance(direction, tuple):
            self.DIR = self.make(*direction)
        elif isinstance(direction, int):
            self.DIR = direction
        else:
            raise TypeError
        if self.DIR != 8:
            self.TUP = self.invlis[self.DIR]
        else:
            self.TUP = (0, 0)
        super().__init__(self.TUP)

    def __repr__(self): return f"direction({self.DIR})"

    def __hash__(self): return hash(self.TUP)

    def make(self, xvar, yvar):
        if not xvar == yvar == 0:
            return self.lis[(sign(xvar), sign(yvar))]


class NotPromotableException(Exception):
    pass


class PromotedException(Exception):
    pass


class DemotedException(Exception):
    pass


class board:
    def __init__(self):
        with open(pathjoin('shogiboard.txt')) as boardtxt:
            boardtxt = boardtxt.readlines()
            for x, y in enumerate(boardtxt):
                boardtxt[x] = y.split()
        self.PIECES = {}
        for (x, y) in self.it():
            if boardtxt[y][x] != '--':
                self.PIECES[coord((x, y))] = piece(*boardtxt[y][x])
        self.INVPIECES = {v: x for x, v in self.PIECES.items()}
        self.CAPTURED = {color(x): [] for x in range(2)}
        self.PCSBYCLR = {}
        self.currplyr = color(0)
        for x in range(1):
            theclr = color(x)
            self.PCSBYCLR[theclr] = {}
            for x, y in self.PIECES.items():
                if y.COLOR == self.currplyr:
                    self.PCSBYCLR[theclr][x] = y
        self.lastmove = (None, None)
        self.nextmove = (None, None)

    def __str__(self):
        toreturn = ""
        toreturn += f"Black pieces: {' '.join(self.CAPTURED[color(1)])}\n\n"
        toreturn += f"  {'  '.join('987654321')}\n"
        for x, var in enumerate(self):
            toreturn += f"{'abcdefghi'[x]} {' '.join(str(k) for k in var)}\n"
        toreturn += f"White pieces: {' '.join(self.CAPTURED[color(1)])}\n"
        return toreturn

    def __iter__(self):
        yield from [[self[x, y] for x in range(9)] for y in range(9)]

    def __getitem__(self, index):
        if isinstance(index, (tuple, coord)):
            coords = coord(index)
            return self.PIECES.get(coords, nopiece())
        elif isinstance(index, piece):
            return self.INVPIECES[index]

    def it(self): yield from [(x, y) for x in range(9) for y in range(9)]

    def occupied(self): yield from self.PIECES

    def move(self, current, new):
        if not isinstance(self[new], nopiece):
            self.capture(new)
        self.PIECES[coord(new)] = self.PIECES.pop(current)

    def capture(self, new):
        piece = self[new]
        piece.demote()
        piece.flipsides()
        self.CAPTURED[self.currplyr] = piece
        del self.PIECES[new]

    def canpromote(self, space):
        zonevar = [[6, 7, 8], [0, 1, 2]]
        return space.y in zonevar[int(self.currplyr)]

    def putinplay(self, piece, movedto):
        player = self.currplyr
        self.CAPTURED[player].remove(piece)
        if not isinstance(self[movedto], nopiece):
            raise IllegalMove

    def playerpcs(self): yield from self.PCSBYCLR[self.currplyr]

    def enemypcs(self): yield from self.PCSBYCLR[self.currplyr.other()]


class IllegalMove(Exception):
    pass


class row:
    def __init__(self, loc, vect):
        loc = coord(loc)
        vect = direction(vect)
        self.SPACES = set()
        for x in range(8):
            if any(abs(x+z) > 8 for z in loc):
                break
            x = coord((x, x))
            self.SPACES.add(loc+x*vect)
        for x in range(-8, 0, -1):
            if any(abs(x+z) > 8 for z in loc):
                break
            x = coord((x, x))
            self.SPACES.add(loc+x*vect)

    def __iter__(self): yield from self.SPACES


class Shogi:
    def __init__(self):
        self.piece = piece
        self.board = board
        self.nopiece = nopiece
        self.color = color
        self.moves = moves
        self.ptype = ptype
        self.direction = direction
        self.coord = coord
        self.NotPromotableException = NotPromotableException
        self.PromotedException = PromotedException
        self.DemotedException = DemotedException
        self.IllegalMove = IllegalMove