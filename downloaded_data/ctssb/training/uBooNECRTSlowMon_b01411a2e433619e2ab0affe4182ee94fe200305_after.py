import logging
from SCMon import (MessageQuery,
                   FEBStatsQuery,
                   DRVStatsQuery,
                   EventsQuery)

from epics import PV

PV_NAMING_SCHEME="{detector}_{subsys}_{rack}_{unit}/{var}"

def create_context():
    return {
        'detector':"uB",
        'subsys': 'DAQStatus',
        'rack': "CRTDAQX",
        'unit': 'evb',
        'var':''
    }

class BaseCalcMixin:
  def update(self):
    value = self.get_value()
    return self.update2epics(value)

  def get_value(self):
    pass

  def update2epics(self, value):
    context = create_context()
    context['var'] = self.path
    name = PV_NAMING_SCHEME.format(**context)
    pv = PV(name)
    return pv.put(value, wait=False)


class DRVErrFlag_Base(BaseCalcMixin, FEBStatsQuery):
  logger = logging.getLogger("DRVErrFlag")
  low=0
  high=9

  def get_value(self):
    self.limit=100000
    self.constraints = ['time > now() - 1d']#,'host = "feb{}"'.format(feb)]
    try:
      df = self.construct_query()

      for feb in range(self.low,self.high):
        label=feb
        if feb<10:
          label = "0{}".format(feb)
          #get the most recent one matching the feb
        feb_rows = df.loc[df['host'] == "\"feb{}\"".format(label)]
        lostcpu = feb_rows['lost_cpu'][0]
        lostfpga = feb_rows['lost_fpga'][0]
        ts0ok= feb_rows['ts0ok'][0]
        ts1ok = feb_rows['ts1ok'][0]
        if lostcpu==0 and lostfpga==0 and ts0ok==None and ts1ok==None:
          return 1
    except Exception as e:
      self.logger.warning("Could not construct Query for feb:"+str(feb))
      self.logger.error(e)

    return 0

class DRVErrFlag_FTSide(DRVErrFlag_Base):
  path="drverrflag_FTSide"
  logger = logging.getLogger(path)
  low=9
  high=22

class DRVErrFlag_bottom(DRVErrFlag_Base):
  path="drverrflag_bottom"  
  logger = logging.getLogger(path)
  low=0
  high=9

class DRVErrFlag_pipeside(DRVErrFlag_Base):
  path="drverrflag_pipeside"
  logger = logging.getLogger(path)
  low =22
  high=49

class DRVErrFlag_top(DRVErrFlag_Base):
  path="drverrflag_top"
  logger = logging.getLogger(path)
  low=49
  high=77

class EVTRate_Sum(BaseCalcMixin, FEBStatsQuery):
  path="EVTRate_Sum"
  logger = logging.getLogger(path)
  low=0
  high=77

  def get_value(self):
    self.limit=100000
    self.constraints = ['time > now() - 1d']
    try:
      df = self.construct_query()

      ratesum=0
      for feb in range(self.low,self.high):
        label = feb
        if feb<10:
          label = "0{}".format(feb)
        feb_rows = df.loc[df['host'] == "\"feb{}\"".format(label)]
        rate = feb_rows['evrate'][0]
        ratesum+=rate
      return ratesum
    except Exception as e:
      self.logger.error(e)
      return 0


class MaxBuff_OCC(BaseCalcMixin, FEBStatsQuery):
  path="macbuff_occ"
  logger = logging.getLogger(path)
  low=0
  high=77

  def get_value(self):
    self.limit=100000
    max_rate = -1.e6
    max_feb=0
    try:
      df = self.construct_query()
      ratesum=0
      for feb in range(self.low,self.high):
        label = feb
        if feb<10:
          label = "0{}".format(feb)
        feb_rows = df.loc[df['host'] == "\"feb{}\"".format(label)]
        rate = feb_rows['evrate'][0]
        if rate>max_rate:
          max_feb = feb
      return max_feb
    except Exception as e:
      self.logger.error(e)
      return -1


class MinBuff_OCC(BaseCalcMixin, FEBStatsQuery):
  path="minbuff_occ"
  logger = logging.getLogger(path)
  low=0
  high=77

  def get_value(self):
    self.limit=1000000
    min_rate = 1.e6
    min_feb=0

    try:
      df = self.construct_query()
      ratesum=0
      for feb in range(self.low,self.high):
        label=feb
        if feb<10:
          label = "0{}".format(feb)
        feb_rows = df.loc[df['host'] == "\"feb{}\"".format(label)]
        rate = feb_rows['evrate'][0]
        if rate<min_rate:
          min_feb = feb
      return min_feb
    except Exception as e:
      self.logger.error(e)
      return -1

