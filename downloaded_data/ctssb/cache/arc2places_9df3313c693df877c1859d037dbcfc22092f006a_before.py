from __future__ import print_function


class Logger:
    def __init__(self):
        self._debug = False

    def debug(self, text):
        if self._debug:
            return
        import datetime
        print('DEBUG', datetime.datetime.now(), text)

    def error(self, text):
        print('ERROR', text)

    def info(self, text):
        print('INFO', text)

    def warn(self, text):
        print('WARN', text)

    def start_debug(self):
        self._debug = True

    def stop_debug(self):
        self._debug = False


class ArcpyLogger(Logger):
    def __init__(self):
        Logger.__init__(self)
        try:
            self.arcpy = __import__('arcpy')
        except ImportError:
            self.arcpy = None

    def debug(self, text):
        if not self._debug:
            return
        if self.arcpy:
            self.arcpy.AddMessage(text)
        else:
            Logger.debug(self, text)

    def error(self, text):
        if self.arcpy:
            self.arcpy.AddError(text)
        else:
            Logger.info(self, text)

    def info(self, text):
        if self.arcpy:
            self.arcpy.AddMessage(text)
        else:
            Logger.info(self, text)

    def warn(self, text):
        if self.arcpy:
            self.arcpy.AddWarning(text)
        else:
            Logger.info(self, text)
