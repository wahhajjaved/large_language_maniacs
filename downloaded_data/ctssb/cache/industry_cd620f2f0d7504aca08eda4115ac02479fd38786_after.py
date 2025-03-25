#!/usr/bin/python

import time
import BaseHTTPServer
import urlparse
import socket
from datetime import timedelta, datetime
from multiprocessing import Process, Value, Queue, Lock
import Adafruit_MCP9808.MCP9808 as MCP9808
import sys
import signal

from daemonize import Daemonize

DOC_ROOT = '/home/pi/thermometer/www/'
INTERVAL = '/home/pi/thermometer/interval'
PID = '/tmp/thermometer.pid'

HOST_NAME = '' # !!!REMEMBER TO CHANGE THIS!!!
PORT_NUMBER = 8080 # Maybe set this to 9000.


mimeTypes = {'png':"image/png", 
            'jpg':"image/jpeg", 
            'jpeg':"image/jpeg", 
            'htm':"text/html",
            'html':"text/html",
            'js':"application/javascript",
            'css':"text/css",
            'txt':"text/plain",
            'xml':"text/xml",
            'php':"text/html"}




class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        """Respond to a GET request."""
        
        url = urlparse.urlparse(self.path)
        params = urlparse.parse_qs(url.query)

        parts = url.path.lower().split('.')
        if (len(parts) > 1 and mimeTypes.get(parts[-1])) or url.path == '/':
            self.handleStatic(url,params)
            
        elif url.path == "/set":
            self.handleSet(url,params)
        elif url.path == "/now":
            self.handleNow(url,params)
        elif url.path == "/get":
            self.handleGet(url,params)

        else:

            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write("<html><head><title>Title goes here.</title></head>")
            self.wfile.write("<body><p>%s Not found </p></body></html>" % (url.path))

        #endif
    #enddef
  
    def handleGet(self,url,params):

        self.send_response(200)
        self.send_header("Content-type","text/plain") 
        self.end_headers()
        while not queue.empty():
            self.wfile.write('|'.join(queue.get()))
            self.wfile.write("\n")
        #endwhile
    #enddef

    def handleNow(self,url,params):
        """
        """
        data = readSensors()

        self.send_response(200)
        self.send_header("Content-type","text/plain") 
        self.end_headers()
        self.wfile.write('|'.join(data))
        self.wfile.write("\n")

    #enddef
    
    def handleSet(self,url,params):
        """
        """
        global process
        try:
            interval = params['interval'][0]
            fl = open(INTERVAL, "wt")
            fl.write(interval)
            fl.close()
            process.terminate()
            while process.is_alive():
                time.sleep(0.2)
            #endwhile
            process = Process(target=readProcess)
            process.start()
        except :
            raise
        #endtry
        
        self.send_response(200)
        self.end_headers()
    #enddef




    def handleStatic(self,url,params):
        """
        """
        try:
            filename = url.path
            if filename == '/':
                filename = "/index.html"
            #endif
            fl = open(DOC_ROOT + filename, 'r')
            
            mime = mimeTypes.get(filename.split('.')[-1],"text/html")

            self.send_response(200)
            self.send_header("Content-type", mime)
            self.end_headers()
            self.wfile.write(fl.read())

        except:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write("<html><head><title>Title goes here.</title></head>")
            self.wfile.write("<body><p>%s Not found</p></body></html>" % filename)
            
        #endtry
    #enddef
#endclass

def readSensors():
    """
    """
    data = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"),]
    lock.acquire()
    temp = sensor.readTempC()    
    lock.release()
    data.append("T%0.1f" % temp)
    return data
    #enddef

def readProcess():
    """
    """
    #read interval
    sys.stdout.flush() 
    fl = open(INTERVAL,'rt')
    interval = int(fl.read())
    fl.close()
    while True:
        data = readSensors()
        queue.put(data)
        #print data
        time.sleep(interval)
    #endwhile
#enddef
   


def main():
    """
    """
    global sensor
    global process 
  
    global lock
    global queue

    lock = Lock()
    queue = Queue()
    
    #sensor = MCP9808.MCP9808(address=0x20, busnum=2)
    sensor = MCP9808.MCP9808()
    sensor.begin()
    
    #make process
    process = Process(target=readProcess)
    process.start()
    signal.signal(signal.SIGTERM, handler)
    

    server_class = BaseHTTPServer.HTTPServer
    httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
    print time.asctime(), "Server Starts - %s:%s" % (HOST_NAME, PORT_NUMBER)

    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    #print time.asctime(), "Server Stops - %s:%s" % (HOST_NAME, PORT_NUMBER)
    
    process.terminate()
#enddef

def handler(signum, frame):
    if signum in [15,9]:
        process.terminate()
        sys.exit(0)


if __name__ == '__main__':
    
     daemon = Daemonize(app="thermometer", pid=PID, action=main, keep_fds=[])
     daemon.start() 
     main()
