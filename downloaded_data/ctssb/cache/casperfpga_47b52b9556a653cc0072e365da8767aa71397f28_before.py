from synth import *
from adc import *
from clockswitch import *
from wishbonedevice import WishBoneDevice
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

# Some codes and docstrings are copied from https://github.com/UCBerkeleySETI/snap_control
class SNAPADC(object):

    RESOLUTION  = 8

    adc = None
    lmx = None
    clksw = None
    ram = None

    # Current delay tap settings for all IDELAYE2
    curDelay = None

    # Wishbone address and mask for read
    WB_DICT = [None] * ((0b11 << 2) + 1)

    WB_DICT[0b00 << 2] = {  'G_ZDOK_REV' : 0b11 << 28,
                'ADC16_LOCKED' : 0b11 << 24,
                'G_NUM_UNITS' : 0b1111 << 20,
                'CONTROLLER_REV' : 0b11 << 18,
                'G_ROACH2_REV' : 0b11 << 16,
                'ADC16_ADC3WIRE_REG' : 0b1111111111111111 << 0,}

    WB_DICT[0b01 << 2] = {'ADC16_CTRL_REG' : 0xffffffff << 0}
    WB_DICT[0b10 << 2] = {'ADC16_DELAY_STROBE_REG_H' : 0xffffffff << 0}
    WB_DICT[0b11 << 2] = {'ADC16_DELAY_STROBE_REG_L' : 0xffffffff << 0}

    # Wishbone address and mask for write
    A_WB_W_3WIRE = 0 << 0
    A_WB_W_CTRL = 1 << 0
    A_WB_W_DELAY_STROBE_L = 2 << 0
    A_WB_W_DELAY_STROBE_H = 3 << 0

    M_WB_W_DEMUX_WRITE      = 0b1 << 26
    M_WB_W_DEMUX_MODE       = 0b11 << 24
    M_WB_W_RESET            = 0b1 << 20
    M_WB_W_SNAP_REQ         = 0b1 << 16
    M_WB_W_DELAY_TAP        = 0b11111 << 0
    M_WB_W_ISERDES_BITSLIP_CHIP_SEL = 0b11111111 << 8
    M_WB_W_ISERDES_BITSLIP_LANE_SEL = 0b111 << 5

    SUCCESS = 0
    ERROR_LMX = 1
    ERROR_MMCM = 2
    ERROR_LINE = 3
    ERROR_FRAME = 4
    ERROR_RAMP = 5

    def __init__(self, interface, ADC='HMCAD1511', defaultDelayTap=0, ref=10):
        # interface => corr.katcp_wrapper.FpgaClient('10.1.0.23')

        self.A_WB_R_LIST = [self.WB_DICT.index(a) for a in self.WB_DICT if a != None]
        self.adcList = [0, 1, 2]
        self.ramList = ['adc16_wb_ram0', 'adc16_wb_ram1', 'adc16_wb_ram2']
        self.laneList = [0, 1, 2, 3, 4, 5, 6, 7]

        self.curDelay = [[defaultDelayTap]*len(self.laneList)]*len(self.adcList)

        if ref is not None:
            self.lmx = LMX2581(interface,'lmx_ctrl', fosc=ref)
        else:
            self.lmx = None

        self.clksw = HMC922(interface,'adc16_use_synth')
        self.ram = [WishBoneDevice(interface,name) for name in self.ramList]

        if ADC not in ['HMCAD1511','HMCAD1520']:
            raise ValueError("Invalid parameter")

        if ADC == 'HMCAD1511':
            self.adc = HMCAD1511(interface,'adc16_controller')
        else:   # 'HMCAD1520'
            self.adc = HMCAD1520(interface,'adc16_controller')

        # test pattern for clock aligning
        pats = [0b10101010,0b01010101,0b00000000,0b11111111]
        mask = (1<<(self.RESOLUTION/2))-1
        ofst = self.RESOLUTION/2
        self.p1 = ((pats[0] & mask) << ofst) + (pats[3] & mask)
        self.p2 = ((pats[1] & mask) << ofst) + (pats[2] & mask)

    def init(self, samplingRate=250, numChannel=4, resolution=None):
        """ Get SNAP ADCs into working condition

        Supported frequency range: 60MHz ~ 1000MHz. Set resolution to
        None to let init() automatically decide the best resolution.

        A run of init() takes approximatly 20 seconds, involving the
        following actions:

        1. configuring frequency synthesizer LMX2581
        2. configuring clock source switch HMC922
        3. configuring ADCs HMCAD1511 (support HMCAD1520 in future)
        4. configuring IDELAYE2 and ISERDESE2 inside of FPGA
        5. Testing under dual pattern and ramp mode

        E.g.
            init(1000,1)    1 channel mode, 1Gsps, 8bit, since 1Gsps
                    is only available in 8bit mode
            init(320,2) 2 channel mode, 320Msps, 8bit for HMCAD1511,
                    or 12bit for HMCAD1520
            init(160,4,8)   4 channel mode, 160Msps, 8bit resolution

        """

        if resolution==None:
            if type(self.adc) is HMCAD1511:
                self.RESOLUTION=8
            elif samplingRate/(4/numChannel)>160:
                self.RESOLUTION=8
            else:
                self.RESOLUTION=12
        elif resolution not in [8,12,14,None]:
            raise ValueError("Invalid parameter")
        elif resolution>8 and samplingRate/(4/numChannel)>160:
            raise ValueError("Invalid parameter")

        logging.info("Reseting adc_unit")
        self.reset()

        self.selectADC()

        if self.lmx is not None:
            logging.info("Reseting frequency synthesizer")
            self.lmx.init()

            logging.info("Configuring frequency synthesizer")
            self.lmx.setFreq(samplingRate)
            if not self.lmx.getDiagnoses('LD_PINSTATE'):
                return self.ERROR_LMX

        logging.info("Configuring clock source switch")
        if self.lmx is not None:
            self.clksw.setSwitch('a')
        else:
            self.clksw.setSwitch('b')

        logging.info("Initialising ADCs")
        self.adc.init()

        if numChannel==1 and samplingRate<240:
            lowClkFreq = True
        elif numChannel==2 and samplingRate<120:
            lowClkFreq = True
        elif numChannel==4 and samplingRate<60:
            lowClkFreq = True
        elif numChannel==4 and self.RESOLUTION==14 and samplingRate<30:
            lowClkFreq = True
        else:
            lowClkFreq = False

        logging.info("Configuring ADC operating mode")
        if type(self.adc) is HMCAD1511:
            self.adc.setOperatingMode(numChannel,1,lowClkFreq)
        elif type(self.adc) is HMCAD1520:
            self.adc.setOperatingMode(numChannel,1,lowClkFreq,resolution)

        self.setDemux(numChannel=1) # calibrate in full interleave mode

        if not self.getWord('ADC16_LOCKED'):
            logging.error('MMCM not locked.')
            return self.ERROR_MMCM

        if not self.alignLineClock():
            return self.ERROR_LINE
        if not self.alignFrameClock():
            return self.ERROR_FRAME

        errs = self.testPatterns(mode='ramp')
        if not np.all(np.array([adc.values() for adc in errs.values()])==0):
            logging.error('ADCs failed on ramp test.')
            return self.ERROR_RAMP

        # Finally place ADC in "correct" mode
        self.setDemux(numChannel=numChannel)

        return self.SUCCESS

    def selectADC(self, chipSel=None):
        """ Select one or multiple ADCs

        Select the ADC(s) to be configured. ADCs are numbered by 0, 1, 2...
        E.g.
            selectADC(0)        # select the 1st ADC
            selectADC([0,1])    # select two ADCs
            selectADC()     # select all ADCs
        """

        # csn active low for HMCAD1511, but inverted in wb_adc16_controller
        if chipSel==None:       # Select all ADC chips
            self.adc.csn = np.bitwise_or.reduce([0b1 << s for s in self.adcList])
        elif isinstance(chipSel, list) and all(s in self.adcList for s in chipSel):
            csnList = [0b1 << s for s in self.adcList if s in chipSel]
            self.adc.csn = np.bitwise_or.reduce(csnList)
        elif chipSel in self.adcList:
            self.adc.csn = 0b1 << chipSel
        else:
            raise ValueError("Invalid parameter")

    def setDemux(self, numChannel=1):
        """
        when mode==0: numChannel=4
            data = data[:,[0,4,1,5,2,6,3,7]]
        when mode==1: numChannel=2
            data = data[:,[0,1,4,5,2,3,6,7]]
        when mode==2: numChannel=1
            data = data[:,[0,1,2,3,4,5,6,7]]
        """
        modeMap = {4:0, 2:1, 1:2} # mapping of numChannel to mode
        if numChannel not in mode.keys():
            raise ValueError("Invalid parameter")
        mode = modeMap[numChannel]
        val = self._set(0x0, mode,  self.M_WB_W_DEMUX_MODE)
        val = self._set(val, 0b1,   self.M_WB_W_DEMUX_WRITE)
        self.adc._write(val, self.A_WB_W_CTRL)

    def reset(self):
        """ Reset all adc16_interface logics inside FPGA """
        val = self._set(0x0, 0x1,   self.M_WB_W_RESET)
        self.adc._write(0x0, self.A_WB_W_CTRL)
        self.adc._write(val, self.A_WB_W_CTRL)
        self.adc._write(0x0, self.A_WB_W_CTRL)

    def snapshot(self):
        """ Save 1024 consecutive samples of each ADC into its corresponding bram """
        # No way to snapshot a single ADC because the HDL code is designed so.
        val = self._set(0x0, 0x1,   self.M_WB_W_SNAP_REQ)
        self.adc._write(0x0, self.A_WB_W_CTRL)
        self.adc._write(val, self.A_WB_W_CTRL)
        self.adc._write(0x0, self.A_WB_W_CTRL)

    def calibrateAdcOffset(self):

        logging.warning('Operation not supported.')


    def calibrationAdcGain(self):

        logging.warning('Operation not supported.')

        
    def getRegister(self, rid=None):
        if rid==None:
            return [self.getRegister(regId) for regId in self.A_WB_R_LIST]
        elif rid in self.A_WB_R_LIST:
            rval = self.adc._read(rid)
            return {name: self._get(rval,mask) for name, mask in self.WB_DICT[rid].items()}
        else:
            raise ValueError("Invalid parameter")

    def _get(self, data, mask):
        data = data & mask
        return data / (mask & -mask)

    def _set(self, d1, d2, mask=None):
        # Update some bits of d1 with d2, while keep other bits unchanged
        if mask:
            d1 = d1 & ~mask
            d2 = d2 * (mask & -mask)
        return d1 | d2

    def getWord(self,name):
        rid = self.getRegId(name)
        rval = self.adc._read(rid)
        return self._get(rval,self.WB_DICT[rid][name])

    def getRegId(self,name):
        rid = [d for d in self.A_WB_R_LIST if name in self.WB_DICT[d]]
        if len(rid) == 0:
            raise ValueError("Invalid parameter")
        else:
            return rid[0]

    def interleave(self,data,mode):
        """ Reorder the data according to the interleaving mode

        E.g.
            data = numpy.arange(1024).reshape(-1,8)
            interleave(data, 1) # return a one-column numpy array
            interleave(data, 2) # return a two-column numpy array
            interleave(data, 4) # return a four-column numpy array
        """
        return self.adc.interleave(data, mode)

    def readRAM(self, ram=None):
        """ Read RAM(s) and return the 1024-sample data

        E.g.
            readRAM()       # read all RAMs, return a list of arrays
            readRAM(1)      # read the 2nd RAMs, return a 128X8 array
            readRAM([0,1])      # read 2 RAMs, return two arrays
        """
        if ram==None:                       # read all RAMs
            return self.readRAM(self.adcList)
        elif isinstance(ram, list) and all(r in self.adcList for r in ram):
                                    # read a list of RAMs
            data = [self.readRAM(r) for r in ram if r in self.adcList]
            return dict(zip(ram,data))
        elif ram in self.adcList:               # read one RAM      
            if self.RESOLUTION>8:       # ADC_DATA_WIDTH == 16
                fmt = '!1024h'
            else:               # ADC_DATA_WIDTH == 8
                fmt = '!1024b'
            vals = self.ram[ram]._read(addr=0, size=1024)
            vals = np.array(struct.unpack(fmt,vals)).reshape(-1,8)

            return vals
        else:
            raise ValueError("Invalid parameter")

    # A lane in this method actually corresponds to a "branch" in HMCAD1511 datasheet.
    # But I have to follow the naming convention of signals in casper repo.
    def bitslip(self, chipSel=None, laneSel=None):
        """ Reorder the parallelize data for word-alignment purpose
        
        Reorder the parallelized data by asserting a itslip command to the bitslip 
        submodule of a ISERDES primitive.  Each bitslip command left shift the 
        parallelized data by one bit.

        E.g.
            bitslip()       # left shift all lanes of all ADCs
            bitslip(0)      # shift all lanes of the 1st ADC
            bitslip(0,3)        # shift the 4th lane of the 1st ADC
            bitslip([0,1],[3,4])    # shift the 4th and 5th lanes of the 1st
                        # and the 2nd ADCs
        """

        if chipSel == None:
            chipSel = self.adcList
        elif chipSel in self.adcList:
            chipSel = [chipSel]

        if not isinstance(chipSel,list):
            raise ValueError("Invalid parameter")
        elif isinstance(chipSel,list) and any(cs not in self.adcList for cs in chipSel):
            raise ValueError("Invalid parameter")

        if laneSel == None:
            laneSel = self.laneList
        elif laneSel in self.laneList:
            laneSel = [laneSel]

        if not isinstance(laneSel,list):
            raise ValueError("Invalid parameter")
        elif isinstance(laneSel,list) and any(cs not in self.laneList for cs in laneSel):
            raise ValueError("Invalid parameter")

        logging.debug('Bitslip lane {0} of chip {1}'.format(str(laneSel),str(chipSel)))

        for cs in chipSel:
            for ls in laneSel:
                val = self._set(0x0, 0b1 << cs, self.M_WB_W_ISERDES_BITSLIP_CHIP_SEL)
                val = self._set(val, ls, self.M_WB_W_ISERDES_BITSLIP_LANE_SEL)
        
                # The registers related to reset, request, bitslip, and other
                # commands after being set will not be automatically cleared.  
                # Therefore we have to clear them by ourselves.
        
                self.adc._write(0x0, self.A_WB_W_CTRL)  
                self.adc._write(val, self.A_WB_W_CTRL)  
                self.adc._write(0x0, self.A_WB_W_CTRL)  


    # The ADC16 controller word (the offset in write_int method) 2 and 3 are for delaying 
    # taps of A and B lanes, respectively.
    #
    # Refer to the memory map word 2 and word 3 for clarification.  The memory map was made 
    # for a ROACH design so it has chips A-H.  SNAP 1 design has three chips.
    def delay(self, tap, chipSel=None, laneSel=None):
        """ Delay the serial data from ADC LVDS links
        
        Delay the serial data by Xilinx IDELAY primitives
        E.g.
            delay(0)        # Set all delay tap of IDELAY to 0
            delay(4, 1, 7)      # set delay on the 8th lane of the 2nd ADC to 4
            delay(31, [0,1,2], [0,1,2,3,4,5,6,7])
                        # Set all delay taps (in SNAP 1 case) to 31
        """

        if chipSel==None:
            chipSel = self.adcList
        elif chipSel in self.adcList:
            chipSel = [chipSel]
        elif isinstance(chipSel, list) and any(s not in self.adcList for s in chipSel):
            raise ValueError("Invalid parameter")

        if laneSel==None:
            laneSel = self.laneList
        elif laneSel in self.laneList:
            laneSel = [laneSel]
        elif isinstance(laneSel,list) and any(s not in self.laneList for s in laneSel):
            raise ValueError("Invalid parameter")
        elif laneSel not in self.laneList:
            raise ValueError("Invalid parameter")

        if not isinstance(tap, int):
            raise ValueError("Invalid parameter")

        strl = ','.join([str(c) for c in laneSel])
        strc = ','.join([str(c) for c in chipSel])
        logging.debug('Set DelayTap of lane {0} of chip {1} to {2}'
                .format(str(laneSel),str(chipSel),tap))

        matc = np.array([(cs*4) for cs in chipSel])

        matla = np.array([int(l/2) for l in laneSel if l%2==0])
        if matla.size:
            mata =  np.repeat(matc.reshape(-1,1),matla.size,1) + \
                np.repeat(matla.reshape(1,-1),matc.size,0)
            vala = np.bitwise_or.reduce([0b1 << s for s in mata.flat])
        else:
            vala = 0
        
        matlb = np.array([int(l/2) for l in laneSel if l%2==1])
        if matlb.size:
            matb =  np.repeat(matc.reshape(-1,1),matlb.size,1) + \
                np.repeat(matlb.reshape(1,-1),matc.size,0)
            valb = np.bitwise_or.reduce([0b1 << s for s in matb.flat])
        else:
            valb = 0

        valt = self._set(0x0, tap, self.M_WB_W_DELAY_TAP)

        # Don't be misled by the naming - "DELAY_STROBE" in casper repo.  It doesn't 
        # generate strobe at all.  You have to manually clear the bits that you set.
        self.adc._write(0x00, self.A_WB_W_CTRL)
        self.adc._write(0x00, self.A_WB_W_DELAY_STROBE_L)
        self.adc._write(0x00, self.A_WB_W_DELAY_STROBE_H)
        self.adc._write(valt, self.A_WB_W_CTRL)
        self.adc._write(vala, self.A_WB_W_DELAY_STROBE_L)
        self.adc._write(valb, self.A_WB_W_DELAY_STROBE_H)
        self.adc._write(0x00, self.A_WB_W_CTRL)
        self.adc._write(0x00, self.A_WB_W_DELAY_STROBE_L)
        self.adc._write(0x00, self.A_WB_W_DELAY_STROBE_H)

        for cs in chipSel:
            for ls in laneSel:
                self.curDelay[cs][ls] = tap


    def testPatterns(self, chipSel=None, taps=None, mode='std', pattern1=None, pattern2=None):
        """ Return a list of std/err for a given tap or a list of taps

        Return the lane-wise standard deviation/error of the data under a given
        tap setting or a list of tap settings.  By default, mode='std', taps=range(32).
        'err' mode with single test pattern check data against the given pattern, while
        'err' mode with dual test patterns guess the counts of the mismatches.
        'guess' because both patterns could come up at first. This method
        always returns the smaller counts.
        'ramp' mode guess the total number of incorrect data. This is implemented based
        on the assumption that in most cases, $cur = $pre + 1. When using 'ramp' mode,
        taps=None

        E.g.
            testPatterns(taps=True) # Return lane-wise std of all ADCs, taps=range(32)
            testPatterns(0,taps=range(32))
                        # Return lane-wise std of the 1st ADC
            testPatterns([0,1],2)   # Return lane-wise std of the first two ADCs 
                        # with tap = 2
            testPatterns(1, taps=[0,2,3], mode='std')
                        # Return lane-wise stds of the 2nd ADC with
                        # three different tap settings
            testPatterns(2, mode='err', pattern1=0b10101010)
                        # Check the actual data against the given test
                        # pattern without changing current delay tap
                        # setting and return lane-wise error counts of
                        # the 3rd ADC,
            testPatterns(2, mode='err', pattern1=0b10101010, pattern2=0b01010101)
                        # Check the actual data against the given alternate
                        # test pattern without changing current delay tap
                        # setting and return lane-wise error counts of
                        # the 3rd ADC,
            testPatterns(mode='ramp')
                        # Check all ADCs under ramp mode

        """

        # The deviation looks like this:
        # {0: array([ 17.18963055,  17.18963055,  17.18963055,  17.18963055,
        #          13.05692914,  13.05692914,  13.05692914,  13.05692914]),
        #  1: array([ 14.08136755,  14.08136755,  14.08136755,  14.08136755,
        #           7.39798788,   7.39798788,   7.39798788,   7.39798788]),
        #  2: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  3: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  4: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  5: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  6: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  7: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  8: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  9: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  10: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  11: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  12: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  13: array([ 6.47320197,  7.39906033,  0.        ,  0.        ,  0.        ,
        #          0.        ,  0.        ,  0.        ]),
        #  14: array([ 16.14016176,  16.63835629,   4.66368953,   1.40867846,
        #          75.989443  ,  69.36052029,   6.92820323,   1.40867846]),
        #  15: array([ 49.30397384,  38.93917329,   7.96476616,   7.43487349,
        #          49.32813242,  49.89897448,  24.89428699,  17.29472061]),
        #  16: array([ 45.83336145,  44.495608  ,  25.20036771,  52.85748304,
        #           5.63471383,   0.        ,  45.64965087,  40.04722554]),
        #  17: array([  0.        ,   0.        ,  57.13889616,  24.2960146 ,
        #           0.        ,   0.        ,  65.0524836 ,  30.79302499]),
        #  18: array([  0.        ,   0.        ,   0.        ,   0.        ,
        #           0.        ,   0.        ,  59.11012465,   0.        ]),
        #  19: array([  0.        ,   0.        ,   0.        ,   0.        ,
        #           0.        ,   0.        ,  24.79919354,   0.        ]),
        #  20: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  21: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  22: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  23: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  24: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  25: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  26: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  27: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  28: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  29: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  30: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]),
        #  31: array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.])}
    
        MODE = ['std', 'err', 'ramp']

        if chipSel==None:
            chipSel = self.adcList
        elif chipSel in self.adcList:
            chipSel = [chipSel]
        if not isinstance(chipSel,list):
            raise ValueError("Invalid parameter")
        elif isinstance(chipSel,list) and any(cs not in self.adcList for cs in chipSel):
            raise ValueError("Invalid parameter")

        if taps==True:
            taps = range(32)
        elif taps in self.adcList:
            taps = [taps]
        if not isinstance(taps,list) and taps!=None:
            raise ValueError("Invalid parameter")
        elif isinstance(taps,list) and any(cs not in range(32) for cs in taps):
            raise ValueError("Invalid parameter")

        if mode not in MODE:
            raise ValueError("Invalid parameter")

        self.selectADC(chipSel)
        if mode=='ramp':        # ramp mode
            self.adc.test('en_ramp')
            taps=None
            pattern1=None
            pattern2=None
        elif pattern1==None and pattern2==None:
            # synchronization mode
            self.adc.test('pat_sync')
            # pattern1 = 0b11110000 when self.RESOLUTION is 8
            # pattern1 = 0b111111000000 when self.RESOLUTION is 12
            pattern1 = ((2**(self.RESOLUTION/2))-1) << (self.RESOLUTION/2)
            pattern1 = self._signed(pattern1,self.RESOLUTION)
        elif isinstance(pattern1,int) and pattern2==None:
            # single pattern mode

            if type(self.adc) is HMCAD1520:
                # test patterns of HMCAD1520 need special cares
                ofst = 16 - self.RESOLUTION
                reg_p1 = pattern1 << ofst
            else:
                reg_p1 = pattern1

            self.adc.test('single_custom_pat',reg_p1)
            pattern1 = self._signed(pattern1,self.RESOLUTION)
        elif isinstance(pattern1,int) and isinstance(pattern2,int):
            # dual pattern mode

            if type(self.adc) is HMCAD1520:
                # test patterns of HMCAD1520 need special cares
                ofst = 16 - self.RESOLUTION
                reg_p1 = pattern1 << ofst
                reg_p2 = pattern2 << ofst
            else:
                reg_p1 = pattern1
                reg_p2 = pattern2

            self.adc.test('dual_custom_pat',reg_p1,reg_p2)
            pattern1 = self._signed(pattern1,self.RESOLUTION)
            pattern2 = self._signed(pattern2,self.RESOLUTION)
        else: 
            raise ValueError("Invalid parameter")

        results = []

        def _check(data):
            d = np.array(data).reshape(-1, 8)
            if mode=='std' and pattern2==None:  # std mode, single pattern
                r = np.std(d,0)
            elif mode=='std' and pattern2!=None:    # std mode, dual patterns
                counts = [np.unique(d[:,i],return_counts=True)[1] for i in range(d.shape[1])]
                r = [np.sum(np.sort(count)[::-1][2:]) for count in counts]
            elif mode=='err' and pattern2==None:    # err mode, single pattern
                r = np.sum(d!=pattern1, 0)
            elif mode=='err' and pattern2!=None:    # err mode, dual pattern
                # Try two patterns with different order, and return the
                # result
                m1,m2 = np.zeros(d.shape),np.zeros(d.shape)
                m1[0::2,:],m1[1::2,:]=pattern1,pattern2
                m2[0::2,:],m2[1::2,:]=pattern2,pattern1
                r=np.minimum(np.sum(d!=m1,0),np.sum(d!=m2,0))
            elif mode=='ramp':          # ramp mode
                diff = d[1:,:]-d[:-1,:]
                counts=[np.unique(diff[:,ls],return_counts=True)[1] for ls in self.laneList]
                r = [d.shape[0]-1-sum(counts[ls][:2]) for ls in self.laneList]
            return r

        if taps == None:
            self.snapshot()
            results = [_check(self.readRAM(cs)) for cs in chipSel]
            results = np.array(results).reshape(len(chipSel),len(self.laneList)).tolist()
            results = dict(zip(chipSel,results))
            for cs in chipSel:
                results[cs] = dict(zip(self.laneList,results[cs]))
        else:
            for tap in taps:
                self.delay(tap, chipSel)
                self.snapshot()
                results += [_check(self.readRAM(cs)) for cs in chipSel]
            results = np.array(results).reshape(-1,len(chipSel),len(self.laneList))
            results = np.einsum('ijk->jik',results).tolist()
            results = dict(zip(chipSel,results))
            for cs in chipSel:
                results[cs] = dict(zip(taps,[np.array(row) for row in results[cs]]))
        
        self.adc.test('off')

        if len(chipSel) == 1:
            return results[chipSel[0]]
        else:
            return results

    def _signed(self, data, res=8):
        """ Convert unsigned number to signed number

        adc16_interface converts ADC outputs into signed numbers by flipping MSB.
        Therefore we have to prepare signed-number test patterns as well.
        """
        width = 16 if res>8 else 8
        msb = (data & (1 << res-1) == 0) << width - 1
        data = data & (0xffff - (1 << res-1)) | msb
        data = data-(1<<width) if msb else data
        return data
        

    def decideDelay(self, data):
        """ Decide and return proper setting for delay tap

        Find the tap setting that has the largest margin of error, i.e. the biggest distance
        to borders (tap=0 and tap=31) and rows with non-zero deviations/mismatches.  The
        parameter data is a 32 by n numpy array, in which the 1st dimension index indicates
        the delay tap setting
        """

        if not isinstance(data,np.ndarray):
            raise ValueError("Invalid parameter")
        elif data.ndim==1:
            data = data.reshape(-1,1)
        elif data.ndim>2:
            raise ValueError("Invalid parameter")

        data = np.sum(data,1)

        if all(d != 0 for d in data):
            return False
            
        dist=np.zeros(data.shape)
        curDist = 0
        for i in range(data.size):
            if data[i] != 0:
                curDist = 0
            else:
                curDist += 1
            dist[i] = curDist
        curDist = 0
        for i in list(reversed(range(data.size))):
            if data[i] != 0:
                curDist = 0
            else:
                curDist += 1
            if dist[i] > curDist:
                dist[i] = curDist

        return np.argmax(dist)

    # Line clock also known as bit clock in ADC datasheets
    def alignLineClock(self, mode='dual_pat'):
        """ Align the rising edge of line clock with data eye

        And return the tap settings being using
        """

        MODE = ['lane_wise_single_pat','chip_wise_single_pat','dual_pat']

        if mode not in MODE:
            raise ValueError("Invalid parameter")
            
        taps = []

        if mode == 'lane_wise_single_pat':
            # Decide lane-wise delay tap under single pattern test mode
            stds = self.testPatterns(taps=True) # Sweep tap settings and get std
            for adc in self.adcList:
                for lane in self.laneList:
                    vals = np.array(stds[adc].values())[:,lane]
                    t = self.decideDelay(vals)  # Find a proper tap setting 
                    if not t:
                        logging.error("ADC{0} lane{1} delay decision failed".format(adc,lane))
                    else:
                        self.delay(t,adc,lane)  # Apply the tap setting

        elif mode == 'chip_wise_single_pat':
            # This method would give all lanes of an ADC the same delay tap setting
            # decide chip-wise delay tap under single pattern test mode
            stds = self.testPatterns(taps=True) # Sweep tap settings and get std
            for adc in self.adcList:
                vals = np.array(stds[adc].values())
                t = self.decideDelay(vals)  # Find a proper tap setting 
                if not t:
                    logging.error("ADC{0} delay decision failed".format(adc))
                else:
                    self.delay(t,adc)   # Apply the tap setting

        elif mode == 'dual_pat':    # dual_pat
            # Fine tune delay tap under dual pattern test mode

            errs = self.testPatterns(taps=True,mode='std',pattern1=self.p1,
                        pattern2=self.p2)

            for adc in self.adcList:
                for lane in self.laneList:
                    vals = np.array(errs[adc].values())[:,lane]
                    t = self.decideDelay(vals)  # Find a proper tap setting 
                    if not t:
                        logging.error("ADC{0} lane{1} delay decision failed".format(adc,lane))
                    else:
                        self.delay(t,adc,lane)  # Apply the tap setting

        # Check if line clock aligned
        errs = self.testPatterns(mode='std',pattern1=self.p1,pattern2=self.p2)
        if np.all(np.array([adc.values() for adc in errs.values()])==0):
            logging.info('Line clock of all ADCs aligned.')
            return True
        else:
            logging.error('Line clock NOT aligned.\n{0}'.format(str(errs)))
            return False

    def alignFrameClock(self):
        """ Align the frame clock with data frame
        """

        for u in range(self.RESOLUTION*2):
            allDone = True
            errs = self.testPatterns(mode='err',pattern1=self.p1,pattern2=self.p2)
            for adc in self.adcList:
                for lane in self.laneList:
                    if errs[adc][lane]!=0:
                        self.bitslip(adc,lane)
                        allDone = False
            if allDone:
                break;

        # Check if frame clock aligned
        errs = self.testPatterns(mode='err',pattern1=self.p1,pattern2=self.p2)
        if all(all(val==0 for val in adc.values()) for adc in errs.values()):
            logging.info('Frame clock of all ADCs aligned.')
            return True
        else:
            logging.error('Frame clock NOT aligned.\n{0}'.format(str(errs)))
            return False

