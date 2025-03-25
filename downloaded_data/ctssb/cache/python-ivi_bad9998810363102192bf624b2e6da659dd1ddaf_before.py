"""

Python Interchangeable Virtual Instrument Library

Copyright (c) 2012 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import Gpib

class LinuxGpibInstrument:
    "Linux GPIB wrapper instrument interface client"
    def __init__(self, name = 'gpib0', pad = None, sad = 0, timeout = 13, send_eoi = 1, eos_mode = 0):
        self.gpib = Gpib.Gpib(name, pad, sad, timeout, send_eoi, eos_mode)

    def write_raw(self, data):
        "Write binary data to instrument"
        
        self.gpib.write(data)

    def read_raw(self, num=-1):
        "Read binary data from instrument"
        
        if num < 0:
            num = 512
        
        return self.gpib.read(len)
    
    def ask_raw(self, data, num=-1):
        "Write then read binary data"
        self.write_raw(data)
        return self.read_raw(num)
    
    def write(self, message, encoding = 'utf-8'):
        "Write string to instrument"
        if message.__class__ is tuple or message.__class__ is list:
            # recursive call for a list of commands
            for message_i in message:
                self.write(message_i, encoding)
            return
        
        self.write_raw(str(message).encode(encoding))

    def read(self, num=-1, encoding = 'utf-8'):
        "Read string from instrument"
        return self.read_raw(num).decode(encoding).rstrip('\r\n')

    def ask(self, message, num=-1, encoding = 'utf-8'):
        "Write then read string"
        self.write(message, encoding)
        return self.read(num, encoding)
    
    def read_stb(self):
        "Read status byte"
        raise NotImplementedError()
    
    def trigger(self):
        "Send trigger command"
        
        self.gpib.trigger()
    
    def clear(self):
        "Send clear command"
        
        self.gpib.clear()
    
    def remote(self):
        "Send remote command"
        raise NotImplementedError()
    
    def local(self):
        "Send local command"
        raise NotImplementedError()
    
    def lock(self):
        "Send lock command"
        raise NotImplementedError()
    
    def unlock(self):
        "Send unlock command"
        raise NotImplementedError()

