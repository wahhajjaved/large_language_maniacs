#   Copyright (c) 2003-2007 Open Source Applications Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import unittest, sys, os, logging, datetime, time
from osaf import pim, sharing

from osaf.sharing import recordset_conduit, translator, eimml
from osaf import timemachine

from repository.item.Item import Item
from util import testcase
from application import schema

from osaf.pim.calendar.Recurrence import RecurrenceRuleSet, RecurrenceRule

logger = logging.getLogger(__name__)

printStatistics = True

def printStats(stats):
    if printStatistics:
        for opStats in stats:
            print "'%s' Add: %3d, Mod: %3d, Rm: %3d" % \
                (opStats['op'],
                 len(opStats['added']),
                 len(opStats['modified']),
                 len(opStats['removed'])
                )
        print

cosmo = False

def checkStats(stats, expecting):
    if cosmo: # For now, if testing against cosmo, skip stats checking
        return True
    for seen, expected in zip(stats, expecting):
        for event in ('added', 'modified', 'removed'):
            count = len(seen[event])
            expect = expected[event]
            if isinstance(expect, tuple):
                if count != expect[1 if cosmo else 0]:
                    printStats(stats)
                    return False
            else:
                if count != expect:
                    printStats(stats)
                    return False
    return True

def findOrphan(share, title, masterToSkip=None):
    for item in share.contents:
        if item.displayName == title:
            if masterToSkip is None:
                return item
            elif getattr(item, 'inheritFrom', None) is not masterToSkip:
                return item

class RoundTripTestCase(testcase.DualRepositoryTestCase):

    def RoundTripRun(self):
        self.setUp()
        self.PrepareTestData()
        self.PrepareShares()
        self.RoundTrip()

    def PrepareTestData(self):

        view = self.views[0]

        self.coll = pim.ListCollection("testCollection", itsView=view,
            displayName="Test Collection")

        titles = [
            u"breakfast",
        ]

        self.uuids = { }
        
        tzinfo = view.tzinfo.floating
        createdOn = datetime.datetime(2007, 3, 1, 10, 0, 0, 0, tzinfo)

        pacific = view.tzinfo.getInstance("America/Los_Angeles")
        now = timemachine.getNow(pacific)
        # make sure to use eleven PM if the current time is AM, so recurring
        # events don't get auto-triaged to NOW
        eleven = datetime.time(11 if now.hour > 12 else 23, 0, tzinfo=pacific)
        
        self.elevenToday = datetime.datetime.combine(now.date(), eleven)
        
        count = len(titles)
        for i in xrange(count):
            n = pim.Note(itsView=view)
            n.createdOn = createdOn
            n.displayName = titles[i % count]
            self.uuids[n.itsUUID] = n.displayName
            n.body = u"Here is the body"
            self.coll.add(n)


    def _makeRecurringEvent(self, view, contents):
        # Helper method for recurring event tests ... creates a weekly
        # recurring event, adds it to contents, and returns the event.
        
        # With auto-triage behaviour, using a weekly event makes for more
        # reproducible behaviour in test cases. With daily events, you
        # can get differences in creation of modifications depending on what
        # time of day the test runs relative to the event start times.
        item = pim.Note(itsView=view)
        pim.EventStamp(item).add()
        event = pim.EventStamp(item)
        
        # Cosmo converts PST8PDT to America/Los_Angeles, so that breaks
        # things.  Until we solve that problem, let's use a timezone they
        # understand
        pacific = view.tzinfo.getInstance("America/Los_Angeles")

        event.startTime = self.elevenToday - datetime.timedelta(days=3)
        event.anyTime = False
        event.transparency = 'confirmed'

        # ...make it recur weekly
        rrule = RecurrenceRule(itsView=view, untilIsDate=False, freq='weekly')
        event.rruleset = RecurrenceRuleSet(itsView=view, rrules=[rrule])

        # ...add it to the collection
        contents.add(item)
        
        return event


    def RoundTrip(self):

        view0 = self.views[0]
        view1 = self.views[1]
        coll0 = self.coll

        item = self.share0.contents.first()
        testUuid = item.itsUUID.str16()
        item.icalUID = testUuid

        self.assert_(not pim.has_stamp(coll0, sharing.SharedItem))
        self.assert_(not pim.has_stamp(item, sharing.SharedItem))

        self.share0.contents.displayName = u"original"
        checkCollName = not isinstance(self.share0.conduit,
            sharing.ResourceRecordSetConduit)

        # Initial publish
        self.share0.create()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 1, 'modified' : 0, 'removed' : 0},)),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(coll0, sharing.SharedItem))
        self.assert_(pim.has_stamp(item, sharing.SharedItem))
        self.assert_(self.share0 in sharing.SharedItem(item).sharedIn)
        self.assertEquals(self.share0.displayName, u"original")

        # Local modification only
        item.body = u"CHANGED"
        item.read = True
        self.share0.contents.displayName = u"changed"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        if checkCollName:
            self.assertEquals(self.share0.displayName, u"original")
        self.assert_(item.read == True)

        # Initial subscribe
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 1, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        if checkCollName:
            self.assertEquals(self.share1.displayName, u"original")

        # Verify items are imported
        for uuid in self.uuids:
            n = view1.findUUID(uuid)
            self.assertEqual(self.uuids[uuid], n.displayName)
        item1 = view1.findUUID(testUuid)
        self.assert_(item1 in self.share1.contents)
        self.assert_(item1.body == u"CHANGED")
        self.assert_(item1.read == True)
        self.assert_(pim.has_stamp(item1, sharing.SharedItem))
        self.assert_(pim.has_stamp(self.share1.contents, sharing.SharedItem))
        self.assertEqual(self.share0.contents.itsUUID,
            self.share1.contents.itsUUID)



        # Local and Remote modification, non-overlapping changes - all changes
        # apply
        item.body = u"body changed in 0"
        item1.displayName = u"displayName changed in 1"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        self.share1.contents.displayName = u"also changed"
        view1.commit(); stats = self.share1.sync(); view1.commit()
        if checkCollName:
            self.assertEquals(self.share1.displayName, u"original")
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        if checkCollName:
            self.assertEquals(self.share0.displayName, u"original")
        self.assertEquals(self.share0.contents.displayName, u"changed")
        self.assert_(item.displayName == "displayName changed in 1")
        self.assert_(item.body == "body changed in 0")
        self.assert_(item.read == False)
        self.assert_(item1.displayName == "displayName changed in 1")
        self.assert_(item1.body == "body changed in 0")
        self.assert_(item1.read == False)




        # Ensure last-modified is transmitted properly

        # 1) Simple case, only one way:
        email = "test@example.com"
        emailAddress = pim.EmailAddress.getEmailAddress(view0, email)
        tzinfo = view0.tzinfo.floating
        lastModified = datetime.datetime(2030, 3, 1, 12, 0, 0, 0, tzinfo)
        item.lastModifiedBy = emailAddress
        item.lastModified = lastModified
        item.lastModification = pim.Modification.edited
        item.displayName = "make a change"
        item.read = True
        item1.read = True
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item1.lastModifiedBy.emailAddress == email)
        self.assert_(item1.lastModified == lastModified)
        self.assert_(item1.lastModification == pim.Modification.edited)
        self.assert_(item.read == True)
        self.assert_(item1.read == False)

        # 2) receiving more recent modification:
        email0 = "test0@example.com"
        emailAddress0 = pim.EmailAddress.getEmailAddress(view0, email0)
        lastModified0 = datetime.datetime(2030, 3, 1, 13, 0, 0, 0, tzinfo)
        item.displayName = "make another change"
        item.lastModifiedBy = emailAddress0
        item.lastModified = lastModified0
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        email1 = "test1@example.com"
        emailAddress1 = pim.EmailAddress.getEmailAddress(view1, email1)
        lastModified1 = datetime.datetime(2030, 3, 1, 11, 0, 0, 0, tzinfo)
        item1.lastModifiedBy = emailAddress1
        item1.lastModified = lastModified1
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        # In this case, the mod from view0 is more recent, so applied
        self.assert_(item1.lastModifiedBy.emailAddress == email0)
        self.assert_(item1.lastModified == lastModified0)

        # (Cosmo won't send older modifications, so that is why the stats
        # are the way they are)
        # 3) receiving an older modification:
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        # In this case, the mod from view1 is out of date, so ignored,
        # and both clients have email0 and lastModified0
        self.assert_(item.lastModifiedBy.emailAddress == email0)
        self.assert_(item.lastModified == lastModified0)




        # Local and Remote modification, overlapping and non-overlapping
        # changes - non-overlapping changes apply, overlapping changes
        # become pending for the second syncer
        item.body = u"body changed again in 0"
        item.displayName = u"displayName changed in 0"
        item.setTriageStatus(pim.TriageEnum.later)
        item1.displayName = u"displayName changed again in 1"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # In Cosmo mode, we end up sending a deletion of an old last modified
        # by record, because of the manner in which Cosmo ignores deletions.
        # That is why the stats are different between non-Cosmo and Cosmo mode:
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : (0,1), 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item1.displayName == "displayName changed again in 1")
        self.assert_(item1.triageStatus == pim.TriageEnum.later)
        self.assert_(item1.body == "body changed again in 0")
        # TODO: Verify the pending here
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : (0,1), 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item.displayName == "displayName changed in 0")
        self.assert_(item.body == "body changed again in 0")

        self.assert_(sharing.hasConflicts(item1))
        self.assert_(self.share1.hasConflicts())
        for conflict in sharing.SharedItem(item1).getConflicts():
            conflict.discard()
        # Verify that conflicts are removed when discarded
        self.assertEqual(len(list(sharing.SharedItem(item1).getConflicts())), 0)
        self.assert_(not sharing.hasConflicts(item1))
        self.assert_(not self.share1.hasConflicts())


        # Remote stamping - stamp applied locally
        self.assert_(not pim.has_stamp(item, pim.EventStamp))
        pim.EventStamp(item).add()
        self.assert_(pim.has_stamp(item, pim.EventStamp))
        time0 = datetime.datetime(2007, 1, 26, 12, 0, 0, 0, tzinfo)
        pim.EventStamp(item).startTime = time0
        pim.EventStamp(item).duration = datetime.timedelta(minutes=60)
        pim.EventStamp(item).anyTime = False
        pim.EventStamp(item).transparency = 'tentative'
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(not pim.has_stamp(item1, pim.EventStamp))
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        self.assertEqual(pim.EventStamp(item1).transparency, 'tentative')




        # Remote unstamping - item unstamped locally
        pim.EventStamp(item).remove()
        self.assert_(not pim.has_stamp(item, pim.EventStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(not pim.has_stamp(item1, pim.EventStamp))




        # Remote unstamping, local modification - item does not get unstamped
        # locally, the unstamping becomes a pending conflict
        # First, put the stamp back
        pim.EventStamp(item).add()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # The cosmo-specific modified count might be due to cosmo sending
        # DisplayAlarmRecords even for items that don't have them
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : (0,1), 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        pim.EventStamp(item).remove()
        self.assert_(not pim.has_stamp(item, pim.EventStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        pim.EventStamp(item1).transparency = 'fyi'
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # The cosmo-specific modified count might be due to cosmo sending
        # DisplayAlarmRecords even for items that don't have them
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : (0,1), 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        self.assertEqual(pim.EventStamp(item1).transparency, 'fyi')
        # TODO: Verify pending is correct
        # print self.share1.conduit.getState(testUuid)[1]

        # Clear the conflict by removing the stamp from item1
        pim.EventStamp(item1).remove()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # The cosmo-specific modified count might be due to cosmo sending
        # DisplayAlarmRecords even for items that don't have them
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : (0,1), 'removed' : 0})),
            "Sync operation mismatch")



        # Non-overlapping stamping - stamps get applied on both ends
        pim.EventStamp(item).add()
        pim.TaskStamp(item1).add()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        # The cosmo-specific modified count might be due to cosmo sending
        # DisplayAlarmRecords even for items that don't have them
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : (0,1), 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(item, pim.EventStamp))
        self.assert_(pim.has_stamp(item, pim.TaskStamp))
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        self.assert_(pim.has_stamp(item1, pim.TaskStamp))




        # Both sides unstamp - no conflict
        pim.EventStamp(item).remove()
        pim.EventStamp(item1).remove()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(not pim.has_stamp(item, pim.EventStamp))
        self.assert_(pim.has_stamp(item, pim.TaskStamp))
        self.assert_(not pim.has_stamp(item1, pim.EventStamp))
        self.assert_(pim.has_stamp(item1, pim.TaskStamp))
        # TODO: Verify no pending


        # make sure duration changes work, but 10043
        pim.EventStamp(item).add()
        pim.EventStamp(item).allDay = True
        pim.EventStamp(item).duration = datetime.timedelta(0)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(pim.has_stamp(item, pim.EventStamp))
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        self.assertEqual(pim.EventStamp(item1).duration, datetime.timedelta(0))

        pim.EventStamp(item1).duration = datetime.timedelta(1)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assertEqual(pim.EventStamp(item).duration, datetime.timedelta(1))
        

        # Local unstamping, remote modification - item does not change locally;
        # the remote modification becomes a pending conflict

        # First, put the event stamp back
        pim.EventStamp(item).transparency = 'confirmed'
        pim.EventStamp(item1).remove()
        self.assert_(not pim.has_stamp(item1, pim.EventStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(not pim.has_stamp(item1, pim.EventStamp))
        self.assertEqual(pim.EventStamp(item1).transparency, 'tentative')
        # TODO: Verify pending is correct
        # print self.share1.conduit.getState(testUuid)[1]

        # Local removal -  sends removal recordset
        self.share0.contents.remove(item)
        self.assert_(pim.has_stamp(item, sharing.SharedItem))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 1})),
            "Sync operation mismatch")
        self.assert_(not pim.has_stamp(item, sharing.SharedItem))




        # Remote removal - results in local removal
        self.assert_(pim.has_stamp(item1, sharing.SharedItem))
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 1},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item1 not in self.share1.contents)
        self.assert_(not pim.has_stamp(item1, sharing.SharedItem))




        # Local addition of once-shared item - sends item
        self.share0.contents.add(item)
        item.body = "back from removal"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 1, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")




        # Remote modification of existing item *not* in the local collection
        # - adds item to local collection
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        item1 = view1.findUUID(testUuid)
        self.assert_(item1 in self.share1.contents)
        # Note, we have pending changes because we already had this item
        # in our repository (and it wasn't deleted). Our body is as we had
        # it before the sync:
        self.assertEqual(item1.body, "body changed again in 0")
        # print self.share1.conduit.getState(testUuid)
        # TODO: When there is an API for examining pending changes, test that
        # here to verify they include "back from removal"




        # Remote modification of locally *deleted* item - reconstitutes the
        # item based on last agreed state and adds to local collection
        item.body = "back from the dead"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        # Completely delete item in view 1, ensure it comes back
        item1.delete(True)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 1, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        item1 = view1.findUUID(testUuid)
        self.assert_(item1 in self.share1.contents)
        # Note, since we completely deleted the item, and we reconstituted
        # it back from the agreed state, there are no pending changes
        # print self.share1.conduit.getState(testUuid)
        self.assertEqual(item1.body, "back from the dead")


        # Remotely removed, locally modified - item does not get put back to
        # server; a local removal conflict is added
        self.share0.contents.remove(item)
        self.assert_(item not in self.share0.contents)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 1})),
            "Sync operation mismatch")
        item1.body = "modification no longer trumps removal"
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        sharedItem1 = sharing.SharedItem(item1)

        conflicts = list(sharing.SharedItem(item1).getConflicts())
        self.assertEquals(len(conflicts), 1)
        self.assertEquals(conflicts[0].pendingRemoval, True)
        # Now we have a pending remote removal, let's apply it

        self.assert_(item1 in self.share1.contents)
        conflicts[0].apply()
        self.assert_(item1 not in self.share1.contents)

        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")

        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item not in self.share0.contents)


        # Put it back in the collection and sync both sides
        self.share0.contents.add(item)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 1, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item in self.share0.contents)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        # Note, the last sync doesn't consider this to be an "added" item
        # in the stats because it doesn't really apply any changes to the item
        # other than stick it back into the collection.  I may rethink how
        # this situation is recorded in the stats later on.

        # We have some pending changes, so let's apply them
        for conflict in sharing.SharedItem(item1).getConflicts():
            conflict.apply()
        self.assert_(item1 in self.share1.contents)



        # Remotely removed, locally modified -- but with a change that is
        # not something that's shared, like "error".  Item is removed locally
        self.share0.contents.remove(item)
        self.assert_(item not in self.share0.contents)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 1})),
            "Sync operation mismatch")
        item1.error = "foo"
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 1},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item1 not in self.share1.contents)
        self.assertEquals(len(list(sharing.SharedItem(item1).getConflicts())),
            0)


        # Put it back in the collection and sync both sides
        self.share0.contents.add(item)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 1, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item in self.share0.contents)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        # Note, the last sync doesn't consider this to be an "added" item
        # in the stats because it doesn't really apply any changes to the item
        # other than stick it back into the collection.  I may rethink how
        # this situation is recorded in the stats later on.

        # We have some pending changes, so let's apply them
        for conflict in sharing.SharedItem(item1).getConflicts():
            conflict.apply()
        self.assert_(item1 in self.share1.contents)


        # Set up a removal conflict, and then add the item back on the other
        # side and the conflict should disappear
        self.share1.contents.remove(item1)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        item.displayName = "changed"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        conflicts = list(sharing.SharedItem(item).getConflicts())
        self.assertEquals(len(conflicts), 1)
        self.assertEquals(conflicts[0].pendingRemoval, True)
        self.share1.contents.add(item1)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        conflicts = list(sharing.SharedItem(item).getConflicts())
        self.assertEquals(len(conflicts), 1)
        self.assertEquals(conflicts[0].pendingRemoval, False)
        # We have some pending changes, so let's apply them
        for conflict in conflicts:
            conflict.apply()






        # Remotely modified, locally removed - item gets put back into local
        # collection with remote state.
        item.body = "I win!"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        self.share1.contents.remove(item1)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item1 in self.share1.contents)



        # Remote *and* Local item removal
        self.share0.contents.remove(item)
        self.share1.contents.remove(item1)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 1})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(item not in self.share0.contents)
        self.assert_(item1 not in self.share1.contents)

        # Test MailMessageRecord
        #=================================

        # Cache variable values for assert comparison later
        mId        = u"1234@test.com"
        inReplyTo  = u"3456@test.com"
        refHeader  = u"5678@test.com\n 456789@test.com"
        references  = [u"5678@test.com", "456789@test.com"]
        subject    = u"\u00FCTest Subject"
        body       = u"\u00FCTest Body"
        rfc2822    = u"From: test@test.com\nTo: test1@test.com\nSubject: \u00FCTest Subject\n\n\u00FCTest Body"


        received = u"""Received: from leilani.osafoundation.org (leilani.osafoundation.org [127.0.0.1])
  by leilani.osafoundation.org (Postfix) with ESMTP id 00D037F537;
  Thu, 29 Mar 2007 13:22:42 -0700 (PDT)"""

        fromAddr = pim.EmailAddress.getEmailAddress(view0, u"test@test.com",
                                                    u"test user")

        prevAddr = pim.EmailAddress.getEmailAddress(view0, u"test0@test.com",
                                                    u"test user0")

        toAddr1 = pim.EmailAddress.getEmailAddress(view0, u"test1@test.com",
                                                   u"test user1")

        toAddr2 = pim.EmailAddress.getEmailAddress(view0, u"test2@test.com",
                                                   u"test user2")

        ccAddr = pim.EmailAddress.getEmailAddress(view0, u"test3@test.com",
                                                  u"test user3")

        bccAddr = pim.EmailAddress.getEmailAddress(view0, u"test4@test.com",
                                                   u"test user4")

        repAddr = pim.EmailAddress.getEmailAddress(view0, u"test5@test.com",
                                                   u"test user5")

        origAddr = pim.EmailAddress.getEmailAddress(view0, u"The Management")

        from osaf.mail.utils import dateTimeToRFC2822Date, dataToBinary, binaryToData

        dateSent = datetime.datetime.now(view0.tzinfo.default)
        dateSentString = dateTimeToRFC2822Date(dateSent)

        # Start over with a new item
        item = pim.Note(itsView=view0)
        ms = pim.MailStamp(item)
        ms.add()

        self.share0.contents.add(item)

        #Assign values to the MailStamp on item
        ms.messageId = mId

        #Populate some random headers
        ms.headers = {}

        ms.headers['X-Chandler-From'] = u"True"
        ms.headers['Received'] = received
        ms.headers["From"] = fromAddr.format()
        ms.headers["Subject"] = subject
        ms.headers["In-Reply-To"] = inReplyTo
        ms.headers["References"] = refHeader

        ms.inReplyTo = inReplyTo
        ms.referencesMID = references
        ms.fromAddress = fromAddr
        ms.previousSender = prevAddr
        ms.replyToAddress = repAddr
        ms.toAddress = [toAddr1, toAddr2]
        ms.ccAddress = [ccAddr]
        ms.bccAddress = [bccAddr]
        ms.originators = [origAddr]
        ms.dateSent = dateSent
        ms.dateSentString = dateSentString

        ms.viaMailService = True
        ms.fromMe = True
        ms.fromEIMML = True
        ms.previousInRecipients = True

        ms.rfc2822Message = dataToBinary(ms, "rfc2822Message",
                                         rfc2822, 'message/rfc822',
                                         'bz2', False)

        item.displayName = subject
        item.body = body

        view0.commit()
        self.share0.sync()
        view0.commit()

        view1.commit()
        self.share1.sync()
        view1.commit()

        item1 = view1.findUUID(item.itsUUID)
        self.assert_(pim.has_stamp(item1, pim.MailStamp))
        ms1 = pim.MailStamp(item1)


        self.assertEquals(ms1.messageId, mId)
        self.assertEquals(ms1.dateSentString, dateSentString)


        self.assertEquals(ms1.inReplyTo, inReplyTo)
        self.assertEquals(ms1.referencesMID, references)
        self.assertEquals(ms1.fromAddress.format(), fromAddr.format())
        self.assertEquals(ms1.toAddress.first().format(), toAddr1.format())
        self.assertEquals(ms1.toAddress.last().format(), toAddr2.format())
        self.assertEquals(ms1.ccAddress.first().format(), ccAddr.format())
        self.assertEquals(ms1.bccAddress.first().format(), bccAddr.format())
        self.assertEquals(ms1.originators.first().format(), origAddr.format())

        self.assertEquals(ms1.headers['X-Chandler-From'], u"True")
        self.assertEquals(ms1.headers['From'], fromAddr.format())
        self.assertEquals(ms1.headers['Subject'], subject)
        self.assertEquals(ms1.headers['In-Reply-To'], inReplyTo)
        self.assertEquals(ms1.headers['References'], refHeader)
        self.assertEquals(ms1.headers['Received'], received)

        self.assertEquals(item1.body, body)
        self.assertEquals(item1.displayName, subject)

        if not cosmo:
            # These are not shared over cosmo
            self.assertEquals(ms1.previousSender.format(), prevAddr.format())
            self.assertEquals(ms1.replyToAddress.format(), repAddr.format())
            self.assertEquals(binaryToData(ms1.rfc2822Message), rfc2822)
            self.assertTrue(ms1.viaMailService)
            self.assertTrue(ms1.fromMe)
            self.assertTrue(ms1.fromEIMML)
            self.assertTrue(ms1.previousInRecipients)

        #
        # Recurrence
        #

        # Start over with a new recurring event
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()

        item1 = view1.findUUID(item.itsUUID)
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        event1 = pim.EventStamp(item1)

        self.assertEqual(len(event1.rruleset.rrules), 1)
        rrule = event1.rruleset.rrules.first()
        self.assertEqual(rrule.freq, 'weekly')
        
        # sync an event deletion
        third = event.getFirstOccurrence().getNextOccurrence().getNextOccurrence()
        thirdRecurrenceID = third.recurrenceID
        
        third.deleteThis()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()

        self.failUnlessEqual(event1.getRecurrenceID(thirdRecurrenceID),
                             None)
                             
                             
        # sync a THISANDFUTURE deletion

        future = event.getNextOccurrence(after=thirdRecurrenceID).getNextOccurrence()
        future.deleteThisAndFuture()
        

        # I could fetch all occurrences here, but that could hang if
        # for some reason the recurrence end date didn't get set during
        # the sync. So, when checking that the right events got deleted,
        # we'll query in a 2-year window.
        start = datetime.datetime.now(view0.tzinfo.default) - datetime.timedelta(days=365)
        end = start + datetime.timedelta(days=710)
        
        def getStartTimes(e):
            return list(x.startTime
                           for x in e.getOccurrencesBetween(start, end))
        
        # Make sure I did my THISANDFUTURE delete calculation right; the
        # third event got deleted, so the deleteThisAndFuture starts with
        # the original 5th occurrence.
        expectedStartTimes =  [
             event.startTime,
             event.startTime + datetime.timedelta(days=7),
             event.startTime + datetime.timedelta(days=21)
         ]
         
        self.failUnlessEqual(getStartTimes(event), expectedStartTimes)

        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        self.failUnlessEqual(getStartTimes(event1), expectedStartTimes)
        
        # sync a THIS displayName modification
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        event.changeAll('displayName', u'This is very original')
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        fourth0 = event.getRecurrenceID(event.startTime +
                                        datetime.timedelta(days=21))
        fourth0.changeThis('displayName', u'What a singular title')

        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        item1 = view1.findUUID(item.itsUUID)
        self.assert_(pim.has_stamp(item1, pim.EventStamp))
        event1 = pim.EventStamp(item1)
        
        fourth1 = event1.getRecurrenceID(fourth0.recurrenceID)
        self.failUnlessEqual(fourth1.itsItem.displayName,
                             u'What a singular title')
        self.failUnlessEqual(event1.itsItem.displayName,
                             u'This is very original')
        self.failUnlessEqual(fourth1.getNextOccurrence().itsItem.displayName,
                             u'This is very original')

        # sync a start-time modification
        second0 = event.getFirstOccurrence().getNextOccurrence()
        
        newStart = second0.startTime + datetime.timedelta(hours=2)
        second0.changeThis(pim.EventStamp.startTime.name, newStart)

        # sync
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        # find the sync'ed second occurrence
        second1 = event1.getRecurrenceID(second0.recurrenceID)
        self.failIf(second1 is None, "Missing occurrence after sync")
        self.failUnless(second1.modificationFor is item1,
                        "Un- or disconnected modification after sync")
                        
        self.failUnlessEqual(second1.startTime, newStart,
                             "startTime not modified correctly")

        # remove recurrence
        event.removeRecurrence()
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        self.failIf(event1.rruleset is not None,
                    "recurrence not removed after sync")
        self.failIf(event1.modifications,
                    "modifications not removed/cleared after sync")
        self.failIf(event1.occurrences,
                    "occurrences not removed/cleared after sync")

        # Sync a THISANDFUTURE change.
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        fourth0 = event.getNextOccurrence(
                        after=event.startTime + datetime.timedelta(days=15))
        fourth0.changeThisAndFuture('displayName', u'New Title')
        
        expectedStartTimes = [
            event.startTime,
            event.startTime + datetime.timedelta(days=7),
            event.startTime + datetime.timedelta(days=14)
        ]
        self.failUnlessEqual(getStartTimes(event), expectedStartTimes)

        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        item1 = view1.findUUID(item.itsUUID)
        fourth1 = pim.EventStamp(
                        view1.findUUID(fourth0.getMaster().itsItem.itsUUID))
        
        self.failUnless(pim.has_stamp(fourth1, pim.EventStamp))
        self.failUnlessEqual(fourth1, fourth1.getMaster())
        self.failUnlessEqual(fourth1.rruleset.rrules.first().freq, 'weekly')
        
        event1 = pim.EventStamp(item1)
        self.failUnlessEqual(getStartTimes(event1), expectedStartTimes)
        self.failUnlessEqual(fourth1.itsItem.displayName, u'New Title')

        
        # Different THIS attribute changes.
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        item1 = view1.findUUID(item.itsUUID)
        event1 = pim.EventStamp(item1)
        
        recurrenceID = event.startTime + datetime.timedelta(days=42)
        occurrence0 = event.getRecurrenceID(recurrenceID)
        occurrence1 = event1.getRecurrenceID(recurrenceID)
        self.failIf(None in (occurrence0, occurrence1))

        # In view0, make the occurrence have a duration of 120 minutes
        occurrence0.changeThis(pim.EventStamp.duration.name,
                               datetime.timedelta(minutes=120))
        # In view1, make its transparency be 'fyi'
        occurrence1.changeThis(pim.EventStamp.transparency.name, 'fyi')
                                        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        # Make sure occurrence1 picked up the duration change
        occurrence1 = event1.getRecurrenceID(recurrenceID)
        self.failUnlessEqual(occurrence1.duration,
                             datetime.timedelta(minutes=120))

        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        
        # Make sure the transparency change made it from view1 to view0
        occurrence0 = event.getRecurrenceID(recurrenceID)
        self.failUnlessEqual(occurrence0.transparency, 'fyi')
        self.failIfEqual(event.getFirstOccurrence().transparency, 'fyi')
        
        # deleteThis() local & changeThis() remote.
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        item1 = view1.findUUID(item.itsUUID)
        event1 = pim.EventStamp(item1)
        
        recurrenceID = event.startTime + datetime.timedelta(days=28)
        occurrence0 = event.getRecurrenceID(recurrenceID)
        occurrence1 = event1.getRecurrenceID(recurrenceID)

        occurrence0.changeThis('displayName', u'Woo-hoo')
        
        occurrence1.deleteThis()
        self.failUnless(event1.getRecurrenceID(recurrenceID) is None)

        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        self.failIf(event.getRecurrenceID(recurrenceID) is None)
        self.failIf(event1.getRecurrenceID(recurrenceID) is None)
        
        # Make sure view1 got the displayName modification
        self.failUnlessEqual(event1.getRecurrenceID(recurrenceID).summary,
                             u'Woo-hoo')
        
        

        # change THIS local, THISANDFUTURE remote.
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        item1 = view1.findUUID(item.itsUUID)
        event1 = pim.EventStamp(item1)
        
        futureRecurrenceID = event.startTime + datetime.timedelta(days=56)
        thisRecurrenceID = futureRecurrenceID + datetime.timedelta(days=7)
        future0 = event.getRecurrenceID(futureRecurrenceID)
        this1 = event1.getRecurrenceID(thisRecurrenceID)
        
        this1.itsItem.setTriageStatus(pim.TriageEnum.now)
        this1.itsItem.resetAutoTriageOnDateChange()

        self.failUnlessEqual(this1.modificationFor, item1)
        
        future0.changeThisAndFuture(pim.EventStamp.transparency.name,
                                    'tentative')
        futureUUID = future0.getMaster().itsItem.itsUUID
        self.failIfEqual(item1.itsUUID, futureUUID)

        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 1, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 1, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")

        
        future1 = pim.EventStamp(view1.findUUID(futureUUID))
        self.failUnlessEqual(future1, future1.getMaster())
        
        # this1 got orphaned
        self.assert_(this1.itsItem.isDeleted())

        # ... but that the first occurrence is unchanged.  This used to check
        # the master's triage status, but the master's triage status isn't used
        # in the UI, so compare instead to the first occurrence
        self.failIfEqual(future1.getFirstOccurrence().itsItem.triageStatus,
                         pim.TriageEnum.now)
        
        # Change recurrence
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        # TODO: Need to investigate why these stats are random!
        # self.assert_(checkStats(stats,
        #     ({'added' : 1, 'modified' : 1, 'removed' : 0},
        #      {'added' : 1, 'modified' : 0, 'removed' : 0})),
        #     "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # TODO: Need to investigate why these stats are random!
        # self.assert_(checkStats(stats,
        #     ({'added' : 0, 'modified' : 0, 'removed' : 0},
        #      {'added' : 0, 'modified' : 1, 'removed' : 0})),
        #     "Sync operation mismatch")
        
        item1 = view1.findUUID(item.itsUUID)
        event1 = pim.EventStamp(item1)            
        event.rruleset.rrules.first().freq = 'daily'
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # TODO: Need to investigate why these stats are random!
        # self.assert_(checkStats(stats,
        #     ({'added' : 0, 'modified' : 1, 'removed' : 0},
        #      {'added' : 0, 'modified' : 0, 'removed' : 0})),
        #     "Sync operation mismatch")
        
        self.failUnlessEqual(event1.rruleset.rrules.first().freq,
                            'daily')



        # Make a modification, sync it, then 'unmodify' it
        second0 = event.getFirstOccurrence().getNextOccurrence()
        second0.itsItem.displayName = "Changed"
        second0.itsItem.setTriageStatus(pim.TriageEnum.now)
        second0.itsItem.resetAutoTriageOnDateChange()
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        # TODO: Need to investigate why these stats are random!
        # self.assert_(checkStats(stats,
        #     ({'added' : 0, 'modified' : 0, 'removed' : 0},
        #      {'added' : 1, 'modified' : 0, 'removed' : 0})),
        #     "Sync operation mismatch")

        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 1, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        second1 = event1.getRecurrenceID(second0.recurrenceID)
        self.assert_(not second1.isGenerated)
        self.assertEqual(second1.itsItem._triageStatus, pim.TriageEnum.now)
        self.assertEqual(second1.itsItem.displayName, "Changed")

        # make sure setting triageStatus back to Inherit works
        second0.itsItem.setTriageStatus(pim.TriageEnum.done)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assertEqual(second1.itsItem._triageStatus, pim.TriageEnum.done)


        second0.unmodify(partial=True)
        # a partial unmodify should leave second0 in the collection
        self.assert_(second0.itsItem in self.share0.contents)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 0},
             {'added' : 0, 'modified' : 0, 'removed' : 1})),
            "Sync operation mismatch")

        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 0, 'removed' : 1},
             {'added' : 0, 'modified' : 0, 'removed' : 0})),
            "Sync operation mismatch")
        self.assertEqual(second1.itsItem._triageStatus, pim.TriageEnum.done)
        self.failIf(second1.itsItem.hasLocalAttributeValue('displayName'))
        
        # Now it's back to an unmodification

        # Make it a modification again on both sides
        second0.itsItem.displayName = "Changed again"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(not second1.isGenerated)
        # In ResourceRecordSet mode, second0 has conflicts (need to research)
        for conflict in sharing.SharedItem(second1.itsItem).getConflicts():
            conflict.apply()

        # Couple an unmodify with an inbound change
        second1.itsItem.displayName = "Changed in view 1"
        view1.commit(); stats = self.share1.sync(); view1.commit()
        second0.unmodify()
        self.assert_(second0.itsItem not in self.share0.contents)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        # Inbound change wins, item is back to being a modification
        self.assertEqual(second0.itsItem.displayName, "Changed in view 1")

        # Couple an outbound change with an incoming EXDATE for that occurrence
        second0.deleteThis()
        self.assert_(pim.isDead(second0.itsItem))
        view0.commit(); stats = self.share0.sync(); view0.commit()

        second1.itsItem.displayName = "Changed again in view 1"
        self.assert_(not second1.isGenerated)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # second1 got orphaned
        self.assert_(pim.isDead(second1.itsItem))
        # Should be no conflict on item1 (the master)
        conflicts = list(sharing.SharedItem(item1).getConflicts())
        self.assertEquals(len(conflicts), 0)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()



        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        item1 = view1.findUUID(item.itsUUID)
        event1 = pim.EventStamp(item1)

        # Verify that stamping and unstamping of Mail works.  Note that
        # stamping/unstamping of Mail always operates on entire series.
        # ...stamp in 0...
        pim.CHANGE_ALL(pim.MailStamp(item)).add()
        self.assert_(pim.has_stamp(item, pim.MailStamp))
        second0 = event.getFirstOccurrence().getNextOccurrence()
        self.assert_(pim.has_stamp(second0.itsItem, pim.MailStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(pim.has_stamp(item1, pim.MailStamp))
        second1 = event1.getRecurrenceID(second0.recurrenceID)

        self.assert_(pim.has_stamp(second1.itsItem, pim.MailStamp))

        # ...unstamp in 1...
        pim.CHANGE_ALL(pim.MailStamp(item1)).remove()
        self.assert_(not pim.has_stamp(item1, pim.MailStamp))
        self.assert_(not pim.has_stamp(second1.itsItem, pim.MailStamp))
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(not pim.has_stamp(item, pim.MailStamp))
        self.assert_(not pim.has_stamp(second0.itsItem, pim.MailStamp))

        # ...stamp in 0...
        pim.CHANGE_ALL(pim.MailStamp(item)).add()
        self.assert_(pim.has_stamp(item, pim.MailStamp))
        self.assert_(pim.has_stamp(second0.itsItem, pim.MailStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(pim.has_stamp(item1, pim.MailStamp))
        self.assert_(pim.has_stamp(second1.itsItem, pim.MailStamp))

        # ...unstamp in 0...
        pim.CHANGE_ALL(pim.MailStamp(item)).remove()
        self.assert_(not pim.has_stamp(item, pim.MailStamp))
        self.assert_(not pim.has_stamp(second0.itsItem, pim.MailStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(not pim.has_stamp(item1, pim.MailStamp))
        self.assert_(not pim.has_stamp(second1.itsItem, pim.MailStamp))


        # Verify that stamping and unstamping of Task works.  Note that
        # we can stamp/unstamp individual occurrences with Task
        # ...stamp master in 0...
        pim.CHANGE_ALL(pim.TaskStamp(item)).add()
        self.assert_(pim.has_stamp(item, pim.TaskStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(pim.has_stamp(item1, pim.TaskStamp))

        # ...unstamp master in 1...
        pim.TaskStamp(pim.CHANGE_ALL(item1)).remove()
        self.assert_(not pim.has_stamp(item1, pim.TaskStamp))
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(not pim.has_stamp(item, pim.TaskStamp))

        # ...stamp master in 0...
        pim.CHANGE_ALL(pim.TaskStamp(item)).add()
        self.assert_(pim.has_stamp(item, pim.TaskStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(pim.has_stamp(item1, pim.TaskStamp))

        # ...unstamp master in 0...
        pim.TaskStamp(pim.CHANGE_ALL(item)).remove()
        self.assert_(not pim.has_stamp(item, pim.TaskStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(not pim.has_stamp(item1, pim.TaskStamp))


        # ...stamp second in 0...
        pim.TaskStamp(pim.CHANGE_THIS(second0)).add()
        self.assert_(pim.has_stamp(second0.itsItem, pim.TaskStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(pim.has_stamp(second1.itsItem, pim.TaskStamp))

        # ...unstamp second in 1...
        pim.TaskStamp(pim.CHANGE_THIS(second1.itsItem)).remove()
        self.assert_(not pim.has_stamp(second1.itsItem, pim.TaskStamp))
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(not pim.has_stamp(second0.itsItem, pim.TaskStamp))

        # ...stamp second in 0...
        pim.TaskStamp(pim.CHANGE_THIS(second0)).add()
        self.assert_(pim.has_stamp(second0.itsItem, pim.TaskStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(pim.has_stamp(second1.itsItem, pim.TaskStamp))

        # create a non-conflicting change in second1 after second0 is changed to
        # a triage-only modification
        pim.TaskStamp(pim.CHANGE_THIS(second0.itsItem)).remove()
        self.assert_(second0.isTriageOnlyModification())
        second1.itsItem.displayName = "Changed title and task"
        
        self.assert_(not pim.has_stamp(second0.itsItem, pim.TaskStamp))
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assert_(not pim.has_stamp(second1.itsItem, pim.TaskStamp))
        
        self.assert_(not second1.isTriageOnlyModification())
        self.assertEqual(second1.itsItem.displayName, "Changed title and task")
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(not pim.has_stamp(second0.itsItem, pim.TaskStamp))
        self.assertEqual(second0.itsItem.displayName, "Changed title and task")
        
        # make second0's title inherit, which makes a triage-only modification,
        # also change second1's title.  In a perfect world this would be seen as
        # a conflicting change to title, instead view1's change should win
        del second0.itsItem.displayName
        self.assert_(second0.isTriageOnlyModification())
        second1.itsItem.displayName = "Changed again"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        self.assertEqual(second1.itsItem.displayName, "Changed again")
        self.assert_(not sharing.hasConflicts(second1.itsItem))

        # See what happens when we "unmodify" a modification on one side,
        # but delete the entire series on the other...

        # First make it a modification, sync it, then 'unmodify' it
        second0.itsItem.displayName = "Changed"
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        second1 = event1.getRecurrenceID(second0.recurrenceID)
        self.assert_(not second1.isGenerated)

        self.assert_(item1 in self.share1.contents)
        self.share1.contents.remove(item1)
        self.assert_(item1 not in self.share1.contents)
        # removing item1 should've removed all occurrences from the collection
        self.assert_(second1.itsItem not in self.share1.contents)
        view1.commit(); stats = self.share1.sync(); view1.commit()

        second0.unmodify()
        self.assert_(second0.itsItem not in self.share0.contents)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        # The master is removed from the collection
        self.assert_(item not in self.share0.contents)



        # Verify that remote removal of a master and local trivial (triage)
        # change of a modification results in local removal of event

        # Create a new recurring event and share it
        event = self._makeRecurringEvent(view0, self.share0.contents)
        event.rruleset.rrules.first().freq = 'daily'
        item = event.getFirstOccurrence().itsItem
        item.setTriageStatus(pim.TriageEnum.later)
        item.resetAutoTriageOnDateChange()
        self.assertEquals(item.triageStatus, pim.TriageEnum.later)
        
        view0.commit(); stats1 = self.share0.sync(); view0.commit()
        view1.commit(); stats2 = self.share1.sync(); view1.commit()
        masterItem1 = view1.findUUID(event.itsItem.itsUUID)
        master1 = pim.EventStamp(masterItem1)
        event1 = master1.getRecurrenceID(pim.EventStamp(item).recurrenceID)
        item1 = event1.itsItem
        self.assertEquals(master1.rruleset.rrules.first().freq, 'daily')

        self.assertEquals(item1.triageStatus, pim.TriageEnum.later)
        self.assertEquals(item1.doAutoTriageOnDateChange, False)

        # Remove it from the server
        self.share1.contents.remove(masterItem1)
        view1.commit(); stats = self.share1.sync(); view1.commit()

        # Make a local triage change to an occurrence, the remote removal
        # will remove the series from the local collection
        second0 = event.getFirstOccurrence().getNextOccurrence()
        second0.itsItem.setTriageStatus(pim.TriageEnum.done)
        second0.itsItem.resetAutoTriageOnDateChange()
        self.assert_(self.share0 in sharing.SharedItem(item).sharedIn)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(item.inheritFrom not in self.share0.contents)
        self.assert_(self.share0 not in sharing.SharedItem(item.inheritFrom).sharedIn)
        # make sure the first occurrence also had its SharedItem stamp removed
        self.assert_(item not in self.share0.contents)
        self.assert_(self.share0 not in sharing.SharedItem(item).sharedIn)


        # check resolvable triage conflicts, which stem from Inherit meaning
        # Now or Done depending on the master's lastPastOccurrence value
        event = self._makeRecurringEvent(view0, self.share0.contents)
        event.rruleset.rrules.first().freq = 'daily'
        elevenTomorrow = self.elevenToday + datetime.timedelta(days=1)
        tomorrowEvent = event.getRecurrenceID(elevenTomorrow)
        
        # pretend the current time is just before eleven tomorrow
        timemachine.setNow(elevenTomorrow - datetime.timedelta(minutes=10))
        
        item = event.itsItem
        item.read = True
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        item1 = view1.findUUID(item.itsUUID)
        item1.read = True
        event1 = pim.EventStamp(item1)
        tomorrowEvent1 = event1.getRecurrenceID(elevenTomorrow)
        self.assert_(tomorrowEvent1.itsItem.read)
        self.assertEqual(tomorrowEvent1.itsItem._triageStatus,
                         pim.TriageEnum.later)

        # pretend the current time is just after eleven tomorrow
        timemachine.setNow(elevenTomorrow + datetime.timedelta(minutes=10))
        
        # emulate tickling in both, move view0's occurrence to done
        tomorrowEvent1.itsItem.setTriageStatus(pim.TriageEnum.now)
        tomorrowEvent.itsItem.setTriageStatus(pim.TriageEnum.done)

        # exercise triageStatusFromDateComparison by creating a far future 
        # occurrence that doesn't yet exist in view1
        muchLater = elevenTomorrow + datetime.timedelta(14)
        muchLaterEvent = event.getRecurrenceID(muchLater)
        muchLaterEvent.itsItem.setTriageStatus(pim.TriageEnum.done)

        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        
        # view0's change should win
        self.assertEqual(tomorrowEvent1.itsItem._triageStatus,
                         pim.TriageEnum.done)
        self.assertEqual(tomorrowEvent.itsItem._triageStatus,
                         pim.TriageEnum.done)
        
        muchLaterEvent1 = event1.getRecurrenceID(muchLater)
        self.assertEqual(muchLaterEvent1.itsItem._triageStatus,
                         pim.TriageEnum.done)
        # adding the new item muchLater1 marked the series as unread, mark it
        # read again
        item1.read = True
        
        # because view0's change won, and there were no other meaningful
        # changes, view0's tomorrowEvent shouldn't be marked unread or popped to
        # now
        self.assert_(tomorrowEvent.itsItem.read)
        self.failIf(hasattr(tomorrowEvent.itsItem, '_sectionTriageStatus'))

        twoDaysLater = self.elevenToday + datetime.timedelta(days=2)
        twoDaysEvent = event.getRecurrenceID(twoDaysLater)
        twoDaysEvent1 = event1.getRecurrenceID(twoDaysLater)
        
        timemachine.setNow(twoDaysLater + datetime.timedelta(minutes=10))
        
        # emulate tickling in both, move view1's occurrence to done
        twoDaysEvent1.itsItem.setTriageStatus(pim.TriageEnum.done)
        twoDaysEvent.itsItem.setTriageStatus(pim.TriageEnum.now)

        view0.commit(); stats = self.share0.sync(); view0.commit()
        # make sure lastPastOccurrence conflicts are automatically resolved
        timemachine.setNow(self.elevenToday + datetime.timedelta(days=5))
        
        view1.commit(); stats = self.share1.sync(); view1.commit()
        
        conflicts = list(sharing.SharedItem(item1).getConflicts())
        self.assertEqual(len(conflicts), 0)

        # view1 won, so its twoDaysEvent shouldn't be unread or popped to now
        self.assert_(twoDaysEvent1.itsItem.read)
        self.failIf(hasattr(twoDaysEvent1.itsItem, '_sectionTriageStatus'))
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        
        # view1's change should win
        self.assertEqual(twoDaysEvent1.itsItem._triageStatus,
                         pim.TriageEnum.done)
        self.assertEqual(twoDaysEvent.itsItem._triageStatus,
                         pim.TriageEnum.done)
        
        timemachine.resetNow()
        
        # Verify that remote removal of a master and local nontrivial change
        # of a modification results in the series getting removed, but
        # the local modifications are orphaned

        # Create a new recurring event and share it
        event = self._makeRecurringEvent(view0, self.share0.contents)
        event.rruleset.rrules.first().freq = 'daily'
        item = event.itsItem
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        item1 = view1.findUUID(item.itsUUID)
        event1 = pim.EventStamp(item1)
        self.assertEquals(event1.rruleset.rrules.first().freq, 'daily')

        # Remove it from the server
        self.share1.contents.remove(item1)
        view1.commit(); stats = self.share1.sync(); view1.commit()

        # Make a local displayName change to an occurrence
        second0 = event.getFirstOccurrence().getNextOccurrence()
        second0.itsItem.displayName = "Don't remove me!"
        self.assert_(self.share0 in sharing.SharedItem(item).sharedIn)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        self.assert_(item not in self.share0.contents)
        self.assert_(self.share0 not in sharing.SharedItem(item).sharedIn)
        # find the replacement for the orphan:
        newItem = findOrphan(self.share0, "Don't remove me!")
        self.assert_(newItem is not None)
        conflicts = list(sharing.getConflicts(newItem))
        self.assertEquals(len(conflicts), 1)
        self.assertEquals(conflicts[0].pendingRemoval, True)





        # Test scenario for bug 10510:

        # Start over with a new recurring event
        event0 = self._makeRecurringEvent(view0, self.share0.contents)
        item0 = event0.itsItem
        event0.rruleset.rrules.first().freq = 'daily'
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # Make modifications out of 2nd/3rd occurrences:
        second0 = event0.getFirstOccurrence().getNextOccurrence()
        third0 = second0.getNextOccurrence()
        newTime = second0.startTime + datetime.timedelta(hours=1)
        second0.changeThis(pim.EventStamp.startTime.name, newTime)
        newTime = third0.startTime + datetime.timedelta(hours=1)
        third0.changeThis(pim.EventStamp.startTime.name, newTime)
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # Make a startime this/future change to 2nd occurrence:
        item1 = view1.findUUID(item0.itsUUID)
        event1 = pim.EventStamp(item1)
        second1 = event1.getFirstOccurrence().getNextOccurrence()
        newTime = second1.startTime + datetime.timedelta(hours=1)
        second1.changeThisAndFuture(pim.EventStamp.startTime.name, newTime)
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()
        # The two unmodifications should disappear, leaving just the master
        # and its first occurrence:
        self.assertEquals(len(event0.occurrences), 1)
        first0 = event0.getFirstOccurrence()
        self.assertEquals(event0.startTime, first0.startTime)


        # scenario for bug 10537, distinguish between inbound deletions and
        # unmodifications
        
        # Start over with a new recurring event
        event0 = self._makeRecurringEvent(view0, self.share0.contents)
        item0 = event0.itsItem
        event0.rruleset.rrules.first().freq = 'daily'
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        item1 = view1.findUUID(item0.itsUUID)
        event1 = pim.EventStamp(item1)
        second0 = event0.getFirstOccurrence().getNextOccurrence()
        second1 = event1.getFirstOccurrence().getNextOccurrence()
        
        third0 = second0.getNextOccurrence()
        third1 = second1.getNextOccurrence()
        
        second1.changeThis('displayName', 'modification to move')
        third1.changeThis('displayName', 'modification to orphan')
        view1.commit(); stats = self.share1.sync(); view1.commit()
        view0.commit(); stats = self.share0.sync(); view0.commit()

        newStart = event0.startTime + datetime.timedelta(hours=1)
        event0.changeAll(pim.EventStamp.startTime.name, newStart)
        third1.changeThis('displayName', 'changed, in conflict')
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()

        self.assert_(second1.itsItem.isDeleted())
        self.assert_(third1.itsItem.isDeleted())
        
        # make sure the second1 wasn't orphaned
        newItem = findOrphan(self.share1, 'modification to move', item1)
        self.assert_(newItem is None)

        # make sure third1 was orphaned
        newItem = findOrphan(self.share1, 'changed, in conflict', item1)
        self.assert_(newItem is not None)


        # new third
        third0 = event0.getFirstOccurrence().getNextOccurrence().getNextOccurrence()
        third0.changeThis('displayName', "modification to delete")
        fourth0 = third0.getNextOccurrence()
        fourth0.changeThis('displayName', "modification to delete and conflict")
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        third1 = event1.getRecurrenceID(third0.recurrenceID)
        fourth1 = event1.getRecurrenceID(fourth0.recurrenceID)
        
        third0.deleteThis()
        fourth0.deleteThis()
        
        fourth1.changeThis('displayName', "should become an orphan")
        
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()

        self.assert_(third1.itsItem.isDeleted())
        self.assert_(fourth1.itsItem.isDeleted())
        
        # make sure third1 wasn't orphaned
        newItem = findOrphan(self.share1, 'modification to move', item1)
        self.assert_(newItem is None)

        # make sure fourth1 was orphaned
        newItem = findOrphan(self.share1, "should become an orphan", item1)
        self.assert_(newItem is not None)




        # Clean out all the items
        for item in list(self.share0.contents):
            self.share0.contents.remove(item)
        view0.commit(); stats = self.share0.sync(); view0.commit()

        # Verify auto-resolve:

        # DisplayAlarmRecord...
        event = self._makeRecurringEvent(view0, self.share0.contents)
        item = event.itsItem
        self.share0.conduit.filters.add('cid:reminders-filter@osaf.us')
        view0.commit(); stats = self.share0.sync(); view0.commit()
        view1.commit(); stats = self.share1.sync(); view1.commit()
        item1 = view1.findUUID(item.itsUUID)
        # modify item1 so that the next sync will send a "None"-filled
        # DisplayAlarmRecord
        item1.displayName = "changed"
        view1.commit(); stats = self.share1.sync(); view1.commit()
        # Assign an alarm (I'm cheating by getting the translator to do the
        # work for me):
        trans = sharing.SharingTranslator(view0)
        trans.importRecord(sharing.DisplayAlarmRecord(item, u'', u'-PT42M',
            None, None))
        self.share0.conduit.filters.remove('cid:reminders-filter@osaf.us')
        view0.commit(); stats = self.share0.sync(forceUpdate=True); view0.commit()
        self.assert_(checkStats(stats,
            ({'added' : 0, 'modified' : 1, 'removed' : 0},
             {'added' : 0, 'modified' : 1, 'removed' : 0})),
            "Sync operation mismatch")
        self.assert_(not sharing.hasConflicts(item))


        self.share0.destroy() # clean up
