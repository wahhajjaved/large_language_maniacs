import os, sys, string, time, re, ctypes
import numpy as N
from TacoServer import *
from Lima.Core import *

DevCcdBase			= 0xc180000

# CCD Commands
DevCcdStart			= DevCcdBase + 1
DevCcdStop			= DevCcdBase + 2
DevCcdRead			= DevCcdBase + 3
DevCcdSetExposure		= DevCcdBase + 4
DevCcdGetExposure		= DevCcdBase + 5
DevCcdSetRoI			= DevCcdBase + 6
DevCcdGetRoI			= DevCcdBase + 7
DevCcdSetBin			= DevCcdBase + 8
DevCcdGetBin			= DevCcdBase + 9
DevCcdSetTrigger		= DevCcdBase + 10
DevCcdGetTrigger		= DevCcdBase + 11
DevCcdGetLstErrMsg		= DevCcdBase + 12
DevCcdXSize			= DevCcdBase + 13
DevCcdYSize			= DevCcdBase + 14
DevCcdSetADC			= DevCcdBase + 15
DevCcdGetADC			= DevCcdBase + 16
DevCcdSetSpeed			= DevCcdBase + 17
DevCcdGetSpeed			= DevCcdBase + 18
DevCcdSetShutter		= DevCcdBase + 19
DevCcdGetShutter		= DevCcdBase + 20
DevCcdSetFrames			= DevCcdBase + 21
DevCcdGetFrames			= DevCcdBase + 22
DevCcdCommand			= DevCcdBase + 23
DevCcdDepth			= DevCcdBase + 24
DevCcdSetMode			= DevCcdBase + 25
DevCcdGetMode			= DevCcdBase + 26
DevCcdSetChannel		= DevCcdBase + 27
DevCcdGetChannel		= DevCcdBase + 28
DevCcdSetRingBuf		= DevCcdBase + 29
DevCcdGetRingBuf		= DevCcdBase + 30
DevCcdLive			= DevCcdBase + 31
DevCcdWriteFile			= DevCcdBase + 32
DevCcdReset			= DevCcdBase + 33
DevCcdGetIdent			= DevCcdBase + 34
DevCcdGetType			= DevCcdBase + 35
DevCcdSetKinWinSize		= DevCcdBase + 36
DevCcdGetKinWinSize		= DevCcdBase + 37
DevCcdSetKinetics		= DevCcdBase + 38
DevCcdGetKinetics		= DevCcdBase + 39
DevCcdCorrect			= DevCcdBase + 40
DevCcdSetFilePar		= DevCcdBase + 41
DevCcdGetFilePar		= DevCcdBase + 42
DevCcdHeader			= DevCcdBase + 43
DevCcdSetFormat			= DevCcdBase + 44
DevCcdGetFormat			= DevCcdBase + 45
DevCcdSetViewFactor		= DevCcdBase + 46
DevCcdGetViewFactor		= DevCcdBase + 47
DevCcdSetHwPar			= DevCcdBase + 48
DevCcdGetHwPar			= DevCcdBase + 49
DevCcdGetCurrent		= DevCcdBase + 50
DevCcdGetBuffer			= DevCcdBase + 51
DevCcdGetBufferInfo		= DevCcdBase + 52
DevCcdReadAll			= DevCcdBase + 53
DevCcdWriteAll			= DevCcdBase + 54
DevCcdDezinger			= DevCcdBase + 55
DevCcdSetThreshold		= DevCcdBase + 56
DevCcdGetThreshold		= DevCcdBase + 57
DevCcdSetMaxExposure		= DevCcdBase + 58
DevCcdGetMaxExposure		= DevCcdBase + 59
DevCcdSetGain			= DevCcdBase + 60
DevCcdGetGain			= DevCcdBase + 61
DevCcdReadJpeg			= DevCcdBase + 62
DevCcdRefreshTime		= DevCcdBase + 63
DevCcdOutputSize		= DevCcdBase + 64
DevCcdGetTGradient		= DevCcdBase + 65
DevCcdGetChanges		= DevCcdBase + 66
DevCcdCalibrate			= DevCcdBase + 67
DevCcdSetThumbnail1		= DevCcdBase + 68
DevCcdSetThumbnail1		= DevCcdBase + 69
DevCcdWriteThumbnail1		= DevCcdBase + 70
DevCcdWriteThumbnail1		= DevCcdBase + 71

# CCD States
DevCcdReady			= DevCcdBase + 1
DevCcdAcquiring			= DevCcdBase + 2
DevCcdFault			= DevCcdBase + 3
DevCcdSaving			= DevCcdBase + 4
DevCcdNotYetInitialised		= DevCcdBase + 5
DevCcdInitializing		= DevCcdBase + 6
DevCcdReadout			= DevCcdBase + 7
DevCcdCorrecting		= DevCcdBase + 8
DevCcdBusy			= DevCcdBase + 9
DevCcdAborting			= DevCcdBase + 10
DevCcdNoRemote			= DevCcdBase + 11

# CCD Errors
DevErrCcdState			= DevCcdBase + 1
DevErrCcdController		= DevCcdBase + 2
DevErrCcdNotEnoughDisk		= DevCcdBase + 3
DevErrCcdNoDirPermission	= DevCcdBase + 4
DevErrCcdNoDirectory		= DevCcdBase + 5
DevErrCcdLongPath		= DevCcdBase + 6
DevErrCcdEmptyPath		= DevCcdBase + 7
DevErrCcdNotAccessible		= DevCcdBase + 8
DevErrCcdNoFilePermission	= DevCcdBase + 9
DevErrCcdFileExist		= DevCcdBase + 10
DevErrCcdCmdNotProc		= DevCcdBase + 11
DevErrCcdCameraModel		= DevCcdBase + 12
DevErrCcdProcessImage		= DevCcdBase + 13
DevErrCcdCameraNotActiveYet	= DevCcdBase + 14

# Debug Commands
DevGetDebugFlags		= 1501
DevSetDebugFlags		= 1502

import Server
TacoLib = ctypes.cdll.LoadLibrary(Server.__file__)
DevErrorPushPtr = TacoLib.dev_error_push
DevErrorPushProto = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_char_p)
DevErrorPush = DevErrorPushProto(DevErrorPushPtr)

def TACO_SERVER_FUNCT(fn):
    deb_container = set()
    deb_fn = DEB_FUNCT(fn, False, 2, deb_container)
    def taco_fn(*arg, **kw):
        try:
            ret = deb_fn(*arg, **kw)
            deb_container.pop()
        except Server.error:
            exc_class, exc_obj, stack_trace = sys.exc_info()
            sys.exc_clear()
            del stack_trace
            deb_container.pop()
            raise exc_class, exc_obj
        except:
            exc_class, exc_obj, stack_trace = sys.exc_info()
            msg = '%s: %s' % (exc_class, exc_obj)
            sys.exc_clear()
            del exc_class, exc_obj, stack_trace
            DevErrorPush(msg)
            deb = deb_container.pop()
            deb.Error(msg)
            del deb
            Server.error.taco_error = DevErr_CommandFailed
            raise Server.error
        return ret
    return taco_fn


class TacoCcdAcq(TacoServer):

    cmd_list = {
        DevState:		[D_VOID_TYPE, D_LONG_TYPE,
                                 'getState', 'DevState'],
        DevStatus:		[D_VOID_TYPE, D_STRING_TYPE,
                                 'getStatus', 'DevStatus'],
        DevCcdReset:		[D_VOID_TYPE, D_VOID_TYPE,
                                 'reset', 'DevCcdReset'],
        DevCcdXSize:		[D_VOID_TYPE, D_LONG_TYPE,
                                 'getXSize', 'DevCcdXSize'],
        DevCcdYSize:		[D_VOID_TYPE, D_LONG_TYPE,
                                 'getYSize', 'DevCcdYSize'],
        DevCcdDepth:		[D_VOID_TYPE, D_LONG_TYPE,
                                 'getDepth', 'DevCcdDepth'],
        DevCcdGetType:		[D_VOID_TYPE, D_LONG_TYPE,
                                 'getType',  'DevCcdGetType'],
        DevCcdGetLstErrMsg:	[D_VOID_TYPE, D_STRING_TYPE,
                                 'getLstErrMsg', 'DevCcdGetLstErrMsg'],
        DevCcdSetFrames:	[D_LONG_TYPE, D_VOID_TYPE,
                                 'setNbFrames', 'DevCcdSetFrames'],
        DevCcdGetFrames:	[D_VOID_TYPE, D_LONG_TYPE,
                                 'getNbFrames', 'DevCcdGetFrames'],
        DevCcdSetTrigger:	[D_LONG_TYPE, D_VOID_TYPE,
                                 'setTrigger', 'DevCcdSetTrigger'],
        DevCcdGetTrigger:	[D_VOID_TYPE, D_LONG_TYPE,
                                 'getTrigger', 'DevCcdGetTrigger'],
        DevCcdSetExposure:	[D_FLOAT_TYPE, D_VOID_TYPE,
                                 'setExpTime', 'DevCcdSetExposure'],
        DevCcdGetExposure:	[D_VOID_TYPE, D_FLOAT_TYPE,
                                 'getExpTime', 'DevCcdGetExposure'],
        DevCcdSetBin:		[D_VAR_LONGARR, D_VOID_TYPE,
                                 'setBin', 'DevCcdSetBin'],
        DevCcdGetBin:		[D_VOID_TYPE, D_VAR_LONGARR, 
                                 'getBin', 'DevCcdGetBin'],
        DevCcdSetRoI:		[D_VAR_LONGARR, D_VOID_TYPE,
                                 'setRoi', 'DevCcdSetRoI'],
        DevCcdGetRoI:		[D_VOID_TYPE, D_VAR_LONGARR, 
                                 'getRoi', 'DevCcdGetRoI'],
        DevCcdSetFilePar:	[D_VAR_STRINGARR, D_VOID_TYPE,
                                 'setFilePar', 'DevCcdSetFilePar'],
        DevCcdGetFilePar:	[D_VOID_TYPE, D_VAR_STRINGARR, 
                                 'getFilePar', 'DevCcdGetFilePar'],
        DevCcdHeader:		[D_STRING_TYPE, D_VOID_TYPE, 
                                 'setFileHeader', 'DevCcdHeader'],
        DevCcdWriteFile:	[D_LONG_TYPE, D_VOID_TYPE, 
                                 'writeFile', 'DevCcdWriteFile'],
        DevCcdSetChannel:	[D_LONG_TYPE, D_VOID_TYPE,
                                 'setChannel', 'DevCcdSetChannel'],
        DevCcdGetChannel:	[D_VOID_TYPE, D_LONG_TYPE, 
                                 'getChannel', 'DevCcdGetChannel'],
        DevCcdSetMode:		[D_LONG_TYPE, D_VOID_TYPE,
                                 'setMode', 'DevCcdSetMode'],
        DevCcdGetMode:		[D_VOID_TYPE, D_LONG_TYPE, 
                                 'getMode', 'DevCcdGetMode'],
        DevCcdSetHwPar:		[D_STRING_TYPE, D_VOID_TYPE,
                                 'setHwPar', 'DevCcdSetHwPar'],
        DevCcdGetHwPar:		[D_VOID_TYPE, D_STRING_TYPE, 
                                 'getHwPar', 'DevCcdGetHwPar'],
        DevCcdSetKinetics:	[D_LONG_TYPE, D_VOID_TYPE,
                                 'setKinetics', 'DevCcdSetKinetics'],
        DevCcdGetKinetics:	[D_VOID_TYPE, D_LONG_TYPE,
                                 'getKinetics', 'DevCcdGetKinetics'],
        DevCcdSetKinWinSize:	[D_LONG_TYPE, D_VOID_TYPE,
                                 'setKinWinSize', 'DevCcdSetKinWinSize'],
        DevCcdGetKinWinSize:	[D_VOID_TYPE, D_LONG_TYPE,
                                 'getKinWinSize', 'DevCcdGetKinWinSize'],
        DevCcdStart:		[D_VOID_TYPE, D_VOID_TYPE,
                                 'startAcq', 'DevCcdStart'],
        DevCcdStop:		[D_VOID_TYPE, D_VOID_TYPE,
                                 'stopAcq', 'DevCcdStop'],
        DevCcdRead:		[D_VAR_LONGARR, D_OPAQUE_TYPE,
                                 'readFrame', 'DevCcdRead'],
        DevCcdLive:		[D_VOID_TYPE, D_VOID_TYPE,
                                 'startLive', 'DevCcdLive'],
        DevCcdGetCurrent:	[D_VOID_TYPE, D_LONG_TYPE, 
                                 'getCurrent', 'DevCcdGetCurrent'],
        DevCcdCommand:		[D_STRING_TYPE, D_STRING_TYPE, 
                                 'execCommand', 'DevCcdCommand'],
        DevCcdGetChanges:	[D_VOID_TYPE, D_LONG_TYPE, 
                                 'getChanges', 'DevCcdGetChanges'],
        DevReadValues:		[D_VOID_TYPE, D_VAR_FLOATARR,
                                 'readBeamParams', 'DevReadValues'],
        DevReadSigValues:	[D_VOID_TYPE, D_VAR_FLOATARR,
                                 'readCcdParams', 'DevReadSigValues'],
	DevSetDebugFlags:	[D_ULONG_TYPE, D_VOID_TYPE,
				 'setDebugFlags', 'DevSetDebugFlags'],
	DevGetDebugFlags:	[D_VOID_TYPE, D_ULONG_TYPE,
				 'getDebugFlags', 'DevGetDebugFlags'],
    }

    LiveDisplay  = 1
    StripeConcat = 4
    AutoSave     = 8

    DEB_CLASS(DebModApplication, 'TacoCcdAcq')

    @DEB_MEMBER_FUNCT
    def __init__(self, dev_name, dev_class=None, cmd_list=None):
	if dev_class is None:
            dev_class = 'TacoCcdDevClass'
        if cmd_list is None:
            cmd_list = self.cmd_list
        TacoServer.__init__(self, dev_name, dev_class, cmd_list)
        self.dev_name = dev_name

    @TACO_SERVER_FUNCT
    def reset(self):
        deb.Trace('Reseting the device!')
        
    @TACO_SERVER_FUNCT
    def getResources(self, default_resources):
        deb.Param('default_resources=%s' % default_resources)
        pars = {}
        for res_name, def_val in default_resources.items():
            val = esrf_getresource(self.dev_name, res_name)
            if not val:
                val = def_val
            pars[res_name] = val
        deb.Return('pars=%s' % pars)
        return pars
    
    @TACO_SERVER_FUNCT
    def getState(self):
        self.state = DevCcdReady
        deb.Return('Device state: 0x%08x (%d)' % (state, state))
        return self.state

    @TACO_SERVER_FUNCT
    def getStatus(self):
        state_desc = { DevCcdReady:     'CCD is Ready',
                       DevCcdAcquiring: 'CCD is Acquiring' }
        state = self.getState()
        status = state_desc[state]
        deb.Return('Device status: %s (0x%08x)' % (status, state))
        return status

    @TACO_SERVER_FUNCT
    def getFrameDim(self, max_dim=False):
        fdim = FrameDim(Size(1024, 1024), Bpp16)
        deb.Return('Frame dim: %s' % fdim)
        return fdim
    
    @TACO_SERVER_FUNCT
    def getXSize(self):
        frame_dim = self.getFrameDim(max_dim=True)
        width = frame_dim.getSize().getWidth()
        deb.Return('width=%s' % width)
        return width
    
    @TACO_SERVER_FUNCT
    def getYSize(self):
        frame_dim = self.getFrameDim(max_dim=True)
        height = frame_dim.getSize().getHeight()
        deb.Return('height=%s' % height)
        return height
    
    @TACO_SERVER_FUNCT
    def getDepth(self):
        frame_dim = self.getFrameDim(max_dim=True)
        depth = frame_dim.getDepth()
        deb.Return('depth=%s' % depth)
        return depth

    @TACO_SERVER_FUNCT
    def getType(self):
        type_nb = 0
        deb.Return('Getting type: %s (#%s)' % (ccd_type, type_nb))
        return type_nb

    @TACO_SERVER_FUNCT
    def getLstErrMsg(self):
        err_msg = ''
        deb.Return('Getting last err. msg: %s' % err_msg)
        return err_msg
    
    @TACO_SERVER_FUNCT
    def setTrigger(self, ext_trig):
        deb.Param('Setting trigger: %s' % ext_trig)
    
    @TACO_SERVER_FUNCT
    def getTrigger(self):
        ext_trig = 0
        deb.Return('Getting trigger: %s' % ext_trig)
        return ext_trig
    
    @TACO_SERVER_FUNCT
    def setNbFrames(self, nb_frames):
        deb.Param('Setting nb. frames: %s' % nb_frames)
    
    @TACO_SERVER_FUNCT
    def getNbFrames(self):
        nb_frames = 1
        deb.Return('Getting nb. frames: %s' % nb_frames)
        return nb_frames
    
    @TACO_SERVER_FUNCT
    def setExpTime(self, exp_time):
        deb.Param('Setting exp. time: %s' % exp_time)
    
    @TACO_SERVER_FUNCT
    def getExpTime(self):
        exp_time = 1
        deb.Return('Getting exp. time: %s' % exp_time)
        return exp_time

    @TACO_SERVER_FUNCT
    def setBin(self, bin):
        # SPEC format Y,X -> incompat. with getBin ...
        bin = Bin(bin[1], bin[0])
        deb.Param('Setting binning: %s' % bin)

    @TACO_SERVER_FUNCT
    def getBin(self):
        bin = Bin(1, 1)
        deb.Return('Getting binning: %s' % bin)
        return [bin.getX(), bin.getY()]

    @TACO_SERVER_FUNCT
    def setRoi(self, roi):
        roi = Roi(Point(roi[0], roi[1]), Point(roi[2], roi[3]))
        deb.Param('Setting roi: %s' % roi)

    @TACO_SERVER_FUNCT
    def getRoi(self):
        roi = Roi()
        deb.Return('Getting roi: %s' % roi)
        tl = roi.getTopLeft()
        br = roi.getBottomRight()
        return [tl.getX(), tl.getY(), br.getX(), br.getY()]
            
    @TACO_SERVER_FUNCT
    def setFilePar(self, pars):
        deb.Param('Setting file pars: %s' % pars)

    @TACO_SERVER_FUNCT
    def getFilePar(self):
        pars = CtSaving.Parameters()
        overwrite = pars.overwritePolicy == CtSaving.Overwrite
        arr = [pars.directory, pars.prefix, pars.suffix, pars.nextNumber,
               pars.fileFormat, overwrite]
        par_arr = map(str, arr)
        deb.Return('File pars: %s' % par_arr)
        return par_arr

    @TACO_SERVER_FUNCT
    def setFileHeader(self, header_str):
        deb.Param('Setting file header: %s' % header_str)
      
    @TACO_SERVER_FUNCT
    def writeFile(self, frame_nb):
        deb.Param('Writing frame %s to file' % frame_nb)
      
    @TACO_SERVER_FUNCT
    def setChannel(self, input_chan):
        deb.Param('Setting input channel: %s' % input_chan)
    
    @TACO_SERVER_FUNCT
    def getChannel(self):
        input_chan = 0
        deb.Return('Getting input channel: %s' % input_chan)
        return input_chan
        
    @TACO_SERVER_FUNCT
    def setMode(self, mode):
        deb.Param('Setting mode: %s (0x%x)' % (mode, mode))
        live_display = (mode & self.LiveDisplay) != 0
        auto_save = (mode & self.AutoSave) != 0
        
    @TACO_SERVER_FUNCT
    def getMode(self):
        auto_save = False
        mode = (auto_save and self.AutoSave) or 0
        deb.Return('Getting mode: %s (0x%x)' % (mode, mode))
        return mode

    @TACO_SERVER_FUNCT
    def setHwPar(self, hw_par_str):
        hw_par = map(int, string.split(hw_par_str))
        deb.Param('Setting hw par: %s' % hw_par)
        
    @TACO_SERVER_FUNCT
    def getHwPar(self):
        hw_par = []
        deb.Return('Getting hw par: %s' % hw_par)
        hw_par_str = string.join(map(str, hw_par))
        return hw_par_str
        
    @TACO_SERVER_FUNCT
    def setKinetics(self, kinetics):
        deb.Param('Setting the profile: %s' % kinetics)
    
    @TACO_SERVER_FUNCT
    def getKinetics(self):
        kinetics = 0
        deb.Return('Getting the profile: %s' % kinetics)
        return kinetics
    
    @TACO_SERVER_FUNCT
    def setKinWinSize(self, kin_win_size):
        deb.Param('Setting the kinetics window size: %s' % kin_win_size)
    
    @TACO_SERVER_FUNCT
    def getKinWinSize(self):
        kin_win_size = 0
        deb.Return('Getting the kinetics window size: %s' % kin_win_size)
        return kin_win_size
    
    @TACO_SERVER_FUNCT
    def startAcq(self):
        deb.Trace('Starting the device')
    
    @TACO_SERVER_FUNCT
    def stopAcq(self):
        deb.Trace('Stopping the device')
    
    @TACO_SERVER_FUNCT
    def readFrame(self, frame_data):
        frame_nb, frame_size = frame_data
        frame_dim = self.getFrameDim()
        if frame_size != frame_dim.getMemSize():
            raise ValueError, ('Client expects %d bytes, frame has %d' % \
                               (frame_size, frame_dim.getMemSize()))
        shape = (frame_dim.getHeight(), frame_dim.getWidth())
        data = N.zeros(shape, N.uint16)
        s = data.tostring()
        if len(s) != frame_size:
            raise ValueError, ('Client expects %d bytes, data str has %d' % \
                               (frame_size, len(s)))
        return s

    @TACO_SERVER_FUNCT
    def startLive(self):
        deb.Trace('Starting live mode')
    
    @TACO_SERVER_FUNCT
    def getCurrent(self):
        last_frame_nb = 0
        return last_frame_nb

    @TACO_SERVER_FUNCT
    def execCommand(self, cmd):
        deb.Param('Sending cmd: %s' % cmd)
        resp = ''
        deb.Return('Received response: %s' % resp)
        return resp

    @TACO_SERVER_FUNCT
    def getChanges(self):
        changes = 0
        deb.Return('Getting changes: %s' % changes)
        return changes

    @TACO_SERVER_FUNCT
    def readCcdParams(self):
        beam_params = self.readBeamParams()
        ccd_params = [0] * 10 + beam_params
        deb.Return('Getting CCD params: %s' % ccd_params)
        return ccd_params

    @TACO_SERVER_FUNCT
    def readBeamParams(self):
        beam_params = [0] * 21
        deb.Return('Getting beam params: %s' % beam_params)
        return beam_params

    @TACO_SERVER_FUNCT
    def setDebugFlags(self, deb_flags):
	deb_flags &= 0xffffffff
	deb.Param('Setting debug flags: 0x%08x' % deb_flags)
	DebParams.setTypeFlags((deb_flags   >> 16)  & 0xff)
	DebParams.setModuleFlags((deb_flags >>  0)  & 0xffff)

	deb.Trace('FormatFlags: %s' % DebParams.getFormatFlagsNameList())
	deb.Trace('TypeFlags:   %s' % DebParams.getTypeFlagsNameList())
	deb.Trace('ModuleFlags: %s' % DebParams.getModuleFlagsNameList())
    
    @TACO_SERVER_FUNCT
    def getDebugFlags(self):
	deb.Trace('FormatFlags: %s' % DebParams.getFormatFlagsNameList())
	deb.Trace('TypeFlags:   %s' % DebParams.getTypeFlagsNameList())
	deb.Trace('ModuleFlags: %s' % DebParams.getModuleFlagsNameList())

	deb_flags = (((DebParams.getTypeFlags()    & 0xff)   << 16) |
		     ((DebParams.getModuleFlags()  & 0xffff) <<  0))
	deb_flags &= 0xffffffff
	deb.Return('Getting debug flags: 0x%08x' % deb_flags)
	return deb_flags

    
class CcdServer:

    DEB_CLASS(DebModApplication, 'CcdServer')

    @DEB_MEMBER_FUNCT
    def __init__(self, bin_name, pers_name):
        self.bin_name = bin_name
        self.pers_name = pers_name
        self.server_name = '%s/%s' % (bin_name, pers_name)
        deb.Always('Getting devices for %s' % self.server_name)
        self.devices = []
        
    @DEB_MEMBER_FUNCT
    def getDevNameList(self, server_name=None):
        if server_name is None:
            server_name = self.server_name
            
        try:
            dev_name_list = dev_getdevlist(server_name)
        except:
            sys.exit(1)

        deb.Always('Devices found in database for %s' % server_name)
        for dev_name in dev_name_list:
            deb.Always('         ' + dev_name)

        return dev_name_list

    @DEB_MEMBER_FUNCT
    def addDev(self, dev):
        deb.Param('Adding device %s' % dev.dev_name)
        self.devices.append(dev)

    @DEB_MEMBER_FUNCT
    def startup(self, sleep_forever=1):
        server_startup(self.devices, self.pers_name, self.bin_name)

        if sleep_forever:
            deb.Always('That\'s all! Going to sleep ...')
            while 1:
                time.sleep(.01)

        
def main(argv):
    bin_name = os.path.basename(argv[0])
    try:
        pers_name = argv[1]
    except:
        print 'Usage: %s <pers_name>' % bin_name
        sys.exit(1)
		
    server = CcdServer(bin_name, pers_name)
    

if __name__ == '__main__':
    main(sys.argv)
    
        


    
