"""ROHDE&SCHWARZ CMD57 specific device implementation and helpers"""

from scpi import scpi_device

class cmd57(scpi_device):
    """Adds the ROHDE&SCHWARZ CMD57 specific SCPI commands as methods"""

    def __init__(self, transport, *args, **kwargs):
        """Initializes a device for the given transport"""
        super(cmd57, self).__init__(transport, *args, **kwargs)
        self.scpi.command_timeout = 60 # Seconds
        self.scpi.ask_default_wait = 0 # Seconds

    ######################################
    ###   Helper functions
    ######################################

    def _format_float_list(val_list):
        return ",".join(["%.2f"%x for x in val_list])
    def _format_int_list(val_list):
        return ",".join(["%d"%x for x in val_list])
    def _format_str_list(val_list):
        return ",".join(val_list)

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

    def make_io_str(self, in_num, out_num):
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

    #
    # 2.2.2 Signaling Parameters for CMD
    #

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
        """ 2.2.2 Configure BTS TSC """
        return self.scpi.send_command("CONF:CHAN:BTS:TSC %d"%int(tsc), False)

    def ask_bts_expected_power(self):
        """ 2.2.2 Configured BTS Expected Power """
        return self.scpi.ask_float("CONF:BTS:POWer:EXPected?")

    def set_bts_expected_power(self, power):
        """ 2.2.2 Configure BTS Expected Power """
        return self.scpi.send_command("CONF:BTS:POWer:EXPected %.2f"%float(power), False)

    def ask_bts_tch_tx_power(self):
        """ 2.2.2 Configured BTS Transmitter power of the TCH in the used timeslot """
        return self.scpi.ask_float("CONF:CHANnel:BTS?")

    def set_bts_tch_tx_power(self, power):
        """ 2.2.2 Configure BTS Transmitter power of the TCH in the used timeslot """
        return self.scpi.send_command("CONF:CHANnel:BTS %.2f"%float(power), False)

    def ask_bts_tch_mode(self):
        """ 2.2.2 Configured BTS Selection of modulation contents on the TCH
            See set_bts_tch_mode() for details   """
        return self.scpi.ask_str("CONF:SPEech:MODE?")

    def set_bts_tch_mode(self, mode):
        """ 2.2.2 Configure BTS Transmitter power of the TCH in the used timeslot
            Supported values:
              ECHO    - Loopback in the CMD with delay
              LOOP    - Loopback in the CMD with minimum possible delay
              PR9     - 2e9-1 PSR bit pattern
              PR11    - 2e11-1 PSR bit pattern
              PR15    - 2e15-1 PSR bit pattern
              PR16    - 2e16-1 PSR bit pattern
              HANDset - Speech coder/decoder mode (requires hardware option) """
        return self.scpi.send_command("CONF:SPEech:MODE %s"%str(mode), False)

    def ask_bts_tch_timing(self):
        """ 2.2.2 Configured BTS Transmit timing (delay)
            Valid in: IDLE, BIDL, BBCH  """
        return self.scpi.ask_int("CONF:BTS:TRANsmit:TIMing?")

    def set_bts_tch_timing(self, ta):
        """ 2.2.2 Configure BTS Transmit timing (delay)
            Valid in: IDLE, BIDL, BBCH  """
        return self.scpi.send_command("CONF:BTS:TRANsmit:TIMing %d"%int(ta), False)

    def ask_bts_tch_input_bandwidth(self):
        """ 2.2.2 Configured BTS Input bandwidth for the TCH
            See set_bts_tch_input_bandwidth() for details.
            Valid in: ALL  """
        return self.scpi.ask_str("PROCedure:SET:POWer:BANDwidth:INPut?")

    def set_bts_tch_input_bandwidth(self, bw):
        """ 2.2.2 Configure BTS Input bandwidth for the TCH
            Note: the value is always set to default when changing to the BTCH state
            Valid in: BTCH
            Supported values:
              NARRow   - narrowband (default for timing reference FIX/BCCH)
              WIDE     - wideband (default for timing reference TRIG)  """
        return self.scpi.send_command("PROCedure:SET:POWer:BANDwidth:INPut %s"%str(bw), False)

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
        """ 2.3 Burst Analysis (Module testing) Input Bandwidth for measurement of peak power
            See set_ban_input_bandwidth() for details """
        return self.scpi.ask_str("CONF:BANalysis:POWer:BANDwidth:INPut1?")

    def set_ban_input_bandwidth(self, band):
        """ 2.3 Burst Analysis (Module testing) Input Bandwidth for measurement of peak power
            Used only with input RF IN/OUT (aka RF In1) selected!
            Supported values:
              NARRow - Narrowband measurement (IF power meter)
              WIDE   - Wideband measurement (RF power meter)  """
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
        return self.scpi.send_command("PROCedure:SYNChronize", False)

    def ask_sync_state(self):
        """ 3 Selected Measurement State
            See set_sync_state() for the list of supported modes  """
        # TODO: The command returns error -113: Undefined header
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

    #
    # 7.3.2 Power Tolerance Measurement
    #

    def ask_power_mask_match(self):
        """ 7.3.1 Power Tolerance values / Query for observance of the tolerances of the power/time template
            Valid in: BTCH, MOD  """
        return self.scpi.ask_str("CALC:LIMit:POWer:MATChing?")

    #
    # 7.3.2 Power Measurement
    #

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
            Values are calculated at 1/4-bit steps and are returned in the range from bit index -10.0 to bit index +157.0. This results in 669 values.
            Valid in: BTCH, BAN
            Unit: dB  """
        return self.scpi.ask_float_list("READ:ARRay:BURSt:POWer?")

    def fetch_burst_power_arr(self):
        """ 7.3.2 Power Measurement / Power values of the entire burst (fetch)
            Valid in: BTCH, BAN
            Unit: dB  """
        return self.scpi.ask_float_list("FETCh:ARRay:BURSt:POWer?")

    #
    # 7.4.1 Phase and Frequency Errors / Tolerance values
    #

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

    #
    # 7.4.2 Phase and Frequency Errors / Test Parameters for Phase and Frequency Error Measurment
    #

    def ask_phase_decoding_mode(self):
        """ 7.4.2 Phase and Frequency Errors / Decoding mode
            See set_phase_decoding_mode() for details """
        return self.scpi.ask_str("CONF:DECoding:MODE?")

    def set_phase_decoding_mode(self, mode):
        """ 7.4.2 Phase and Frequency Errors / Decoding mode
            Supported values:
              STANdard  - Guard and tail bits assumed to be set according to the Standard
              GATBits   - Guard and tail bits decoded just as normal data bits without assumptions   """
        return self.scpi.send_command("CONF:DECoding:MODE %s"%mode, False)

    #
    # 7.4.3 Phase and Frequency Errors / Phase Error Measurement
    #

    def ask_phase_err_rms(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst RMS (single-value measurment, execute)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("READ:BURSt:PHASe:ERRor:RMS?")

    def fetch_phase_err_rms(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst RMS (single-value measurment, fetch)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("FETCh:BURSt:PHASe:ERRor:RMS?")

    def ask_phase_err_pk(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst Peak (single-value measurment, execute)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("READ:BURSt:PHASe:ERRor:PEAK?")

    def fetch_phase_err_pk(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of Burst Peak (single-value measurment, fetch)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float("FETCh:BURSt:PHASe:ERRor:PEAK?")

    def ask_phase_err_arr(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of the Total Burst (single-value measurment, execute)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float_list("READ:ARRay:BURSt:PHASe:ERRor?")

    def fetch_phase_err_arr(self):
        """ 7.4.3 Phase and Frequency Errors / Total Phase Error of the Total Burst (single-value measurment, fetch)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float_list("FETCh:ARRay:BURSt:PHASe:ERRor?")

    #
    # 7.4.4 Phase and Frequency Errors / Frequency Error Measurement
    #

    def ask_freq_err(self):
        """ 7.4.3 Phase and Frequency Errors / Total Frequency Error of Burst (single-value measurment, execute)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_int("READ:BURSt:FREQ:ERRor?")

    def fetch_freq_err(self):
        """ 7.4.3 Phase and Frequency Errors / Total Frequency Error of Burst (single-value measurment, fetch)
            Valid in: BTCH, MOD  """
        return self.scpi.ask_int("FETCh:BURSt:FREQ:ERRor?")

    #
    # 7.5.1 Spectrum Measurements / Tolerance values
    #

    def reset_spectrum_modulation_tolerance(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Reset tolerance values to default (Modulation)
            Valid in: ALL  """
        return self.scpi.send_command("CALCulate:LIMit:SPECtrum:MODulation:CLEar", False)

    def reset_spectrum_switching_tolerance(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Reset tolerance values to default (Switching)
            Valid in: ALL  """
        return self.scpi.send_command("CALCulate:LIMit:SPECtrum:SWITching:CLEar", False)

    def ask_spectrum_modulation_tolerance_abs(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Absolute tolerance for spectrum (Modulation)
            Returns a list of 2 values. (UNDOCUMENTED)
            Supported values: -100.0 to 5.0 dBm
            Default value: -57.0 dBm
            Valid in: ALL  """
        return self.scpi.ask_float_list("CALCulate:LIMit:SPECtrum:MODulation:ABSolute?")

    def set_spectrum_modulation_tolerance_abs(self, dbm_list):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Absolute tolerance for spectrum (Modulation)
            Supported values: -100.0 to 5.0 dBm
            Default value: -57.0 dBm
            Valid in: ALL  """
        return self.scpi.send_command("CALCulate:LIMit:SPECtrum:MODulation:ABSolute %s" % self._format_float_list(dbm_list), False)

    def ask_spectrum_modulation_tolerance_rel(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Relative tolerance for spectrum (Modulation)
            Returns values for 10 frequency offsets (in kHz): [100, 200, 250, 400, 600, 800, 1000, 1200, 1400, 1600]
            Supported values: -100.0 to 5.0 dBm
            Valid in: ALL  """
        return self.scpi.ask_float_list("CALCulate:LIMit:SPECtrum:MODulation:RELative?")

    def set_spectrum_modulation_tolerance_rel(self, db_list):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Relative tolerance for spectrum (Modulation)
            Requires values at 10 frequency offsets (in kHz): [100, 200, 250, 400, 600, 800, 1000, 1200, 1400, 1600]
            Supported values: -100.0 to 5.0 dB
            Valid in: ALL  """
        return self.scpi.send_command("CALCulate:LIMit:SPECtrum:MODulation:RELative %s" % self._format_float_list(db_list), False)

    def ask_spectrum_switching_tolerance_abs(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Absolute tolerance for spectrum (Switching)
            Returns values at 4 frequency offsets (in kHz): [400, 600, 1200, 1800]
            Supported values: -100.0 to 5.0 dBm
            Valid in: ALL  """
        return self.scpi.ask_float_list("CALCulate:LIMit:SPECtrum:SWITching:ABSolute?", False)

    def set_spectrum_switching_tolerance_abs(self, dbm_list):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Absolute tolerance for spectrum (Switching)
            Requires values at 4 frequency offsets (in kHz): [400, 600, 1200, 1800]
            Supported values: -100.0 to 5.0 dBm
            Valid in: ALL  """
        return self.scpi.send_command("CALCulate:LIMit:SPECtrum:SWITching:ABSolute %s" % self._format_float_list(dbm_list), False)

    def ask_spectrum_switching_tolerance_rel(self):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Relative tolerance for spectrum (Switching)
            Returns values at 4 frequency offsets (in kHz): [400, 600, 1200, 1800]
            Supported values: -100.0 to 5.0 dB
            Valid in: ALL  """
        return self.scpi.ask_float_list("CALCulate:LIMit:SPECtrum:SWITching:RELative?", False)

    def set_spectrum_switching_tolerance_rel(self, db_list):
        """ 7.5.1 Spectrum Measurements / Tolerance values / Relative tolerance for spectrum (Switching)
            Requires values at 4 frequency offsets (in kHz): [400, 600, 1200, 1800]
            Supported values: -100.0 to 5.0 dB
            Valid in: ALL  """
        return self.scpi.send_command("CALCulate:LIMit:SPECtrum:SWITching:RELative %s" % self._format_float_list(db_list), False)

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
        # TODO: For some reason always returns INV.
        return self.scpi.ask_str("CALCulate:LIMit:SPECtrum:SWITching:MATChing?")

    #
    # 7.5.3 Spectrum Measurements / Measurements
    #

    def ask_spectrum_modulation(self):
        """ 7.5.3 Executing Spectrum Measurement (Modulation)
            Returns 23 frequency offsets (in kHz): [-1600, -1400, -1200, -1000, -800, -600, -400, -250, -200, -100, 0, 100, 200, 250, 400, 600, 800, 1000, 1200, 1400, 1600]
            Valid in: BTCH, MOD  """
        # TODO: LONG operation
        return self.scpi.ask_float_list("READ:ARRay:SPECtrum:MODulation?")

    def fetch_spectrum_modulation(self):
        """ 7.5.3 Executing Spectrum Measurement (Modulation)
            Returns 23 frequency offsets (in kHz): [-1600, -1400, -1200, -1000, -800, -600, -400, -250, -200, -100, 0, 100, 200, 250, 400, 600, 800, 1000, 1200, 1400, 1600]
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float_list("FETCh:ARRay:SPECtrum:MODulation?")

    def ask_spectrum_switching(self):
        """ 7.5.3 Executing Spectrum Measurement (Switching)
            Returns 9 frequency offsets (in kHz): [-1800, -1200, -600, -400, 0, 400, 600, 1200, 1800]
            Valid in: BTCH, MOD  """
        # TODO: LONG operation
        return self.scpi.ask_float_list("READ:ARRay:SPECtrum:BTS:SWITching?")

    def fetch_spectrum_switching(self):
        """ 7.5.3 Executing Spectrum Measurement (Switching)
            Returns 9 frequency offsets (in kHz): [-1800, -1200, -600, -400, 0, 400, 600, 1200, 1800]
            Valid in: BTCH, MOD  """
        return self.scpi.ask_float_list("FETCh:ARRay:SPECtrum:BTS:SWITching?")

    #
    # 7.8 Other measurements
    #

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

    #
    # Test modes configuration
    #

    def configure_mod(self, expected_power=None, arfcn=None, tsc=None, decode=None, input_bandwidth=None, trigger_mode=None):
        if expected_power is not None: self.set_ban_expected_power(expected_power)
        if arfcn is not None: self.set_ban_arfcn(arfcn)
        if tsc is not None: self.set_ban_tsc(tsc)
        if decode is not None: self.set_phase_decoding_mode(decode)
        if input_bandwidth is not None: self.set_ban_input_bandwidth(input_bandwidth)
        if trigger_mode is not None: self.set_ban_trigger_mode(trigger_mode)

    def confiure_man(self, ccch_arfcn=None, tch_arfcn=None, tch_ts=None, tsc=None, expected_power=None, tch_tx_power=None, tch_mode=None, tch_timing=None, tch_input_bandwidth=None):
        if ccch_arfcn is not None: self.set_bts_ccch_arfcn(ccch_arfcn)
        if tch_arfcn is not None: self.set_bts_tch_arfcn(tch_arfcn)
        if tch_ts is not None: self.set_bts_tch_ts(tch_ts)
        if tsc is not None: self.set_bts_tsc(tsc)
        if expected_power is not None: self.set_bts_expected_power(expected_power)
        if tch_tx_power is not None: self.set_bts_tch_tx_power(tch_tx_power)
        if tch_mode is not None: self.set_bts_tch_mode(tch_mode)
        if tch_timing is not None: self.set_bts_tch_timing(tch_timing)
        if tch_input_bandwidth is not None: self.set_bts_tch_input_bandwidth(tch_input_bandwidth)

    def configure_spectrum_modulation_mask_rel(self, bts_power):
        # According to the Table 6.5-1
        if bts_power <= 33:
            dev.set_spectrum_modulation_tolerance_rel([0.5, -30.0, -33.0, -60.0, -60.0, -60.0, -60.0, -63.0, -63.0, -63.0])
        elif bts_power <= 35:
            dev.set_spectrum_modulation_tolerance_rel([0.5, -30.0, -33.0, -60.0, -62.0, -62.0, -62.0, -65.0, -65.0, -65.0])
        elif bts_power <= 37:
            dev.set_spectrum_modulation_tolerance_rel([0.5, -30.0, -33.0, -60.0, -64.0, -64.0, -64.0, -67.0, -67.0, -67.0])
        elif bts_power <= 39:
            dev.set_spectrum_modulation_tolerance_rel([0.5, -30.0, -33.0, -60.0, -66.0, -66.0, -66.0, -69.0, -69.0, -69.0])
        elif bts_power <= 41:
            dev.set_spectrum_modulation_tolerance_rel([0.5, -30.0, -33.0, -60.0, -68.0, -68.0, -68.0, -68.0, -71.0, -71.0])
        elif bts_power > 41: # >= 43 in the standard
            dev.set_spectrum_modulation_tolerance_rel([0.5, -30.0, -33.0, -60.0, -70.0, -70.0, -70.0, -70.0, -73.0, -73.0])

    #
    # Switching between test modes
    #

    def _switch_to_x(self, mode):
        if self.ask_test_mode() != mode:
            self.set_test_mode("NONE")
            self.set_test_mode(mode)

    def switch_to_mod(self):
        self._switch_to_x("MOD")

    def switch_to_ban(self):
        self._switch_to_x("BAN")

    def switch_to_man(self):
        self._switch_to_x("MAN")

    def switch_to_man_bbch(self):
        self.switch_to_man()
        if self.ask_dev_state() != "BBCH":
            self.bcch_sync()

    def switch_to_man_btch(self):
        self.switch_to_man()
        if self.ask_dev_state() != "BTCH":
            if self.ask_dev_state() != "BBCH":
                self.bcch_sync()
            self.set_sync_state("BTCH")


def rs232(port, **kwargs):
    """Quick helper to connect via RS232 port"""
    import serial as pyserial
    from scpi.transports import rs232 as serial_transport

    # Try opening at 2400 baud (default setting) and switch to 9600 baud
    serial_port = pyserial.Serial(port, 2400, timeout=0, **kwargs)
    serial_port.write(":SYSTem:COMMunicate:SERial:BAUD 9600"+"\n")
#    transport = serial_transport(serial_port)
#    transport.send_command(":SYSTem:COMMunicate:SERial:BAUD 9600")
#    transport.quit()
#    dev = cmd57(transport)
#    dev.scpi.command_timeout = 0.1 # Seconds
#    try:
#        dev.scpi.send_command_unchecked(":SYSTem:COMMunicate:SERial:BAUD 9600", expect_response=False)
#    except:
#        # It's ok to fail, because we can already be at 9600
#        pass
#    dev.quit()

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

