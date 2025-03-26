import re
import numpy as np
import scipy as sp
import os, sys
import pickle
import pandas as pd
from scipy.interpolate import interp1d

import FormPars


#import ROOT
#from ROOT import TFile
#from ROOT import TTree
#from ROOT import TBranch

class MyHistorianData:

    def __init__(self, SCPickleFile):
        self.ReferenceUnixTime = 0
        self.SpecialPeriod = FormPars.GetSpecialPeriods()
#        self.SpecialPeriod = [
#                                         [1465913920, 1466517600]
#                                        ] # in this period don't do the valve status treatment
        # during the gas only period, the circulation route is very different
        # see: https://xecluster.lngs.infn.it/dokuwiki/lib/exe/fetch.php?media=xenon:xenon1t:org:commissioning:meetings:160817:xenon1t-operating_modes-circulation-mode_3_x-circulation_gxe_high_flow-v0.pdf
        # so now the total flow is not basically the sum of FCV201&FCV202
        # but only FCV201
        self.GasOnlyPeriod = FormPars.GetGasOnlyPeriods()
#        self.GasOnlyPeriod = [
#                                              [1471900000, 1472840000],# the end day is 09/10 temporarily
#                                             ]
        # configuration for getter deficiency periods and fraction
        self.GetterDeficiencyConfigs = []
#        self.ProbableCathodeRange1 = [10, 20.]
#        self.ProbableCathodeRange2 = [7., 10.]
        if not self.LoadFile(SCPickleFile):
            raise ValueError("SC pickle file error!")
#        self.MaximumHeatingPower = 260. # W
        self.MaximumHeatingPower = FormPars.GetMaximumHeatingPower() # W
        return

    def AddGasOnlyPeriod(self, Period):
        self.GasOnlyPeriod.append(Period)
        return

    def AddOneGetterDeficiencyConfig(self, Config):
        if len(Config)!=3:
            print("The config doesn't match the format! Nothing done!")
            return
        self.GetterDeficiencyConfigs.append(Config)
        return

    def PopOneGetterDeficiencyConfig(self):
        if len(self.GetterDeficiencyConfigs)>0:
            self.GetterDeficiencyConfigs.pop()
        return

    def GetGetterDeficiencyConfigs(self):
        return self.GetterDeficiencyConfigs

    def __eq__(self, other):
        # general ones
        self.ReferenceUnixTime = other.ReferenceUnixTime
        self.SpecialPeriod = other.SpecialPeriod
        self.GasOnlyPeriod = other.GasOnlyPeriod
        self.GetterDeficiencyConfigs = other.GetterDeficiencyConfigs
        self.MaximumHeatingPower = other.MaximumHeatingPower
        self.ProbableCathodeRange = other.ProbableCathodeRange
        # Min unixtimes
        self.MinUnixTime_FC201 = other.MinUnixTime_FC201
        self.MinUnixTime_FC202 = other.MinUnixTime_FC202
        self.MinUnixTime_FCV101 = other.MinUnixTime_FCV101
        self.MinUnixTime_FCV102 = other.MinUnixTime_FCV102
        self.MinUnixTime_FCV103 = other.MinUnixTime_FCV103
        self.MinUnixTime_FCV104 = other.MinUnixTime_FCV104
        self.MinUnixTime_FIC401 = other.MinUnixTime_FIC401
        self.MinUnixTime_HeatPower = other.MinUnixTime_HeatPower
        self.MinUnixTime_FV217 = other.MinUnixTime_FV217
        self.MinUnixTime_FV224 = other.MinUnixTime_FV224
        # Max unixtimes
        self.MaxUnixTime_FC201 = other.MaxUnixTime_FC201
        self.MaxUnixTime_FC202 = other.MaxUnixTime_FC202
        self.MaxUnixTime_FCV101 = other.MaxUnixTime_FCV101
        self.MaxUnixTime_FCV102 = other.MaxUnixTime_FCV102
        self.MaxUnixTime_FCV103 = other.MaxUnixTime_FCV103
        self.MaxUnixTime_FCV104 = other.MaxUnixTime_FCV104
        self.MaxUnixTime_FIC401 = other.MaxUnixTime_FIC401
        self.MaxUnixTime_HeatPower = other.MaxUnixTime_HeatPower
        self.MaxUnixTime_FV217 = other.MaxUnixTime_FV217
        self.MaxUnixTime_FV224 = other.MaxUnixTime_FV224
        # interpolation
        self.inter_FC201 = other.inter_FC201
        self.inter_FC202 = other.inter_FC202
        self.inter_FCV101 = other.inter_FCV101
        self.inter_FCV102 = other.inter_FCV102
        self.inter_FCV103 = other.inter_FCV103
        self.inter_FCV104 = other.inter_FCV104
        self.inter_FIC401 = other.inter_FIC401
        self.inter_HeatPower = other.inter_HeatPower
        self.inter_FV217 = other.inter_FV217
        self.inter_FV224 = other.inter_FV224
        self.MaximumUnixTime = other.MaximumUnixTime
        return
        

    def LoadFile(self, Filename):
        print("===== start loading SC pickle =======")
        PickleData = pickle.load( open(Filename, 'rb') )
        dict_FC201 = PickleData["PUR_FC201"]
        dict_FC202 = PickleData["PUR_FC202"]
        dict_FCV101 = PickleData["CRY_FCV101"]
        dict_FCV102 = PickleData["CRY_FCV102"]
        dict_FCV103 = PickleData["CRY_FCV103"]
        dict_FCV104 = PickleData["CRY_FCV104"]
        dict_FIC401 = PickleData["DST_FIC401"]
        dict_HeatPower = PickleData["CRY_R121P"]
        dict_FV217 = PickleData["PUR_FV217V"]
        dict_FV224 = PickleData["PUR_FV224V"]
        dict_Cathode = PickleData["TPC_Monitor_Voltage"]
        if not dict_FC201:
            raise ValueError("FC 201 not available")
        if not dict_FC202:
            raise ValueError("FC 202 not available")
        if not dict_FCV101:
            raise ValueError("FCV 101 not available")
        if not dict_FCV102:
            raise ValueError("FCV 102 not available")
        if not dict_FCV103:
            raise ValueError("FCV 103 not available")
        if not dict_FCV104:
            raise ValueError("FCV 104 not available")
        if not dict_FIC401:
            raise ValueError("FIC 401s not available")
        if not dict_HeatPower:
            raise ValueError("Heat power not available")
        if not dict_FV217:
            raise ValueError("FV 217 not available")
        if not dict_FV224:
            raise ValueError("FV 224 not available")
        if not dict_Cathode:
            raise ValueError("Cathode not available")
        self.MinUnixTime_FC201, self.MaxUnixTime_FC201, self.inter_FC201 = self.GetInterpolation(dict_FC201)
        self.MinUnixTime_FC202, self.MaxUnixTime_FC202,  self.inter_FC202 = self.GetInterpolation(dict_FC202)
        self.MinUnixTime_FCV101, self.MaxUnixTime_FCV101, self.inter_FCV101 = self.GetInterpolation(dict_FCV101)
        self.MinUnixTime_FCV102, self.MaxUnixTime_FCV102, self.inter_FCV102 = self.GetInterpolation(dict_FCV102)
        self.MinUnixTime_FCV103, self.MaxUnixTime_FCV103, self.inter_FCV103 = self.GetInterpolation(dict_FCV103)
        self.MinUnixTime_FCV104, self.MaxUnixTime_FCV104, self.inter_FCV104 = self.GetInterpolation(dict_FCV104)
        self.MinUnixTime_FIC401, self.MaxUnixTime_FIC401, self.inter_FIC401 = self.GetInterpolation(dict_FIC401)
        self.MinUnixTime_HeatPower, self.MaxUnixTime_HeatPower, self.inter_HeatPower = self.GetInterpolation(dict_HeatPower)
        self.MinUnixTime_FV217, self.MaxUnixTime_FV217, self.inter_FV217 = self.GetInterpolationSpecial(dict_FV217)
        self.MinUnixTime_FV224, self.MaxUnixTime_FV224, self.inter_FV224 = self.GetInterpolationSpecial(dict_FV224)
        self.MinUnixTime_Cathode, self.MaxUnixTime_Cathode, self.inter_Cathode = self.GetInterpolationCathode(dict_Cathode)
        self.ReferenceUnixTime = np.min([self.MinUnixTime_FC201,
                                                                 self.MinUnixTime_FC202,
                                                                 self.MinUnixTime_FCV101,
                                                                 self.MinUnixTime_FCV102,
                                                                 self.MinUnixTime_FCV103,
                                                                 self.MinUnixTime_FCV104,
                                                                 self.MinUnixTime_FIC401,
                                                                 self.MinUnixTime_HeatPower,
                                                                 self.MinUnixTime_FV217,
                                                                 self.MinUnixTime_FV224,
                                                                 self.MinUnixTime_Cathode,
                                                                ], axis=0
                                                               )
        self.MaximumUnixTime = np.max([self.MaxUnixTime_FC201,
                                                                      self.MaxUnixTime_FC202,
                                                                      self.MaxUnixTime_FCV101,
                                                                      self.MaxUnixTime_FCV102,
                                                                      self.MaxUnixTime_FCV103,
                                                                      self.MaxUnixTime_FCV104,
                                                                      self.MaxUnixTime_FIC401,
                                                                      self.MaxUnixTime_HeatPower,
                                                                      self.MaxUnixTime_FV217,
                                                                      self.MaxUnixTime_FV224,
                                                                      self.MaxUnixTime_Cathode,
                                                                    ], axis=0
                                                                   )
        print("===== finish loading SC pickle =======")
        return True

    def GetReferenceUnixTime(self):
        return self.ReferenceUnixTime

    def GetMaximumUnixTime(self):
        return self.MaximumUnixTime

    def GetInterpolation(self, Dict):
        # get the interp1d from a tree
        UnixTimes = Dict['unixtimes']
        Values = Dict['values']
        MinUnixTime = min(UnixTimes)
        MaxUnixTime = max(UnixTimes)
        return (MinUnixTime, MaxUnixTime, interp1d(UnixTimes, Values))

    # special interpolation
    # only for cathode SC
    # since its values sometime went down to zero
    # but actually it wasn't zero.
    # we need to define a confident region
    # if values appear to be below/above that
    # use the previous value
    def GetInterpolationCathode(self, Dict):
        UnixTimes = Dict['unixtimes']
        Values = Dict['values']
        MinUnixTime = min(UnixTimes)
        MaxUnixTime = max(UnixTimes)
        ReturnValues = []
        previousValue = 15. #default
        CathodeVoltages = FormPars.GetCathodeVoltages()
        for unixtime, value in zip(UnixTimes, Values):
            for Array in CathodeVoltages:
                if unixtime >= Array[0][0] and unixtime < Array[0][1]:
                    # force voltage to take on value
                    if Array[1][0] == Array[1][1]:
                        value = Array[1][0]
                        RetrunValues.append(value)
                        previousValue = value
                    else:
                        if value >= Array[1][0] and value < Array[1][1]:
                            ReturnValues.append(value)
                            previousValue = value
                        else:
                            ReturnValues.append(previousValue)
                    continue
#        for unixtime, value in zip(UnixTimes, Values):
#            if unixtime < 1484768100:
#                if unixtime >  1473956519 and unixtime < 1473997763:
#                    value = 15.
#                    ReturnValues.append(value)
#                    previousValue = value
#                    continue
#                if unixtime >  1475301507 and unixtime < 1475391507:
#                    value = 12.
#                    ReturnValues.append(value)
#                    previousValue = value
#                    continue
#                elif value<self.ProbableCathodeRange1[0] or value>self.ProbableCathodeRange1[1]:
#                    ReturnValues.append(previousValue)
#                    continue
#                ReturnValues.append( value )
#                previousValue = value
#            elif unixtime >= 1484768100 and unixtime < 1484949120:
#                value = 0.
#                ReturnValues.append( value )
#                previousValue = value
#            elif unixtime >= 1484949120 and unixtime < 1485445200:
#                value = 9.
#                ReturnValues.append( value )
#                previousValue = value
#            elif unixtime >= 1485445200 and unixtime < 1485802500:
#                value = 0.
#                ReturnValues.append( value )
#                previousValue = value
#            elif unixtime >= 1485802500 and unixtime < 1486054320:
#                value = 7.
#                ReturnValues.append( value )
#                previousValue = value
#            elif unixtime >= 1486054320 and unixtime < 1487265420:
#                value = 8.
#                ReturnValues.append( value )
#                previousValue = value
#            else:
#                if value<self.ProbableCathodeRange2[0] or value>self.ProbableCathodeRange2[1]:
#                    ReturnValues.append(previousValue)
#                    continue
#                ReturnValues.append( value )
#                previousValue = value

        return (MinUnixTime, MaxUnixTime, interp1d(UnixTimes, ReturnValues))

    # principle
    # Two conditions that consider there's a valve status changing
    # 1) 0 -> 1 or 1->0 changing
    #     putting another '0' (or '1') 1 second before '1' (or '0')
    # 2) 1 <-> 1 longer than 10hr
    #     putting 4hr '1' before/after the end/begin '1'
    def GetInterpolationSpecial(self, Dict):
        # get the interp1d from a tree
        UnixTimes = []
        Values = []
        nEvents = len(Dict['unixtimes'])
        MinUnixTime = 10000000000
        MaxUnixTime = 0
        # generate the first one
        unixtime = Dict['unixtimes'][0]
        UnixTimes.append(unixtime-1)
        Values.append(0) # default starting point zero
        if unixtime < MinUnixTime:
            MinUnixTime = unixtime
        if unixtime > MaxUnixTime:
            MaxUnixTime = unixtime
        previous_value = 0
        previous_unixtime = unixtime - 1
        for event_id in range(nEvents):
            unixtime = Dict['unixtimes'][event_id]
            value = float(Dict['values'][event_id])
            # two choices
            if not value==previous_value:
                UnixTimes.append(unixtime-1)
                Values.append(previous_value)
                UnixTimes.append(unixtime)
                Values.append(value)
            elif ( (unixtime>lower and unixtime<upper) for (lower, upper) in self.SpecialPeriod):
                UnixTimes.append(unixtime)
                Values.append(value)
            elif (unixtime-previous_unixtime)/3600. > 10 and value==previous_value and value==1:
                UnixTimes.append(previous_unixtime+4.*3600.)
                Values.append(previous_value)
                UnixTimes.append(prevous_unixtime+4.*3600.+1)
                Values.append(abs(1-previous_value))
                UnixTimes.append(unixtime - 4.*3600-1)
                Values.append(abs(1-value))
                UnixTimes.append(unixtime - 4.*3600)
                Values.append(value)
                UnixTimes.append(unixtime)
                Values.append(value)
            else:
                UnixTimes.append(unixtime)
                Values.append(value)
            previous_unixtime = unixtime
            previous_value = value
            if unixtime < MinUnixTime:
                MinUnixTime = unixtime
            if unixtime > MaxUnixTime:
                MaxUnixTime = unixtime
        return (MinUnixTime, MaxUnixTime, interp1d(UnixTimes, Values))

    # return (liquid flow, gas flow, cooling power, cathode voltage)
    def GetHistorian(self, unixtime):
        GasFlow = self.GetGasFlow(unixtime)
        TotalFlow, ByPassFraction = self.GetLiquidFlow(unixtime)
        TrueGasFlow = GasFlow*(1. - ByPassFraction)
        TrueLiquidFlow = (TotalFlow-GasFlow)*(1.-ByPassFraction)
        CathodeVoltage = self.GetCathodeVoltage(unixtime)
        # if it is gas only
        for Period in self.GasOnlyPeriod:
            if unixtime>Period[0] and unixtime<Period[1]:
                return (
                             0., # not liquid flow
                             TotalFlow*(1. - ByPassFraction), # note here it is not 100% correct if we decide not bypassing getter 202
                             self.GetCoolingPower(unixtime),
                             CathodeVoltage,
                            )
        # if it is in period with suspecious getter deficiency
        for Config in self.GetterDeficiencyConfigs:
            if unixtime>Config[0] and unixtime<Config[1]:
                GetterEfficiency = Config[2]
                return (
                             GetterEfficiency*TrueLiquidFlow,
                             GetterEfficiency*TrueGasFlow,
                             self.GetCoolingPower(unixtime),
                             CathodeVoltage,
                            )
        return (
                     TrueLiquidFlow,
                     TrueGasFlow,
                     self.GetCoolingPower(unixtime),
                     CathodeVoltage,
                    )

    # return valve status
    def GetValveStatus(self, unixtime):
        EffUnixTime_FV217 = unixtime
        if unixtime<self.MinUnixTime_FV217:
            EffUnixTime_FV217 = self.MinUnixTime_FV217
        if unixtime>self.MaxUnixTime_FV217:
            EffUnixTime_FV217 = self.MaxUnixTime_FV217
        EffUnixTime_FV224 = unixtime
        if unixtime<self.MinUnixTime_FV224:
            EffUnixTime_FV224 = self.MinUnixTime_FV224
        if unixtime>self.MaxUnixTime_FV224:
            EffUnixTime_FV224 = self.MaxUnixTime_FV224
        FV217_Status = self.inter_FV217(EffUnixTime_FV217)
        if FV217_Status<0.5:
            FV217_Status=0
        else:
            FV217_Status=1
        FV224_Status = self.inter_FV224(EffUnixTime_FV224)
        if FV224_Status<0.5:
            FV224_Status=0
        else:
            FV224_Status=1
        return (FV217_Status, FV224_Status)

    # return liquid flow
    def GetLiquidFlow(self, unixtime):
        EffUnixTime_FC201 = unixtime
        if unixtime<self.MinUnixTime_FC201:
            EffUnixTime_FC201 = self.MinUnixTime_FC201
        if unixtime>self.MaxUnixTime_FC201:
            EffUnixTime_FC201 = self.MaxUnixTime_FC201
        EffUnixTime_FC202 = unixtime
        if unixtime<self.MinUnixTime_FC202:
            EffUnixTime_FC202 = self.MinUnixTime_FC202
        if unixtime>self.MaxUnixTime_FC202:
            EffUnixTime_FC202 = self.MaxUnixTime_FC202
        EffUnixTime_FIC401 = unixtime
        if unixtime<self.MinUnixTime_FIC401:
            EffUnixTime_FIC401 = self.MinUnixTime_FIC401
        if unixtime>self.MaxUnixTime_FIC401:
            EffUnixTime_FIC401 = self.MaxUnixTime_FIC401
        ByPass_FC201, ByPass_FC202 = self.GetValveStatus(unixtime)
        TotalFlow = self.inter_FC201(EffUnixTime_FC201) + self.inter_FC202(EffUnixTime_FC202) - self.inter_FIC401(EffUnixTime_FIC401)
        EffFlow = self.inter_FC201(EffUnixTime_FC201)*(1-ByPass_FC201)+self.inter_FC202(EffUnixTime_FC202)*(1-ByPass_FC202)
        if EffFlow<0 or TotalFlow<=0:
            return (0, 0)
        ByPassFraction = (TotalFlow - EffFlow) / TotalFlow
        return (TotalFlow, ByPassFraction)

    def GetFCV201Flow(self, unixtime):
        EffUnixTime_FC201 = unixtime
        if unixtime<self.MinUnixTime_FC201:
            EffUnixTime_FC201 = self.MinUnixTime_FC201
        if unixtime>self.MaxUnixTime_FC201:
            EffUnixTime_FC201 = self.MaxUnixTime_FC201
        return self.inter_FC201(EffUnixTime_FC201)

    # return gas flow
    def GetGasFlow(self, unixtime):
        EffUnixTime_FCV101 = unixtime
        if unixtime<self.MinUnixTime_FCV101:
            EffUnixTime_FCV101 = self.MinUnixTime_FCV101
        if unixtime>self.MaxUnixTime_FCV101:
            EffUnixTime_FCV101 = self.MaxUnixTime_FCV101
        EffUnixTime_FCV102 = unixtime
        if unixtime<self.MinUnixTime_FCV102:
            EffUnixTime_FCV102 = self.MinUnixTime_FCV102
        if unixtime>self.MaxUnixTime_FCV102:
            EffUnixTime_FCV102 = self.MaxUnixTime_FCV102
        EffUnixTime_FCV103 = unixtime
        if unixtime<self.MinUnixTime_FCV103:
            EffUnixTime_FCV103 = self.MinUnixTime_FCV103
        if unixtime>self.MaxUnixTime_FCV103:
            EffUnixTime_FCV103 = self.MaxUnixTime_FCV103
        Flow = self.inter_FCV101(EffUnixTime_FCV101)+self.inter_FCV102(EffUnixTime_FCV102)+self.inter_FCV103(EffUnixTime_FCV103)
        if Flow<0:
            return 0
        return Flow

    # return the cooling power
    def GetCoolingPower(self, unixtime):
        EffUnixTime_CoolingPower = unixtime
        if unixtime<self.MinUnixTime_HeatPower:
            EffUnixTime_CoolingPower = self.MinUnixTime_HeatPower
        if unixtime>self.MaxUnixTime_HeatPower:
            EffUnixTime_CoolingPower = self.MaxUnixTime_HeatPower
        return self.MaximumHeatingPower - self.inter_HeatPower(EffUnixTime_CoolingPower)

    # get the end point liquid flow
    def GetEndLiquidFlow(self):
        EffUnixTime_FC201 = self.MaxUnixTime_FC201
        EffUnixTime_FC202 = self.MaxUnixTime_FC202
        return self.inter_FC201(EffUnixTime_FC201)+self.inter_FC202(EffUnixTime_FC202)

    # get the cathode voltage
    def GetCathodeVoltage(self, unixtime):
        EffUnixTime_Cathode = unixtime
        if unixtime<self.MinUnixTime_Cathode:
            EffUnixTime_Cathode = self.MinUnixTime_Cathode
        if unixtime>self.MaxUnixTime_Cathode:
            EffUnixTime_Cathode = self.MaxUnixTime_Cathode
        return self.inter_Cathode (EffUnixTime_Cathode)
