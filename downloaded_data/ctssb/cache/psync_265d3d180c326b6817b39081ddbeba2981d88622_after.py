import watcher.sync

LABEL = 'SYNC_MSG_'
FIELD_SEPARATOR = '\x00'
SUBFIELD_SEPARATOR = '\x01'

class UnknownMessageException(Exception):
    pass

class Message(object):
    def __init__(self):
        super(Message, self).__init__()

    @staticmethod
    def deserialize(message,_from=None):
        fields = message.split(FIELD_SEPARATOR)
        if fields[0] == LABEL + 'DISCOVERY':
            uuids = fields[1].split(SUBFIELD_SEPARATOR) if len(
                fields) > 1 else []
            return DiscoveryMSG(uuids,_from)
        else:
            raise UnknownMessageException

    def handle(self): raise NotImplemented

class DiscoveryMSG(Message):
    def __init__(self, uuids,_from=None):
        super(DiscoveryMSG, self).__init__()
        self.label = LABEL + 'DISCOVERY'
        self.uuids = set(uuids)
        self._from = _from

    def serialize(self):
        field = SUBFIELD_SEPARATOR.join(map(str,self.uuids))
        return FIELD_SEPARATOR.join((self.label, field))

    def handle(self):
        if self._from:
            watcher.sync.Sync.newPeer(self._from,self.uuids)
