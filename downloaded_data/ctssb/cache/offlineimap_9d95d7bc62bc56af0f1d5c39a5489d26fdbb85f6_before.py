# IMAP folder support
# Copyright (C) 2002-2007 John Goerzen
# <jgoerzen@complete.org>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA

import email
import random
import binascii
import re
import time
from copy import copy
from Base import BaseFolder
from offlineimap import imaputil, imaplibutil, OfflineImapError

class IMAPFolder(BaseFolder):
    def __init__(self, imapserver, name, visiblename, accountname, repository):
        self.config = imapserver.config
        self.expunge = repository.getexpunge()
        self.name = imaputil.dequote(name)
        self.root = None # imapserver.root
        self.sep = imapserver.delim
        self.imapserver = imapserver
        self.messagelist = None
        self.visiblename = visiblename
        self.accountname = accountname
        self.repository = repository
        self.randomgenerator = random.Random()
        BaseFolder.__init__(self)
        #self.ui is set in BaseFolder

    def selectro(self, imapobj):
        """Select this folder when we do not need write access.

        Prefer SELECT to EXAMINE if we can, since some servers
        (Courier) do not stabilize UID validity until the folder is
        selected. 
        .. todo: Still valid? Needs verification

        :returns: raises :exc:`OfflineImapError` severity FOLDER on error"""
        try:
            imapobj.select(self.getfullname())
        except imapobj.readonly:
            imapobj.select(self.getfullname(), readonly = 1)

    def getaccountname(self):
        return self.accountname

    def suggeststhreads(self):
        return 1

    def waitforthread(self):
        self.imapserver.connectionwait()

    def getcopyinstancelimit(self):
        return 'MSGCOPY_' + self.repository.getname()

    def getvisiblename(self):
        return self.visiblename

    def getuidvalidity(self):
        imapobj = self.imapserver.acquireconnection()
        try:
            # Primes untagged_responses
            self.selectro(imapobj)
            return long(imapobj._get_untagged_response('UIDVALIDITY', True)[0])
        finally:
            self.imapserver.releaseconnection(imapobj)

    def quickchanged(self, statusfolder):
        # An IMAP folder has definitely changed if the number of
        # messages or the UID of the last message have changed.  Otherwise
        # only flag changes could have occurred.
        imapobj = self.imapserver.acquireconnection()
        try:
            # Primes untagged_responses
            imaptype, imapdata = imapobj.select(self.getfullname(), readonly = 1, force = 1)
            # 1. Some mail servers do not return an EXISTS response
            # if the folder is empty.  2. ZIMBRA servers can return
            # multiple EXISTS replies in the form 500, 1000, 1500,
            # 1623 so check for potentially multiple replies.
            if imapdata == [None]:
                return True
            maxmsgid = 0
            for msgid in imapdata:
                maxmsgid = max(long(msgid), maxmsgid)

            # Different number of messages than last time?
            if maxmsgid != statusfolder.getmessagecount():
                return True

        finally:
            self.imapserver.releaseconnection(imapobj)
        return False

    # TODO: Make this so that it can define a date that would be the oldest messages etc.
    def cachemessagelist(self):
        imapobj = self.imapserver.acquireconnection()
        self.messagelist = {}

        try:
            # Primes untagged_responses
            imaptype, imapdata = imapobj.select(self.getfullname(), readonly = 1, force = 1)

            maxage = self.config.getdefaultint("Account " + self.accountname, "maxage", -1)
            maxsize = self.config.getdefaultint("Account " + self.accountname, "maxsize", -1)

            if (maxage != -1) | (maxsize != -1):
                try:
                    search_condition = "(";

                    if(maxage != -1):
                        #find out what the oldest message is that we should look at
                        oldest_time_struct = time.gmtime(time.time() - (60*60*24*maxage))

                        #format this manually - otherwise locales could cause problems
                        monthnames_standard = ["Jan", "Feb", "Mar", "Apr", "May", \
                            "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

                        our_monthname = monthnames_standard[oldest_time_struct[1]-1]
                        daystr = "%(day)02d" % {'day' : oldest_time_struct[2]}
                        date_search_str = "SINCE " + daystr + "-" + our_monthname \
                            + "-" + str(oldest_time_struct[0])

                        search_condition += date_search_str

                    if(maxsize != -1):
                        if(maxage != 1): #There are two conditions - add a space
                            search_condition += " "

                        search_condition += "SMALLER " + self.config.getdefault("Account " + self.accountname, "maxsize", -1)

                    search_condition += ")"
                    searchresult = imapobj.search(None, search_condition)

                    #result would come back seperated by space - to change into a fetch
                    #statement we need to change space to comma
                    messagesToFetch = searchresult[1][0].replace(" ", ",")
                except KeyError:
                    return
                if len(messagesToFetch) < 1:
                    # No messages; return
                    return
            else:
                # 1. Some mail servers do not return an EXISTS response
                # if the folder is empty.  2. ZIMBRA servers can return
                # multiple EXISTS replies in the form 500, 1000, 1500,
                # 1623 so check for potentially multiple replies.
                if imapdata == [None]:
                    return

                maxmsgid = 0
                for msgid in imapdata:
                    maxmsgid = max(long(msgid), maxmsgid)
                if maxmsgid < 1:
                    #no messages; return
                    return
                messagesToFetch = '1:%d' % maxmsgid;

            # Now, get the flags and UIDs for these.
            # We could conceivably get rid of maxmsgid and just say
            # '1:*' here.
            response = imapobj.fetch(messagesToFetch, '(FLAGS UID)')[1]
        finally:
            self.imapserver.releaseconnection(imapobj)
        for messagestr in response:
            # Discard the message number.
            messagestr = messagestr.split(' ', 1)[1]
            options = imaputil.flags2hash(messagestr)
            if not options.has_key('UID'):
                self.ui.warn('No UID in message with options %s' %\
                                          str(options),
                                          minor = 1)
            else:
                uid = long(options['UID'])
                flags = imaputil.flagsimap2maildir(options['FLAGS'])
                rtime = imaplibutil.Internaldate2epoch(messagestr)
                self.messagelist[uid] = {'uid': uid, 'flags': flags, 'time': rtime}

    def getmessagelist(self):
        return self.messagelist

    def getmessage(self, uid):
        """Retrieve message with UID from the IMAP server (incl body)

        :returns: the message body or throws and OfflineImapError
                  (probably severity MESSAGE) if e.g. no message with
                  this UID could be found.
        """
        imapobj = self.imapserver.acquireconnection()
        try:
            imapobj.select(self.getfullname(), readonly = 1)
            res_type, data = imapobj.uid('fetch', str(uid), '(BODY.PEEK[])')
            if data == [None] or res_type != 'OK':
                #IMAP server says bad request or UID does not exist
                severity = OfflineImapError.ERROR.MESSAGE
                reason = "IMAP server '%s' responded with '%s' to fetching "\
                    "message UID '%d'" % (self.getrepository(), res_type, uid)
                if data == [None]:
                    #IMAP server did not find a message with this UID
                    reason = "IMAP server '%s' does not have a message "\
                             "with UID '%s'" % (self.getrepository(), uid)
                raise OfflineImapError(reason, severity)
            # data looks now e.g. [('320 (UID 17061 BODY[]
            # {2565}','msgbody....')]  we only asked for one message,
            # and that msg is in data[0]. msbody is in [0][1]

            #NB & TODO: When the message on the IMAP server has been
            #deleted in the mean time, it will respond with an 'OK'
            #res_type, but it will simply not send any data. This will
            #lead to a crash in the below line. We need urgently to
            #detect this, protect from this and need to think about what
            #to return in this case. Probably returning `None` in this
            #case would be good. But we need to make sure that all
            #Backends behave the same, and that we actually check the
            #return value and behave accordingly.
            data = data[0][1].replace("\r\n", "\n")

            if len(data)>200:
                dbg_output = "%s...%s" % (str(data)[:150],
                                          str(data)[-50:])
            else:
                dbg_output = data
            self.ui.debug('imap', "Returned object from fetching %d: '%s'" %
                          (uid, dbg_output))
        finally:
            self.imapserver.releaseconnection(imapobj)
        return data

    def getmessagetime(self, uid):
        return self.messagelist[uid]['time']

    def getmessageflags(self, uid):
        return self.messagelist[uid]['flags']

    def generate_randomheader(self, content):
        """Returns a unique X-OfflineIMAP header

         Generate an 'X-OfflineIMAP' mail header which contains a random
         unique value (which is based on the mail content, and a random
         number). This header allows us to fetch a mail after APPENDing
         it to an IMAP server and thus find out the UID that the server
         assigned it.

        :returns: (headername, headervalue) tuple, consisting of strings
                  headername == 'X-OfflineIMAP' and headervalue will be a
                  random string
        """
        headername = 'X-OfflineIMAP'
        # We need a random component too. If we ever upload the same
        # mail twice (e.g. in different folders), we would still need to
        # get the UID for the correct one. As we won't have too many
        # mails with identical content, the randomness requirements are
        # not extremly critial though.

        # compute unsigned crc32 of 'content' as unique hash
        # NB: crc32 returns unsigned only starting with python 3.0
        headervalue  = str( binascii.crc32(content) & 0xffffffff ) + '-'
        headervalue += str(self.randomgenerator.randint(0,9999999999))
        return (headername, headervalue)


    def savemessage_addheader(self, content, headername, headervalue):
        self.ui.debug('imap',
                 'savemessage_addheader: called to add %s: %s' % (headername,
                                                                  headervalue))
        insertionpoint = content.find("\r\n")
        self.ui.debug('imap', 'savemessage_addheader: insertionpoint = %d' % insertionpoint)
        leader = content[0:insertionpoint]
        self.ui.debug('imap', 'savemessage_addheader: leader = %s' % repr(leader))
        if insertionpoint == 0 or insertionpoint == -1:
            newline = ''
            insertionpoint = 0
        else:
            newline = "\r\n"
        newline += "%s: %s" % (headername, headervalue)
        self.ui.debug('imap', 'savemessage_addheader: newline = ' + repr(newline))
        trailer = content[insertionpoint:]
        self.ui.debug('imap', 'savemessage_addheader: trailer = ' + repr(trailer))
        return leader + newline + trailer


    def savemessage_searchforheader(self, imapobj, headername, headervalue):
        self.ui.debug('imap', 'savemessage_searchforheader called for %s: %s' % \
                 (headername, headervalue))
        # Now find the UID it got.
        headervalue = imapobj._quote(headervalue)
        try:
            matchinguids = imapobj.uid('search', 'HEADER', headername, headervalue)[1][0]
        except imapobj.error, err:
            # IMAP server doesn't implement search or had a problem.
            self.ui.debug('imap', "savemessage_searchforheader: got IMAP error '%s' while attempting to UID SEARCH for message with header %s" % (err, headername))
            return 0
        self.ui.debug('imap', 'savemessage_searchforheader got initial matchinguids: ' + repr(matchinguids))

        if matchinguids == '':
            self.ui.debug('imap', "savemessage_searchforheader: UID SEARCH for message with header %s yielded no results" % headername)
            return 0

        matchinguids = matchinguids.split(' ')
        self.ui.debug('imap', 'savemessage_searchforheader: matchinguids now ' + \
                 repr(matchinguids))
        if len(matchinguids) != 1 or matchinguids[0] == None:
            raise ValueError, "While attempting to find UID for message with header %s, got wrong-sized matchinguids of %s" % (headername, str(matchinguids))
        matchinguids.sort()
        return long(matchinguids[0])


    def getmessageinternaldate(self, content, rtime=None):
        """Parses mail and returns an INTERNALDATE string

        It will use information in the following order, falling back as an attempt fails:
          - rtime parameter
          - Date header of email

        We return None, if we couldn't find a valid date. In this case
        the IMAP server will use the server local time when appening
        (per RFC).

        Note, that imaplib's Time2Internaldate is inherently broken as
        it returns localized date strings which are invalid for IMAP
        servers. However, that function is called for *every* append()
        internally. So we need to either pass in `None` or the correct
        string (in which case Time2Internaldate() will do nothing) to
        append(). The output of this function is designed to work as
        input to the imapobj.append() function.

        TODO: We should probably be returning a bytearray rather than a
        string here, because the IMAP server will expect plain
        ASCII. However, imaplib.Time2INternaldate currently returns a
        string so we go with the same for now.

        :param rtime: epoch timestamp to be used rather than analyzing
                  the email.
        :returns: string in the form of "DD-Mmm-YYYY HH:MM:SS +HHMM"
                  (including double quotes) or `None` in case of failure
                  (which is fine as value for append)."""
        if rtime is None:
            message = email.message_from_string(content)
            # parsedate returns a 9-tuple that can be passed directly to
            # time.mktime(); Will be None if missing or not in a valid
            # format.  Note that indexes 6, 7, and 8 of the result tuple are
            # not usable.
            datetuple = email.utils.parsedate(message.get('Date'))
            if datetuple is None:
                #could not determine the date, use the local time.
                return None
            #make it a real struct_time, so we have named attributes
            datetuple = time.struct_time(datetuple)
        else:
            #rtime is set, use that instead
            datetuple = time.localtime(rtime)

        try:
            # Check for invalid dates
            if datetuple[0] < 1981:
                raise ValueError

            # Check for invalid dates
            datetuple_check = time.localtime(time.mktime(datetuple))
            if datetuple[:2] != datetuple_check[:2]:
                raise ValueError

        except (ValueError, OverflowError):
            # Argh, sometimes it's a valid format but year is 0102
            # or something.  Argh.  It seems that Time2Internaldate
            # will rause a ValueError if the year is 0102 but not 1902,
            # but some IMAP servers nonetheless choke on 1902.
            self.ui.debug('imap', "Message with invalid date %s. Server will use local time." \
                              % datetuple)
            return None

        #produce a string representation of datetuple that works as
        #INTERNALDATE
        num2mon = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun',
                   7:'Jul', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}

        #tm_isdst coming from email.parsedate is not usable, we still use it here, mhh
        if datetuple.tm_isdst == '1':
            zone = -time.altzone
        else:
            zone = -time.timezone
        offset_h, offset_m = divmod(zone//60, 60)

        internaldate = '"%02d-%s-%04d %02d:%02d:%02d %+03d%02d"' \
            % (datetuple.tm_mday, num2mon[datetuple.tm_mon], datetuple.tm_year, \
               datetuple.tm_hour, datetuple.tm_min, datetuple.tm_sec, offset_h, offset_m)

        return internaldate

    def savemessage(self, uid, content, flags, rtime):
        """Save the message on the Server

        This backend always assigns a new uid, so the uid arg is ignored.

        This function will update the self.messagelist dict to contain
        the new message after sucessfully saving it.

        :param rtime: A timestamp to be used as the mail date
        :returns: the UID of the new message as assigned by the
                  server. If the folder is read-only it will return 0."""
        self.ui.debug('imap', 'savemessage: called')

        # already have it, just save modified flags
        if uid > 0 and self.uidexists(uid):
            self.savemessageflags(uid, flags)
            return uid

        try:
            imapobj = self.imapserver.acquireconnection()

            try:
                imapobj.select(self.getfullname()) # Needed for search and making the box READ-WRITE
            except imapobj.readonly:
                # readonly exception. Return original uid to notify that
                # we did not save the message. (see savemessage in Base.py)
                self.ui.msgtoreadonly(self, uid, content, flags)
                return uid

            # UIDPLUS extension provides us with an APPENDUID response to our append()
            use_uidplus = 'UIDPLUS' in imapobj.capabilities

            # get the date of the message file, so we can pass it to the server.
            date = self.getmessageinternaldate(content, rtime)
            content = re.sub("(?<!\r)\n", "\r\n", content)

            if not use_uidplus:
                # insert a random unique header that we can fetch later
                (headername, headervalue) = self.generate_randomheader(content)
                self.ui.debug('imap', 'savemessage: new header is: %s: %s' % \
                             (headername, headervalue))
                content = self.savemessage_addheader(content, headername,
                                                     headervalue)    
            if len(content)>200:
                dbg_output = "%s...%s" % (content[:150],
                                          content[-50:])
            else:
                dbg_output = content

            self.ui.debug('imap', "savemessage: date: %s, content: '%s'" %
                          (date, dbg_output))

            (typ,dat) = imapobj.append(self.getfullname(),
                                       imaputil.flagsmaildir2imap(flags),
                                       date, content)
            assert(typ == 'OK')

            # Checkpoint.  Let it write out the messages, etc.
            (typ,dat) = imapobj.check()
            assert(typ == 'OK')

            # get the new UID. Test for APPENDUID response even if the
            # server claims to not support it, as e.g. Gmail does :-(
            if use_uidplus or imapobj._get_untagged_response('APPENDUID', True):
                # get the new UID from the APPENDUID response, it could look like
                # OK [APPENDUID 38505 3955] APPEND completed
                # with 38505 bein folder UIDvalidity and 3955 the new UID
                if not imapobj._get_untagged_response('APPENDUID', True):
                    self.ui.warn("Server supports UIDPLUS but got no APPENDUID "
                                 "appending a message.")
                    return 0
                uid = long(imapobj._get_untagged_response('APPENDUID', True)[-1].split(' ')[1])

            else:
                # we don't support UIDPLUS
                uid = self.savemessage_searchforheader(imapobj, headername,
                                                       headervalue)
                # See docs for savemessage in Base.py for explanation of this and other return values
                if uid == 0:
                    self.ui.debug('imap', 'savemessage: first attempt to get new UID failed.  Going to run a NOOP and try again.')
                    assert(imapobj.noop()[0] == 'OK')
                    uid = self.savemessage_searchforheader(imapobj, headername,
                                                       headervalue)

        finally:
            self.imapserver.releaseconnection(imapobj)

        if uid: # avoid UID FETCH 0 crash happening later on
            self.messagelist[uid] = {'uid': uid, 'flags': flags}

        self.ui.debug('imap', 'savemessage: returning new UID %d' % uid)
        return uid


    def savemessageflags(self, uid, flags):
        imapobj = self.imapserver.acquireconnection()
        try:
            try:
                imapobj.select(self.getfullname())
            except imapobj.readonly:
                self.ui.flagstoreadonly(self, [uid], flags)
                return
            result = imapobj.uid('store', '%d' % uid, 'FLAGS',
                                 imaputil.flagsmaildir2imap(flags))
            assert result[0] == 'OK', 'Error with store: ' + '. '.join(r[1])
        finally:
            self.imapserver.releaseconnection(imapobj)
        result = result[1][0]
        if not result:
            self.messagelist[uid]['flags'] = flags
        else:
            flags = imaputil.flags2hash(imaputil.imapsplit(result)[1])['FLAGS']
            self.messagelist[uid]['flags'] = imaputil.flagsimap2maildir(flags)

    def addmessageflags(self, uid, flags):
        self.addmessagesflags([uid], flags)

    def addmessagesflags_noconvert(self, uidlist, flags):
        self.processmessagesflags('+', uidlist, flags)

    def addmessagesflags(self, uidlist, flags):
        """This is here for the sake of UIDMaps.py -- deletemessages must
        add flags and get a converted UID, and if we don't have noconvert,
        then UIDMaps will try to convert it twice."""
        self.addmessagesflags_noconvert(uidlist, flags)

    def deletemessageflags(self, uid, flags):
        self.deletemessagesflags([uid], flags)

    def deletemessagesflags(self, uidlist, flags):
        self.processmessagesflags('-', uidlist, flags)

    def processmessagesflags(self, operation, uidlist, flags):
        if len(uidlist) > 101:
            # Hack for those IMAP ervers with a limited line length
            self.processmessagesflags(operation, uidlist[:100], flags)
            self.processmessagesflags(operation, uidlist[100:], flags)
            return

        imapobj = self.imapserver.acquireconnection()
        try:
            try:
                imapobj.select(self.getfullname())
            except imapobj.readonly:
                self.ui.flagstoreadonly(self, uidlist, flags)
                return
            r = imapobj.uid('store',
                            imaputil.listjoin(uidlist),
                            operation + 'FLAGS',
                            imaputil.flagsmaildir2imap(flags))
            assert r[0] == 'OK', 'Error with store: ' + '. '.join(r[1])
            r = r[1]
        finally:
            self.imapserver.releaseconnection(imapobj)
        # Some IMAP servers do not always return a result.  Therefore,
        # only update the ones that it talks about, and manually fix
        # the others.
        needupdate = copy(uidlist)
        for result in r:
            if result == None:
                # Compensate for servers that don't return anything from
                # STORE.
                continue
            attributehash = imaputil.flags2hash(imaputil.imapsplit(result)[1])
            if not ('UID' in attributehash and 'FLAGS' in attributehash):
                # Compensate for servers that don't return a UID attribute.
                continue
            lflags = attributehash['FLAGS']
            uid = long(attributehash['UID'])
            self.messagelist[uid]['flags'] = imaputil.flagsimap2maildir(lflags)
            try:
                needupdate.remove(uid)
            except ValueError:          # Let it slide if it's not in the list
                pass
        for uid in needupdate:
            if operation == '+':
                for flag in flags:
                    if not flag in self.messagelist[uid]['flags']:
                        self.messagelist[uid]['flags'].append(flag)
                    self.messagelist[uid]['flags'].sort()
            elif operation == '-':
                for flag in flags:
                    if flag in self.messagelist[uid]['flags']:
                        self.messagelist[uid]['flags'].remove(flag)

    def deletemessage(self, uid):
        self.deletemessages_noconvert([uid])

    def deletemessages(self, uidlist):
        self.deletemessages_noconvert(uidlist)

    def deletemessages_noconvert(self, uidlist):
        # Weed out ones not in self.messagelist
        uidlist = [uid for uid in uidlist if self.uidexists(uid)]
        if not len(uidlist):
            return

        self.addmessagesflags_noconvert(uidlist, ['T'])
        imapobj = self.imapserver.acquireconnection()
        try:
            try:
                imapobj.select(self.getfullname())
            except imapobj.readonly:
                self.ui.deletereadonly(self, uidlist)
                return
            if self.expunge:
                assert(imapobj.expunge()[0] == 'OK')
        finally:
            self.imapserver.releaseconnection(imapobj)
        for uid in uidlist:
            del self.messagelist[uid]


