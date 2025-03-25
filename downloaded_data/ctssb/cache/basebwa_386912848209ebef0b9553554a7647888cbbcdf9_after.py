from pysmvt import db
from sqlitefktg4sa import auto_assign
from pysmvt import commands as cmds
from pysmvt import modimport
from pysmvt.script import console_broadcast

def action_module(modname='', template=('t', 'pysapp'),
        interactive=True, verbose=False, overwrite=True):
    """ creates a new module file structure (pysapp default)"""
    cmds.action_module(modname, template, interactive, verbose, overwrite)

@console_broadcast
def action_pysapp_initdb(sqlite_triggers=True):
    """ initialize the database """
    # create foreign keys for SQLite
    if sqlite_triggers and not getattr(db.meta, 'triggers', False):
        auto_assign(db.meta, db.engine)
        db.meta.triggers = True

    # create the database objects
    #print db
    #for t in db.meta.tables:
    #    print t
    db.meta.create_all(bind=db.engine)
    
    # add a session to the db
    #db.sess = db.Session()

@console_broadcast
def action_pysapp_initapp():
    permission_add = modimport('users.actions', 'permission_add')
    permission_add(name=u'webapp-controlpanel', safe='unique')