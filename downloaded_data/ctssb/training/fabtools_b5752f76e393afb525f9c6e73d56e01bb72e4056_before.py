"""
Fabric tools for managing PostgreSQL users and databases
"""
from __future__ import with_statement

from fabric.api import *


def _run_as_pg(command):
    """
    Run command as 'postgres' user
    """
    return sudo(command, user='postgres')


def user_exists(name):
    """
    Check if a PostgreSQL user exists
    """
    with settings(hide('running', 'stdout', 'stderr', 'warnings'), warn_only=True):
        res = _run_as_pg('''psql -t -A -c "SELECT COUNT(*) FROM pg_user WHERE usename = '%(name)s';"''' % locals())
    return (res == "1")


def create_user(name, password):
    """
    Create a PostgreSQL user
    """
    _run_as_pg('''psql -c "CREATE USER %(name)s WITH PASSWORD '%(password)s';"''' % locals())


def database_exists(name):
    """
    Check if a PostgreSQL database exists
    """
    with settings(hide('running', 'stdout', 'stderr', 'warnings'), warn_only=True):
        return _run_as_pg('''psql -d %(name)s -c ""''' % locals()).succeeded


def create_database(name, owner, template='template0', encoding='UTF8', locale='en_US.UTF-8'):
    """
    Create a PostgreSQL database
    """
    _run_as_pg('''createdb --owner %(owner)s --template %(template)s --encoding=%(encoding)s\
 --lc-ctype=%(locale)s --lc-collate=%(locale)s %(name)s''' % locals())
