from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectAI import DistributedObjectAI
from toontown.uberdog.ClientServicesManagerUD import executeHttpRequestAndLog
import ReportGlobals, threading, time

class DistributedReportMgrAI(DistributedObjectAI):
    notify = DirectNotifyGlobal.directNotify.newCategory("DistributedReportMgrAI")

    def __init__(self, air):
        DistributedObjectAI.__init__(self, air)
        self.reports = []
        self.interval = config.GetInt('report-interval', 600)
        taskMgr.add(self.scheduleReport, 'schedule-report')

    def scheduleReport(self, task):
        self.sendAllReports()
        
        # add a delay to the task.
        task.setDelay(self.interval)
        
        # loop the task.
        return task.again

    def sendReport(self, avId, category):
        if not ReportGlobals.isValidCategoryName(category) or not len(str(avId)) == 9:
            return

        reporter = self.air.doId2do.get(self.air.getAvatarIdFromSender())

        if not reporter or reporter.isReported(avId):
            return

        timestamp = int(round(time.time() * 1000))
        self.reports.append('%s|%s|%s|%s' % (timestamp, reporter.doId, avId, category))

    def sendAllReports(self):
        if not self.reports or config.GetString('accountdb-type', 'developer') != 'remote':
            return

        executeHttpRequestAndLog('report', reports=','.join(self.reports))
        self.reports = []
