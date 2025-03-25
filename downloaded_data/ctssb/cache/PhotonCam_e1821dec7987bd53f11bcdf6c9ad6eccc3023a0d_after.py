#!/usr/bin/python

import numpy as np
import cv2
import ROOT
from epics import PV
import sys
import os
import datetime
import curses
from time import sleep

###### Default Settings #########
numframes = 25
xbins = 64
ybins = 48
automode = True
epicson = True
windowsize = (1200,800)
average_factor = 0.01
dumpdata = False
fits=True
videostandard = "0x00000400"
v4l2settings = os.environ['HOME'] + "/.v4l2-default-optimized"
if not os.path.isfile(v4l2settings):
    print("Optimized v4l2-configuration doesn't exist yet!!")
    print("    1.) Optimize using v4l2ucp.")
    print("    2.) Store:         v4l2ctrl -s " + v4l2settings)

                


def PrintKeys():
        print("======= Beam Camera =====================")
        print("")
        print("Keys (in camera windows):")
        print("")
        print("  Options:")
        print("    a: toggle auto mode      < " + str(automode) + " >")
        print("    e: toggle EPICS logging  < " + str(epicson)  + " >")
        print("    f: toggle fitting        < " + str(fits)     + " >")
        print("  Actions:")
        print("    r: remeasure")
        print("    s: save histograms as png")
        print("    p: save camera picture as png")
        print("    l: generate an entry for Elog")
        print("    q: quit")
        print("")

### Parse Command Line ###
for arg in sys.argv:
    if arg.startswith("--numframes="):
        numframes = int(arg.split('=')[1])
    if arg.startswith("--xbins="):
        xbins = int(arg.split('=')[1])
    if arg.startswith("--ybins="):
        ybins = int(arg.split('=')[1])
    if arg.startswith("--noauto"):
        automode=False
    if arg.startswith("--v4l2-settings="):
        v4l2settings = arg.split('=')[1];
        if not os.path.isfile(v4l2settings):
            print(" Error loading v4l2-config-file: " + v4l2settings + " doesn't exist!")
            sys.exit(128)
    if arg.startswith("--dump-data"):
        dumpdata = True;
            
    if arg.startswith("--help" or "-help" ):
	print "=====  OpenCV beam camera analyzer ======"
	print ""
	print "  Usage:"
	print ""
	print "     ",sys.argv[0]," [--numframes=< # frames to for fitting center = 25> "
	print "                    --xbins=<64> "
	print "                    --ybins=<48> "
	print "                    --noauto  turn of auto mode"
	print "                    --v4l2-settings=<user-settings-file>"
	print ""
        PrintKeys()
	print ""


### Init ###

# Init v4l2-driver:

print
print "=====  Initializing v4l2 - driver  ==================="
print
os.system("v4l2-ctl --set-standard=" + videostandard)

if os.system("v4l2ctrl -l " + v4l2settings):
    print("Error loading v4l2-config-file!")

# Init Video Capture

cap = cv2.VideoCapture(0)

###### Initialize EPICS-Records #########
print
print "=====  Initializing all PVs  ========================="
print

EpicsRecords = dict( [ ( record , PV(record) ) for record in 
                        [ "BEAM:IonChamber",
                          "TAGG:EPT:LadderP2Ratio",
                          "BEAM:PhotonCam:CenterX",
                          "BEAM:PhotonCam:CenterX.A",
                          "BEAM:PhotonCam:CenterY",
                          "BEAM:PhotonCam:CenterY.A",
                          "BEAM:PhotonCam:WidthX.A",
                          "BEAM:PhotonCam:WidthY.A",
                          "BEAM:PhotonCam:Sum.A"      ] 
                     ] )

def check_records():
    return [ pv.pvname for pv in EpicsRecords.itervalues() if not pv.connected ]

print("  +-"+4*len(EpicsRecords)*"-"+"-+")
sys.stdout.write("    ")
sys.stdout.flush()
for pv in EpicsRecords.itervalues():
    pv.connect()
    sys.stdout.write(4*"#")
    sys.stdout.flush()
sys.stdout.write("  ")
sys.stdout.flush()
print
print("  +-"+4*len(EpicsRecords)*"-"+"-+")
print

if check_records():
    print "Warning, Following PVs are not connected:"
    print check_records()
    print
    print "  --> Check your EpicsRecords-dict"
    print "      for full EPICS support!     "
    print
    raw_input("Smash head on keyboard, then hit return to continue!")

        

def caget(record):
    if EpicsRecords[record].connected:
        return EpicsRecords[record].get()
    #print("  Warning: PV {0} not connected. Check your EpicsRecords!".format(EpicsRecords[record].pvname) )
    return False

def caput(record,value):
    if EpicsRecords[record].connected:
        EpicsRecords[record].put(value)
    #else:
        #print("  Warning: PV {0} not connected. Check your EpicsRecords!".format(EpicsRecords[record].pvname) )
# Set up ROOT

# Canvas
print
print "=====  Initializing ROOT canvas  ====================="
print

c = ROOT.TCanvas("profile","Beam Profile")
c.Divide(2,2)
c.SetWindowSize(windowsize[0], windowsize[1])

# 2D profile histogram
hist = ROOT.TH2D("frame","Beam Profile",xbins,0,640,ybins,0,480)
hist.SetXTitle("x")
hist.SetYTitle("y")
hist.SetZTitle("Intensity [a.u.]")
histx = ROOT.TH1D()
histx.SetTitle("X-Projection")
histy = ROOT.TH1D()
histy.SetTitle("Y-Projection")

# Fit functions
f2 = ROOT.TF2("f2","xygaus",0 ,640,0,640);
f1 = ROOT.TF1("f1","gaus",0 ,640);

curframe = 0
last_p = 0

if dumpdata:
    datafile = open("beam.dat","w")

def CheckBeam():
    #listhistx = [ histx.GetBinContent(i+1) for i in range(histx.GetNbinsX()) ]
    hasbeam = caget("BEAM:IonChamber") > 500
    return hasbeam

# ======= init curses ============


def refreshWin(window,windowTitle=""):
        window.box()
        if not windowTitle=="":
            window.addstr(0,2,"< " + windowTitle + " >")
        window.refresh()
    

mscreen = curses.initscr()
refreshWin(mscreen,"Photon Camera Programm")
mmaxy, mmaxx = mscreen.getmaxyx()
loadscreen = curses.newwin(3, mmaxx - 16 ,2, 8)
keyscreen = curses.newwin(14, 40 ,6,4)
statescreen = curses.newwin(14, mmaxx - 42 - 8 ,6,42 + 4 )
mscreen.keypad(1)
curses.noecho()
curses.cbreak()
curses.curs_set(0)

def putLoading(p):
    loadscreen.erase()
    pstring = "Accumulating " +str(numframes) + " frames... "
    pstring = pstring + int(p) * 2 * "#"
    loadscreen.addstr(1,2,pstring)

def putState(analysed):
    statescreen.erase()
    statescreen.addstr( 2,4,"screen size:  (" + str(sumbuf.shape[1]) + ", " + str(sumbuf.shape[0])+")")
    statescreen.addstr( 4,4,   "Has beam:     " + str(CheckBeam()))
    formstr = "{:>.2f}"
    if analysed and fits:
        statescreen.addstr( 6,4,"x-center:     " + formstr.format(hist.GetFunction("f2").GetParameter(1)))
        statescreen.addstr( 7,4,"y-center:     " + formstr.format(hist.GetFunction("f2").GetParameter(3)))
        statescreen.addstr( 8,4,"x-width:      " + formstr.format(hist.GetFunction("f2").GetParameter(2)))
        statescreen.addstr( 9,4,"y-width:      " + formstr.format(hist.GetFunction("f2").GetParameter(4)))
    if check_records():
        statescreen.addstr(11,4,"Warning:")
        statescreen.addstr(12,4,"{0} disconnected PVs!".format(len(check_records())))


def putKeys():
    keyscreen.erase()
    keyscreen.addstr( 2,4,"Options:")
    keyscreen.addstr( 3,9,"a: auto mode      < " + str(automode) + " >")
    keyscreen.addstr( 4,9,"e: EPICS logging  < " + str(epicson)  + " >")
    keyscreen.addstr( 5,9,"f: fitting        < " + str(fits)     + " >")
    keyscreen.addstr( 6,4,"Actions:")
    keyscreen.addstr( 7,9,"r: remeasure")
    keyscreen.addstr( 8,9,"s: save histograms as png")
    keyscreen.addstr( 9,9,"p: save camera picture as png")
    keyscreen.addstr(10,9,"l: generate an entry for Elog")
    keyscreen.addstr(11,9,"q: quit")

def undoCurses():
    mscreen.keypad(0)
    curses.nocbreak()
    curses.echo()
    curses.curs_set(1)
    curses.endwin()

    

# Grab a grayscale video frame as 64bit floats
def GrabFrame():
    ret, frame = cap.read()
    # convert to grayscale and floats
    return ret, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(float)


def Clear():
    sys.stderr.write("\x1b[2J\x1b[H")


def ToEpics():
    hsum = hist.GetSum()
    beam = CheckBeam()
    if beam and fits:
        caput("BEAM:PhotonCam:CenterX.A",hist.GetFunction("f2").GetParameter(1))
        caput("BEAM:PhotonCam:CenterY.A",hist.GetFunction("f2").GetParameter(3))
        caput("BEAM:PhotonCam:WidthX.A",hist.GetFunction("f2").GetParameter(2))
        caput("BEAM:PhotonCam:WidthY.A",hist.GetFunction("f2").GetParameter(4))
        caput("BEAM:PhotonCam:Sum.A",hsum)
    else:
        caput("BEAM:PhotonCam:CenterX.A",float('nan'))
        caput("BEAM:PhotonCam:CenterY.A",float('nan'))
        caput("BEAM:PhotonCam:WidthX.A",float('nan'))
        caput("BEAM:PhotonCam:WidthY.A",float('nan'))
        caput("BEAM:PhotonCam:Sum.A",hsum)
        

def GenerateElog():
        filename1 = SaveHistograms()
        filename2 = SaveCamera()

        statescreen.erase()

        date = datetime.datetime.now()
        elog_cmd = "echo 'Beamspot Pictures from " + date.strftime("%Y-%m-%d-%H:%M:%S") + "\\n\\n"
        elog_cmd = elog_cmd + "  Center is at:     (x,y) = ( {:>.2f} , {:>.2f} )\\n".format(caget("BEAM:PhotonCam:CenterX"),
                                                                                          caget("BEAM:PhotonCam:CenterY") )
        elog_cmd = elog_cmd + "  Ratio:         Ladder/p2 = {:>.2f}".format(caget("TAGG:EPT:LadderP2Ratio")) + "' | "
        elog_cmd = elog_cmd + "/opt/elog/bin/elog -h elog.office.a2.kph -u a2online a2messung "
        elog_cmd = elog_cmd + "-l 'Main Group Logbook' -a Experiment='2015-06 Compton' "
        elog_cmd = elog_cmd + "-a Author='PLEASE FILL IN' -a Type=Routine "
        elog_cmd = elog_cmd + "-a Subject='Photon beam profile' "
        elog_cmd = elog_cmd + "-f " + filename1 + " ";
        elog_cmd = elog_cmd + "-f " + filename2;


        statescreen.addstr( 2,2, "Generate Elog-entry: ")

        statescreen.addstr( 3,4, "Saving histograms...")
        statescreen.addstr( 4,4, "Saving beamspot images...")
        

        if os.system(elog_cmd) == 0:
            statescreen.addstr( 6,6, "Elog, entry ready,")
            statescreen.addstr( 7,6, "please add names!")
        else:
            statescreen.addstr( 6,6, "Error:")
            statescreen.addstr( 7,6, "Posting elog entry failed!")

        os.remove(filename1)
        os.remove(filename2)
	

def SaveHistograms():
        date = datetime.datetime.now()
        filename = date.strftime('BeamspotFit-%Y-%m-%d_%H-%M-%S.png')
        #print "Saving Histograms to ",filename
        c.SetWindowSize(windowsize[0], windowsize[1])
        c.Update()
        c.SaveAs(filename)
        return filename

def SaveCamera():
        date = datetime.datetime.now()
        filename = date.strftime('Beamspot-%Y-%m-%d_%H-%M-%S.png')
        #print "Saving Camera Picture to ",filename
        cv2.imwrite( filename, sumbuf )
        return filename

def StartMeasurement():
    global last_p
    global curframe
    curframe = 0
    last_p = 0

def Analyse():
        global buf
        hist.Reset()

        date = datetime.datetime.now()
        Title = date.strftime('Beam Profile %Y-%m-%d %H:%M:%S')
        hist.SetTitle(Title)
	#print("Filling Histogram...")
        buf /= numframes
        size=buf.shape

        # this is SLOOOOOW
        for x in range(size[1]):
            for y in range(size[0]):
                 hist.Fill(x,y, buf[size[0] - y - 1][x])

        histx = hist.ProjectionX()
        histx.SetTitle(date.strftime('Beam X-Projection %Y-%m-%d %H:%M:%S'))
        histy = hist.ProjectionY()
        histy.SetTitle(date.strftime('Beam Y-Projection %Y-%m-%d %H:%M:%S'))

        #print("Fitting...")
        c.cd(1)
        if fits:
            hist.Fit("f2","Q")
        if dumpdata:
            datafile.write(str(f2.GetChisquare()) + "    " )
        hist.Draw("ARR")
        c.cd(2)
        if fits:
            hist.GetFunction("f2").SetBit(ROOT.TF2.kNotDraw);
        hist.Draw("cont")
	c.cd(1)
        if fits:
            f2.Draw("same")
	
        c.cd(3)
        if fits:
            histx.Fit("f1","Q")
        if dumpdata:
            datafile.write(str(f1.GetChisquare()) + "    " )

        histx.Draw("")
        c.cd(4)
        if fits:
            histy.Fit("f1","Q")
        if dumpdata:
            datafile.write(str(f1.GetChisquare()) + "    ")
            datafile.write(str(f2.GetParameter(1)) + "    " + str(f2.GetParameter(3)) + "    ")
            datafile.write(str(caget("TAGG:EPT:LadderP2Ratio")))
            datafile.write("\n" )
        histy.Draw("")
        c.Update()
        #print("Done")
        

        if(epicson):
            ToEpics()

        if(automode):
            StartMeasurement()


if( cap.isOpened()):
    ret, sumbuf = GrabFrame()
    buf = sumbuf


analysed = False

while(cap.isOpened()):

    ret, frame = GrabFrame()

    if curframe == 0:
        mscreen.clear()
        refreshWin(mscreen,"Photon Camera Programm")

        refreshWin(statescreen,"Status")
        putState(analysed)

        buf=frame

    if ret==True:
        sumbuf = cv2.addWeighted(sumbuf, 1-average_factor, frame, average_factor, 0)
        
        if curframe < numframes:
            p = round(1.0 * curframe/numframes*10)
            if( p > last_p):
                putKeys()
                refreshWin(keyscreen, "Hotkeys (in CV2-frames)")
                putLoading(p)
                refreshWin(loadscreen)
                last_p = p
            # accumulate frames
            buf+=frame

        # show actual frame, converted to 8bit
        cv2.imshow("BEAMCAMERA", frame.astype(np.uint8))
        cv2.imshow("BEAMCAMERA - Averaged", sumbuf.astype(np.uint8))

        curframe = curframe + 1
    else:
	#print("Error reading video.")
        break

    # Keyboad Input
    cvkey = cv2.waitKey(1) & 0xFF;
    #nckey = mscreen.getkey()          #blocks programm, fix this?

    if(cvkey == ord('q')):
        break

    elif( cvkey == ord('r')):
        StartMeasurement()

    elif( cvkey == ord('p')):
        SaveCamera()

    elif( cvkey == ord('s')):
        SaveHistograms()

    elif( cvkey == ord('l')):
        GenerateElog()

    elif( cvkey == ord('e')):
        epicson ^= True;

    elif( cvkey == ord('a')):
        automode ^= True;
        if(automode):
           StartMeasurement()
    elif( cvkey == ord('f')):
	fits ^= True
        epicson = fits


    if (curframe == numframes):
        Analyse()
        analysed = True


# Release everything if job is finished
cap.release()
cv2.destroyAllWindows()
if dumpdata:
    datafile.close()
undoCurses()
