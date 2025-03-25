#!/usr/bin/python3
"""
quicky (?I hope) to read a log file as it is being written.
"""
import sys, os, time, struct
from sendmail import sendMail
# from PySide import QtCore, QtGui

class EyeSDNFile:
    tell_tale_bytes = 'EyeSDN'.encode('utf8')

    def unrecognized(self, body, name="oh dear"):
        pass  # print (name)

    def outside_line_requested(self, body, name):
        print(name)

    def our_number_dialled(self, body, name):
        print(*[(i, hex(b)) for (i, b) in enumerate(body)]) # , sep='\n')
        iStart = 20
        iEnd = int(body[17]) + 18
        # can't explain or logically deduce location of called number,but this seems to work:
        if iStart==iEnd:
            caller = "(caller's number withheld)"
        else:
            caller = "(0)" + body[20:iEnd].decode()
        iStart = 1 + body.rindex(b'\xa1')
        iEnd = iStart+9
        called = "(0)" + body[iStart:iEnd].decode()
        #called = body[iEnd+3:iEnd + 2 + body[iEnd + 1]] # '(0)' + body[32:41].decode()
        subject = "on " + self.s_time_then + ", " + caller + " called " + called
        print(subject)
        if self.dither_count:
            print("must send mail!")
            sendMail(recipients = ['hippos@chello.nl', 'g.m.myerscough@gmail.com'],
                     subject=subject)
        else:
            print("old cow - no need to send mail.")

    def __init__(self, name, mode='rb', block_size=1024, dither=False):
        if not 'b' in mode:
            raise ValueError("must use binary (e.g. 'rb' or 'wb') mode for EyeSDN files")
        self.actual_file = open(name, mode=mode)
        self.block_size = block_size
        self.dither= dither
        if 0: # 'r' in mode:
            starter = self.actual_file.read(7)
            if  starter != self.tell_tale_bytes:
                raise IOError("file does not start with '%s'" % self.tell_tale_bytes)
        if 'w' in mode:
            self.actual_file.write(self.tell_tale_bytes)
        self.carry_bytes = b''
        self.dither_count = 0

        self.interpret_log_bytes = (
            ((0x00, 0x91, 0x73), self.outside_line_requested),
            ((0x02, 0xff, 0x03), self.our_number_dialled),
            ((),                 self.unrecognized),
        )

    def read_packet(self):
        while 1:
            i = self.carry_bytes.find(0xff)
            # print ("index of 0xff =", i)
            if i >= 0:
                packet = self.carry_bytes[:i]
                self.carry_bytes = self.carry_bytes[i+1:]
                break
            new_bytes = self.actual_file.read(self.block_size)
            if new_bytes:
                self.carry_bytes += new_bytes
                continue
            if not self.dither:
                packet = self.carry_bytes
                self.carry_bytes = b''
                break
            self.dither_count += 1
            time.sleep(self.dither)
        # print ("carry bytes", self.carry_bytes)
        return (packet.replace(b'\xfe\xfd', b'\xff')
                      .replace(b'\xfe\xfc', b'\xfe'))

    def get_packet_parts(self):
        packet = self.read_packet()
        if packet ==self.tell_tale_bytes:
            return None
        head = bytes([0]) + packet[:12]  # prefix null byte to facilitate unpacking
        usecs, secs, origin, length = struct.unpack('>LxLxbH', head)
        local_time_then = time.localtime(secs)
        body = packet[12:]
        self.s_time_then = time.strftime('%A %Y-%b-%d %H:%M:%S', local_time_then)
        #print(self.s_time_then + ('%06u' % usecs), end=' ')
        #print([hex(b) for b in head] + [' ---'] + [hex(b) for b in body], end=' ')
        if length != len(body):
            raise ValueError('actual length %s != advertized lengh %s'
                             %(len(body), length))
        return local_time_then, usecs, body


    def process_next_packet(self):
        packet_parts = self.get_packet_parts()
        if not packet_parts:
            print("logger daemon (re-)started")
            return
        local_time_then, usecs, body = packet_parts
        #print(time.strftime('%Y-%b-%d %H:%M:%S.', local_time_then) + ('%06u ---' % usecs),
        #      ', '.join([hex(b) for b in body]))
        for first_bytes, func in self.interpret_log_bytes:
            if body.startswith(bytes(first_bytes)):
                func(body, func.__name__)
                return

def main():
    prog = sys.argv.pop(0)
    log =  EyeSDNFile(sys.argv and sys.argv.pop() or
                      '/home/gill/log/misdn_ws.log', 'rb', dither=0.2)
    while 1:
        log.process_next_packet()


if __name__ == '__main__':
    main()
