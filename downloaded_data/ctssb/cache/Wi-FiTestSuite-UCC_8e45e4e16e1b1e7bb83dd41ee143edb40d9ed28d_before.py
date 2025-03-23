###################################################################
#
# Copyright (c) 2014 Wi-Fi Alliance
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
# RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
# USE OR PERFORMANCE OF THIS SOFTWARE.
#
###################################################################

#!/usr/bin/evn python
import os, sys
from socket import *
from time import gmtime, strftime
import thread, time, Queue, os
import sys, time
from select import select
import logging
import re
import ctypes
import pprint
import xml.dom.minidom
from xml.dom.minidom import Node
import HTML
from decimal import Decimal



### Input Files ####
MasterTestInfo = "\MasterTestInfo.xml"
DUTInfoFile = "\DUTInfo.txt"
TestbedAPFile = "\802.11n-Testbed-APs.txt"
InitFile = "\init_802.11n.txt"
RADIUSServer = "\RADIUS-Servers.txt"
STAMACAddress = "\STA_MAC_Addresses.txt"
APMACAddress = "\AP_MAC_Addresses.txt"
ProgName = os.getenv("PROG_NAME")
TestbedAPList = "\TestbedAPNames.txt"


### Output Files ####
InitEnvLogFile = "InitEnvLog.log"
#File which would be used by UCC core
UCCInitEnvFile = "\InitEnv.txt"
LogFile = ""
DUTFeatureInfoFile = "./log/DUTFeatureInfo.html"


#Variable List
VarList = {}

# List of EAPMethods
EAPList = ["TLS", "TTLS", "PEAP0", "FAST", "PEAP1", "SIM", "AKA", "AKA\'", "PWD"]

# List of WPS Config Methods
WPSConfigList = ["WPS_Keypad", "WPS_Display", "WPS_PushButton", "WPS_Label"]

#default command file path
uccPath = "..\\cmds"

bandSelectionList = {}
doc = ""

#Global Object to handle Test ENV Variables
testEnvVariables = ""

# Qualification changes
qual = 0
QualAP = ""
QualSTA = ""

# Main function
def InitTestEnv(testID, cmdPath, progName, initFile, TBFile, q=0, qualAP="", qualSTA=""):
    global MasterTestInfo, DUTInfoFile, doc, InitFile, TestbedAPFile, ProgName, uccPath, testEnvVariables, QualAP, QualSTA, qual, VarList

    uccPath = cmdPath
    VarList = {}

    doc = xml.dom.minidom.parse(uccPath + MasterTestInfo)
    InitFile = "\\" + initFile
    ProgName = progName
    TestbedAPFile = "\\" + TBFile
    TestID = testID
    testEnvVariables = envVariables()

    # For test bed qualification only
    if q:
        qual = q
        QualAP = qualAP
        QualSTA = qualSTA

    #TestID=TestID.split('_')[0]

    InitLog(InitEnvLogFile)
    ReadDUTInfo(DUTInfoFile, TestID)

    LogMsg("Input Files - \n MasterTestInfo = %s \n DUTInfoFile =%s \n" %(MasterTestInfo, DUTInfoFile))
    #Check for WEP Support

    if getattr(dutInfoObject, "WEP") == "1":
        LogMsg("WEP is supported by DUT ")
        if check_isNode_Level1("%s-%s" % (TestID, "WEP")):
            TestID = ("%s-%s"%(TestID, "WEP"))
            LogMsg("Test ID = %s" % TestID)

    LogMsg("----Test ID = %s-------" % TestID)
    GetCAPIFileNames(TestID)
    GetTestbedDeviceInfo(TestID)
    if ProgName == "P2P" or ProgName == "WFD" or ProgName == "WFDS" or ProgName == "NAN":
        GetP2PVariables(TestID)

    if not (ProgName == "P2P" or ProgName == "TDLS" or ProgName == "NAN"):
        GetServerSupplicantInfo(TestID)

    if ProgName == "HS2-R2":
        GetSubscriptionServerInfo(TestID)

    GetSnifferInfo(TestID)
    LogMsg(dutInfoObject)
    LogMsg(testEnvVariables)
    GetOtherVariables(TestID)
    createUCCInitEnvFile(UCCInitEnvFile)
    createDownloadLog()

#
# Class: dutInfo
# This class holds all the required information about DUT
#
class dutInfo:
    def __init__(self,
                 DUTType="",
                 DUTCategory="",
                 DUTBand="",
                 TestCaseID="",
                 DUTEAPMethod="",
                 WEP=0,
                 preAuth=0,
                 _11h=0,
                 SupportedChannelWidth=0,
                 Streams=0,
                 Greenfield=0,
                 SGI20=0,
                 SGI40=0,
                 RIFS_TX=0,
                 Coexistence_2040=0,
                 STBC_RX=0,
                 STBC_TX=0,
                 MCS32=0,
                 WTSSupport=1,
                 OBSS=0,
                 AMPDU_TX=0,
                 AP_Concurrent=0,
                 TDLSDiscReq=0,
                 PUSleepSTA=0,
                 _11d=0,
                 STAUT_PM=0,
                 Open_Mode=0,
                 Mixedmode_WPA2WPA=0,
                 PMF_OOB=0,
                 ASD=0):
        self.DUTType = DUTType
        self.DUTCategory = DUTCategory
        self.DUTBand = DUTBand
        self.TestCaseID = TestCaseID
        self.DUTEAPMethod = DUTEAPMethod
        self.WEP = WEP
        self.PreAuth = preAuth
        self._11h = _11h
        self.SupportedChannelWidth = SupportedChannelWidth
        self.Streams = Streams
        self.Greenfield = Greenfield
        self.SGI20 = SGI20
        self.SGI40 = SGI40
        self.RIFS_TX = RIFS_TX
        self.Coexistence_2040 = Coexistence_2040
        self.STBC_RX = STBC_RX
        self.STBC_TX = STBC_TX
        self.MCS32 = MCS32
        self.WTSSupport = WTSSupport
        self.OBSS = OBSS
        self.AMPDU_TX = AMPDU_TX
        self.AP_Concurrent = AP_Concurrent
        self._11d = _11d
        self.STAUT_PM = STAUT_PM
        self.Open_Mode = Open_Mode
        self.Mixedmode_WPA2WPA = Mixedmode_WPA2WPA
        self.PMF_OOB = PMF_OOB
        #TDLS Specific
        self.TDLSDiscReq = TDLSDiscReq
        self.PUSleepSTA = PUSleepSTA
        #ASD Device
        self.ASD = ASD

    def __setattr__(self, attr, value):
        self.__dict__[attr] = value

    def __str__(self):
        return ("""Type = %s
                 Category = %s
                 Band = %s
                 EAP = %s
                 TestCase = %s
                 WEP =%s
                 PreAuth = %s
                 11h = %s
                 WTS Support =%s
                 11d = %s
                 STAUT_PM = %s""" %
                (self.DUTType,
                 self.DUTCategory,
                 self.DUTBand,
                 self.DUTEAPMethod,
                 self.TestCaseID,
                 self.WEP,
                 self.PreAuth,
                 self._11h,
                 self.WTSSupport,
                 self._11d,
                 self.STAUT_PM))

#Global Object to handle DUT Information
dutInfoObject = dutInfo()

#
# Class: testbedAP
# This class holds all the required variables for any testbed AP
#

class testbedAP:
    def __init__(self, Name="", Number=0, state="off"):
        self.Name = Name
        self.Number = Number
        self.State = state

    def formatAPUCC(self):
        return "\n\ndefine!$AP%s!%s!\ndefine!$AP%sPowerSwitchPort!%s!\ndefine!$AP%sState!%s!\ndefine!$AP%sIPAddress!%s!\n" % (self.Number, self.Name, self.Number, GetAPPortNumber(self.Name), self.Number, self.State, self.Number, GetAPIPAddress(self.Name))
    def __str__(self):
        return "AP Name = %s | AP Number = %s | AP Powerswitch Port = %s | AP IP Address = %s | AP State = %s" % (self.Name, self.Number, GetAPPortNumber(self.Name), GetAPIPAddress(self.Name), self.State)

class server:
    def __init__(self, Name="-", IP=0, Port="-", Password="-", supplicant="-", tesbedsupplicant="-"):
        self.name = Name
        self.IP = IP
        self.Port = Port
        self.Password = Password
        self.Supplicant = supplicant
        self.STASupplicant = tesbedsupplicant
    def formatUCC(self):
        return "\n\ndefine!$RADIUSIPAddress!%s!\ndefine!$RADIUSPort!%s!\ndefine!$RADIUSSharedSecret!%s!\ndefine!$SupplicantName!%s!\ndefine!$STASupplicantName!%s!\n" % (self.IP, self.Port, self.Password, self.Supplicant, self.STASupplicant)
    def __str__(self):
        return "RADIUS Name = %s | RADIUS IP  = %s | RADIUS  Port = %s | RADIUS Shared Secret = %s | Supplicant = %s | Testbed STA Supplicant = %s" % (self.name, self.IP, self.Port, self.Password, self.Supplicant, self.STASupplicant)

#Global Object to handle server Information
serverInfo = server()

class envVariables:
    """This class holds all the required variables for the test"""
    global ProgName, uccPath
    def __init__(self,
                 Channel="",
                 Channel_1="",
                 Channel_2="",
                 Channel_3="",
                 Band="",
                 SSID="",
                 SSID_1="",
                 SSID_2="",
                 SSID_3="",
                 TSTA1="",
                 TSTA2="",
                 TSTA3="",
                 TSTA4="",
                 TSTA5="",
                 TestbedConfigCAPIFile="",
                 DUTConfigCAPIFile="",
                 STAConfigCAPIFile="",
                 WLANTestCAPIFile=""):
        self.Channel = Channel
        self.Channel_1 = Channel_1
        self.Channel_2 = Channel_2
        self.Channel_3 = Channel_3
        self.Band = Band
        self.SSID = SSID
        self.SSID_1 = SSID_1
        self.SSID_2 = SSID_2
        self.SSID_3 = SSID_3
        self.APs = {}

        # For each program, create a file 'TestbedAPNames.txt' in cmds folder and list the name of APs in that file
        # E.G., for 11n, create a file 'TestbedAPNames.txt' in cmds\WTS-11n folder with list of AP Names
        if os.path.exists(uccPath + TestbedAPList):
            APNames = open(uccPath + TestbedAPList, 'r')
            for l in APNames.readlines():
                n = l.rstrip("\n")
                self.APs.setdefault(n, testbedAP(n))
        else:
            print "No Testbed APs-"

        self.TSTA1 = TSTA1
        self.TSTA2 = TSTA2
        self.TSTA3 = TSTA3
        self.TSTA4 = TSTA4
        self.TSTA5 = TSTA5
        self.TestbedConfigCAPIFile = TestbedConfigCAPIFile
        self.DUTConfigCAPIFile = DUTConfigCAPIFile
        self.STAConfigCAPIFile = STAConfigCAPIFile
        self.WLANTestCAPIFile = WLANTestCAPIFile

    def __setattr__(self, attr, value):
        self.__dict__[attr] = value

    def formatNameUCC(self):
        return ("""define!$Channel!%s!\n
                 define!$Channel_1!%s!\n
                 define!$Channel_2!%s!\n
                 define!$Channel_3!%s!\n
                 define!$Band!%s!\n
                 define!$SSID!%s!\n
                 define!$SSID_1!%s!\n
                 define!$SSID_2!%s!\n
                 define!$SSID_3!%s!\n
                 define!$STA1!%s!\n
                 define!$STA2!%s!\n
                 define!$STA3!%s!\n
                 define!$TestbedConfigCAPIFile!%s!\n
                 define!$DUTConfigCAPIFile!%s!\n
                 define!$STAConfigCAPIFile!%s!\n
                 define!$WLANTestCAPIFile!%s!\n""" %
                (self.Channel,
                 self.Channel_1,
                 self.Channel_2,
                 self.Channel_3,
                 self.Band,
                 self.SSID,
                 self.SSID_1,
                 self.SSID_2,
                 self.SSID_3,
                 self.TSTA1,
                 self.TSTA2,
                 self.TSTA3,
                 self.TestbedConfigCAPIFile,
                 self.DUTConfigCAPIFile,
                 self.STAConfigCAPIFile,
                 self.WLANTestCAPIFile))
    def __str__(self):
        return ("""Channel = %s
                 Channel_1 = %s
                 Channel_2 = %s
                 Channel_3 = %s |
                 Band = %s |
                 SSID = %s
                 SSID_1 = %s
                 SSID_2 = %s
                 SSID_3 = %s  |
                 STA1 - %s
                 STA2 - %s
                 STA3 - %s
                 Testbed File - %s
                 DUTConfig File - %s
                 STAConfig File - %s
                 WLANTest File - %s""" %
                (self.Channel,
                 self.Channel_1,
                 self.Channel_2,
                 self.Channel_3,
                 self.Band,
                 self.SSID,
                 self.SSID_1,
                 self.SSID_2,
                 self.SSID_3,
                 self.TSTA1,
                 self.TSTA2,
                 self.TSTA3,
                 self.TestbedConfigCAPIFile,
                 self.DUTConfigCAPIFile,
                 self.STAConfigCAPIFile,
                 self.WLANTestCAPIFile))



def InitLog(FileName):
    """
    Initializes the log file

    Parameters
    ----------
    FileName : str

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    global LogFile
    LogFile = open(FileName, 'w')
    return 1

def LogMsg(Msg):
    """
    Writes the message to the log file

    Parameters
    ----------
    Msg : str

    Returns
    -------
    void
    """
    global LogFile
    LogFile.write("\n %s - %s" %(time.strftime("%H-%M-%S_%b-%d-%y", time.localtime()), Msg))
    return

def createUCCInitEnvFile(filename):
    """
    Creates the Init Environment file for UCC core and writes all the
    required variables from class object of envVariables

    Parameters
    ----------
    filename : str

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    LogMsg("Init file created --- > %s" % (uccPath+filename))
    uccInitFile = open(uccPath+filename, 'w')
    uccInitFile.write("# This is an auto generated file  - %s \n# For test case - %s\n#DO NOT modify this file manually \n\n" %(time.strftime("%b-%d-%y_%H:%M:%S", time.localtime()), dutInfoObject.TestCaseID))

    uccInitFile.write(testEnvVariables.formatNameUCC())
    for p in testEnvVariables.APs:
        uccInitFile.write(testEnvVariables.APs[p].formatAPUCC())

    uccInitFile.write(serverInfo.formatUCC())
    #Writing other variables
    for var in VarList:
        uccInitFile.write("\ndefine!$%s!%s!\n"%(var, VarList[var]))

    uccInitFile.write("#EOF")
    uccInitFile.close()
    return

def ReadDUTInfo(filename, TestCaseID):
    """
    This Function reads the DUT Info (Band, DUT Type, Category) from
    DUTInfo.txt file and load them into the class object of envVariables

    Parameters
    ----------
    filename : str
    TestCaseID : str

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    LogMsg("Read DUT Info Function")
    DUTFile = uccPath+filename
    dutInfoObject.__setattr__("DUTType", ReadMapFile(DUTFile, "DUTType", "!"))
    dutInfoObject.__setattr__("DUTBand", ReadMapFile(DUTFile, "DUTBand", "!"))
    dutInfoObject.__setattr__("DUTCategory", ReadMapFile(DUTFile, "DUTCategory", "!"))
    dutInfoObject.__setattr__("WEP", ReadMapFile(DUTFile, "WEP", "!"))
    dutInfoObject.__setattr__("PreAuth", ReadMapFile(DUTFile, "PreAuth", "!"))
    dutInfoObject.__setattr__("_11h", ReadMapFile(DUTFile, "11h", "!"))
    dutInfoObject.__setattr__("SupportedChannelWidth", ReadMapFile(DUTFile, "SupportedChannelWidth", "!"))
    dutInfoObject.__setattr__("Streams", ReadMapFile(DUTFile, "Streams", "!"))
    dutInfoObject.__setattr__("Greenfield", ReadMapFile(DUTFile, "Greenfield", "!"))
    dutInfoObject.__setattr__("SGI20", ReadMapFile(DUTFile, "SGI20", "!"))
    dutInfoObject.__setattr__("SGI40", ReadMapFile(DUTFile, "SGI40", "!"))
    dutInfoObject.__setattr__("RIFS_TX", ReadMapFile(DUTFile, "RIFS_TX", "!"))
    dutInfoObject.__setattr__("Coexistence_2040", ReadMapFile(DUTFile, "Coexistence_2040", "!"))
    dutInfoObject.__setattr__("STBC_RX", ReadMapFile(DUTFile, "STBC_RX", "!"))
    dutInfoObject.__setattr__("STBC_TX", ReadMapFile(DUTFile, "STBC_TX", "!"))
    dutInfoObject.__setattr__("MCS32", ReadMapFile(DUTFile, "MCS32", "!"))
    dutInfoObject.__setattr__("WTSSupport", ReadMapFile(DUTFile, "WTS_ControlAgent_Support", "!"))
    dutInfoObject.__setattr__("OBSS", ReadMapFile(DUTFile, "OBSS", "!"))
    dutInfoObject.__setattr__("AMPDU_TX", ReadMapFile(DUTFile, "AMPDU_TX", "!"))
    dutInfoObject.__setattr__("AP_Concurrent", ReadMapFile(DUTFile, "AP_Concurrent", "!"))
    dutInfoObject.__setattr__("_11d", ReadMapFile(DUTFile, "11d", "!"))
    dutInfoObject.__setattr__("STAUT_PM", ReadMapFile(DUTFile, "STAUT_PM", "!"))
    dutInfoObject.__setattr__("Open_Mode", ReadMapFile(DUTFile, "Open_Mode", "!"))
    dutInfoObject.__setattr__("Mixedmode_WPA2WPA", ReadMapFile(DUTFile, "Mixedmode_WPA2WPA", "!"))
    dutInfoObject.__setattr__("PMF_OOB", ReadMapFile(DUTFile, "PMF_OOB", "!"))

    #EAP Methods
    dutInfoObject.__setattr__("TLS", ReadMapFile(DUTFile, "TLS", "!"))
    dutInfoObject.__setattr__("TTLS", ReadMapFile(DUTFile, "TTLS", "!"))
    dutInfoObject.__setattr__("PEAP0", ReadMapFile(DUTFile, "PEAP0", "!"))
    dutInfoObject.__setattr__("PEAP1", ReadMapFile(DUTFile, "PEAP1", "!"))
    dutInfoObject.__setattr__("FAST", ReadMapFile(DUTFile, "FAST", "!"))
    dutInfoObject.__setattr__("SIM", ReadMapFile(DUTFile, "SIM", "!"))
    dutInfoObject.__setattr__("AKA", ReadMapFile(DUTFile, "AKA", "!"))
    dutInfoObject.__setattr__("AKA'", ReadMapFile(DUTFile, "AKA'", "!"))
    dutInfoObject.__setattr__("PWD", ReadMapFile(DUTFile, "PWD", "!"))

    #VE Specific
    dutInfoObject.__setattr__("BSS_Trans_Query_Support", ReadMapFile(DUTFile, "BSS_Trans_Query_Support", "!"))
    dutInfoObject.__setattr__("TSM_Support", ReadMapFile(DUTFile, "TSM_Support", "!"))

    #TDLS Specific
    dutInfoObject.__setattr__("TDLSDiscReq", ReadMapFile(DUTFile, "DiscoveryRequest_Support", "!"))
    dutInfoObject.__setattr__("PUSleepSTA", ReadMapFile(DUTFile, "PUAPSDSleepSTA_Support", "!"))

    dutInfoObject.__setattr__("TestCaseID", TestCaseID)

    #Default method is TTLS
    dutInfoObject.__setattr__("DUTEAPMethod", "TTLS")

    #ASD device testing
    dutInfoObject.__setattr__("ASD", ReadMapFile(DUTFile, "ASD", "!"))

    for EAP in EAPList:
        Ret = ReadMapFile(DUTFile, EAP, "!")
        if int(Ret) == 1:
            dutInfoObject.__setattr__("DUTEAPMethod", EAP)
            break
    if TestCaseID == "WPA2-5.8" and dutInfoObject._11h == "0":
        LogMsg("11h not supported by DUT; Skipping the Test.")
        VarList.setdefault("TestNA", "11h not supported by DUT; Skipping the Test.")
    if TestCaseID == "WPA2-5.5.1" and dutInfoObject.PreAuth == "0":
        LogMsg("Pre Authentication not supported by DUT; Skipping the Test.")
        VarList.setdefault("TestNA", "Pre Authentication not supported by DUT; Skipping the Test.")
    if "N-4.2" in TestCaseID or "N-ExA" in TestCaseID:
        VarList.setdefault("APUT_state", "on")

    if "N-5.2" in TestCaseID or "N-ExS" in TestCaseID:
        VarList.setdefault("APUT_state", "off")

    if (ProgName == "P2P" or
            ProgName == "TDLS" or
            ProgName == "PMF" or
            ProgName == "HS2" or
            ProgName == "WFD" or
            ProgName == "WFDS" or
            ProgName == "VHT" or
            ProgName == "HS2-R2" or
            ProgName == "WMMPS" or
            ProgName == "NAN"):
        fFile = open(DUTFeatureInfoFile, "w")
        T = HTML.Table(col_width=['70%', '30%'])
        R1 = HTML.TableRow(cells=['Optional Feature', 'DUT Support'], bgcolor="Gray", header="True")
        T.rows.append(R1)

        if (ProgName == "P2P" or
                ProgName == "TDLS" or
                ProgName == "HS2" or
                ProgName == "WFD" or
                ProgName == "WFDS" or
                ProgName == "HS2-R2" or
                ProgName == "NAN"):
            P2PVarList = ReadAllMapFile(DUTFile, ProgName, "!")
            if P2PVarList != -1:
                P2PVarList = P2PVarList.split('!')
                LogMsg("P2P Supported Features = %s" % P2PVarList)
                for var in P2PVarList:
                    if var != "":
                        v = var.split(',')
                        VarList.setdefault(v[0], v[1])
                        featureSupport = find_TestcaseInfo_Level1(TestCaseID, v[0])
                        if featureSupport != "":
                            LogMsg("%s-%s" % (featureSupport, v[1]))
                            if featureSupport != v[1]:
                                LogMsg("DUT does not support the feature")
                                VarList.setdefault("TestNA", "DUT does not support the feature")

                        if v[1] == "0":
                            dis = "No"
                        elif v[1] == "1":
                            dis = "Yes"
                        else:
                            dis = v[1]
                        if "DUT_" not in v[0]:
                            T.rows.append([v[0], dis])

        else:
            ProgVarList = ReadAllMapFile(DUTFile, ProgName, "!")
            if ProgVarList != -1:
                ProgVarList = ProgVarList.split('!')
                LogMsg("%s Supported Features = %s" % (ProgName, ProgVarList))
                checkFeatureFlag = find_TestcaseInfo_Level1(TestCaseID, "checkFeatureFlag")
                LogMsg("checkFeatureFlag = %s" % checkFeatureFlag)
                for var in ProgVarList:
                    if var != "":
                        v = var.split(',')
                        VarList.setdefault(v[0], v[1])
                        featureSupport = find_TestcaseInfo_Level1(TestCaseID, v[0])
                        #LogMsg("Feature Support = %s" % featureSupport)
                        if checkFeatureFlag == v[0]:
                            LogMsg("%s-%s"%(checkFeatureFlag, v[1]))
                            if v[1] != "1":
                                LogMsg("DUT does not support the feature")
                                VarList.setdefault("TestNA", "DUT does not support the feature")

                        if v[1] == "0":
                            dis = "No"
                        elif v[1] == "1":
                            dis = "Yes"
                        else:
                            dis = v[1]
                        if "DUT_" not in v[0]:
                            T.rows.append([v[0], dis])

        htmlcode = str(T)
        fFile.write(htmlcode)
        fFile.write('<p>')

    return 1

def GetCAPIFileNames(TestCaseID):
    """
    Gets the CAPI file name for Testbed Config, DUT Config for given
    testcaseID and load them into the class object of testEnvVariables

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    global ProgName
    setattr(testEnvVariables, "TestbedConfigCAPIFile", find_TestbedFile(TestCaseID))

    if (int(dutInfoObject.WTSSupport) == 0 and
            ProgName != "P2P" and
            ProgName != "HS2" and
            ProgName != "WFD" and
            ProgName != "WFDS" and
            ProgName != "HS2-R2" and
            ProgName != "WMMPS" and
            ProgName != "NAN"):
        setattr(testEnvVariables, "DUTConfigCAPIFile", "NoWTSSupportMsg.txt")
        VarList.setdefault("WTSMsg", "Configure DUT for Testcase = -- %s --" % TestCaseID)
        VarList.setdefault("DUT_WTS_VERSION", "NA")

    else:
        setattr(testEnvVariables, "DUTConfigCAPIFile", find_STAFile(TestCaseID, "DUTFile"))
        VarList.setdefault("WTSMsg", "")
    setattr(testEnvVariables, "STAConfigCAPIFile", find_STAFile(TestCaseID, "STAFile"))
    if ProgName == "PMF":
        setattr(testEnvVariables, "WLANTestCAPIFile", find_WLANTestFile(TestCaseID, "WLanTestFile"))

    return 1

def GetServerSupplicantInfo(TestCaseID):
    """
    Gets the RADIUS Server Information and
    Supplicant name for given test and load them into Env file

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    if dutInfoObject.DUTEAPMethod == "TLS":
        tag = "TLS"
    else:
        tag = "Other"

    serverName = find_Server(TestCaseID, tag)

    VarList.setdefault("RadiusServerName", serverName)

    if dutInfoObject.DUTCategory != -1:
        suppName = find_Supplicant(TestCaseID, "DUT", dutInfoObject.DUTCategory.lower())
        setattr(serverInfo, "Supplicant", suppName)
        staSuppName = find_Supplicant(TestCaseID, "STA", "c2")
        setattr(serverInfo, "STASupplicant", staSuppName)

    setattr(serverInfo, "name", serverName)
    setattr(serverInfo, "IP", ReadMapFile(uccPath+RADIUSServer, "%s%s"%(serverName, "IPAddress"), "!"))
    setattr(serverInfo, "Port", ReadMapFile(uccPath+RADIUSServer, "%s%s"%(serverName, "Port"), "!"))
    setattr(serverInfo, "Password", ReadMapFile(uccPath+RADIUSServer, "%s%s"%(serverName, "SharedSecret"), "!"))

def GetSnifferInfo(TestCaseID):
    """
    Gets the value set in init file and sets sniffer default
    to start/stop or disable

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    void
    """
    sniffer_enable = ReadMapFile(uccPath+InitFile, "sniffer_enable", "!")
    VarList.setdefault("SnifferFileName", "%s_%s" % ("SnifferTrace", TestCaseID))
    if sniffer_enable == '1':
        VarList.setdefault("StartSniffer", "Sniffer-Start.txt")
        VarList.setdefault("StopSniffer", "Sniffer-Stop.txt")
    else:
        VarList.setdefault("StartSniffer", "Sniffer-Disable.txt")
        VarList.setdefault("StopSniffer", "Sniffer-Disable.txt")

def GetTestbedDeviceInfo(TestCaseID):
    """
    Reads the TestbedDevice Info(Name of TestbedAPs,STAs) for given
    testcaseID and loads them into the class object of testEnvVariables

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    global ProgName, qual, QualAP, QualSTA
    iCount = 1
    LogMsg("Read Testbed Device Info Function")
    # Searching Band
    FindBandChannel(TestCaseID)

    # Searching APs
    APs = find_TestcaseInfo_Level1(TestCaseID, "AP").split(",")

    if qual:
        APs = QualAP.split(",")
        LogMsg("Qualification Mode - APs-[%s]" % APs)

    for AP in APs:
        if AP == "":
            continue
        AddTestCaseAP(AP, iCount)
        if int(testEnvVariables.Channel) > 35:
            VarList.setdefault("bssid", ("$%sAPMACAddress_5G" % AP))
            VarList.setdefault(("AP%sMACAddress"%iCount), ("$%sAPMACAddress_5G" % AP))
            VarList.setdefault(("AP%sMACAddress2"%iCount), ("$%sAPMACAddress2_5G" % AP))
            VarList.setdefault(("AP%sMACAddress3"%iCount), ("$%sAPMACAddress3_5G" % AP))
        else:
            VarList.setdefault("bssid", ("$%sAPMACAddress_24G" % AP))
            VarList.setdefault(("AP%sMACAddress"%iCount), ("$%sAPMACAddress_24G" % AP))
            VarList.setdefault(("AP%sMACAddress2"%iCount), ("$%sAPMACAddress2_24G" % AP))
            VarList.setdefault(("AP%sMACAddress3"%iCount), ("$%sAPMACAddress3_24G" % AP))
        VarList.setdefault("AP%s_control_agent" %(iCount), "wfa_control_agent_%s_ap" % (AP.lower()))
        iCount = iCount+1

    for p in testEnvVariables.APs:
        if testEnvVariables.APs[p].Number == 0:
            testEnvVariables.APs[p].Number = iCount
            iCount = iCount+1
        LogMsg(testEnvVariables.APs[p])

    iCount = 1
    # Searching STAs
    STAs = find_TestcaseInfo_Level1(TestCaseID, "STA").split(",")
    if qual:
        STAs = QualSTA.split(",")
        LogMsg("Qualification Mode - STAs-[%s]" % STAs)


    for STA in STAs:
        setattr(testEnvVariables, "TSTA%s" % (iCount), STA)
        VarList.setdefault("STA%s_control_agent" % (iCount), "wfa_control_agent_%s_sta" % (STA.lower()))
        VarList.setdefault("STA%s_wireless_ip" % iCount, ReadMapFile(uccPath+InitFile, "%s_sta_wireless_ip" % STA.lower(), "!"))

        if ProgName == "TDLS":
            VarList.setdefault("STA%s_wireless_ip2" % iCount, ReadMapFile(uccPath+InitFile, "%s_sta_wireless_ip2" % STA.lower(), "!"))
            VarList.setdefault("STA%s_wireless_ip3" % iCount, ReadMapFile(uccPath+InitFile, "%s_sta_wireless_ip3" % STA.lower(), "!"))
        if ProgName == "HS2-R2":
            VarList.setdefault("STA%s_wireless_ipv6" % iCount, ReadMapFile(uccPath+InitFile, "%s_sta_wireless_ipv6" % STA.lower(), "!"))
        VarList.setdefault("STA%s_MACAddress" % iCount, ("$%sSTAMACAddress"%STA))

        iCount = iCount+1
    # Searching SSID
    iCount = 1

    setattr(testEnvVariables, "SSID", find_TestcaseInfo_Level1(TestCaseID, "SSID"))
    setattr(testEnvVariables, "SSID_1", find_TestcaseInfo_Level1(TestCaseID, "SSID"))
    SSIDs = find_TestcaseInfo_Level1(TestCaseID, "SSID").split(" ")

    for SSID in SSIDs:
        if len(SSIDs) > 1:
            setattr(testEnvVariables, "SSID_%s"%(iCount), SSID)
            iCount = iCount + 1

    if ProgName != "P2P" and ProgName != "WFD" and ProgName != "WFDS" and ProgName != "NAN":
        FindBandChannel(TestCaseID)

    return 1

def GetSubscriptionServerInfo(TestCaseID):
    """
    Reads the TestbedDevice Info(Name of TestbedAPs,STAs) for given testcaseID and
    load them into the class object of testEnvVariables

    Parameters
    ----------
    TestcaseID : str
    index : str
    delim : str
        occurs nth instance of index

    Returns
    -------
    PASS(1)/Fail(-1) : int
    """

    global ProgName
    iCount = 1
    LogMsg("Read Testbed Subscription Server Info Function")

    if dutInfoObject.DUTEAPMethod == "TLS":
        tag = "TLS"
    else:
        tag = "Other"

    subsServerName = find_SubsServer(TestCaseID, tag)

    setattr(testEnvVariables, "SS%s" % (iCount), subsServerName)
    VarList.setdefault("SS%s_control_agent" %(iCount), "wfa_control_agent_%s_osu" % (subsServerName.lower()))
    VarList.setdefault("SS%s" % (iCount), "%s" % (subsServerName.lower()))

    return 1

def ReadMapFile(filename, index, delim):
    """
    Reads the MapFile of format
    Param1<delim>value1<delim>Param2<delim>value2<delim>
    based on given Index,Delim and returns the value.

    Parameters
    ----------
    filename : str
    index : str
    delim : str
        occurs nth instance of index

    Returns
    -------
    Value/Fail(-1) : str
    """
    iCount = 1
    returnString = -1
    if os.path.exists(filename) == 0:
        LogMsg("File not found - %s" % filename)
        return -1
    LogMsg("ReadMapFile ------- %s-%s-%s" % (filename, index, delim))
    fileP = open(filename, 'r')
    for l in fileP.readlines():
        if not l: break
        line = l.split('#')
        command = line[0].split(delim)
        if index in command:
            returnString = command[command.index(index)+1]
            break

    fileP.close()
    return returnString

def ReadAllMapFile(filename, index, delim):
    """
    Reads all the MapFile of format
    Param1<delim>value1<delim>Param2<delim>value2<delim>
    based on given Index,Delim and returns the value.

    Parameters
    ----------
    filename : str
    index : str
    delim : str
        occurs nth instance of index

    Returns
    -------
    Value/Fail(-1) : str
    """
    iCount = 1
    returnString = -1
    if os.path.exists(filename) == 0:
        LogMsg("File not found - %s" % filename)
        return -1
    LogMsg("Read All MapFile ------- %s-%s-%s" % (filename, index, delim))
    fileP = open(filename, 'r')
    for l in fileP.readlines():
        if not l: break
        line = l.split('#')
        if delim in line[0]:
            command = line[0].split(delim)
            if returnString == -1:
                returnString = "%s,%s%s" % (command[0], command[1], delim)
            else:
                returnString = "%s%s,%s%s" % (returnString, command[0], command[1], delim)

    fileP.close()

    return returnString

def GetAPPortNumber(APName):
    """
    Gets the power switch port number for given AP

    Parameters
    ----------
    APName : str

    Returns
    -------
    Port Number/Fail(-1) : str
    """
    return ReadMapFile(uccPath+TestbedAPFile, "%s%s" % (APName, "APPowerSwitchPort"), "!")

def GetAPIPAddress(APName):
    """
    Gets the IP Address of given AP

    Parameters
    ----------
    APName : str

    Returns
    -------
    IP Address/Fail(-1) : str
    """
    if ReadMapFile(uccPath+TestbedAPFile, "%s%s" % (APName, "APIPAddress"), "!") != -1:
        return ReadMapFile(uccPath+TestbedAPFile, "%s%s" % (APName, "APIPAddress"), "!").split(' ')[0]
    else:
        return -1

def AddTestCaseAP(APName, pos):
    """
    Gets the IP Address of given AP

    Parameters
    ----------
    APName : str
    pos : int
        position in list

    Returns
    -------
    Pass(1)/Fail(-1) : int
    """
    try:
        setattr(testEnvVariables.APs[APName], "Number", pos)
        setattr(testEnvVariables.APs[APName], "State", "On")
        return 1
    except:
        LogMsg("Invalid AP Name")
        return -1

def GetOtherVariables(TID):
    global dutInfoObject
    if getattr(dutInfoObject, "ASD") != "0":
        find_ASD_threshold_values(TID, "Throughputs_ASD")
    else:
        find_throughput_values(TID, "Throughputs")
    cw = find_TestcaseInfo_Level1(TID, "APChannelWidth")
    LogMsg("Channel Width = %s" % cw)
    if cw != "":
        VarList.setdefault("APChannelWidth", cw)

    if ProgName == "PMF":
        #Security get parameters
        findSecurity(TID, "Security")
        #PMF Capability get parameters
        findPMFCap(TID, "PMFCapability")
        if "PMF-4" in TID:
            VarList.setdefault("sender", "sta")

        if "PMF-5" in TID:
            VarList.setdefault("sender", "ap")
        #WLAN Tester for frame injection-sniffing
        cond = find_TestcaseInfo_Level1(TID, "WFA_Tester")
        VarList.setdefault("WFA_Tester", cond)
        VarList.setdefault("TBAPConfigServer", "TestbedAPConfigServer")
        VarList.setdefault("WFA_Sniffer", "wfa_sniffer")
        VarList.setdefault("WFA_TEST_control_agent", "wfa_test_control_agent")

    combo = find_TestcaseInfo_Level1(TID, "QualCombinationInfo")
    LogMsg("Combination Info = %s" % combo)
    if combo != "":
        VarList.setdefault("QualCombinationInfo", combo)
    # MIMO Related Checks
    VarList.setdefault("ChannelWidth_Value", dutInfoObject.SupportedChannelWidth)
    VarList.setdefault("GreenField_Value", dutInfoObject.Greenfield)
    VarList.setdefault("SGI20_Value", dutInfoObject.SGI20)
    VarList.setdefault("SGI40_Value", dutInfoObject.SGI40)
    VarList.setdefault("MCS_Set_Value", dutInfoObject.Streams)
    VarList.setdefault("MCS32_Value", dutInfoObject.MCS32)
    VarList.setdefault("STBC_RX_Value", dutInfoObject.STBC_RX)
    VarList.setdefault("STBC_TX_Value", dutInfoObject.STBC_TX)

    VarList.setdefault("STAUT_PM", dutInfoObject.STAUT_PM)
    VarList.setdefault("BSS_Trans_Query_Support", dutInfoObject.BSS_Trans_Query_Support)
    VarList.setdefault("TSM_Support", dutInfoObject.TSM_Support)
    VarList.setdefault("Streams", "%sSS" % dutInfoObject.Streams)
    VarList.setdefault("Open_Mode", dutInfoObject.Open_Mode)
    VarList.setdefault("Mixedmode_WPA2WPA", dutInfoObject.Mixedmode_WPA2WPA)
    VarList.setdefault("PMF_OOB", dutInfoObject.PMF_OOB)
    VarList.setdefault("ASD", dutInfoObject.ASD)

    #Check for 11n Optional Test Cases Flag
    FindCheckFlag11n(TID)

    #TDLS specific conditional step
    cond = find_TestcaseInfo_Level1(TID, "ConditionalStep-DiscReq")
    if cond != "":
        if dutInfoObject.TDLSDiscReq == "1":
            VarList.setdefault("ConditionalStep-DiscReq", cond)
        else:
            VarList.setdefault("ConditionalStep-DiscReq", "DoNothing.txt")


    cond = find_TestcaseInfo_Level1(TID, "ConditionalStep-PUSleep")
    if cond != "":
        if dutInfoObject.PUSleepSTA == "1":
            VarList.setdefault("ConditionalStep-PUSleep", cond)
        else:
            VarList.setdefault("ConditionalStep-PUSleep", "DoNothing.txt")

    #Check for conditional step
    cond = find_TestcaseInfo_Level1(TID, "ConditionalStep-Aonly-40")
    if cond != "":
        if re.search('A', dutInfoObject.DUTBand) and dutInfoObject.SupportedChannelWidth == "40":
            VarList.setdefault("ConditionalStep-Aonly-40", cond)
        else:
            VarList.setdefault("ConditionalStep-Aonly-40", "DoNothing.txt")

    cond = find_TestcaseInfo_Level1(TID, "ConditionalStep-2SS")
    if cond != "":
        if dutInfoObject.Streams == "3" or dutInfoObject.Streams == "2":
            VarList.setdefault("ConditionalStep-2SS", cond)
        else:
            VarList.setdefault("ConditionalStep-2SS", "DoNothing.txt")
    cond = find_TestcaseInfo_Level1(TID, "ConditionalStep-3SS")
    if cond != "":
        if dutInfoObject.Streams == "3":
            VarList.setdefault("ConditionalStep-3SS", cond)
        else:
            VarList.setdefault("ConditionalStep-3SS", "DoNothing.txt")
    #Check for Special Stream
    cond = find_TestcaseInfo_Level1(TID, "TX-SS")
    if cond != "":
        VarList.setdefault("TX-SS", cond)
    #Check for Special Stream
    cond = find_TestcaseInfo_Level1(TID, "RX-SS")
    if cond != "":
        VarList.setdefault("RX-SS", cond)
    AddVariableInit(TID, "STA_Frag", "2346")
    AddVariableInit(TID, "STA_Legacy_PS", "off")
    AddVariableInit(TID, "STA2_Legacy_PS", "off")
    AddVariableInit(TID, "HTFlag", "on")
    AddVariableInit(TID, "WMMFlag", "off")
    AddVariableInit(TID, "CheckFlag11n", "off")
    #TDLS specific
    AddVariableInit(TID, "CheckFlag11n", "off")
    AddVariableInit(TID, "Offch", "44")
    AddVariableInit(TID, "Offchwidth", "20")
    VarList.setdefault("DUTSupportedCW", dutInfoObject.SupportedChannelWidth)
    find_stream_threshold_values(TID, "WMMStreamThreshold")

def AddVariableInit(TID, VarName, VarDefault):
    VarValue = find_TestcaseInfo_Level1(TID, VarName)
    if VarValue != "":
        VarList.setdefault(VarName, VarValue)
    else:
        VarList.setdefault(VarName, VarDefault)

def FindCheckFlag11n(TestCaseID):
    """
    Finds the 11n optional test case flags and decides whether
    test case should be executed or not

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    Pass/Fail : str
    """
    global dutInfoObject
    chkFlag = find_TestcaseInfo_Level1(TestCaseID, "CheckFlag11n")
    LogMsg("%s is check flag" % chkFlag)
    if chkFlag == "":
        LogMsg("Options Check for 11n not required for test case %s" % TestCaseID)
    elif getattr(dutInfoObject, chkFlag) == "0":
        LogMsg("%s not supported by DUT; Skipping the Test." % chkFlag)
        VarList.setdefault("TestNA", "%s not supported by DUT; Skipping the Test. Re-Check the file \"DUTInfo.txt\"" % chkFlag)
    else:
        LogMsg("%s is supported by DUT; Make sure [%s] is enabled" % (chkFlag, chkFlag))
        for EAP in EAPList:
            if EAP == chkFlag:
                dutInfoObject.__setattr__("DUTEAPMethod", EAP)
                VarList.setdefault("DUTEAPMethod", dutInfoObject.DUTEAPMethod)
                LogMsg("%s EAP method is supported by DUT" % chkFlag)
                break

def AddWPSConfigMethod(TID, VarName, VarValue):
    DUTFile = uccPath+DUTInfoFile
    dut_wps_support = ReadMapFile(DUTFile, VarValue, "!")
    if int(dut_wps_support) != 1:
        for m in WPSConfigList:
            if int(ReadMapFile(DUTFile, m, "!")) == 1:
                VarValue = m
                break
    VarList.setdefault(VarName, VarValue)

# For P2P Parameters
def GetP2PVariables(TID):
    global ProgName
    oper_chn = -1
    list_chn = -1
    intent_val = -1
    serv_pref = -1

    if ProgName == "WFD":
        FindBandOperChannel(TID)
    else:
        oper_chn = find_TestcaseInfo_Level1(TID, "OperatingChannel")
        if oper_chn != "":
            VarList.setdefault("OPER_CHN", oper_chn)

    if ProgName == "WFDS":
        serv_pref = find_TestcaseInfo_Level1(TID, "ServicePref")
        if serv_pref != "":
            VarList.setdefault("WfdsTestServicePref", serv_pref)

    list_chn = find_TestcaseInfo_Level1(TID, "ListenChannel")
    if list_chn != "":
        VarList.setdefault("LISTEN_CHN", list_chn)
    intent_val = find_TestcaseInfo_Level1(TID, "IntentValue_DUT")
    if intent_val != "":
        VarList.setdefault("INTENT_VAL_DUT", intent_val)

    intent_val = find_TestcaseInfo_Level1(TID, "IntentValue_STA")
    if intent_val != "":
        VarList.setdefault("INTENT_VAL_STA", intent_val)

    AddVariableInit(TID, "PERSISTENT", 0)
    AddVariableInit(TID, "SERDISC", 0)

    wps_method = find_TestcaseInfo_Level1(TID, "WPS_Config")
    if wps_method != "":
        AddWPSConfigMethod(TID, "DUT_WPS_METHOD", wps_method)

def FindBandOperChannel(TestCaseID):
    """
    Finds the band and Operating channel required for given test case
    and puts them into testEnvVariables

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    testOperChannel : int
    """
    global ProgName
    LoadBandSelection()
    band = -1
    operchannel1 = []
    testOperChannel = []

    Band = find_TestcaseInfo_Level1(TestCaseID, "Band")
    if Band == "A/G":
        Band = "AG"
    if Band == "A/G/N":
        Band = "AGN"
    if Band == "G/N":
        Band = "GN"
    if Band == "A/N":
        Band = "AN"
    if Band == "A/B":
        Band = "AB"

    try:
        band = bandSelectionList["%s:%s" % (Band, dutInfoObject.DUTBand)]
    except KeyError:
        LogMsg("Invalid band information %s" % Band)

    operChannel1 = find_TestcaseInfo_Level1(TestCaseID, "OperatingChannel").split(",")
    if operChannel1[0] == "":
        return

    for chan in range(0, len(operChannel1)):
        operchannel1.append(operChannel1[chan].split("/"))
        LogMsg("Test case Operating Channel %s %s" % (operchannel1[chan][0], operchannel1[chan][1]))

        if band != "11a" and band != "11na" and band != -1:
            testOperChannel.append(operchannel1[chan][1])
        elif band != -1:
            testOperChannel.append(operchannel1[chan][0])
        if band == -1 and ProgName != "P2P":
            VarList.setdefault("TestNA", "Invalid Band. DUT Capable Band is [%s] and Test requires [%s]" % (dutInfoObject.DUTBand, Band))

    LogMsg("Test execution in %s Band and Operating Channel %s" % (band, testOperChannel))

    setattr(testEnvVariables, "Band", band)
    iCount = 1
    for chan in testOperChannel:
        if len(testOperChannel) > 1:
            VarList.setdefault("OPER_CHN_%s"%(iCount), chan)
            iCount = iCount + 1
            VarList.setdefault("OPER_CHN", OPER_CHN_1)
        else:
            VarList.setdefault("OPER_CHN", chan)

    return testOperChannel

def FindBandChannel(TestCaseID):
    """
    Finds the band and channel required for given test case
    and puts them into testEnvVariables

    Parameters
    ----------
    TestCaseID : str

    Returns
    -------
    testChannel : int
    """
    global ProgName
    LoadBandSelection()
    band = -1
    channel1 = []
    testChannel = []

    DUTBAND = "%s" % dutInfoObject.DUTBand
    Band = find_TestcaseInfo_Level1(TestCaseID, "Band")
    if Band == "A/G":
        Band = "AG"
    if Band == "A/G/N":
        Band = "AGN"
    if Band == "G/N":
        Band = "GN"
    if Band == "A/N":
        Band = "AN"
    if Band == "A/B":
        Band = "AB"
    if Band == "AC":
        Band = "AC"

    try:
        band = bandSelectionList["%s:%s" % (Band, dutInfoObject.DUTBand)]
    except KeyError:
        LogMsg("Invalid band information %s" % Band)

    Channel1 = find_TestcaseInfo_Level1(TestCaseID, "Channel").split(",")
    if Channel1[0] == "":
        return

    for chan in range(0, len(Channel1)):
        channel1.append(Channel1[chan].split("/"))
        LogMsg("Test case Channel %s %s" % (channel1[chan][0], channel1[chan][1]))

        if band != "11a" and band != "11na" and band != "11ac" and band != -1:
            testChannel.append(channel1[chan][1])
        elif band != -1:
            testChannel.append(channel1[chan][0])
        if band == -1 and ProgName != "P2P":
            VarList.setdefault("TestNA", "Invalid Band. DUT Capable Band is [%s] and Test requires [%s]" % (dutInfoObject.DUTBand, Band))

    LogMsg("Test execution in %s Band and Channel %s" % (band, testChannel))

    if band == "11a" or band == "11g":
        VarList.setdefault("STAPHY", "ag")
    elif band == "11b":
        VarList.setdefault("STAPHY", "b")
    elif band == "11na" or band == "11ng":
        VarList.setdefault("STAPHY", "11n")
    elif band == "11ac":
        VarList.setdefault("STAPHY", "11ac")

    # APUT Band for 11n
    if int(testChannel[0]) > 35:
        if band == "11ac":
            VarList.setdefault("APUT_Band", "11ac")
            VarList.setdefault("STAUT_Band", "11ac")
            VarList.setdefault("Band_Legacy", "11a")
            VarList.setdefault("Band_LegacyN", "11na")
        else:
            if DUTBAND == "AN" or DUTBAND == "ABGN":
                VarList.setdefault("APUT_Band", "11na")
                VarList.setdefault("STAUT_Band", "11na")
                VarList.setdefault("Band_Legacy", "11a")
            elif DUTBAND == "A" or DUTBAND == "ABG":
                VarList.setdefault("APUT_Band", "11a")
                VarList.setdefault("STAUT_Band", "11a")
                VarList.setdefault("Band_Legacy", "11a")
    else:
        if DUTBAND == "GN" or DUTBAND == "ABGN":
            VarList.setdefault("APUT_Band", "11ng")
            VarList.setdefault("STAUT_Band", "11ng")
            VarList.setdefault("Band_Legacy", "11g")
        elif DUTBAND == "BG" or DUTBAND == "ABG":
            VarList.setdefault("APUT_Band", "11g")
            VarList.setdefault("STAUT_Band", "11g")
            VarList.setdefault("Band_Legacy", "11g")
        elif DUTBAND == "B":
            VarList.setdefault("APUT_Band", "11b")
            VarList.setdefault("STAUT_Band", "11b")
            VarList.setdefault("Band_Legacy", "11b")

    setattr(testEnvVariables, "Band", band)
    iCount = 1
    for chan in testChannel:
        if len(testChannel) > 1:
            setattr(testEnvVariables, "Channel_%s" % (iCount), chan)
            iCount = iCount + 1
            setattr(testEnvVariables, "Channel", testEnvVariables.Channel_1)
        else:
            setattr(testEnvVariables, "Channel", chan)
        LogMsg("%s %s %s" %(testEnvVariables.Channel_1, testEnvVariables.Channel_2, testEnvVariables.Channel_3))

    return testChannel

def LoadBandSelection():
    """Init band selection array"""
    #Testcase Band : DUT Band
    #DUT Mode BG
    bandSelectionList.setdefault("A:BG", "11g")
    bandSelectionList.setdefault("B:BG", "11b")
    bandSelectionList.setdefault("G:BG", "11g")
    bandSelectionList.setdefault("AG:BG", "11g")
    bandSelectionList.setdefault("AB:BG", "11b")

    #DUT Mode A only
    bandSelectionList.setdefault("A:A", "11a")
    bandSelectionList.setdefault("B:A", "11a")
    bandSelectionList.setdefault("G:A", "11a")
    bandSelectionList.setdefault("AG:A", "11a")
    bandSelectionList.setdefault("AB:A", "11a")

    #DUT Mode ABG
    bandSelectionList.setdefault("A:ABG", "11a")
    bandSelectionList.setdefault("B:ABG", "11b")
    bandSelectionList.setdefault("G:ABG", "11g")
    bandSelectionList.setdefault("AG:ABG", "11a")
    bandSelectionList.setdefault("AB:ABG", "11a")

    #DUT Mode b only
    bandSelectionList.setdefault("A:B", "11g")
    bandSelectionList.setdefault("B:B", "11b")
    bandSelectionList.setdefault("G:B", "11g")
    bandSelectionList.setdefault("AG:B", "11g")
    bandSelectionList.setdefault("AB:B", "11b")

    #DUT Mode G only
    bandSelectionList.setdefault("A:G", "11g")
    bandSelectionList.setdefault("B:G", "11g")
    bandSelectionList.setdefault("G:G", "11g")
    bandSelectionList.setdefault("AG:G", "11g")
    bandSelectionList.setdefault("AB:G", "11b")

    # DUT mode A and b only
    bandSelectionList.setdefault("A:AB", "11a")
    bandSelectionList.setdefault("B:AB", "11b")
    bandSelectionList.setdefault("G:AB", "11b")
    bandSelectionList.setdefault("AG:AB", "11b")
    bandSelectionList.setdefault("AB:AB", "11a")

    #DUT mode ABGN
    bandSelectionList.setdefault("A:ABGN", "11a")
    bandSelectionList.setdefault("B:ABGN", "11b")
    bandSelectionList.setdefault("G:ABGN", "11g")
    bandSelectionList.setdefault("AG:ABGN", "11a")
    bandSelectionList.setdefault("AB:ABGN", "11a")

    bandSelectionList.setdefault("AGN:ABGN", "11na")
    bandSelectionList.setdefault("AN:ABGN", "11na")
    bandSelectionList.setdefault("GN:ABGN", "11ng")

    #DUT mode GN
    bandSelectionList.setdefault("A:GN", "11g")
    bandSelectionList.setdefault("B:GN", "11b")
    bandSelectionList.setdefault("G:GN", "11g")
    bandSelectionList.setdefault("AG:GN", "11g")
    bandSelectionList.setdefault("AB:GN", "11b")

    bandSelectionList.setdefault("AGN:GN", "11ng")
    bandSelectionList.setdefault("AN:GN", "11ng")
    bandSelectionList.setdefault("GN:GN", "11ng")

    #DUT mode AN
    bandSelectionList.setdefault("A:AN", "11a")
    bandSelectionList.setdefault("B:AN", "11a")
    bandSelectionList.setdefault("G:AN", "11a")
    bandSelectionList.setdefault("AG:AN", "11a")
    bandSelectionList.setdefault("AB:AN", "11a")

    bandSelectionList.setdefault("AGN:AN", "11na")
    bandSelectionList.setdefault("AN:AN", "11na")
    bandSelectionList.setdefault("GN:AN", "11na")

    bandSelectionList.setdefault("AGN:ABG", "11a")
    bandSelectionList.setdefault("AGN:BG", "11g")
    bandSelectionList.setdefault("AGN:B", "11b")
    bandSelectionList.setdefault("AN:ABG", "11a")
    bandSelectionList.setdefault("AN:BG", "11g")
    bandSelectionList.setdefault("AN:B", "11b")
    bandSelectionList.setdefault("GN:ABG", "11g")
    bandSelectionList.setdefault("GN:BG", "11g")
    bandSelectionList.setdefault("GN:B", "11b")

    # DUT Mode AC
    bandSelectionList.setdefault("A:AC", "11a")
    bandSelectionList.setdefault("AN:AC", "11na")
    bandSelectionList.setdefault("AC:AC", "11ac")
    bandSelectionList.setdefault("B:BGNAC", "11b")
    bandSelectionList.setdefault("BG:BGNAC", "11g")
    bandSelectionList.setdefault("BGN:BGNAC", "11ng")

def find_TestcaseInfo_Level1(testID, tag):
    """
    Finds the value of given tag in master XML file of Testcase Info

    Parameters
    ----------
    testID : str
    tag : str

    Returns
    -------
    result : int
        tag value as per XML file
    """
    result = ""
    LogMsg("\n|\n|\n| Searching %s for TestID %s" % (tag, testID))
    for node in doc.getElementsByTagName(testID):
        L = node.getElementsByTagName(tag)
        for node2 in L:
            for node3 in node2.childNodes:
                if node3.nodeType == Node.TEXT_NODE:
                    result = node3.nodeValue
                    LogMsg("\n|\n|\n| Found %s = %s" %(tag, result))
                    return result

    LogMsg("\n|\n|\n| Found %s = %s" % (tag, result))
    return result

def check_isNode_Level1(tag):
    result = 0
    LogMsg("\n|\n|\n| Searching for Node %s" % tag)
    for node in doc.getElementsByTagName(tag):
        LogMsg("Node exsits")
        result = 1
        L = node.getElementsByTagName(tag)
    LogMsg(" Match for %s = %s" %(tag, result))
    return result

def find_STAFile(testID, tag):
    result = ""
    LogMsg("\n|\n|\n| Searching DUT File for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        L = node.getElementsByTagName(tag)
        LogMsg("Node1 = %s" % node.nodeName)
        for node2 in L:
            LogMsg("----Node2 = %s" % node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == "_Value":
                    LogMsg('--------Found %s' % node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    break
                else:
                    LogMsg("--------Node3 = %s" % node3.nodeName)
                    if node3.nodeName == "WPA2-Personal" and node3.nodeName == dutInfoObject.DUTType:
                        LogMsg("------------Node4 Personal= %s" % node3.firstChild.nodeValue)
                        result = node3.firstChild.nodeValue
                        break
                    elif node3.nodeName == "WPA2-Enterprise" and node3.nodeName == dutInfoObject.DUTType:
                        for node4 in node3.childNodes:
                            LogMsg("------------Node4. = %s" % node4.nodeName)
                            for node5 in node4.childNodes:
                                if node5.nodeName == dutInfoObject.DUTEAPMethod:
                                    LogMsg("------------Node5. = %s" %node5.firstChild.nodeValue)
                                    result = node5.firstChild.nodeValue
    if result == "NA":
        LogMsg("\n The test %s is not applicable for DUT Type %s" % (testID, dutInfoObject.DUTType))
        VarList.setdefault("TestNA", "The test %s is not applicable for DUT Type %s" % (testID, dutInfoObject.DUTType))
    LogMsg("\n|\n|\n| Found DUT File -%s-" % (result))
    return result

def find_TestbedFile(testID):
    result = ""
    LogMsg("\n|\n|\n| Searching Testbed File for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        L = node.getElementsByTagName("TestbedFile")
        LogMsg("Node1 = %s" % node.nodeName)
        for node2 in L:
            LogMsg("----Node2 = %s" % node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == "_Value":
                    LogMsg('--------Found %s' % node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    break
                if node3.nodeType == Node.TEXT_NODE and node3.nodeValue.isalnum() == True:
                    LogMsg('--------Found -%s-' % node3.nodeValue)
                    if node3.nodeValue == '0':
                        continue
                    else:
                        result = node3.nodeValue
                        break
                else:
                    LogMsg("--------Node3 = %s" % node3.nodeName)
                    if node3.nodeName == dutInfoObject.DUTType:
                        LogMsg("------------Node4 = %s" % node3.firstChild.nodeValue)
                        result = node3.firstChild.nodeValue
                        break

    if result == "NA":
        LogMsg("\n The test %s is not applicable for DUT Type %s" % (testID, dutInfoObject.DUTType))
        VarList.setdefault("TestNA", "The test %s is not applicable for DUT Type %s" % (testID, dutInfoObject.DUTType))
    LogMsg("\n|\n|\n| Found Testbed File -%s-" % (result))
    return result

def find_Supplicant(testID, tag, category):
    result = ""
    LogMsg("\n|\n|\n| Searching Supplicant for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        L = node.getElementsByTagName("Supplicant")
        LogMsg("Node1 = %s" %node.nodeName)
        L = L[0].getElementsByTagName(tag)
        for node2 in L:
            LogMsg("----Node2 = %s" % node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == category:
                    LogMsg("------------Node4 Personal= %s" %node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    if result == "NA":
                        LogMsg("\n The test %s is not applicable for DUT category %s" % (testID, category))
                        VarList.setdefault("TestNA", "The test %s is not applicable for DUT category %s" % (testID, category))
                    break
    LogMsg("\n|\n|\n| Found Supplicant -%s-" % (result))
    return result

def find_Server(testID, tag):
    result = ""
    LogMsg("\n|\n|\n| Searching Server for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" % node.nodeName)
        L = node.getElementsByTagName("Server")

        for node2 in L:
            LogMsg("----Node2 = %s" %node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == tag:
                    LogMsg("------------Node4 = %s" %node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    break

    LogMsg("\n|\n|\n| Found server File -%s-" % (result))
    return result

def find_SubsServer(testID, tag):
    result = ""
    LogMsg("\n|\n|\n| Searching Subscription Server for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" % node.nodeName)
        L = node.getElementsByTagName("SubscriptionServer")

        for node2 in L:
            LogMsg("----Node2 = %s" %node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == tag:
                    LogMsg("------------Node4 = %s" %node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    break

    LogMsg("\n|\n|\n| Found Subscription server File -%s-" % (result))
    return result

#PMF specific
def find_WLANTestFile(testID, tag):
    result = ""
    LogMsg("\n|\n|\n| Searching WLAN Tester File for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" % node.nodeName)
        L = node.getElementsByTagName(tag)

        for node2 in L:
            LogMsg("----Node2 = %s" % node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == "_Value":
                    LogMsg("------------Node4 = %s" % node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    break

    LogMsg("\n|\n|\n| Found WLAN Tester File -%s-" % (result))
    return result

def findSecurity(testID, tag):
    result = ""
    LogMsg("\n|\n|\n| Searching Security Info for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" %node.nodeName)
        L = node.getElementsByTagName(tag)

        for node2 in L:
            LogMsg("----Node2 = %s" % node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == "KeyMgmt":
                    LogMsg("------------Security Info= %s" % node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    if result == "WPA2-Ent":
                        if dutInfoObject.DUTType == "WPA2-Enterprise":
                            VarList.setdefault("Keymgnt", node3.firstChild.nodeValue)
                            VarList.setdefault("keymgmttpye", "%s" % ("WPA2"))
                        else:
                            VarList.setdefault("Keymgnt", "%s" % ("WPA2-PSK"))
                            VarList.setdefault("keymgmttpye", "%s" % ("WPA2"))
                    else:
                        VarList.setdefault("Keymgnt", "%s-%s" % (node3.firstChild.nodeValue, "PSK"))
                        VarList.setdefault("keymgmttpye", node3.firstChild.nodeValue)
                elif node3.nodeName == "Encryption":
                    LogMsg("------------Security Info= %s" % node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    VarList.setdefault("encpType", node3.firstChild.nodeValue)
                elif node3.nodeName == "Passphrase":
                    LogMsg("------------Security Info= %s" %node3.firstChild.nodeValue)
                    result = node3.firstChild.nodeValue
                    VarList.setdefault("passphrase", node3.firstChild.nodeValue)

    LogMsg("\n|\n|\n| Found Security Info -%s-" % (result))

def findPMFCap(testID, tag):
    result = ""
    LogMsg("\n|\n|\n| Searching PMF Capability for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" % node.nodeName)
        L = node.getElementsByTagName(tag)

    for node2 in L:
        LogMsg("----Node2 = %s" % node2.nodeName)
        for node3 in node2.childNodes:
            if node3.nodeName == "DUT_PMFCap":
                LogMsg("------------DUT PMF Cap= %s" % node3.firstChild.nodeValue)
                VarList.setdefault("DUT_PMFCap", node3.firstChild.nodeValue)
            elif node3.nodeName == "PMFCap1":
                LogMsg("------------Testbed PMF Cap1= %s" % (node3.firstChild.nodeValue))
                VarList.setdefault("PMFCap1", node3.firstChild.nodeValue)
            elif node3.nodeName == "PMFCap2":
                LogMsg("------------Testbed PMF Cap2= %s" % (node3.firstChild.nodeValue))
                VarList.setdefault("PMFCap2", node3.firstChild.nodeValue)
            elif node3.nodeName == "PMFCap3":
                LogMsg("------------Testbed PMF Cap3= %s" % (node3.firstChild.nodeValue))
                VarList.setdefault("PMFCap3", node3.firstChild.nodeValue)

def get_ASD_framerate(ASDvalue):
    # The expected traffic is about 30% more than the expected throughput value
    offset = 0.3
    # payload value is 1000, which is hard-coded in the script
    ASDframerate = ((float(ASDvalue) * (1+offset) * 1000000) / (1000 * 8))
    ASDframerate = "{:.2f}".format(ASDframerate)
    return ASDframerate

def find_ASD_threshold_values(testID, tag):
    result = ""
    tag1 = ""
    LogMsg("\n|\n|\n| Searching ASD Throughput values for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" % node.nodeName)
        L = node.getElementsByTagName(tag)
        asd_type = getattr(dutInfoObject, "ASD")
        if asd_type == "1":
            tag1 = "Handsets"
        elif asd_type == "2":
            tag1 = "TV"
        elif asd_type == "3":
            tag1 = "Printer"
        elif asd_type == "4":
            tag1 = "SetTopBox"
        elif asd_type == "5":
            tag1 = "MobileAP"
        LogMsg(" Test Running ASD -%s-%s- " % (asd_type, tag1))
        for node2 in L:
            for node3 in node2.childNodes:
                if node3.nodeName == tag1:
                    for node4 in node3.childNodes:
                        if node4.nodeName != "#text":
                            LogMsg("------------Node4. = %s %s" % (node4.nodeName, node4.firstChild.nodeValue))
                            VarList.setdefault(node4.nodeName, node4.firstChild.nodeValue)
                            #Add new key value in the Varlist dictionary to store coresponding framerate for ASD project
                            ASDkey = "FrameRate_" + node4.nodeName
                            ASDframerate = get_ASD_framerate(node4.firstChild.nodeValue)
                            VarList.update({ASDkey:ASDframerate})
                            result = 1

    LogMsg("\n|\n|\n| Found ASD Throughput values -%s-" % (result))
    return result

def find_throughput_values(testID, tag):
    result = ""
    tag1 = ""
    LogMsg("\n|\n|\n| Searching Throughput values for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" % node.nodeName)
        L = node.getElementsByTagName(tag)
        bnd = getattr(testEnvVariables, "Band")
        if bnd == "11a" or bnd == "11na":
            tag1 = "A"
        elif bnd == "11g" or bnd == "11ng":
            tag1 = "G"
        elif bnd == "11b":
            tag1 = "B"
        elif bnd == "11ac":
            tag1 = "AC"

        LogMsg(" Test Running in band -%s-%s- " % (bnd, tag1))
        for node2 in L:
            LogMsg("----Node2 = %s" % node2.nodeName)
            for node3 in node2.childNodes:
                if node3.nodeName == tag1:
                    for node4 in node3.childNodes:
                        if node4.nodeName != "#text":
                            LogMsg("------------Node4. = %s %s" % (node4.nodeName, node4.firstChild.nodeValue))
                            VarList.setdefault(node4.nodeName, node4.firstChild.nodeValue)
                            result = 1

    LogMsg("\n|\n|\n| Found Throughput values -%s-" % (result))
    return result

def find_stream_threshold_values(testID, tag):
    result = ""
    tag1 = ""
    LogMsg("\n|\n|\n| Searching WMM Stream Thrshold values for TestID %s" % (testID))
    for node in doc.getElementsByTagName(testID):
        LogMsg("Node1 = %s" %node.nodeName)
        L = node.getElementsByTagName(tag)
        for node2 in L:
            LogMsg("----Node2 = %s" %node2.nodeName)
            for node4 in node2.childNodes:
                if node4.nodeName != "#text":
                    LogMsg("------------Node4. = %s %s" % (node4.nodeName, node4.firstChild.nodeValue))
                    VarList.setdefault(node4.nodeName, node4.firstChild.nodeValue)
                    result = 1

    LogMsg("\n|\n|\n| Found Throughput values -%s-" % (result))
    return result

def createDownloadLog():
    downloadLogs = open("DownloadLogs.bat", 'w')
    downloadLogs.write("@@echo off \n")
    downloadLogs.write("FOR /F  %%T in ('findstr \".\" p') do (\n set LogPath=%%T\n )\n")
    #DUT Log

    #Sniffer Trace
    LogMsg("============================= Init File -%s-  Sniffer Flag-%s-  Sniffer IP -%s--" % (uccPath+InitFile, ReadMapFile(uccPath+InitFile, "sniffer_enable", "!"), ReadMapFile(uccPath+InitFile, "wfa_console_tg", "!")))
    if ReadMapFile(uccPath+InitFile, "sniffer_enable", "!") == "1":
        downloadLogs.write("wget -q -t 1 -T 4 -P %sLogPath%s\Sniffer --ftp-user=wifiuser --ftp-password=asdlinux ftp://%s/sniffer_trace*\n"%("%", "%", ReadMapFile(uccPath+InitFile, "wfa_sniffer", "!").split(',')[0].split('=')[1]))

    downloadLogs.close()
