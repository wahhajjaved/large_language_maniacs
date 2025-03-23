import os, sys
from pypy.objspace.std.objspace import StdObjSpace
# XXX from pypy.annotation.model import *
# since we are execfile()'ed this would pull some
# weird objects into the globals, which we would try to pickle.
from pypy.annotation.model import SomeList, SomeString
from pypy.annotation.listdef import ListDef
from pypy.interpreter import gateway
from pypy.interpreter.error import OperationError

# WARNING: this requires the annotator.
# There is no easy way to build all caches manually,
# but the annotator can do it for us for free.

try:
    this_dir = os.path.dirname(__file__)
except NameError:
    this_dir = os.path.dirname(sys.argv[0])

def debug(msg): 
    os.write(2, "debug: " + msg + '\n')

# __________  Entry point  __________

def entry_point(argvstring):
    debug("entry point starting") 
    debug(argvstring) 
    argv = argvstring.split('\x00')
    for arg in argv: 
        debug(" argv -> " + arg)
    try:
        w_argv = space.newlist([space.wrap(s) for s in argv])
        w_exitcode = space.call_function(w_entry_point, w_argv)
        # try to pull it all in
    ##    from pypy.interpreter import main, interactive, error
    ##    con = interactive.PyPyConsole(space)
    ##    con.interact()
    except OperationError, e:
        debug("OperationError:")
        debug(e.w_type.name)
        debug(space.str_w(space.str(e.w_value)))
        return 1
    return space.int_w(w_exitcode)

# _____ Define and setup target ___

def target():
    global space, w_entry_point
    # disable translation of the whole of classobjinterp.py
    StdObjSpace.setup_old_style_classes = lambda self: None
    # disable geninterp for now -- we have faaar toooo much interp-level code
    # for the poor translator already
    # XXX why can't I enable this? crashes the annotator!
    space = StdObjSpace(nofaking=True,
                        compiler="pyparseapp",
                        translating=True,
                        geninterp=False)

    # manually imports app_main.py
    filename = os.path.join(this_dir, 'app_main.py')
    w_dict = space.newdict([])
    space.exec_(open(filename).read(), w_dict, w_dict)
    w_entry_point = space.getitem(w_dict, space.wrap('entry_point'))

    # sanity-check: call the entry point
    res = entry_point("pypy\x00app_example.py")
    assert res == 0

    return entry_point, [SomeString()]

def get_llinterp_args():
    from pypy.rpython import rstr
    ll_str = rstr.string_repr.convert_const("app_example.py")
    return [ll_str]


# _____ Run translated _____
def run(c_entry_point):
    argv = [os.path.join(this_dir, 'app_example.py')]
    exitcode = c_entry_point('\x00'.join(argv))
    assert exitcode == 0
