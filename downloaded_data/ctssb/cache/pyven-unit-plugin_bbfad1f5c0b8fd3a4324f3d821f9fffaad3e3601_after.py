import os, subprocess, time
import pyven.constants

from pyven.plugins.plugin_api.process import Process

from pyven.logging.logger import Logger
from pyven.results.xml_parser import XMLParser
from pyven.exceptions.exception import PyvenException

class Unit(Process):

    def __init__(self, cwd, name, path, filename, arguments, format):
        super(Unit, self).__init__(cwd, name)
        self.duration = 0
        self.type = 'unit'
        self.path = path
        self.cwd = os.path.join(self.cwd, self.path)
        self.filename = filename
        self.arguments = arguments
        self.parser = XMLParser(format)
    
    @Process.error_checks
    def process(self, verbose=False, warning_as_error=False):
        if not os.path.isfile(os.path.join(self.cwd, self.filename)):
            raise PyvenException('Test file not found : ' + os.path.join(self.path, self.filename))
        if os.path.isdir(self.cwd):
            Logger.get().info('Running test : ' + self.filename)
            
            self.duration, out, err, returncode = self._call_command(self._format_call())
        
            if verbose:
                for line in out.splitlines():
                    Logger.get().info(line)
                for line in err.splitlines():
                    Logger.get().info(line)
            
            self.parser.parse(os.path.join(self.cwd, self._format_report_name()))
            if returncode != 0 or len(self.parser.errors) > 0:
                self.status = pyven.constants.STATUS[1]
                if os.path.isfile(os.path.join(self.cwd, self._format_report_name())):
                    self.errors = self.parser.errors
                else:
                    msg = 'Could not find XML report --> '+os.path.join(self.path, self._format_report_name())
                    self.errors.append([msg])
                    Logger.get().error(msg)
                Logger.get().error('Test failed : ' + self.filename)
            else:
                self.status = pyven.constants.STATUS[0]
                Logger.get().info('Test OK : ' + self.filename)
            return returncode == 0
        Logger.get().error('Unknown directory : ' + self.path)
        return False
    
    @Process.error_checks
    def clean(self, verbose=False, warning_as_error=False):
        self.status = pyven.constants.STATUS[0]
        return True
        
    def report_summary(self):
        return self.report_title()
    
    def report_title(self):
        return self.name
        
    def report_properties(self):
        properties = []
        properties.append(('Executable', os.path.join(self.path, self.filename)))
        properties.append(('Duration', str(self.duration) + ' seconds'))
        return properties
        
    def _format_report_name(self):
        return self.filename+'-'+self.type+'.xml'
    
    def _call_command(self, command):
        tic = time.time()
        out = ''
        err = ''
        try:
            
            sp = subprocess.Popen(command,\
                                  stdin=subprocess.PIPE,\
                                  stdout=subprocess.PIPE,\
                                  stderr=subprocess.PIPE,\
                                  universal_newlines=True,\
                                  cwd=self.cwd,\
                                  shell=pyven.constants.PLATFORM == pyven.constants.PLATFORMS[1])
            out, err = sp.communicate(input='\n')
            returncode = sp.returncode
        except FileNotFoundError as e:
            returncode = 1
            self.errors.append(['Unknown command'])
        toc = time.time()
        return round(toc - tic, 3), out, err, returncode
        
    def _format_call(self, clean=False):
        if os.name == 'nt':
            call = [self.filename]
            call.append(self._format_report_name())
        elif os.name == 'posix':
            call = ['./'+self.filename+' '+self._format_report_name()]
        for argument in self.arguments:
            call.append(argument)
        Logger.get().info(' '.join(call))
        return call
        