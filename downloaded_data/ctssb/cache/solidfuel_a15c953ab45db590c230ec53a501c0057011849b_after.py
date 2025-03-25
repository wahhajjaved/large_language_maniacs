class Event:
    def __init__(self):
        self._responders = []
        self.active = True

    def addResponder(self, resp):
        self._responders.append(resp)

    def removeResponder(self, resp):
        self._responders.remove(resp)

    def trigger(self, *args, **kwargs):
        if self.active:
            for resp in self._responders:
                resp(*args, **kwargs)
    
    def setActive(self, value):
        self.active = value
