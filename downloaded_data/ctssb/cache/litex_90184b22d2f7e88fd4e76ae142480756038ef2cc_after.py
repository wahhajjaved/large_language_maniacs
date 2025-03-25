from functools import partial

from migen.fhdl.structure import *
from migen.fhdl.structure import _Operator, _Slice, _Assign, _StatementList
from migen.fhdl.tools import *
from migen.fhdl.namer import Namespace, build_namespace
from migen.fhdl import verilog_mem_behavioral

def _printsig(ns, s):
	if s.bv.signed:
		n = "signed "
	else:
		n = ""
	if s.bv.width > 1:
		n += "[" + str(s.bv.width-1) + ":0] "
	n += ns.get_name(s)
	return n

def _printexpr(ns, node):
	if isinstance(node, Constant):
		if node.n >= 0:
			return str(node.bv) + str(node.n)
		else:
			return "-" + str(node.bv) + str(-node.n)
	elif isinstance(node, Signal):
		return ns.get_name(node)
	elif isinstance(node, _Operator):
		arity = len(node.operands)
		if arity == 1:
			r = node.op + _printexpr(ns, node.operands[0])
		elif arity == 2:
			r = _printexpr(ns, node.operands[0]) + " " + node.op + " " + _printexpr(ns, node.operands[1])
		else:
			raise TypeError
		return "(" + r + ")"
	elif isinstance(node, _Slice):
		# Verilog does not like us slicing non-array signals...
		if isinstance(node.value, Signal) \
		  and node.value.bv.width == 1 \
		  and node.start == 0 and node.stop == 1:
			  return _printexpr(ns, node.value)

		if node.start + 1 == node.stop:
			sr = "[" + str(node.start) + "]"
		else:
			sr = "[" + str(node.stop-1) + ":" + str(node.start) + "]"
		return _printexpr(ns, node.value) + sr
	elif isinstance(node, Cat):
		l = list(map(partial(_printexpr, ns), node.l))
		l.reverse()
		return "{" + ", ".join(l) + "}"
	elif isinstance(node, Replicate):
		return "{" + str(node.n) + "{" + _printexpr(ns, node.v) + "}}"
	else:
		raise TypeError

(_AT_BLOCKING, _AT_NONBLOCKING, _AT_SIGNAL) = range(3)

def _printnode(ns, at, level, node):
	if node is None:
		return ""
	elif isinstance(node, _Assign):
		if at == _AT_BLOCKING:
			assignment = " = "
		elif at == _AT_NONBLOCKING:
			assignment = " <= "
		elif is_variable(node.l):
			assignment = " = "
		else:
			assignment = " <= "
		return "\t"*level + _printexpr(ns, node.l) + assignment + _printexpr(ns, node.r) + ";\n"
	elif isinstance(node, _StatementList):
		return "".join(list(map(partial(_printnode, ns, at, level), node.l)))
	elif isinstance(node, If):
		r = "\t"*level + "if (" + _printexpr(ns, node.cond) + ") begin\n"
		r += _printnode(ns, at, level + 1, node.t)
		if node.f.l:
			r += "\t"*level + "end else begin\n"
			r += _printnode(ns, at, level + 1, node.f)
		r += "\t"*level + "end\n"
		return r
	elif isinstance(node, Case):
		r = "\t"*level + "case (" + _printexpr(ns, node.test) + ")\n"
		for case in node.cases:
			r += "\t"*(level + 1) + _printexpr(ns, case[0]) + ": begin\n"
			r += _printnode(ns, at, level + 2, case[1])
			r += "\t"*(level + 1) + "end\n"
		if node.default.l:
			r += "\t"*(level + 1) + "default: begin\n"
			r += _printnode(ns, at, level + 2, node.default)
			r += "\t"*(level + 1) + "end\n"
		r += "\t"*level + "endcase\n"
		return r
	else:
		raise TypeError

def _list_comb_wires(f):
	r = set()
	groups = group_by_targets(f.comb)
	for g in groups:
		if len(g[1]) == 1 and isinstance(g[1][0], _Assign):
			r |= g[0]
	return r

def _printheader(f, ios, name, ns):
	sigs = list_signals(f) | list_inst_ios(f, True, True, True) | list_mem_ios(f, True, True)
	inst_mem_outs = list_inst_ios(f, False, True, False) | list_mem_ios(f, False, True)
	inouts = list_inst_ios(f, False, False, True)
	targets = list_targets(f) | inst_mem_outs
	wires = _list_comb_wires(f) | inst_mem_outs
	r = "module " + name + "(\n"
	firstp = True
	for sig in ios:
		if not firstp:
			r += ",\n"
		firstp = False
		if sig in inouts:
			r += "\tinout " + _printsig(ns, sig)
		elif sig in targets:
			if sig in wires:
				r += "\toutput " + _printsig(ns, sig)
			else:
				r += "\toutput reg " + _printsig(ns, sig)
		else:
			r += "\tinput " + _printsig(ns, sig)
	r += "\n);\n\n"
	for sig in sigs - ios:
		if sig in wires:
			r += "wire " + _printsig(ns, sig) + ";\n"
		else:
			r += "reg " + _printsig(ns, sig) + ";\n"
	r += "\n"
	return r

def _printcomb(f, ns):
	r = ""
	if f.comb.l:
		# Generate a dummy event to get the simulator
		# to run the combinatorial process once at the beginning.
		syn_off = "// synthesis translate off\n"
		syn_on = "// synthesis translate on\n"
		dummy_s = Signal(name_override="dummy_s")
		r += syn_off
		r += "reg " + _printsig(ns, dummy_s) + ";\n"
		r += "initial " + ns.get_name(dummy_s) + " <= 1'b0;\n"
		r += syn_on
		
		groups = group_by_targets(f.comb)
		
		for g in groups:
			if len(g[1]) == 1 and isinstance(g[1][0], _Assign):
				r += "assign " + _printnode(ns, _AT_BLOCKING, 0, g[1][0])
			else:
				dummy_d = Signal(name_override="dummy_d")
				r += "\n" + syn_off
				r += "reg " + _printsig(ns, dummy_d) + ";\n"
				r += syn_on
				
				r += "always @(*) begin\n"
				for t in g[0]:
					r += "\t" + ns.get_name(t) + " <= " + str(t.reset) + ";\n"
				r += _printnode(ns, _AT_NONBLOCKING, 1, _StatementList(g[1]))
				r += syn_off
				r += "\t" + ns.get_name(dummy_d) + " <= " + ns.get_name(dummy_s) + ";\n"
				r += syn_on
				r += "end\n"
	r += "\n"
	return r

def _printsync(f, ns, clk, rst):
	r = ""
	if f.sync.l:
		r += "always @(posedge " + ns.get_name(clk) + ") begin\n"
		r += _printnode(ns, _AT_SIGNAL, 1, insert_reset(rst, f.sync))
		r += "end\n\n"
	return r

def _printinstances(f, ns, clk, rst):
	r = ""
	for x in f.instances:
		r += x.of + " "
		if x.parameters:
			r += "#(\n"
			firstp = True
			for p in x.parameters:
				if not firstp:
					r += ",\n"
				firstp = False
				r += "\t." + p[0] + "("
				if isinstance(p[1], int) or isinstance(p[1], float) or isinstance(p[1], Constant):
					r += str(p[1])
				elif isinstance(p[1], str):
					r += "\"" + p[1] + "\""
				else:
					raise TypeError
				r += ")"
			r += "\n) "
		r += ns.get_name(x) 
		if x.parameters: r += " "
		r += "(\n"
		ports = list(x.ins.items()) + list(x.outs.items()) + list(x.inouts.items())
		if x.clkport:
			ports.append((x.clkport, clk))
		if x.rstport:
			ports.append((x.rstport, rst))
		firstp = True
		for p in ports:
			if not firstp:
				r += ",\n"
			firstp = False
			r += "\t." + p[0] + "(" + ns.get_name(p[1]) + ")"
		if not firstp:
			r += "\n"
		r += ");\n\n"
	return r

def _printmemories(f, ns, handler, clk):
	r = ""
	for memory in f.memories:
		r += handler(memory, ns, clk)
	return r

def convert(f, ios=set(), name="top",
  clk_signal=None, rst_signal=None,
  return_ns=False,
  memory_handler=verilog_mem_behavioral.handler):
	if clk_signal is None:
		clk_signal = Signal(name_override="sys_clk")
		ios.add(clk_signal)
	if rst_signal is None:
		rst_signal = Signal(name_override="sys_rst")
		ios.add(rst_signal)
	ios |= f.pads

	ns = build_namespace(list_signals(f) \
		| list_inst_ios(f, True, True, True) \
		| list_mem_ios(f, True, True) \
		| ios)

	r = "/* Machine-generated using Migen */\n"
	r += _printheader(f, ios, name, ns)
	r += _printcomb(f, ns)
	r += _printsync(f, ns, clk_signal, rst_signal)
	r += _printinstances(f, ns, clk_signal, rst_signal)
	r += _printmemories(f, ns, memory_handler, clk_signal)
	r += "endmodule\n"

	if return_ns:
		return r, ns
	else:
		return r
