import csv
import os
import subprocess
import sys
import time
import datetime
from threading import Thread, Lock


#
# Example usage:
#
#  t1 = temperature_thread.Temperature_Thread(filename = "main_floor_temps.csv", 
#                                             device_name = ["main_floor_temp"])
#  if t1 != None:
#    t1.start()
#

def isfloat(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

class Temperature_Thread(Thread):
    def __init__(self, filename, device_names):
        Thread.__init__(self)
        self.mutex = Lock()
        self.running = False
        self.initialized = False
        self.filename = filename
        self.device_names = device_names
        self.current_temperature = "0.0"
        try:
            self.file_handle = open(self.filename, 'a+')
            self.file_handle.seek(0,2)
        except:
            print "Failed to open", self.filename, ":", sys.exc_info()[1]
            return
        
        self.initialized = True
    
    def isInitialized(self):
        return self.initialized
    
    def run(self):
        
        if not self.initialized:
            print "Warning: Temperature_Thread started before initialized, not running."
            return
        
        self.running = True
        while self.running:
          
          t = {}
          x = 0.0
          count = 0
          for device in self.device_names:
              
              t[device] = subprocess.Popen(["spark","get",device,"temperature"], stdout=subprocess.PIPE).stdout.read().strip()
              
              try:
                x = x + float(t[device])
                count = count + 1
              except:
                print "Error getting temperature ("+device+"), got: \"" + t[device] + "\" setting to null"
                t[device] = "null"
          
          if count > 0:
            self.current_temperature = x / count
          
          self.mutex.acquire()
          self.file_handle.write(str(time.time()))
          for device in self.device_names:
            self.file_handle.write("," + t[device])
          self.file_handle.write("\n")
          self.file_handle.flush()
          self.mutex.release()
          time.sleep(10)
  
    def stop(self):
        self.running = False
        self.file_handle.close()
    
    def get_temp(self):
        return self.current_temperature
    
    def get_history(self, days=1, seconds=0):
        
        # start_time is "now" minus days and seconds
        # only this much data will be shown
        start_time = datetime.datetime.now() - datetime.timedelta(days,seconds)
        
        # Load the data from the file
        self.mutex.acquire()
        file_handle = open(self.filename, 'r')
        csvreader = csv.reader(file_handle)
        tempdata = []
        try:
            for row in csvreader:
                tempdata.append(row)
        except csv.Error, e:
            print 'ERROR: file %s, line %d: %s' % (self.filename, csvreader.line_num, e)
        self.mutex.release()
        
        # Build the return string
        return_string = ""
        for i, row in enumerate(tempdata):
            
            # Skip the ones before the start_time
            dt = datetime.datetime.fromtimestamp(float(row[0]))
            if dt < start_time:
                continue
            
            time = dt.strftime('%I:%M:%S %p')
            temp1 = row[1]
            temp2 = row[2]
            temp3 = row[3]
            
            return_string += ("        ['%s',  %s, %s, %s],\n" % (time,temp1,temp2,temp3))
        
        if len(return_string) > 2:
            return_string = return_string[:-2]
        
        return return_string
            
            
            
            
            
            
            
            
            
            
            
            
            
            
