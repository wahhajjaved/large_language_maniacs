#!/usr/bin/python

from os import listdir, mkdir
from os.path import isfile, join
import numpy as np
import time
import sys 
import json
import matplotlib.pyplot as plt

class AppInfo:
  def __init__(self, json_fname):
    self.json_fname = json_fname

    # App identification data
    self.app_id = None
    self.conf_id = None
    self.app_name = None
    self.parameters = None

    # App metrics
    self.running_time = None
    self.gc_time = None

    self.avg_sytem_cpu_load = None
    self.avg_process_cpu_load = None

    self.avg_non_heap = None
    self.avg_heap = None
    self.avg_memory = None

    self.max_non_heap = None
    self.max_heap = None
    self.max_memory = None

    self.parse()

  def parse(self):

    # We (actually) expect the DB to be ONE line of the form:
    # {'avg_memory': float MB, 'avg_system_cpu_load': float 0-1, 'gc_time: int MS, 'max_non_heap': float MB, 'parameter': '5m', 'app_id': 'app-20151105181354-0005', 'max_memory': float MB, 'avg_heap': float MB, 'avg_process_cpu_load': float 0-1, 'conf_id': '58-1-4', 'max_heap': float MB, 'app_name': 'cc', 'running_time': int MS, 'avg_non_heap': float MB}


    fh = open(self.json_fname, 'r')
    for line in fh.readlines():
      data = json.loads(line)

      self.app_id = data['app_id']
      self.conf_id = data['conf_id'] 
      self.app_name = data['app_name']
      self.parameters = data['parameter']

      self.running_time = data['running_time']
      self.gc_time = data['gc_time']

      self.avg_sytem_cpu_load = data['avg_system_cpu_load']
      self.avg_process_cpu_load = data['avg_process_cpu_load']

      self.avg_non_heap = data['avg_non_heap']
      self.avg_heap = data['avg_heap']
      self.avg_memory = data['avg_memory']

      self.max_non_heap = data['max_non_heap']
      self.max_heap = data['max_heap']
      self.max_memory = data['max_memory']


    fh.close()
    

"""
Generates a bar chart for an executor
:param indicators: a list of tuples (executor_id, metric_value)
:param xlabel text for abscissa
:param ylabel text for ordinate
:param plot_loc where to save the plot
:return None
"""

def genBarPlot(indicators, xlabel, ylabel, plot_loc):
  fig,ax = plt.subplots()

  ind = np.arange(len(indicators))
  values = [i[1] for i in indicators]
  executors = [i[0] for i in indicators]

  rects1 = ax.bar(ind, values, color = 'black')

  ax.set_ylabel(ylabel)
  ax.set_title(xlabel)
  xTickMarks = [executor for executor in executors]
  ax.set_xticks(ind)
  xtickNames = ax.set_xticklabels(xTickMarks)
  plt.setp(xtickNames, rotation=45, fontsize=10)

  plt.savefig(plot_loc)

def main(directory_list):
  fh = open(directory_list, 'r')

  list_path = directory_list.split('/')[:-1]
  plot_dir = '/'.join(list_path) + 'configuration-comparison-plots-' + str(int(time.time())) + '/'
  mkdir(plot_dir)

  applications = []

  for directory in fh.readlines():
    directory = directory.rstrip('\n\r')

    #TODO: make this parser more tolerant to unexpected JS files, placement errors, etc
    for f in listdir(directory):
      if '.js' in f:
        print(f)
        applications.append(AppInfo(join(directory, f)))

    plots = {'running_time'         : 'running time (MS)',
             'max_heap'             : 'max heap usage (MB)',
             'avg_process_cpu_load' : 'average cpu load',
             'avg_heap'             : 'average heap usage (MB)'}

    for plot in plots.keys():
      plot_loc = plot_dir + plot + '.png'
    
      indicators = []
      for app in applications:
        p_id = app.app_name + '-' + app.conf_id
        metric = getattr(app, plot)
        indicators.append((p_id, metric))

      genBarPlot(indicators, plots[plot], 'Configurations', plot_loc)



if __name__ == "__main__":
  main(sys.argv[1])
