
import os
import time
import datetime
import logging
from threading import Lock

logger = logging.getLogger('allspark.data_logger')

MAX_DAYS_OF_HISTORY = 7

class Data_Logger():
    def __init__(self, data_directory, archive_prefix):
        self._initialized = False
        self.mutex = Lock()
        self.archive_prefix = archive_prefix
        self.filename = data_directory + "/today.csv"
                
        # Create the log directory if it does not exist
        self.data_directory = data_directory
        if not os.path.exists(self.data_directory):
            os.makedirs(self.data_directory)
        
        logger.debug("Data directory: " + self.data_directory)
        
        self.last_day = time.localtime().tm_mday
        
        #
        # 2-D array where D1 = days of data and D2 is an array of data items for that day
        #
        # data[0][0]  = first item in the oldest day of loaded history (up to MAX_DAYS_OF_HISTORY old)
        # data[-1][0] = first item in todays data
        # data[-1][-1] = most recent item in todays data
        #
        self.data = self.load_history()
        
        self._initialized = True
        
        # Setup the link to todays data
        self.setup_data_file()
        
    def isInitialized(self):
        return self._initialized
    
    def setup_data_file(self):
        if not self._initialized:
            logger.error( "setup_data_file called before _initialized." )
            return
        
        today = datetime.date.today().strftime( self.archive_prefix + '_%Y_%m_%d.csv' )
        todays_filename = self.data_directory + "/" + today
        
        # If the "today" link exists, delete it
        if os.path.islink(self.filename):
            os.unlink(self.filename)
        
        # Touch todays data file (does nothing if it already exists)
        open(todays_filename, 'a').close()
        
        # Create the "today" link to todays data file
        os.symlink(today, self.filename)

    
    def get_data_item(self, dataset = -1, index = -1):
        if self.isInitialized():
            try:
                return self.data[dataset][index]
            except IndexError:
                logger.warning( "Asked for an item out of bounds: ["+str(dataset)+"],["+str(index)+"]" )
                return None
        return None
    
    
    def get_data_set(self, dataset = -1):
        if self.isInitialized():
            try:
                return self.data[dataset]
            except IndexError:
                logger.warning( "Asked for a dataset out of bounds: ["+str(dataset)+"]" )
                return None
        return None
    
    def num_data_sets(self):
        if self.isInitialized():
            return len(self.data)
        return 0
    
    def load_file(self, filepath):
        data = []
        
        logger.debug("loading: " + filepath)
        
        if os.path.isfile(filepath):
            f = open(filepath, 'r')
            for line in f.readlines():
                try:
                    line_data = line.rstrip().split(',')
                    
                    dt = datetime.datetime.fromtimestamp(float(line_data[0]))
                    year   = dt.strftime('%Y')
                    month  = str(int(dt.strftime('%m')) - 1) # javascript expects month in 0-11, strftime gives 1-12 
                    day    = dt.strftime('%d')
                    hour   = dt.strftime('%H')
                    minute = dt.strftime('%M')
                    second = dt.strftime('%S')
                    time_str = 'new Date(%s,%s,%s,%s,%s,%s)' % (year,month,day,hour,minute,second)
                    
                    data.append( {'time_str':time_str, 
                                  'time':float(line_data[0]), 
                                  'data':line_data[1:]} )
                except:
                    logger.warning("Error parsing line in %s : '%s'" % (filepath, line.strip()) )
                
            f.close()
            
        logger.debug("got: " + str(len(data)) )
            
        return data
    
    
    def load_history(self):
        history = []
        
        # For each file in the directory (sorted)
        file_list = sorted( os.listdir( self.data_directory ) )
        recent_list = file_list[MAX_DAYS_OF_HISTORY:]
        logger.info("Parsing %d of %d files" % ( len(recent_list), len(file_list) ) )

        for filename in recent_list:
            
            filepath = os.path.join( self.data_directory, filename )
            
            # Skip links
            if not os.path.islink(filepath):
                
                # Add an array to the data
                history.append( self.load_file(filepath) )
        
        return history
    
    
    
    def add_data(self, data): # data should be an array of strings
        
        if not self._initialized:
            logger.error( "add_data called before _initialized." )
            return
        
        if not isinstance(data, list):
            logger.error( "add_data called with non-list data" )
            return
        
        # If this item is blank and the last item was not blank, add a blank item
        if len( data ) < 1:
            last_item = self.get_data_item()
            if last_item != None and len( last_item['data'] ) == 0:
                return
        
        #logger.debug( "caller: " + os.path.basename(inspect.stack()[1][1]) + " gave me: " + str( data ) )
        
        self.mutex.acquire()
        
        # Check if file needs to be changed
        now = time.time()
        if time.localtime(now).tm_mday != self.last_day:
            self.last_day = time.localtime(now).tm_mday
            self.setup_data_file()
            self.data = self.load_history()
        
        # Build the data string
        result = str(now)
        for item in data:
            result += "," + item
    
        # Write to the file
        file_handle = open(self.filename, "a+")
        file_handle.write(result)
        file_handle.write("\n")
        file_handle.flush()
        file_handle.close()
        
        # Compute the javascript time string (probably not the best place for this)
        dt = datetime.datetime.fromtimestamp(now)
        year   = dt.strftime('%Y')
        month  = str(int(dt.strftime('%m')) - 1) # javascript expects month in 0-11, strftime gives 1-12 
        day    = dt.strftime('%d')
        hour   = dt.strftime('%H')
        minute = dt.strftime('%M')
        second = dt.strftime('%S')
        time_str = 'new Date(%s,%s,%s,%s,%s,%s)' % (year,month,day,hour,minute,second)
    
        # Add the data
        self.data[-1].append({'time_str':time_str, 
                              'time':now,
                              'data':data})
        
        self.mutex.release()
    
    
if __name__ == "__main__":
    from pprint import pprint
    
    data_logger = Data_Logger("data/temperature_data", "temperatures")
    
    data_logger.add_data(["one","two","three"])
    
    pprint( data_logger.load_history() )
    
    
