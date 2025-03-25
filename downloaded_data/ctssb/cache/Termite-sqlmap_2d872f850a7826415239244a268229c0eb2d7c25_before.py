#!/usr/bin/env python

"""
$Id$

Copyright (c) 2006-2010 sqlmap developers (http://sqlmap.sourceforge.net/)
See the file 'doc/COPYING' for copying permission
"""

from lib.controller.handler import setHandler
from lib.core.common import getHtmlErrorFp
from lib.core.common import dataToStdout
from lib.core.data import conf
from lib.core.data import kb
from lib.core.data import paths
from lib.core.exception import sqlmapUnsupportedDBMSException
from lib.core.settings import SUPPORTED_DBMS
from lib.techniques.blind.timebased import timeTest
from lib.techniques.brute.use import columnExists
from lib.techniques.brute.use import tableExists
from lib.techniques.error.test import errorTest
from lib.techniques.inband.union.test import unionTest
from lib.techniques.outband.stacked import stackedTest

def action():
    """
    This function exploit the SQL injection on the affected
    url parameter and extract requested data from the
    back-end database management system or operating system
    if possible
    """

    # First of all we have to identify the back-end database management
    # system to be able to go ahead with the injection
    setHandler()

    if not conf.dbmsHandler:
        htmlParsed = getHtmlErrorFp()

        errMsg  = "sqlmap was not able to fingerprint the "
        errMsg += "back-end database management system"

        if htmlParsed:
            errMsg += ", but from the HTML error page it was "
            errMsg += "possible to determinate that the "
            errMsg += "back-end DBMS is %s" % htmlParsed

        if htmlParsed and htmlParsed.lower() in SUPPORTED_DBMS:
            errMsg += ". Do not specify the back-end DBMS manually, "
            errMsg += "sqlmap will fingerprint the DBMS for you"
        elif kb.nullConnection:
            errMsg += ". You can try to rerun without using optimization "
            errMsg += "switch '%s'" % ("-o" if conf.optimize else "--null-connection")
        else:
            errMsg += ". Support for this DBMS will be implemented at "
            errMsg += "some point"

        raise sqlmapUnsupportedDBMSException, errMsg

    dataToStdout("%s\n" % conf.dbmsHandler.getFingerprint())

    # Techniques options
    if conf.stackedTest:
        conf.dumper.technic("stacked queries injection payload", stackedTest())

    if conf.errorTest:
        conf.dumper.technic("error-based injection payload", errorTest())

    if conf.timeTest:
        conf.dumper.technic("time-based blind injection payload", timeTest())

    if conf.unionTest and kb.unionPosition is None:
        conf.dumper.technic("inband injection payload", unionTest())

    # Enumeration options
    if conf.getBanner:
        conf.dumper.banner(conf.dbmsHandler.getBanner())

    if conf.getCurrentUser:
        conf.dumper.currentUser(conf.dbmsHandler.getCurrentUser())

    if conf.getCurrentDb:
        conf.dumper.currentDb(conf.dbmsHandler.getCurrentDb())

    if conf.isDba:
        conf.dumper.dba(conf.dbmsHandler.isDba())

    if conf.getUsers:
        conf.dumper.users(conf.dbmsHandler.getUsers())

    if conf.getPasswordHashes:
        conf.dumper.userSettings("database management system users password hashes",
                                 conf.dbmsHandler.getPasswordHashes(), "password hash")

    if conf.getPrivileges:
        conf.dumper.userSettings("database management system users privileges",
                                 conf.dbmsHandler.getPrivileges(), "privilege")

    if conf.getRoles:
        conf.dumper.userSettings("database management system users roles",
                                 conf.dbmsHandler.getRoles(), "role")

    if conf.getDbs:
        conf.dumper.dbs(conf.dbmsHandler.getDbs())

    if conf.getTables:
        conf.dumper.dbTables(conf.dbmsHandler.getTables())

    if conf.commonTables:
        conf.dumper.dbTables(tableExists(paths.COMMON_TABLES))

    if conf.getColumns:
        conf.dumper.dbTableColumns(conf.dbmsHandler.getColumns())

    if conf.commonTables:
        conf.dumper.dbTableColumns(columnExists(paths.COMMON_COLUMNS))

    if conf.dumpTable:
        conf.dumper.dbTableValues(conf.dbmsHandler.dumpTable())

    if conf.dumpAll:
        conf.dbmsHandler.dumpAll()

    if conf.search:
        conf.dbmsHandler.search()

    if conf.query:
        conf.dumper.query(conf.query, conf.dbmsHandler.sqlQuery(conf.query))

    if conf.sqlShell:
        conf.dbmsHandler.sqlShell()

    # User-defined function options
    if conf.udfInject:
        conf.dbmsHandler.udfInjectCustom()

    # File system options
    if conf.rFile:
        conf.dumper.rFile(conf.rFile, conf.dbmsHandler.readFile(conf.rFile))

    if conf.wFile:
        conf.dbmsHandler.writeFile(conf.wFile, conf.dFile, conf.wFileType)

    # Operating system options
    if conf.osCmd:
        conf.dbmsHandler.osCmd()

    if conf.osShell:
        conf.dbmsHandler.osShell()

    if conf.osPwn:
        conf.dbmsHandler.osPwn()

    if conf.osSmb:
        conf.dbmsHandler.osSmb()

    if conf.osBof:
        conf.dbmsHandler.osBof()

    # Windows registry options
    if conf.regRead:
        conf.dumper.registerValue(conf.dbmsHandler.regRead())

    if conf.regAdd:
        conf.dbmsHandler.regAdd()

    if conf.regDel:
        conf.dbmsHandler.regDel()

    # Miscellaneous options
    if conf.cleanup:
        conf.dbmsHandler.cleanup()

    if conf.direct:
        conf.dbmsConnector.close()
