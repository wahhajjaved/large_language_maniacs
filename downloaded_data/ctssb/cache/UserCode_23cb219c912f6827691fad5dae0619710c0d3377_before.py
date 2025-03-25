#!/usr/bin/env python

from Tools.MyCondTools.gt_tools import *
from Tools.MyCondTools.color_tools import *
#from Tools.MyCondTools.Tier0LastRun import *
#from Tools.MyCondTools.RunValues import *

from Tools.MyCondTools.RunInfo import *


import Tools.MyCondTools.RunRegistryTools as RunRegistryTools
import Tools.MyCondTools.tier0DasInterface as tier0DasInterface
import Tools.MyCondTools.pclMonitoringTools as pclMonitoringTools



import shutil


# --------------------------------------------------------------------------------
# configuratio
runinfoTag             = 'runinfo_31X_hlt'
#runinfoTag             = 'runinfo_start_31X_hlt'
promptCalibDir         = '/afs/cern.ch/cms/CAF/CMSALCA/ALCA_PROMPT/'
webArea                = '/afs/cern.ch/user/c/cerminar/www/PCLMonitor/'
tagLumi                = "BeamSpotObject_ByLumi"
tagRun                 = "BeamSpotObject_ByRun"
tier0DasSrc            = "https://cmsweb.cern.ch/tier0/"
#tier0DasSrc            = "http://gowdy-wttest.cern.ch:8304/tier0/runs"
passwd                 = "/afs/cern.ch/cms/DB/conddb"
connectOracle          =  "oracle://cms_orcoff_prod/CMS_COND_31X_BEAMSPOT"
tagRunOracle           = "BeamSpotObjects_PCL_byRun_v0_offline"
tagLumiOracle          = "BeamSpotObjects_PCL_byLumi_v0_prompt"
cacheFileName          = "PCLMonitorCache.txt"
weburl                 = "http://cerminar.web.cern.ch/cerminar/PCLMonitor/"

writeToWeb             = True
nRunsToPlot            = 100

#os.putenv("CORAL_AUTH_PATH","/afs/cern.ch/cms/DB/conddb")



#webArea = './'
# for inspecting last run after run has stopped  
#tag = 'runsummary_test'




import datetime

# -- status must include:
# 1. errori nell'esecuzione -> exit code !=0 + messaggio di descrizione
# 2. problema PCL -> exit code !=0 + messaggio di descrizione
# 3. data update (controllata dal plugin di nagios)
# NOTE: il plugin di nagios deve anche controllare che l'url sia raggiungibile


def fill1DHisto(histo, xarray, yarray, labels = False):
    lastBin= int(len(xarray))
    counter = 0
    for runnumber in xarray:
#        print "run: " + str(runnumber)
#        print "bin: " + str(lastBin)
        histo.SetBinContent(lastBin, yarray[counter])
        if labels:
            histo.GetXaxis().SetBinLabel(lastBin, str(int(runnumber)))
        lastBin-=1
        counter+=1

    

def runBackEnd():
    # --------------------------------------------------------------------------------
    # --- read the cache
    allCachedRuns = pclMonitoringTools.readCache(cacheFileName)
    cachedRuns = allCachedRuns[0]
    runReports = allCachedRuns[1]

    unknownRun = False # this is set to true only if one run can not be processed
    unknownRunMsg = ''
    # --------------------------------------------------------------------------------
    # --- get the last cached run
    if len(cachedRuns) != 0:
        cachedRuns.sort()
    else:
        cachedRuns.append(1)

    lastCachedRun = cachedRuns[len(cachedRuns)-1]
    print "last cached run #: " + str(lastCachedRun)

    
    # --------------------------------------------------------------------------------
    # --- get the list of collision runs from RR (only for the runs not yet cached)
    runList = []
    try:
        runList = RunRegistryTools.getRunList(lastCachedRun+1)
    except Exception as error:
        print '*** Error 1: RR query has failed'
        print error
        return 101, "Error: failed to get collision runs from RunRegistry: " + str(error)
        
    # --- get the prompt reco status from Tier0-DAS
    tier0Das = tier0DasInterface.Tier0DasInterface(tier0DasSrc) 
    lastPromptRecoRun = lastCachedRun
    try:
        lastPromptRecoRun = tier0Das.lastPromptRun()
        print "Tier0 DAS last run released for PROMPT:       ", lastPromptRecoRun
        #print "Tier0 DAS first run safe for condition update:", tier0Das.firstConditionSafeRun()
    except Exception as error:
        print '*** Error 2: Tier0-DAS query has failed'
        print error
        return 102, "Error: Tier0-DAS query has failed: " + str(error)

    # --------------------------------------------------------------------------------
    # list the IOVs in oracle
    # FIXME: get the tag name directly from the GT through the Tier0-DAS interface for the prompt_cfg
    # runbased tag
    listiov_run_oracle = listIov(connectOracle, tagRunOracle, passwd)
    if listiov_run_oracle[0] == 0:
        iovtableByRun_oracle = IOVTable()
        iovtableByRun_oracle.setFromListIOV(listiov_run_oracle[1])
        #iovtableByRun_oracle.printList()

    # iovbased tag
    listiov_lumi_oracle = listIov(connectOracle, tagLumiOracle, passwd)
    if listiov_lumi_oracle[0] == 0:
        iovtableByLumi_oracle = IOVTable()
        iovtableByLumi_oracle.setFromListIOV(listiov_lumi_oracle[1])

    # --------------------------------------------------------------------------------
    # find the file produced by PCL in the afs area
    fileList = os.listdir(promptCalibDir)
    
    retValues = 0, 'OK'
    # --------------------------------------------------------------------------------
    # run on runs not yet cached
    isFirst = True
    lastDate = datetime.datetime
    isLastProcessed = True
    for run in runList:
        #print run
        if run == 167551:
            continue #FIXME: implement a workaround to the fact that the run-info payload is not there
        # get the run report
        rRep = None
        try:
            rRep = pclMonitoringTools.getRunReport(runinfoTag, run, promptCalibDir, fileList,
                                                   iovtableByRun_oracle, iovtableByLumi_oracle)
        except Exception as error:
            unknownRun = True
            unknownRunMsg = "Error: can not get report for run: " + str(167551) + ", reason: " + str(error)
            print unknownRunMsg
        else:
            
            # check this is not older than the one for the following run
            if isFirst or rRep.jobTime() < lastDate:
                rRep.isOutoforder(False)
                if rRep._pclRun:
                    isFirst = False
                    lastDate = rRep.jobTime()
            else:
                print "   " + warning("Warning: ") + " this comes after the following run!!!"
                rRep.isOutoforder(True)

            runReports.append(rRep)

            if not isLastProcessed:
                if not rRep._pclRun:
                    retValues =  1001, "PCL not run for run: " + str(rRep._runnumber)
                elif not rRep._hasPayload:
                    retValues =  1002, "PCL produced no paylaod for run: " + str(rRep._runnumber)
                elif rRep._isOutOfOrder and not rRep._hasUpload:
                    retValues =  1003, "PCL run out of order for run: " + str(rRep._runnumber)
                elif not rRep._hasUpload:
                    retValues = 1004, "Upload to DB failed for run: " + str(rRep._runnumber)
            if rRep._pclRun:
                isLastProcessed = False
                
    runReports.sort(key=lambda rr: rr._runnumber)


    # -----------------------------------------------------------------
    # ---- cache the results for runs older than 48h and write the log for the web
    pclMonitoringTools.writeCacheAndLog(cacheFileName, webArea + "log.txt", runReports)
    status = retValues[0]
    message = retValues[1]
    if status == 0 and unknownRun:
        status = 1005
        message = unknownRunMsg
    return status, message

import Tools.MyCondTools.monitorStatus as monitorStatus


if __name__ == "__main__":

    # TODO:
    # 1. separa script che genera lo stato da script che fa il plot
    # 5. aggiuni check sulla latency
    # 6. come fai a catchare problemi nel frontend?

    # start here
    status = monitorStatus.MonitorStatus("PCLMonitor")
    status.setWebUrl(weburl)
    statAndMsg = None
    #try:
    statAndMsg = runBackEnd()
    #except:
    #    print "*** Error running back-end call"
    #    statAndMsg = 1000, "unknown error"
    
    status.setStatus(statAndMsg[0],statAndMsg[1])
    status.setUpdateTime(datetime.datetime.today())
    status.writeJsonFile(webArea + "status.json")

    sys.exit(0)
