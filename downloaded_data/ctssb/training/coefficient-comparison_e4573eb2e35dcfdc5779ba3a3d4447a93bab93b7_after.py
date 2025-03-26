"""Definition of all similarity coefficients

Functions should be defined as (set, set) -> float,
with return value in [0;1].

"""


def functions() -> tuple:
    """Return functions of this module, excluding this one"""
    return tuple(attr for name, attr in globals().items()
                 if callable(attr) and name != 'functions')


def jaccard(a:set, b:set) -> float:
    return len(a & b) / (len(a | b))

def dice(a:set, b:set) -> float:
    return 2 * len(a & b) / (len(a) + len(b))
