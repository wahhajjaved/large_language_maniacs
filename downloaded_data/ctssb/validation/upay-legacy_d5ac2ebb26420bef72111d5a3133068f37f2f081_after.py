#!/usr/bin/python

# $Id: checkout.py 84 2009-02-26 23:08:06Z fpletz $
# ----------------------------------------------------------------------------
# "THE MATE-WARE LICENSE"
# codec <codec@muc.ccc.de> wrote this file. As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a mate in return.
# ----------------------------------------------------------------------------

import socket
import sys
import time
import threading
from select import select

sys.path.insert(0, '/root/upay/trunk/lib')

from upay.config import config
import upay.tokens as tokens
from upay.logger import flogger, getLogger

if not config.getboolean('general', 'testing'):
    import upay.matemat as matemat
else:
    import upay.matemat_sim as matemat

class Checkout(threading.Thread):
    log = getLogger('Checkout')

    @flogger(log)
    def __init__(self):
        threading.Thread.__init__(self)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        #self.sock.setblocking(0)
        self.sock.bind((config.get('checkout', 'listen_ip'),
            config.getint('checkout', 'listen_port')))
        self.matemat = matemat.Matemat()

    @flogger(log)
    def go(self):
        self.matemat.writeLCD('OBEY AND CONSUME')
        while not self.gotPurse:
            self.waitForSocket()
            if not self.processCommand():
                return

        credit = self.token.eot()
        self.log.debug('credit=%s' % credit)
        self.report('Credit: %s' % credit)

        priceline = None
        while 1:
            if self.checkAbort():
                return

            priceline = self.matemat.getPriceline()
            if priceline == -1:
                self.report('TIMEOUT', 3)
                return
            elif priceline != 0:
                self.log.info('priceline=%s' % priceline)
                break
            time.sleep(0.01)

        assets = self.token.assets(priceline)
        if assets < 0:
            self.report('Not enough credits!', 3)
            return
        
        self.token.finish(priceline)
        if self.matemat.serve(priceline):
            self.log.info('Serving %s' % priceline)
            self.report('%i left! kthxbye' % assets, 3)
        else:
            self.log.info('Failed to serve %s' % priceline)
            self.report('Failed to serve!', 3)
            self.token.rollback(priceline)
            return

        if False: #not self.matemat.completeserve():
            self.log.info('Failed to complete serve %s' % priceline)
            self.report('Failed to cserve!', 3)
            self.token.rollback(priceline)

    @flogger(log)
    def report(self, msg, wait=0):
        self.matemat.writeLCD(msg)
        if wait != 0:
            time.sleep(wait)
    
    @flogger(log)
    def waitForSocket(self, timeout=None):
        r = select([self.sock], [], [], timeout)
        return len(r[0]) == 1

    @flogger(log)
    def checkAbort(self):
        if self.waitForSocket(timeout=0):
            return self.processCommand(checkAbort=True)
        return False

    @flogger(log)
    def processCommand(self, checkAbort=False):
        data, self.raddr = self.sock.recvfrom(128)
        data.strip()
        if len(data) == 0:
            return

        cmd = data[:2]
        self.log.info('cmd=%s' % cmd)
        data = data[2:].strip()
        self.log.info('data=%s' % data)

        if checkAbort:
            return cmd == 'Ab'

        ret = False
        if cmd == 'Rd':
            if self.idle:
                self.send('READY')
                ret = True
        elif cmd == 'Ab':
            pass
        elif cmd == 'Bp':
            self.matemat.writeLCD('Bad Purse!', 3)
        elif cmd == 'Td':
            self.gotPurse = True
            ret = True
        elif cmd == 'Tc':
            #self.report('Reading tokens...')
            self.token.check(data)
            self.report('Credit: %s' % self.token.tokencount)
            self.send('OK')
            ret = True

        return ret

    @flogger(log)
    def send(self, msg):
        self.log.info('msg=%s' % msg)
        return self.sock.sendto(msg, self.raddr) == 0

    @flogger(log)
    def run(self):
        self.token = tokens.Token()
        while 1:
            self.idle = True
            self.gotPurse = False
            self.go()
            self.token.clear()


class CheckoutOld(threading.Thread):
    IDLE, COUNTING, CHECKING, WAITING, SERVING, CHECKINGSERVE, ABORTING,\
            WAITSTATE, REPORTING = range(9)
    log = getLogger('Checkout')

    @flogger(log)
    def __init__(self, test=False):
        threading.Thread.__init__(self)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(0)
        self.socket.bind((config.get('checkout', 'listen_ip'),
            config.getint('checkout', 'listen_port')))
        self.matemat = matemat.Matemat()
        
        self.state = self.IDLE
        self.newstate = True
        self.served = False
        self.waiting = 0

    @flogger(log)
    def send(self, msg):
        self.log.info('msg=%s' % msg)
        # print "sending",msg
        sent = self.socket.sendto(msg, self.raddr)
        if sent == 0:
            return False
        else:
            return True

    @flogger(log)
    def checkState(self):
        if self.waiting:
            if time.time() >= self.waiting:
                self.log.debug('setting state ' + str(self.nextstate))
                self.state = self.nextstate
                self.newstate = True
                self.waiting = False

    @flogger(log)
    def setState(self, nextstate, wait=0):
        self.log.debug('nextstate=%d wait%d'%(nextstate,wait))
        self.waiting = time.time()+wait
        self.nextstate = nextstate
        self.state = self.WAITSTATE

    @flogger(log)
    def fetchCommand(self):
        try:
            data, self.raddr = self.socket.recvfrom(64)
            data.strip()
            if len(data) > 0:
                self.cmd = "%s%s" % (data[0], data[1])
                self.log.info('cmd=%s' % self.cmd)
                self.data = data[2:].strip()
                self.log.info('data=%s' % self.data)
                return True
        except:
            pass
        return False

    @flogger(log)
    def reset(self):
        if self.served:
            self.token.finish(0)
        self.token.tokenreset = True
        self.matemat.writeLCD("OBEY AND CONSUME")
        self.served = False

    @flogger(log)
    def pay(self):
        self.token.pay()

    @flogger(log)
    def run(self):
        self.token = tokens.Token()      #has to be in this thread
        while 1:
            self.checkState()
            if (self.state == self.IDLE or self.state == self.COUNTING) and \
                    select([self.socket],[],[]) and self.fetchCommand():
                if not self.command():
                    self.log.info('command failed')
                    self.send("FAIL")
            self.process()

    def process(self):
        self.log.debug('processing state %d'%self.state)
        if self.state == self.IDLE:
            self.idle()
        elif self.state == self.COUNTING:
            if self.newstate:
                self.newstate = False
                self.socket.setblocking(1)
                self.matemat.writeLCD("Reading tokens")
            if self.tokendata:
                self.token.check(self.tokendata)
                self.send("OK")
                #print time.time()
                self.tokendata = ""
        elif self.state == self.ABORTING:
            self.abort()
        elif self.state == self.WAITING:
            self.wait()
        elif self.state == self.CHECKING:
            self.check()
        elif self.state == self.SERVING:
            self.serve()
        elif self.state == self.CHECKINGSERVE:
            self.checkserve()
        elif self.state == self.REPORTING:
            if self.newstate:
                self.newstate = False
                self.matemat.writeLCD(self.report)
            self.setState(self.IDLE,3)

    def idle(self):
        if self.newstate:
            self.newstate = False
            self.reset()
        #time.sleep(0.1)

    def abort(self):
        if self.newstate:
            self.newstate = False
            self.matemat.writeLCD("aborting")
            self.setState(self.IDLE,3)

    def wait(self):
        #sys.exit(0)
        if self.newstate:
            self.newstate = False
            self.credit = self.token.eot()
            self.log.debug('credit=%s' % self.credit)
            self.matemat.writeLCD("Credit: %s" % self.credit)
        self.priceline = self.matemat.getPriceline()
        if self.priceline == -1:
            self.matemat.writeLCD("TIMEOUT")
            self.setState(self.ABORTING,3)
        elif self.priceline != 0:
            self.log.info('priceline=%s' % self.priceline)
            self.setState(self.CHECKING)
        time.sleep(0.01)

    def check(self):
        liquidity = self.token.assets(self.priceline)
        if liquidity == False:
            self.matemat.writeLCD("Not enough credits")
            self.setState(self.IDLE,3)
        else:
            self.setState(self.SERVING)

    def serve(self):
        if self.matemat.serve(self.priceline):
            self.log.info('Serving %s' % self.priceline)
            self.matemat.writeLCD("Enjoy it")
            self.served = True;
            self.setState(self.CHECKINGSERVE)
        else:
            self.log.info('Failed to serve %s' % self.priceline)
            self.matemat.writeLCD("Failed to serve")
            served = False;
            self.setState(self.ABORTING,3)

    def checkserve(self):
        if not self.matemat.completeserve():
            self.log.info('Failed to serve %s' % self.priceline)
            self.matemat.writeLCD("Failed to serve")
            served = False;
            self.setState(self.ABORTING,3)
        else:
            self.setState(self.IDLE,3)

    @flogger(log)
    def command(self):
        if self.cmd == "Ta":
            if self.token.add(tokendata):
                self.send("OK")
                return True
            return False
        elif self.cmd == "Rd":
            if self.state == self.IDLE:
                self.send("READY")
                return True
            return False
        elif self.cmd == "Ab":
            if self.state != self.IDLE and self.nextstate != self.IDLE:
                self.setState(self.ABORTING);
            return False
        elif self.cmd == "Tc":
            if self.state == self.IDLE or self.state == self.COUNTING:
                self.tokendata = self.data
                if self.state == self.IDLE:
                    self.setState(self.COUNTING)
                return True
            else:
                return False
            return True
        elif self.cmd == "Td":
            if self.state == self.COUNTING:
                self.setState(self.WAITING);
                self.socket.setblocking(0)
                return True
            return False
        elif self.cmd == "Bp":
            self.setState(self.REPORTING)
            self.report = "Bad Purse!"
            self.socket.setblocking(0)

# "Testing"
if __name__ == '__main__':
    co = Checkout()
    #co.listen()
    co.start()
    co.join()

