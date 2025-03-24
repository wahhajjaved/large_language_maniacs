from __future__ import absolute_import
from __future__ import print_function

import veriloggen.core.vtypes as vtypes
import veriloggen.core.module as module
import veriloggen.dataflow as dataflow
from veriloggen.seq.seq import Seq, make_condition
from . import util


class BramInterface(object):
    _I = 'Reg'
    _O = 'Wire'

    def __init__(self, m, name=None, datawidth=32, addrwidth=10, itype=None, otype=None,
                 p_addr='addr', p_rdata='rdata', p_wdata='wdata', p_wenable='wenable',
                 index=None):

        if itype is None:
            itype = self._I
        if otype is None:
            otype = self._O

        self.m = m

        name_addr = p_addr if name is None else '_'.join([name, p_addr])
        name_rdata = p_rdata if name is None else '_'.join([name, p_rdata])
        name_wdata = p_wdata if name is None else '_'.join([name, p_wdata])
        name_wenable = p_wenable if name is None else '_'.join(
            [name, p_wenable])

        if index is not None:
            name_addr = name_addr + str(index)
            name_rdata = name_rdata + str(index)
            name_wdata = name_wdata + str(index)
            name_wenable = name_wenable + str(index)

        self.addr = util.make_port(m, itype, name_addr, addrwidth, initval=0)
        self.rdata = util.make_port(m, otype, name_rdata, datawidth, initval=0)
        self.wdata = util.make_port(m, itype, name_wdata, datawidth, initval=0)
        self.wenable = util.make_port(m, itype, name_wenable, initval=0)

    def connect(self, targ):
        util.connect_port(self.addr, targ.addr)
        util.connect_port(targ.rdata, self.rdata)
        util.connect_port(self.wdata, targ.wdata)
        util.connect_port(self.wenable, targ.wenable)


class BramSlaveInterface(BramInterface):
    _I = 'Input'
    _O = 'Output'


class BramMasterInterface(BramInterface):
    _I = 'Output'
    _O = 'Input'


#-------------------------------------------------------------------------
def mkBramDefinition(name, datawidth=32, addrwidth=10, numports=2):
    m = module.Module(name)
    clk = m.Input('CLK')

    interfaces = []

    for i in range(numports):
        interface = BramSlaveInterface(
            m, name + '_%d' % i, datawidth, addrwidth)
        interface.delay_addr = m.Reg(name + '_%d_daddr' % i, addrwidth)
        interfaces.append(interface)

    mem = m.Reg('mem', datawidth, length=2**addrwidth)

    for interface in interfaces:
        m.Always(vtypes.Posedge(clk))(
            vtypes.If(interface.wenable)(
                mem[interface.addr](interface.wdata)
            ),
            interface.delay_addr(interface.addr)
        )
        m.Assign(interface.rdata(mem[interface.delay_addr]))

    return m


#-------------------------------------------------------------------------
class Bram(object):

    def __init__(self, m, name, clk, rst, datawidth=32, addrwidth=10, numports=1):
        self.m = m
        self.name = name
        self.clk = clk
        self.rst = rst
        self.datawidth = datawidth
        self.addrwidth = addrwidth
        self.interfaces = [BramInterface(m, name + '_%d' % i, datawidth, addrwidth)
                           for i in range(numports)]

        self.definition = mkBramDefinition(
            name, datawidth, addrwidth, numports)
        self.inst = self.m.Instance(self.definition, 'inst_' + name,
                                    ports=m.connect_ports(self.definition))

        self.seq = Seq(m, name, clk, rst)
        # self.m.add_hook(self.seq.make_always)

        self._write_disabled = [False for i in range(numports)]

    def __getitem__(self, index):
        return self.interfaces[index]

    def disable_write(self, port):
        self.seq(
            self.interfaces[port].wdata(0),
            self.interfaces[port].wenable(0)
        )
        self._write_disabled[port] = True

    def write(self, port, addr, wdata, cond=None):
        """ 
        @return None
        """
        
        if self._write_disabled[port]:
            raise TypeError('Write disabled.')

        if cond is not None:
            self.seq.If(cond)

        self.seq(
            self.interfaces[port].addr(addr),
            self.interfaces[port].wdata(wdata),
            self.interfaces[port].wenable(1)
        )

        self.seq.Then().Delay(1)(
            self.interfaces[port].wenable(0)
        )

    def write_dataflow(self, port, addr, data, length=1, cond=None):
        """ 
        @return done
        """
        
        if self._write_disabled[port]:
            raise TypeError('Write disabled.')

        counter = self.m.TmpReg(length.bit_length() + 1, initval=0)
        last = self.m.TmpReg(initval=0)
        
        data_cond = make_condition(cond, vtypes.Not(last))
        raw_data, raw_valid = data.read(cond=data_cond)

        self.seq.If(vtypes.Ands(raw_valid, counter == 0))(
            self.interfaces[port].addr(addr),
            self.interfaces[port].wdata(raw_data),
            self.interfaces[port].wenable(1),
            counter(length - 1),
        )

        self.seq.If(vtypes.Ands(raw_valid, counter > 0))(
            self.interfaces[port].addr.inc(),
            self.interfaces[port].wdata(raw_data),
            self.interfaces[port].wenable(1),
            counter.dec()
        )

        self.seq.If(vtypes.Ands(raw_valid, counter == 1))(
            last(1)
        )

        # de-assert
        self.seq.Delay(1)(
            self.interfaces[port].wenable(0),
            last(0)
        )

        done = last

        return done

    def read(self, port, addr, cond=None):
        """ 
        @return data, valid
        """
        
        if cond is not None:
            self.seq.If(cond)

        self.seq(
            self.interfaces[port].addr(addr)
        )

        rdata = self.interfaces[port].rdata
        rvalid = self.m.TmpReg(initval=0)
        self.seq.Then().Delay(1)(
            rvalid(1)
        )
        self.seq.Then().Delay(2)(
            rvalid(0)
        )

        return rdata, rvalid

    def read_dataflow(self, port, addr, length=1, cond=None):
        """ 
        @return data, last, done
        """
        
        data_valid = self.m.TmpReg(initval=0)
        last_valid = self.m.TmpReg(initval=0)
        data_ready = self.m.TmpWire()
        last_ready = self.m.TmpWire()
        data_ready.assign(1)
        last_ready.assign(1)

        data_ack = vtypes.Ors(data_ready, vtypes.Not(data_valid))
        last_ack = vtypes.Ors(last_ready, vtypes.Not(last_valid))

        ext_cond = make_condition(cond)
        data_cond = make_condition(data_ack, last_ack)
        prev_data_cond = self.seq.Prev(data_cond, 1)
        all_cond = make_condition(data_cond, ext_cond)

        data = self.m.TmpWireLike(self.interfaces[port].rdata)
        prev_data = self.seq.Prev(data, 1)
        data.assign(vtypes.Mux(prev_data_cond,
                               self.interfaces[port].rdata, prev_data))

        counter = self.m.TmpReg(length.bit_length() + 1, initval=0)

        next_valid_on = self.m.TmpReg(initval=0)
        next_valid_off = self.m.TmpReg(initval=0)

        next_last = self.m.TmpReg(initval=0)
        last = self.m.TmpReg(initval=0)

        self.seq.If(vtypes.Ands(data_cond, next_valid_off))(
            last(0),
            data_valid(0),
            last_valid(0),
            next_valid_off(0)
        )
        self.seq.If(vtypes.Ands(data_cond, next_valid_on))(
            data_valid(1),
            last_valid(1),
            last(next_last),
            next_last(0),
            next_valid_on(0),
            next_valid_off(1)
        )
        self.seq.If(vtypes.Ands(all_cond, counter == 0,
                                vtypes.Not(next_last), vtypes.Not(last)))(
            self.interfaces[port].addr(addr),
            counter(length - 1),
            next_valid_on(1),
        )
        self.seq.If(vtypes.Ands(data_cond, counter > 0))(
            self.interfaces[port].addr.inc(),
            counter.dec(),
            next_valid_on(1),
            next_last(0)
        )
        self.seq.If(vtypes.Ands(data_cond, counter == 1))(
            next_last(1)
        )

        df_data = dataflow.Variable(data, data_valid, data_ready)
        df_last = dataflow.Variable(last, last_valid, last_ready, width=1)
        done = last

        return df_data, df_last, done
