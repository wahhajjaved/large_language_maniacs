from queue import Queue
from binascii import hexlify

def view_hex(b: bytes):
    return '0x{}'.format(hexlify(b).decode('ascii'))

class QueueStream:
    stream_counter = 0
    def __init__(self, name=None):
        self.name = name or str(self.stream_counter)
        QueueStream.stream_counter += 1
        self.queue = Queue()

    def __repr__(self):
        return 'QueueStream("{}")'.format(self.name)

    def write(self, data: bytes):
        # lock!
        for byt in data:
            self.queue.put(byt)
        return len(data)

    def read(self, size: int):
        return b''.join(self.queue.get().to_bytes(1, 'little') for i in range(size))

    def flush(self):
        pass


class TypeWrapper:
    '''Wraps a core.Type and provides a nice annotation for Signature instances'''
    def __init__(self, typ, name_converter):
        self.typ = typ
        self.name_converter = name_converter

    def __repr__(self):
        return self.type_name(self.typ)
