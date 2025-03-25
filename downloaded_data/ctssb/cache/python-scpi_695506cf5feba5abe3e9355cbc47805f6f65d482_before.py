"""ROHDE&SCHWARZ CMD57 specific device implementation and helpers"""

from scpi import scpi_device

class cmd57(scpi_device):
    """Adds the ROHDE&SCHWARZ CMD57 specific SCPI commands as methods"""

    def __init__(self, transport, *args, **kwargs):
        """Initializes a device for the given transport"""
        super(cmd57, self).__init__(transport, *args, **kwargs)
        self.scpi.command_timeout = 5 # Seconds
        self.scpi.ask_default_wait = 0 # Seconds

    ######################################
    ###   Low level functions
    ######################################

    def ask_installed_options(self):
        """ List installed option """
        return self.scpi.ask_str_list("*OPT?")

    #
    # 2.1 Input and Output
    #

    def ask_io_used(self):
        """ 2.1 Input and output used
            See set_io_used() for supported values """
        return self.scpi.ask_str("ROUTe:IOConnector?")

    def set_io_used(self, io):
        """ 2.1 Input and output used
            Supported values:
              I1O1  - Input: RF In/Out   Output: RF In/Out
              I1O2  - Input: RF In/Out   Output: RF Out 2
              I2O1  - Input: RF In 2     Output: RF In/Out
              I2O2  - Input: RF In 2     Output: RF Out 2     """
        return self.scpi.send_command("ROUTe:IOConnector %s" % io, False)

    def parse_io_str(self, io):
        """ Returns array with [RF_In_num, RF_Out_num] """
        if len(io) != 4:
            return None
        return [int(io[1:2]), int(io[3:4])]

    def parse_io_str(self, in_num, out_num):
        if not in_num in [0,1] or not out_num in [0,1]:
            return None
        return "I%dO%d" % (in_num, out_num)

    def ask_ext_att_rf_in1(self):
        """ 2.1 External Attenuation at RF In 1 """
        return self.scpi.ask_float("SENSe1:CORRection:LOSS?")

    def set_ext_att_rf_in1(self, att):
        """ 2.1 External Attenuation at RF In 1 """
        return self.scpi.send_command("SENSe1:CORRection:LOSS %f" % att, False)

    def ask_ext_att_rf_out1(self):
        """ 2.1 External Attenuation at RF Out 1 """
        return self.scpi.ask_float("SOURce1:CORRection:LOSS?")

    def set_ext_att_rf_out1(self, att):
        """ 2.1 External Attenuation at RF Out 1 """
        return self.scpi.send_command("SOURce1:CORRection:LOSS %f" % att, False)

    def ask_ext_att_rf_in2(self):
        """ 2.1 External Attenuation at RF In 2 """
        return self.scpi.ask_float("SENSe2:CORRection:LOSS?")

    def set_ext_att_rf_in2(self, att):
        """ 2.1 External Attenuation at RF In 2 """
        return self.scpi.send_command("SENSe2:CORRection:LOSS %f" % att, False)

    def ask_ext_att_rf_out2(self):
        """ 2.1 External Attenuation at RF Out 2 """
        return self.scpi.ask_float("SOURce2:CORRection:LOSS?")

    def set_ext_att_rf_out2(self, att):
        """ 2.1 External Attenuation at RF Out 2 """
        return self.scpi.send_command("SOURce2:CORRection:LOSS %f" % att, False)

    #
    # 2.2.1 Signaling Parameters of the BTS
    #

    def ask_bts_mcc(self):
        """ 2.2.1 Detected BTS MCC """
        return self.scpi.ask_int("SENSE:SIGN:IDEN:MCC?")

    def ask_bts_mnc(self):
        """ 2.2.1 Detected BTS MNC """
        return self.scpi.ask_int("SENSE:SIGN:IDEN:MNC?")

    def ask_bts_bsic(self):
        """ 2.2.1 Detected BTS BSIC
            Returned as two digit integer XY.
            First digit  X - NCC
            Second digit Y - BCC   """
        return self.scpi.ask_int("SENSE:SIGN:BSIC?")

    def ask_bts_ccch_arfcn(self):
        """ 2.2.2 Configured CCCH ARFCN """
        return self.scpi.ask_int("CONF:CHAN:BTS:CCCH:ARFCN?")

    def set_bts_ccch_arfcn(self, arfcn):
        """ 2.2.2 Configure CCCH ARFCN """
        return self.scpi.send_command("CONF:CHAN:BTS:CCCH:ARFCN %d"%int(arfcn), False)

    def ask_bts_tch_arfcn(self):
        """ 2.2.2 Configured TCH ARFCN """
        return self.scpi.ask_int("CONF:CHAN:BTS:TCH:ARFCN?")

    def set_bts_tch_arfcn(self, arfcn):
        """ 2.2.2 Configure TCH ARFCN """
        return self.scpi.send_command("CONF:CHAN:BTS:TCH:ARFCN %d"%int(arfcn), False)

    def ask_bts_tch_ts(self):
        """ 2.2.2 Configured TCH timeslot """
        return self.scpi.ask_int("CONF:CHAN:BTS:TCH:SLOT?")

    def set_bts_tch_ts(self, slot):
        """ 2.2.2 Configure TCH timeslot """
        return self.scpi.send_command("CONF:CHAN:BTS:TCH:SLOT %d"%int(slot), False)

    def ask_bts_tsc(self):
        """ 2.2.2 Configured BTS TSC """
        return self.scpi.ask_int("CONF:CHAN:BTS:TSC?")

    def set_bts_tsc(self, tsc):
        """ 2.2.2 Configur BTS TSC """
        return self.scpi.send_command("CONF:CHAN:BTS:TSC %d"%int(tsc), False)

    #
    # 2.3 Burst Analysis
    #

    def ask_ban_arfcn(self):
        """ 2.3 Burst Analysis (Module testing) / Channel number (ARFCN) """
        return self.scpi.ask_int("CONF:CHAN:BANalysis:ARFCn?")

    def set_ban_arfcn(self, arfcn):
        """ 2.3 Burst Analysis (Module testing) / Channel number (ARFCN) """
        return self.scpi.send_command("CONF:CHAN:BANalysis:ARFCn %d"%int(arfcn), False)

    def ask_mod_freq(self):
        """ 2.3 Burst Analysis (Module testing) / Channel frequency
            WARN: UNSUPPORTED? """
        return self.scpi.ask_float("CONF:CHAN:MODalysis:ARFCn:FREQ?")

    def set_mod_freq(self, freq):
        """ 2.3 Burst Analysis (Module testing) / Channel frequency
            WARN: UNSUPPORTED? """
        return self.scpi.send_command("CONF:CHAN:MODalysis:ARFCn:FREQ %f"%float(freq), False)

    def ask_ban_tsc(self):
        """ 2.3 Burst Analysis (Module testing) TSC """
        return self.scpi.ask_int("CONF:CHAN:BANalysis:TSC?")

    def set_ban_tsc(self, tsc):
        """ 2.3 Burst Analysis (Module testing) TSC """
        return self.scpi.send_command("CONF:CHAN:BANalysis:TSC %d"%int(tsc), False)

    def ask_ban_expected_power(self):
        """ 2.3 Burst Analysis (Module testing) Expected power (of BTS) """
        return self.scpi.ask_float("CONF:BANalysis:POWer:EXPected?")

    def set_ban_expected_power(self, pwr):
        """ 2.3 Burst Analysis (Module testing) Expected power (of BTS) """
        return self.scpi.send_command("CONF:BANalysis:POWer:EXPected %f"%float(pwr), False)

    def ask_ban_input_bandwidth(self):
        """ 2.3 Burst Analysis (Module testing) Input Bandwidth for measurement of peak power """
        return self.scpi.ask_str("CONF:BANalysis:POWer:BANDwidth:INPut1?")

    def set_ban_input_bandwidth(self, band):
        """ 2.3 Burst Analysis (Module testing) Input Bandwidth for measurement of peak power
            Supported values:
              NARRow - Narrowband measurement
              WIDE   - Wideband measurement   """
        return self.scpi.send_command("CONF:BANalysis:POWer:BANDwidth:INPut1 %s"%band, False)

    def ask_ban_trigger_mode(self):
        """ 2.3 Burst Analysis (Module testing) Trigger mode """
        return self.scpi.ask_str("CONF:BANalysis:TRIGger:MODE?")

    def set_ban_trigger_mode(self, mode):
        """ 2.3 Burst Analysis (Module testing) Trigger mode
            Supported values:
              POWer    - Trigger on rising signal edge
              FREerun  - Trigger without slope   """
        return self.scpi.send_command("CONF:BANalysis:TRIGger:MODE %s"%mode, False)

    #
    # 2.4 Network and Test Mode
    #

    def ask_test_mode(self):
        """ 2.4 Test mode
            See set_test_mode() for the list of supported modes
        """
        return self.scpi.ask_str("PROCedure:SEL?")

    def set_test_mode(self, mode):
        """ 2.4 Test mode
            Supported modes:
              NONE        - No tes mode (switch on state)
              MANual      - BTS test without signaling
              SIGNal      - BTS test with signaling (requires option K30)
              MODultest   - Module test (same as BAN?) (requires option B4)
              BANalysis   - Burst analysis (same as MOD?)
              RFM         - RF generator (same as RFG?)
              RFGenerator - RF generator (same as RFM?)
              IQSPec      - IQ spectrum (requires option K43)
        """
        return self.scpi.send_command("PROCedure:SEL %s"%str(mode), False)

    def bcch_sync(self):
        """ 3 Perform Synchronization with BCCH or Wired Sync """
        # TODO: Introduce longer timeout
        return self.scpi.send_command("PROCedure:SYNChronize", False)

    def ask_sync_state(self):
        """ 3 Selected Measurement State
            See set_sync_state() for the list of supported modes
        """
        return self.scpi.ask_str("PROCedure:BTSState?")

    def set_sync_state(self, state):
        """ 3 Selecting Measurement State
            Supported states:
              BIDL      - Idle
              BBCH      - BCCH measurements
              BTCH      - TCH measurements
              BEXTernal - BER measurements with RS232 / IEEE488
        """
        return self.scpi.send_command("PROCedure:BTSState %s"%str(state), False)

    def ask_power_mask_match(self):
        """ 7.3.1 Power Tolerance values / Query for observance of the tolerances of the power/time template
            Valid in: BTCH, MOD
            Unit: dBm  """
        return self.scpi.ask_str("CALC:LIMit:POWer:MATChing?")

    def ask_burst_power_avg(self):
        """ 7.3.2 Power Measurement / Average power of the burst (read)
            Valid in: BBCH, BTCH, BAN
            Unit: dBm  """
        return self.scpi.ask_float("READ:BURSt:POWer:AVERage?")

    def fetch_burst_power_avg(self):
        """ 7.3.2 Power Measurement / Average power of the burst (fetch)
            Valid in: BBCH, BTCH, BAN
            Unit: dBm  """
        return self.scpi.ask_float("FETCh:BURSt:POWer:AVERage?")

    def ask_burst_power_arr(self):
        """ 7.3.2 Power Measurement / Power values of the entire burst (read)
            Valid in: BTCH, BAN
            Unit: dB  """
        return self.scpi.ask_float_list("READ:ARRay:BURSt:POWer?")

    def fetch_burst_power_arr(self):
        """ 7.3.2 Power Measurement / Power values of the entire burst (fetch)
            Valid in: BTCH, BAN
            Unit: dB  """
        return self.scpi.ask_float_list("FETCh:ARRay:BURSt:POWer?")

    def ask_phase_freq_match(self):
        """ 7.4.1 Phase and Frequency Errors / Tolerance values / Query for observance of tolerances (single-value measurment)
            Valid in: BBCH, BTCH, BAN, MOD
            Return: (MATC | NMAT | INV) for each of:
                    - Peak phase error
                    - RMS phase error
                    - Frequency error """
        return self.scpi.ask_str_list("CALCulate:LIMit:PHFR:TOLerance:MATChing?")

    def ask_phase_freq_match_avg(self):
        """ 7.4.1 Phase and Frequency Errors / Tolerance values / Query for observance of tolerances (average measurment)
            Valid in: BTCH, BAN, MOD
            Return: (MATC | NMAT | INV) for each of:
                    - Peak phase error
                    - RMS phase error
                    - Frequency error """
        return self.scpi.ask_str_list("CALCulate:LIMit:PHFR:TOLerance:MATChing:AVERage?")

    def ask_phase_freq_match_max(self):
        """ 7.4.1 Phase and Frequency Errors / Tolerance values / Query for observance of tolerances (max measurment)
            Valid in: BTCH, BAN, MOD
            Return: (MATC | NMAT | INV) for each of:
                    - Peak phase error
                    - RMS phase error
                    - Frequency error """
        return self.scpi.ask_str_list("CALCulate:LIMit:PHFR:TOLerance:MATChing:MAXimum?")

    def ask_phase_err_rms(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst RMS (single-value measurment, execute)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("READ:BURSt:PHASe:ERRor:RMS?")

    def fetch_phase_err_rms(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst RMS (single-value measurment, fetch)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("FETCh:BURSt:PHASe:ERRor:RMS?")

    def ask_phase_phase_err_pk(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst Peak (single-value measurment, execute)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("READ:BURSt:PHASe:ERRor:PEAK?")

    def fetch_phase_phase_err_pk(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst Peak (single-value measurment, fetch)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("FETCh:BURSt:PHASe:ERRor:PEAK?")

    def ask_spectrum_modulation_match(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Query for observance of tolerances of the Spectrum (Modulation)
            Note: Supplies result for the last measurement
            Valid in: BTCH, MOD
            Return: (MATC | NMAT | INV) """
        return self.scpi.ask_str("CALCulate:LIMit:SPECtrum:MODulation:MATChing?")

    def ask_spectrum_switching_match(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Query for observance of tolerances of the Spectrum (Switching)
            Note: Supplies result for the last measurement
            Valid in: BTCH, MOD
            Return: (MATC | NMAT | INV) """
        return self.scpi.ask_str("CALCulate:LIMit:SPECtrum:SWITching:MATChing?")

    def ask_spectrum_modulation(self):
        """ 7.5.3 Executing Spectrum Measurement (Modulation)
            Valid in: BTCH, MOD  """
        # TODO: LONG operation
        return self.scpi.ask_float_list("READ:ARRay:SPECtrum:MODulation?")

    def fetch_spectrum_modulation(self):
        """ 7.5.3 Executing Spectrum Measurement (Modulation)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float_list("FETCh:ARRay:SPECtrum:MODulation?")

    def ask_spectrum_switching(self):
        """ 7.5.3 Executing Spectrum Measurement (Switching)
            Valid in: BTCH, MOD  """
        # TODO: LONG operation
        return self.scpi.ask_float_list("READ:ARRay:SPECtrum:BTS:SWITching?")

    def fetch_spectrum_switching(self):
        """ 7.5.3 Executing Spectrum Measurement (Switching)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float_list("FETCh:ARRay:SPECtrum:BTS:SWITching?")

    def ask_peak_power(self):
        """ 7.8 Other measurements / Peak Power Measurement (read) """
        return self.scpi.ask_float("READ:POWer?")

    def fetch_peak_power(self):
        """ 7.8 Other measurements / Peak Power Measurement (fetch) """
        return self.scpi.ask_float("FETCh:POWer?")

    def ask_dev_state(self):
        """ 9.1 Current Device State """
        return self.scpi.ask_str("STATus:DEVice?")

    ######################################
    ###   High level functions
    ######################################



def rs232(port, **kwargs):
    """Quick helper to connect via RS232 port"""
    import serial as pyserial
    from scpi.transports import rs232 as serial_transport

    # Try opening at 2400 baud (default setting) and switch to 9600 baud
    serial_port = pyserial.Serial(port, 2400, timeout=0, **kwargs)
    transport = serial_transport(serial_port)
    dev = cmd57(transport)
    dev.scpi.command_timeout = 0.1 # Seconds
    try:
        dev.scpi.send_command_unchecked(":SYSTem:COMMunicate:SERial:BAUD 9600", expect_response=False)
    except:
        # It's ok to fail, because we can already be at 9600
        pass
    dev.quit()

    # Now we should be safe to open at 9600 baud
    serial_port = pyserial.Serial(port, 9600, timeout=0, **kwargs)
    transport = serial_transport(serial_port)
    dev = cmd57(transport)
    # Clear error status
    dev.scpi.send_command("*CLS", expect_response=False)
    # This must be excessive, but check that we're actually at 9600 baud
    ret = dev.scpi.ask_int(":SYSTem:COMMunicate:SERial:BAUD?")
    if ret != 9600:
       raise Exception("Can't switch to 9600 baud!")

    return dev

