#
# (c) 2004-2007 Linbox / Free&ALter Soft, http://linbox.com
#
# $Id$
#
# This file is part of MMC.
#
# MMC is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# MMC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MMC; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from mmc.plugins.pulse2.group import ComputerGroupManager

from pulse2.database.dyngroup.dyngroup_database_helper import DyngroupDatabaseHelper
from pulse2.database.utilities import unique, toH, DbObject
from pulse2.database.sqlalchemy_tests import checkSqlalchemy
from pulse2.database.inventory.mapping import OcsMapping
from pulse2.utils import Singleton

from sqlalchemy import *
from sqlalchemy.orm import *

import datetime
import time
import re
import logging

SA_MAJOR = 0
SA_MINOR = 4
DATABASEVERSION = 9
MAX_REQ_NUM = 100

class UserTable(object):
    pass

class UserEntitiesTable(object):
    pass

class Inventory(DyngroupDatabaseHelper):
    """
    Class to query the LRS/Pulse2 inventory database, populated by OCS inventory.

    DyngroupDatabaseHelper is a Singleton, so is Inventory

    This class does not read the inventory files created by the LRS during a boot phase (/tftpboot/revoboot/log/*.ini)
    """

    def db_check(self):
        self.my_name = "Inventory"
        self.configfile = "inventory.ini"
        return DyngroupDatabaseHelper.db_check(self, DATABASEVERSION)

    def activate(self, config):
        self.logger = logging.getLogger()
        DyngroupDatabaseHelper.init(self)
        if self.is_activated:
            self.logger.info("Inventory don't need activation")
            return None
        self.logger.info("Inventory is activating")
        self.config = config
        PossibleQueries().init(self.config)
        self.db = create_engine(self.makeConnectionPath(), pool_recycle = self.config.dbpoolrecycle, pool_size = self.config.dbpoolsize, convert_unicode=True, echo = True)
        self.metadata = MetaData(self.db)
        self.initMappers()
        self.metadata.create_all()
        self.is_activated = True
        self.dbversion = self.getInventoryDatabaseVersion()
        self.logger.debug("Inventory finish activation")

    def initMappers(self):
        """
        Initialize all SQLalchemy mappers needed for the inventory database
        """
        self.table = {}
        self.klass = {}

        self.version = Table("Version", self.metadata, autoload = True)
        self.machine = Table("Machine", self.metadata, autoload = True)
        self.inventory = Table("Inventory", self.metadata, autoload = True)
        self.user = Table("User", self.metadata, autoload = True)
        self.userentities = Table('UserEntities',
                                  self.metadata,
                                  Column('fk_User', Integer, ForeignKey('User.id'), primary_key = True),
                                  Column('fk_Entity', Integer, ForeignKey('Entity.id'), primary_key = True))

        noms = self.config.getInventoryNoms()

        for item in self.config.getInventoryParts():
            # Declare the SQL table
            self.table[item] = Table(item, self.metadata, autoload = True)
            # Create the class that will be mapped
            # This will create the Bios, BootDisk, etc. classes
            exec "class %s(DbObject): pass" % item
            self.klass[item] = eval(item)
            # Map the python class to the SQL table
            mapper(self.klass[item], self.table[item])

            # Declare the has* SQL table
            hasitem = "has" + item
            has_columns = [
                          Column("machine", Integer, ForeignKey("Machine.id"), primary_key=True),
                          Column("inventory", Integer, ForeignKey("Inventory.id"), primary_key=True),
                          Column(item.lower(), Integer, ForeignKey(item + ".id"), primary_key=True)
                          ]
            if noms.has_key(item):
                for nom in noms[item]:
                    nomitem = "nom" + item + nom
                    self.table[nomitem] = Table(nomitem, self.metadata, autoload = True)
                    # add the needed column in hasTable
                    has_columns.append(Column(nom.lower(), Integer, ForeignKey(nomitem + ".id"), primary_key=True))
                    # Create the class that will be mapped
                    # This will create the hasBios, hasBootDisk, etc. classes
                    exec "class %s(object): pass" % nomitem
                    self.klass[nomitem] = eval(nomitem)
                    # Map the python class to the SQL table
                    mapper(eval(nomitem), self.table[nomitem])

            self.table[hasitem] = Table(hasitem, self.metadata, *has_columns)

            # Create the class that will be mapped
            # This will create the hasBios, hasBootDisk, etc. classes
            exec "class %s(object): pass" % hasitem
            self.klass[hasitem] = eval(hasitem)
            # Map the python class to the SQL table
            mapper(eval(hasitem), self.table[hasitem])

        mapper(Machine, self.machine)
        mapper(InventoryTable, self.inventory)
        mapper(UserTable, self.user)
        mapper(UserEntitiesTable, self.userentities)

    def getInventoryDatabaseVersion(self):
        """
        Return the inventory database version.
        We don't use this information for now, but if we can get it this means the database connection is working.

        @rtype: int
        """
        return self.version.select().execute().fetchone()[0]

    def inventoryExists(self, ctx, uuid):
        """
        Return True or False depending on the existance of machine "name" in the inventory DB

        @param name: the name of the machine
        @typa name: str

        @return: Return True if the machine exists in the inventory DB
        @rtype: bool
        """
        session = create_session()
        result = session.query(Machine).filter(self.machine.c.id == fromUUID(uuid)).all()
        session.close()
        if result and len(result) == 1:
            return True
        return False

    def complete_ctx(self, ctx):
        """
        Set user locations in current security context.
        """
        if not hasattr(ctx, "locations") or ctx.locations == None:
            logging.getLogger().debug("adding locations in context for user %s" % (ctx.userid))
            ctx.locations = self.getUserLocations(ctx.userid)
            ctx.locationsid = map(lambda e: e.id, ctx.locations)

    def __machinesOnlyQuery(self, ctx, pattern = None, session = None, count = False):
        self.complete_ctx(ctx)
        if not session:
            session = create_session()

        # doing dyngroups stuff
        join_query, query_filter = self.filter(ctx, self.machine, pattern, session.query(Machine), self.machine.c.id)

        # Join on entity table for location support
        join_query = join_query.join(self.table['hasEntity']).join(self.table['Entity']).join(self.inventory)
        
        query = session.query(Machine).select_from(join_query).filter(query_filter)
        # end of dyngroups

        # We first filter the computer list according to the entities the user
        # has the right to see.
        query = query.filter(self.table['Entity'].c.id.in_(ctx.locationsid))
        # Then we apply extra filter according to pattern content
        if pattern:
            if 'hostname' in pattern:
                query = query.filter(self.machine.c.Name.like("%" + pattern['hostname'] + "%"))
            if 'filter' in pattern:
                query = query.filter(self.machine.c.Name.like("%" + pattern['filter'] + "%"))
            if 'uuid' in pattern:
                query = query.filter(self.machine.c.id == fromUUID(pattern['uuid']))
            if 'location' in pattern:
                query = query.filter(self.table['Entity'].c.Label == pattern['location']).filter(self.inventory.c.Last == 1)
            if 'request' in pattern:
                request = pattern['request']
                if 'equ_bool' in pattern:
                    bool = pattern['equ_bool']
                else:
                    bool = None
                machines = map(lambda m: fromUUID(m), ComputerGroupManager().request(ctx, request, bool, 0, -1, ''))
                query = query.filter(self.machine.c.id.in_(machines))
            if 'gid' in pattern:
                gid = pattern['gid']

                machines = list()
                if ComputerGroupManager().isrequest_group(ctx, gid):
                    machines = map(lambda m: fromUUID(m), ComputerGroupManager().requestresult_group(ctx, gid, 0, -1, ''))
                else:
                     filt = ''
                     if pattern.has_key('hostname'):
                         filt = pattern['hostname']
                     if pattern.has_key('filter'):
                         filt = pattern['filter']
                     if count:
                         return ComputerGroupManager().countresult_group(ctx, gid, filt)
                     else:
                         min = 0
                         max = -1
                         if pattern.has_key('min'):
                             min = pattern['min']
                         if pattern.has_key('max'):
                             max = pattern['max']
                         machines = map(lambda m: fromUUID(m), ComputerGroupManager().result_group(ctx, gid, min, max, filt))

                query = query.filter(self.machine.c.id.in_(machines))
                if not ComputerGroupManager().isrequest_group(ctx, gid):
                    if count:
                        return query.count()
                    else:
                        return query

        if count:
            return query.count()
        else:
            return query.group_by(self.machine.c.id)

    def getMachinesOnly(self, ctx, pattern = None):
        """
        Return all available machines
        """
        session = create_session()
        query = self.__machinesOnlyQuery(ctx, pattern, session)

        query = query.order_by(asc(self.machine.c.Name))

        if 'max' in pattern:
            if pattern['max'] != -1:
                if ('gid' in pattern and ComputerGroupManager().isrequest_group(ctx, pattern['gid'])) or 'gid' not in pattern:
                    query = query.offset(pattern['min'])
                    query = query.limit(int(pattern['max']) - int(pattern['min']))
                else:
                    query = query.all()
            else:
                query = query.all()
        else:
            query = query.all()
        session.close()
        return query

    def countMachinesOnly(self, ctx, pattern = None):
        """
        Return the number of available machines
        """
        session = create_session()
        ret = self.__machinesOnlyQuery(ctx, pattern, session, True)
        session.close()
        return ret

    def optimizedQuery(self, ctx, filt):
        """
        @returns: a list of couples (UUID, hostname)
        @rtype: list
        """
        criterion = filt['optimization']['criterion']
        criterion = ["Path", criterion.split("/")[2]]
        values = ['Value', filt['optimization']['data']]
        result = self.getLastMachineInventoryPart(
            ctx, 'Registry',
            {'where' : [criterion, values] } )
        # Just returns a list of couple (UUID, hostname)
        ret = map(lambda x: (x[0], x[2]), result)
        return ret

    def getComputersOptimized(self, ctx, filt):
        """
        Return a list of computers, but try to optimize the way we get its
        inventory.
        """
        optimization = False
        if 'optimization' in filt:
            if 'criterion' in filt['optimization']:
                if filt['optimization']['criterion'].startswith('Registry/Value/'):
                    optimization = True
        if optimization:
            # In optimized mode, we don't return the full of inventory of the
            # computers corresponding to the request, but just list of couples
            # (UUID, hostname)
            return self.optimizedQuery(ctx, filt)
        else:
            result = self.getMachinesOnly(ctx, filt)

        tables = self.config.content
        if len(tables) == 1 and "Registry" in tables:
            # The inventory to display is to be taken from the same Registry
            # table
            computers = {}
            ids = []
            uuids = []
            for machine in result:
                ids.append(machine.id)
                uuid = toUUID(machine.id)
                tmp = [ False,
                        { 'cn' : [machine.Name],
                          'objectUUID' : [uuid] } ]
                computers[uuid] = tmp
                # Keep UUID order
                uuids.append(uuid)
            if len(uuids):
                # For all resulting machines ids, get the inventory part
                inventoryResult = self.getLastMachineInventoryPart(ctx, tables.keys()[0], {'ids' : ids })
                # Process each row, one row == one computer inventory
                for row in inventoryResult:
                    uuid = row[2]
                    # Process inventory content
                    for inv in row[1]:
                        computers[uuid][1][inv["Path"]] = inv["Value"]
            # Build the result
            ret = []
            for uuid in uuids:
                ret.append(computers[uuid])
        else:
            result = self.getMachinesOnly(ctx, filt)
            ret = map(lambda m: m.toDN(ctx), result)
        return ret

    # needed by DyngroupDatabaseHelper
    def computersTable(self):
        return [self.machine]

    def computersMapping(self, computers, invert = False):
        if not invert:
            return Machine.c.id.in_(*map(lambda x:fromUUID(x), computers))
        else:
            return Machine.c.id.not_(in_(*map(lambda x:fromUUID(x), computers)))

    def mappingTable(self, ctx, query):
        q = query[2].split('/')
        table, field = q[0:2]
        self.logger.debug("### >> table %s, field %s"%(table, field))
        if len(q) > 2:
            self.logger.debug("##### >> semi static name : %s"%(q[2]))
        if table == 'Machine':
            return [self.machine, self.table['hasHardware'], self.inventory]
        else:
            partTable = self.table[table]
            haspartTable = self.table["has" + table]
        if self.config.getInventoryNoms(table) == None:
            return [haspartTable, partTable]
        self.logger.debug("### Nom")
        ret = [haspartTable, partTable, self.inventory]
        for nom in self.config.getInventoryNoms(table):
            nomTableName = 'nom%s%s' % (table, nom)
            self.logger.debug("### nomTableName %s"%(nomTableName))
            nomTable = self.table[nomTableName]
            ret.append(nomTable)
        return ret

    def mapping(self, ctx, query, invert = False):
        q = query[2].split('/')
        table, field = q[0:2]
        if PossibleQueries().possibleQueries('double').has_key(query[2]): # double search
            value = PossibleQueries().possibleQueries('double')[query[2]]
            return and_(# TODO NEED TO PATH TO GET THE GOOD SEP!
                self.mapping(ctx, [None, None, value[0][0], query[3][0].replace('(', '')]),
                self.mapping(ctx, [None, None, value[1][0], query[3][1].replace(')', '')])
            )
        elif PossibleQueries().possibleQueries('list').has_key(query[2]): # list search
            if table == 'Machine':
                partKlass = Machine
            else:
                partKlass = self.klass[table]
            value = query[3]
            if value.startswith('>') and not invert or value.startswith('<') and invert:
                value = value.replace('>', '').replace('<', '')
                return and_(getattr(partKlass.c, field) > value, self.inventory.c.Last == 1)
            elif value.startswith('>') and invert or value.startswith('<') and not invert:
                value = value.replace('>', '').replace('<', '')
                return and_(getattr(partKlass.c, field) < value, self.inventory.c.Last == 1)
            elif invert:
                return and_(getattr(partKlass.c, field) != value, self.inventory.c.Last == 1)
            else:
                if re.compile('\*').search(value):
                    value = re.compile('\*').sub('%', value)
                    return and_(getattr(partKlass.c, field).like(value), self.inventory.c.Last == 1)
                return and_(getattr(partKlass.c, field) == value, self.inventory.c.Last == 1)

        elif PossibleQueries().possibleQueries('halfstatic').has_key(query[2]): # halfstatic search
            if table == 'Machine':
                partKlass = Machine
            else:
                partKlass = self.klass[table]
            value = query[3]

            hs = PossibleQueries().possibleQueries('halfstatic')[query[2]]
            condition = 1
            if self.config.getInventoryNoms(table) == None:
                condition = (getattr(partKlass.c, hs[1]) == hs[2])
            else:
                noms = self.config.getInventoryNoms(table)
                try:
                    noms.index(hs[1])
                    nomTableName = 'nom%s%s' % (table, hs[1])
                    nomKlass = self.klass[nomTableName]
                    if hasattr(nomKlass.c, hs[1]):
                        condition = (getattr(nomKlass.c, hs[1]) == hs[2])
                except ValueError, e:
                    condition = (getattr(partKlass.c, hs[1]) == hs[2])

            if value.startswith('>') and not invert or value.startswith('<') and invert:
                value = value.replace('>', '').replace('<', '')
                return and_(getattr(partKlass.c, field) > value, condition, self.inventory.c.Last == 1)
            elif value.startswith('>') and invert or value.startswith('<') and not invert:
                value = value.replace('>', '').replace('<', '')
                return and_(getattr(partKlass.c, field) < value, condition, self.inventory.c.Last == 1)
            elif invert:
                return and_(getattr(partKlass.c, field) != value, condition, self.inventory.c.Last == 1)
            else:
                if re.compile('\*').search(value):
                    value = re.compile('\*').sub('%', value)
                    return and_(getattr(partKlass.c, field).like(value), condition, self.inventory.c.Last == 1)
                return and_(getattr(partKlass.c, field) == value, condition, self.inventory.c.Last == 1)

    def getMachines(self, ctx, pattern = None):
        """
        Return all available machines with their Bios and Hardware inventory informations

        @param pattern: pattern to filter the machine list
        @typa pattern: str

        @return: Returns the list of machines recorded into the inventory database in alphabetical order, with the Bios and Hardware inventory information
        @rtype: list
        """
        ret = []
        for machine in self.getMachinesOnly(ctx, pattern):
            tmp = []
            tmp.append(machine.Name)
            tmp.append(self.getLastMachineInventoryPart(ctx, "Bios", {'hostname':machine.Name}))
            tmp.append(self.getLastMachineInventoryPart(ctx, "Hardware", {'hostname':machine.Name}))
            tmp.append(toUUID(machine.id))
            ret.append(tmp)
        return ret

    def getLastMachineInventoryFull(self, ctx, params):
        """
        Return the full and last inventory of a machine

        @param name: the name of the machine to get inventory
        @type params: dict

        @return: Returns a dictionary where each key is an inventory part name
        @rtype: dict
        """
        ret = {}
        for part in self.config.getInventoryParts():
            ret[part] = self.getLastMachineInventoryPart(ctx, part, params)
        return ret

    def getMachinesByDict(self, ctx, table, params):
        """
        Return a list of machine that correspond to the params "table.field = value"
        """
        ret = []
        partKlass = self.klass[table]
        partTable = self.table[table]
        haspartTable = self.table["has" + table]
        import re
        p1 = re.compile('\*')
        p2 = re.compile('<')
        p3 = re.compile('>')

        filters = []
        for field in params:
            value = params[field]
            if p1.search(value):
                value = p1.sub('%', value)
                filters.append(getattr(partKlass.c, field).like(value))
            elif p2.search(value):
                value = p2.sub('', value)
                filters.append(getattr(partKlass.c, field) < value)
            elif p3.search(value):
                value = p3.sub('', value)
                filters.append(getattr(partKlass.c, field) > value)
            else:
                filters.append(getattr(partKlass.c, field) == value)

        session = create_session()
        query = session.query(Machine).\
            add_column(func.max(haspartTable.c.inventory).label("inventoryid")).\
            add_column(func.min(self.inventory.c.Date)).\
            select_from(
                self.machine.join(haspartTable.join(self.inventory).join(partTable))
            )

        # apply filters
        for filter in filters:
            query = query.filter(filter)

        result = query.group_by(self.machine.c.Name).group_by(haspartTable.c.machine).order_by(haspartTable.c.machine).order_by(desc("inventoryid")).order_by(haspartTable.c.inventory)
        session.close()

        if result:
            for res in result:
                ret.append(res[0].Name)

        return ret

    def getMachinesBy(self, ctx, table, field, value):
        """
        Return a list of machine that correspond to the table.field = value
        """
        ret = []
        session = create_session()
        partKlass = self.klass[table]
        partTable = self.table[table]
        haspartTable = self.table["has" + table]

        result = session.query(Machine).\
            add_column(func.max(haspartTable.c.inventory).label("inventoryid")).\
            add_column(func.min(self.inventory.c.Date)).\
            select_from(self.machine.join(haspartTable.join(self.inventory).join(partTable)))

        import re
        p1 = re.compile('\*')
        if p1.search(value):
            result = result.filter(getattr(partKlass.c, field).like(p1.sub('%', value)))
        else:
            result = result.filter(getattr(partKlass.c, field) == value)

        result = result.group_by(self.machine.c.Name).\
            group_by(haspartTable.c.machine).\
            order_by(haspartTable.c.machine).\
            order_by(desc("inventoryid")).\
            order_by(haspartTable.c.inventory)
        session.close()

        if result:
            for res in result:
                ret.append(res[0].Name)

        return ret

    def getValues(self, table, field):
        """
        return every possible values for a field in a table
        """
        ret = []
        session = create_session()
        if table == 'Machine':
            partKlass = Machine
            partTable = self.machine
        else:
            partKlass = self.klass[table]
            partTable = self.table[table]

        result = session.query(partKlass).add_column(getattr(partKlass.c, field)).limit(MAX_REQ_NUM)
        session.close()

        if result:
            for res in result:
                ret.append(res[1])
        return unique(ret)

    def getValuesFuzzy(self, table, field, fuzzy_value):
        """
        return every possible values for a field in a table where the field is like fuzzy_value
        """
        ret = []
        session = create_session()
        if table == 'Machine':
            partKlass = Machine
            partTable = self.machine
        else:
            partKlass = self.klass[table]
            partTable = self.table[table]

        result = session.query(partKlass).add_column(getattr(partKlass.c, field)).filter(getattr(partKlass.c, field).like('%'+fuzzy_value+'%')).limit(MAX_REQ_NUM).all()
        session.close()

        if result:
            for res in result:
                ret.append(res[1])
        return unique(ret)

    def getValueFuzzyWhere(self, table, field1, value1, field2, fuzzy_value):
        """
        return every possible values for a field (field2) in a table, where field1 = value1 and field2 like fuzzy_value
        """
        ret = []
        if table == 'Machine':
            partKlass = Machine
        else:
            partKlass = self.klass[table]
        session = create_session()
        result = self.__getValuesWhereQuery(table, field1, value1, field2, session)
        result = result.filter(getattr(partKlass.c, field2).like('%'+fuzzy_value+'%')).limit(MAX_REQ_NUM)
        session.close()

        if result:
            for res in result:
                ret.append(res[1])
        return unique(ret)


    def getValuesWhere(self, table, field1, value1, field2):
        """
        return every possible values for a field (field2) in a table, where field1 = value1
        """
        ret = []
        session = create_session()
        result = self.__getValuesWhereQuery(table, field1, value1, field2, session).limit(MAX_REQ_NUM)
        session.close()

        if result:
            for res in result:
                ret.append(res[1])
        return unique(ret)

    def __getValuesWhereQuery(self, table, field1, value1, field2, session = None):
        if session == None:
            session = create_session()
        if table == 'Machine':
            partKlass = Machine
            partTable = self.machine
        else:
            partKlass = self.klass[table]
            partTable = self.table[table]
        query = session.query(partKlass).add_column(getattr(partKlass.c, field2))
        filterDone = False

        if self.config.getInventoryNoms(table) != None:
            for nom in self.config.getInventoryNoms(table):
                hasTable = self.table['has%s'%(table)]
                nomTableName = 'nom%s%s' % (table, nom)
                nomKlass = self.klass[nomTableName]
                if hasattr(nomKlass.c, field1):
                    nomTable = self.table[nomTableName]
                    query = query.select_from(partTable.join(hasTable).join(nomTable))
                    query = query.filter(self.__filterOn(nomKlass, field1, value1))
                    filterDone = True

        if not filterDone:
            query = query.filter(self.__filterOn(partKlass, field1, value1))
        return query

    def __filterOn(self, partKlass, field, value):
        import re
        p1 = re.compile('\*')
        self.logger.debug("%s %s"%(field, value))
        if p1.search(value):
            value = p1.sub('%', value)
            return getattr(partKlass.c, field).like(value)
        else:
            return getattr(partKlass.c, field) == value

    def getMachineNetwork(self, ctx, params):
        return self.getLastMachineInventoryPart(ctx, 'Network', params)

    def getMachineCustom(self, ctx, params):
        return self.getLastMachineInventoryPart(ctx, 'Custom', params)

    def doesUserHaveAccessToMachine(self, userid, machine_uuid): # TODO implement ...
        return True

    def doesUserHaveAccessToMachines(self, userid, machine_uuid, all = True): # TODO implement ...
        return True

    def countLastMachineInventoryPart(self, ctx, part, params):
        session = create_session()
        result, grp_by = self.__lastMachineInventoryPartQuery(session, ctx, part, params)
        for grp in grp_by:
            result = result.group_by(grp)
        # The alias is needed for MySQL
        s = select([func.count(text('*'))]).select_from(result.compile().alias('foo'))
        result = session.execute(s)
        session.close()
        return result.fetchone()[0]

    def getLastMachineInventoryPart(self, ctx, part, params):
        return self.__getLastMachineInventoryPart(part, params, ctx)

    def __getLastMachineInventoryPart(self, part, params, ctx = None):
        """
        Return a list where each item belongs to the last machine inventory.
        Each item is a dictionary of the inventory description.
        An extra key of the dictionary called 'timestamp' contains the inventory item first appearance.

        @param params: parameters to get the machine in the inventory (hostname, uuid, ...)
        @type name: dict

        @return: Returns a list of dictionary
        @type: list
        """
        ret = []
        session = create_session()
        partKlass = self.klass[part]
        partTable = self.table[part]
        haspartTable = self.table["has" + part]
        result, grp_by = self.__lastMachineInventoryPartQuery(session, ctx, part, params)

        if params.has_key('min') and params.has_key('max'):
            result = result.offset(int(params['min']))
            result = result.limit(int(params['max']) - int(params['min']))

        for grp in grp_by:
            result = result.group_by(grp)
        result = result.order_by(haspartTable.c.machine).order_by(desc("inventoryid")).order_by(haspartTable.c.inventory)
        session.close()
        if result:
            # Build the result as a simple dictionary
            # We return only the information from the latest inventory
            inventoryid = None
            machine_inv = {}
            machine_uuid = {}
            for res in result:
                if inventoryid == None:
                    inventoryid = res[3]
                #else:
                #    if inventoryid != res[3]: break
                # Build the dictionary using the partTable column names as keys
                tmp = {}
                for col in partTable.columns:
                    tmp[col.name] = eval("res[0]." + col.name)
                # Build a time tuple for the appearance timestamp
                d = res[4]
                if type(res[4]) == str:
                    y, m, day = res[4].split("-")
                    d = datetime.datetime(int(y), int(m), int(day))
                tmp["timestamp"] = d
                if not machine_inv.has_key(res[1]):
                    machine_inv[res[1]] = []
                    machine_uuid[res[1]] = toUUID(res[2])
                if len(res) > 5:
                    noms = self.config.getInventoryNoms()
                    if noms.has_key(part):
                        for i in range(5, len(res)):
                            tmp[noms[part][i-5]] = res[i]
                machine_inv[res[1]].append(tmp)
            for name in machine_uuid:
                ret.append([name, machine_inv[name], machine_uuid[name]])
        return ret

    def __lastMachineInventoryPartQuery(self, session, ctx, part, params):
        self.complete_ctx(ctx)
        partKlass = self.klass[part]
        partTable = self.table[part]
        haspartTable = self.table["has" + part]
        haspartKlass = self.klass["has" + part]
        grp_by = [partTable.c.id, haspartTable.c.machine]

        # This SQL query has been built using the one from the LRS inventory module
        # TODO : this request has to be done on Machine and then add the columns so that the left join works...
        #result = session.query(partKlass).add_column(self.machine.c.Name).add_column(self.machine.c.id).add_column(haspartTable.c.inventory.label("inventoryid")).add_column(self.inventory.c.Date).select_from(partTable.outerjoin(haspartTable.join(self.inventory).join(self.machine))).filter(self.inventory.c.Last == 1)
        result = session.query(partKlass).\
            add_column(self.machine.c.Name).\
            add_column(self.machine.c.id).\
            add_column(haspartTable.c.inventory.label("inventoryid")).\
            add_column(self.inventory.c.Date)

        noms = self.config.getInventoryNoms()
        select_from = haspartTable.join(self.inventory).join(partTable).outerjoin(self.machine)
        # Also join on the entity related table to filter on the computers the
        # user has the right to see
        select_from = select_from.join(self.table['hasEntity'], self.table['hasEntity'].c.machine == self.machine.c.id)
        
        if noms.has_key(part):
            for nom in noms[part]:
                nomTable = self.table['nom%s%s' % (part, nom)]
                select_from = select_from.join(nomTable)
                result = result.add_column(getattr(nomTable.c, nom))
                grp_by.append(nomTable.c.id)

        result = result.select_from(select_from).filter(self.inventory.c.Last == 1)
        # Filter on the entities the user has the right to see
        result = result.filter(self.table['hasEntity'].c.entity.in_(ctx.locationsid))
        # Apply other filters
        result = self.__filterQuery(ctx, result, params)

        # this can't be put in __filterQuer because it's not a generic filter on Machine...
        if params.has_key('where') and params['where'] != '':
            for where in params['where']:
                if hasattr(partTable.c, where[0]):
                    if type(where[1]) == list:
                        result = result.filter(getattr(partTable.c, where[0]).in_(where[1]))
                    else:
                        result = result.filter(getattr(partTable.c, where[0]) == where[1])
                else:
                    if noms.has_key(part):
                        try:
                            noms[part].index(where[0])
                            nomTableName = 'nom%s%s' % (part, where[0])

                            nomTable = self.table[nomTableName]
                            if hasattr(nomTable.c, where[0]):
                                result = result.filter(getattr(nomTable.c, where[0]) == where[1])
                            else:
                                self.logger.warn("cant find the required field (%s) in table %s"%(where[0], nomTableName))
                        except ValueError:
                            self.logger.warn("cant find any %s field"%(where[0]))
                    else:
                        self.logger.warn("cant find any %s field"%(where[0]))
        return (result, grp_by)

    def __filterQuery(self, ctx, query, params):
        if params.has_key('hostname') and params['hostname'] != '':
            query = query.filter(Machine.c.Name==params['hostname'])
        if params.has_key('filter') and params['filter'] != '':
            query = query.filter(Machine.c.Name.like('%'+params['filter']+'%'))
        if params.has_key('uuid') and params['uuid'] != '':
            query = query.filter(Machine.c.id==fromUUID(params['uuid']))
        if params.has_key('uuids') and len(params['uuids']):
            uuids = map(lambda m: fromUUID(m), params['uuids'])
            query = query.filter(Machine.c.id.in_(uuids))
        if params.has_key('gid') and params['gid'] != '':
            if ComputerGroupManager().isrequest_group(ctx, params['gid']):
                machines = map(lambda m: fromUUID(m), ComputerGroupManager().requestresult_group(ctx, params['gid'], 0, -1, ''))
            else:
                machines = map(lambda m: fromUUID(m), ComputerGroupManager().result_group(ctx, params['gid'], 0, -1, ''))
            query = query.filter(self.machine.c.id.in_(machines))
        # Filter using a list of machine ids
        if params.has_key('ids') and len(params['ids']):
            query = query.filter(self.machine.c.id.in_(params['ids']))
        return query

    def getIdInTable(self, tableName, values, session = None):
        sessionCreator = False
        if session == None:
            sessionCreator = True
            session = create_session()
        klass = self.klass[tableName]
        table = self.table[tableName]

        result = session.query(klass)
        for v in values:
            if type(v) == str or type(v) == unicode:
                if hasattr(table.c, v):
                    result = result.filter(getattr(table.c, v) == values[v])
        res = result.first()
        if sessionCreator:
            session.close()
        try:
            return res.id
        except:
            return None

    def isElemInTable(self, tableName, values, session = None):
        sessionCreator = False
        if session == None:
            sessionCreator = True
            session = create_session()
        klass = self.klass[tableName]
        table = self.table[tableName]

        result = session.query(klass)
        for v in values:
            if hasattr(table.c, v):
                result = result.filter(getattr(table.c, v) == values[v])
        res = result.count()
        if sessionCreator:
            session.close()
        try:
            return res
        except:
            return None

    def addMachine(self, name, ip, mac, netmask, comment = None, location = None): # TODO add the location association
        session = create_session()
        m = Machine()
        m.Name = name
        session.save(m)
        # TODO need to put all other Last to 0
        query = session.query(InventoryTable).select_from(self.inventory.join(self.table['hasNetwork']).join(self.machine)).filter(self.machine.c.Name == name)
        for inv in query:
            inv.Last = 0
            session.save(inv)
        i = InventoryTable()
        i.Last = 1
        session.save(i)
        session.flush()
        net = self.klass['Network']
        hasNet = self.klass['hasNetwork']
        n = net()
        n.MACAddress = mac
        n.IP = ip
        n.SubnetMask = netmask
        session.save(n)
        session.flush()
        h = hasNet()
        h.machine = m.id
        h.network = n.id
        h.inventory = i.id
        session.save(h)
        session.flush()
        if comment != None:
            custom = self.klass['Custom']
            hasCustom = self.klass['hasCustom']
            c = custom()
            c.Comments = comment
            session.save(c)
            session.flush()
            h = hasCustom()
            h.machine = m.id
            h.custom = c.id
            h.inventory = i.id
            session.save(h)
            session.flush()
        session.close()
        return toUUID(m.id)

    def delMachine(self, uuid):
        uuid = fromUUID(uuid)
        session = create_session()
        for item in self.config.getInventoryParts():
            tk = self.klass[item]
            tt = self.table[item]
            lk = self.klass['has'+item]
            lt = self.table['has'+item]
# TODO : check if more than one machine use this entry
#            ts = session.query(tk).select_from(tt.join(lt)).filter(lt.c.machine == uuid)
#            for t in ts:
#                session.delete(t)
            ls = session.query(lk).filter(lt.c.machine == uuid)
            for l in ls:
                i = session.query(InventoryTable).filter(self.inventory.c.id == l.inventory).first()
                session.delete(i)
                session.delete(l)
        m = session.query(Machine).filter(self.machine.c.id == uuid).first()
        session.delete(m)
        session.flush()
        session.close()
        return True

    # User management method
    
    def setUserEntities(self, userid, entities):
        """
        Set entities associated to a user.
        A user that doesn't exist in the database will be added.
        Entities that doesn't exist in the database will be added below the
        root entity. The dot character '.' is the root entity.

        @param userid: the user id (login)
        @param entities: list of entity string
        """
        class RootEntity:
            def __init__(self):
                self.id = 1

        session = create_session()
        # Start transaction
        session.begin()
        # Create/get user
        try:
            u = session.query(UserTable).filter_by(uid = userid).one()
        except Exception:
            u = UserTable()
            u.uid = userid
            session.save(u)
            session.flush()
        
        # Create/get entities
        elist = []
        for entity in entities:
            if entity == '.':
                e = RootEntity()
            else:
                try:
                    e = session.query(self.klass['Entity']).filter_by(Label = entity).one()
                except Exception:
                    e = self.klass['Entity']()
                    e.Label = entity
                    session.save(e)
                    session.flush()
            elist.append(e)
        # Look for the user to entities mappings that need to be added or
        # removed in database
        toadd = elist[:]
        todel = []
        for ue in session.query(UserEntitiesTable).filter_by(fk_User = u.id):
            found = False
            for entity in elist:
                if entity.id == ue.fk_Entity:
                    # The mapping already exists
                    toadd.remove(entity)
                    found = True
                    break
            if not found:
                # The mapping should be removed
                todel.append(ue)
        # Apply changes
        for ue in todel:
            session.delete(ue)
        for entity in toadd:
            ue = UserEntitiesTable()
            ue.fk_User = u.id
            ue.fk_Entity = entity.id
            session.save(ue)
        session.commit()
        session.close()

    def locationExists(self, location):
        """
        Returns true if the given location exists in database
        """
        session = create_session()
        ret = True
        try:
            e = session.query(self.klass['Entity']).filter_by(Label = location).one()
        except:
            ret = False
        session.close()
        return ret
                
    def getUserLocations(self, userid, with_level = False):
        """
        Returns all the locations granted for a given userid.

        @param with_level: if True, the locations level are also returned
        @returns: a list of locations, or a list of couples (location, level)
                  if with_level is true
        """

        def __addChildren(session, rootid, level):
            # Search children of the root id
            ret = []
            level = level + 1
            q = session.query(self.klass['Entity']).filter(self.table['Entity'].c.parentId == rootid)
            for entity in q:
                if entity.id != 1:
                    if with_level:
                        ret.append((entity, level))
                    else:
                        ret.append(entity)
                    ret.extend(__addChildren(session, entity.id, level))
            return ret
        
        session = create_session()
        ret = session.query(self.klass['Entity'])
        if userid != 'root':
            ret = []
            q = session.query(self.klass['Entity']).select_from(self.table['Entity'].join(self.userentities).join(self.user)).filter(self.user.c.uid == userid)
            level = 1
            for entity in q:
                if with_level:
                    ret.append((entity, level))
                else:
                    ret.append(entity)
                # Also add entity children
                ret.extend(__addChildren(session, entity.id, level))
        session.close()
        return ret

    def getLocationsCount(self):
        session = create_session()
        count = session.query(self.klass['Entity']).count()
        session.close()
        return count

    def getUsersInSameLocations(self, userid, locations = None):
        """
        Returns all the users id that share the same locations than the given
        user. 
        """
        if locations == None:
            locations = self.getUserLocations(userid)
        ret = []
        if locations:
            inloc = []
            for location in locations:
                inloc.append(location.id)
            session = create_session()
            q = session.query(UserTable).select_from(self.user.join(self.userentities)).filter(self.userentities.c.fk_Entity.in_(inloc)).filter(self.user.c.uid != userid).distinct().all()
            session.close()
            # Only returns the user id
            ret = map(lambda u: u.uid, q)
        # Always append the given userid
        ret.append(userid)
        return ret

def toUUID(id): # TODO : change this method to get a value from somewhere in the db, depending on a config param
    return "UUID%s" % (str(id))

def fromUUID(uuid):
    return int(uuid.replace('UUID', ''))

def getComputerDict(c):
    if type(c) == dict:
        return c
    for m in ['toH', 'to_h', 'toh', 'to_H']:
        if hasattr(c, m):
            return getattr(c,m)()
    raise Exception("don't know how to convert in dict")

# Class for SQLalchemy mapping
class Machine(object):
    def toH(self):
        return { 'hostname':self.Name, 'uuid':toUUID(self.id) }

    def uuid(self):
        return toUUID(self.id)

    def toDN(self, ctx, advanced = False):
        ret = [ False, {'cn':[self.Name], 'objectUUID':[toUUID(self.id)]} ]
        comment = Inventory().getMachineCustom(ctx, {'uuid':toUUID(self.id)})
        if len(comment) != 0:
            ret[1]['displayName'] = [comment[0][1][0]['Comments']]
        for table in Inventory().config.content:
            content = Inventory().config.content[table]
            for col in content:
                params = {'uuid':toUUID(self.id)}
                if len(col) > 2:
                    for p in col[2:]:
                        if not params.has_key('where'):
                            params['where'] = []
                        params['where'].append(p)

                part = Inventory().getLastMachineInventoryPart(ctx, table, params)
                if len(part) == 0:
                    ret[1][col[1]] = ''
                else:
                    part = part[0][1]
                    ret[1][col[1]] = []
                    for n in part:
                        ret[1][col[1]].append(n[col[0]])

        if advanced:
            net = Inventory().getMachineNetwork(ctx, {'uuid':toUUID(self.id)})
            if len(net) == 0:
                ret[1]['ipHostNumber'] = ''
                ret[1]['macAddress'] = ''
                ret[1]['subnetMask'] = ''
            else:
                net = net[0]
                ret[1]['ipHostNumber'] = []
                ret[1]['macAddress'] = []
                ret[1]['subnetMask'] = []
                for n in net[1]:
                    if n['IP'] != None:
                        ret[1]['ipHostNumber'].append(n['IP'])
                    if n['MACAddress'] != None and n['MACAddress'] != '00-00-00-00-00-00-00-00-00-00-00':
                        ret[1]['macAddress'].append(n['MACAddress'])
                    if n['SubnetMask'] != None:
                        ret[1]['subnetMask'].append(n['SubnetMask'])
        return ret

    def toCustom(self, get):
        ma = {}
        for field in get:
            if hasattr(self, field):
                ma[field] = getattr(self, field)
            if field == 'uuid' or field == 'objectUUID':
                ma[field] = toUUID(self.id)
            if field == 'cn':
                ma[field] = self.Name
        return ma

class InventoryTable(object):
    pass

class PossibleQueries(Singleton):
    def init(self, config):
        self.list = config.list
        self.double = config.double
        self.halfstatic = config.halfstatic

    def possibleQueries(self, value = None): # TODO : need to put this in the conf file
        if value == None:
            return {
                'list':self.list,
                'double':self.double,
                'halfstatic':self.halfstatic
            }
        else:
            if hasattr(self, value):
                return getattr(self, value)
            return []

class InventoryCreator(Inventory):
    def createNewInventory(self, hostname, inventory, date):
        """
        Add a new inventory for a computer
        """
        # TODO : check that inventory is not empty....
        k = 0
        for i in map(lambda x: len(inventory[x]), inventory):
            k = i+k
        if k == 0:
            return False

        date = date.split(' ')

        session = create_session()
        transaction = session.create_transaction()
        try:
            m = self.getMachinesOnly(None, {'hostname': hostname}) # TODO uuids!
            if len(m) == 0:
                # If this computer is not in the Machine table, add it
                m = Machine()
                m.Name = hostname
                session.save(m)
            elif len(m) > 1:
                # If this computer has been registered twice, exit
                session.close()
                loggin.getLogger().error("Computer %s seem to appear more than one time in database" % hostname)
                return False
            else:
                # Get the current computer
                m = m[0]
            # Set last inventory flag to 0 for already existing inventory for
            # this computer
            result = session.query(InventoryTable).\
                select_from(
                    self.inventory.join(self.table['hasHardware']).join(self.machine)
                ).\
                filter(self.machine.c.Name == hostname)

            for inv in result:
                inv.Last = 0
                session.save_or_update(inv)

            # Create a new empty inventory, and flag it as the last
            i = InventoryTable()
            i.Date, i.Time = date
            i.Last = 1
            session.save(i)
            session.flush()

            # Loop on all inventory parts
            for table in inventory:
                content = inventory[table]
                tname = table.lower()

                # This part of inventory is empty, so skip it
                if len(content) == 0:
                    continue

                klass = self.klass[table]
                hasKlass = self.klass['has'+table]
                hasTable = self.table['has'+table]

                h = hasTable.insert()
                # keep track of already inserted datas for this table
                already_inserted = []
                # loop on all inventory part columns
                for cols in content:
                    # skip if empty
                    if len(cols) == 0:
                        continue
                    try:
                        # Look up these columns in the inventory table
                        id = self.getIdInTable(table, cols, session)
                        # Create them if none found
                        if id == None:
                            k = klass()
                            for col in cols:
                                if type(col) == str or type(col) == unicode:
                                    setattr(k, col, cols[col])
                            session.save(k)
                            # Immediatly flush this new row, because we need an
                            # id
                            session.flush([k])
                            id = k.id

                        nids = {}
                        if OcsMapping().nomenclatures.has_key(table):
                            for nom in OcsMapping().nomenclatures[table]:
                                nomName = 'nom%s%s' % (table, nom)
                                nomKlass = self.klass[nomName]
                                nomTable = self.table[nomName]

                                ncols = {}
                                for col in cols:
                                    if type(col) == tuple and col[0] == nomName:
                                        ncols[col[1]] = cols[col]

                                nid = self.getIdInTable(nomName, ncols, session)
                                if nid == None:
                                    n = nomKlass()
                                    for col in ncols:
                                        setattr(n, col, ncols[col])
                                    session.save(n)
                                    # Immediatly flush this new row, because
                                    # we need an id
                                    session.flush([n])
                                    nid = n.id
                                nids[nom] = nid
                        # closes if block

                        params = {'machine':m.id, 'inventory':i.id, tname:id}
                        if len(nids.keys()) > 0:
                            for nom in nids:
                                params[nom.lower()] = nids[nom]
                        if params not in already_inserted:
                            # Prepare insertion in the 'has' table
                            hk = hasKlass()
                            for attr, value in params.items():
                                setattr(hk, attr, value)
                            # We will flush the new rows for the 'has' tables
                            # at the end, because it's faster to do it in one
                            # shot
                            session.save(hk)
                            already_inserted.append(params)
                    except UnicodeDecodeError, e: # just for test
                        pass
                    except Exception, e:
                        logging.getLogger().exception(e)
                        pass
                # closes for block
            # closes for block on inventory parts
        except Exception, e:
            transaction.rollback()
            session.close()
            logging.getLogger().exception(e)
            raise e

        session.flush()
        transaction.commit()
        session.close()
        return True


