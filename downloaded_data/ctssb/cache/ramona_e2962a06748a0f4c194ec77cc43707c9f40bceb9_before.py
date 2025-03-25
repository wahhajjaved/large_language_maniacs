import logging, time
from ..config import config
from ..cnscom import svrcall_error
from .program import program
from .seqctrl import sequence_controller

###

L = logging.getLogger('proaster')

###

class program_roaster(object):
	'''
Program roaster is object that control all configured programs, their start/stop operations etc.
	'''

	def __init__(self):
		self.start_seq = None
		self.stop_seq = None
		self.restart_seq = None

		self.roaster = []
		for config_section in config.sections():
			if config_section.find('program:') != 0: continue
			sp = program(self.loop, config_section)
			self.roaster.append(sp)


	def filter_roaster_iter(self, pfilter=None):
		if pfilter is None:
			for p in self.roaster: yield p
			return

		filter_set = frozenset(pfilter)
		roaster_dict = dict((p.ident, p) for p in self.roaster)

		# Pass only known program names
		not_found = filter_set.difference(roaster_dict)
		if len(not_found) > 0: raise svrcall_error("Unknown/invalid program names: {0}".format(', '.join(not_found)))

		for ident, p in roaster_dict.iteritems():
			if ident in filter_set: yield p


	def start_program(self, pfilter=None, force=False):
		'''Start processes that are STOPPED and (forced) FATAL'''
		if self.start_seq is not None or self.stop_seq is not None or self.restart_seq is not None:
			raise svrcall_error("There is already start/stop sequence running - please wait and try again later.")

		l = self.filter_roaster_iter(pfilter)

		L.debug("Initializing start sequence")
		self.start_seq = sequence_controller()

		# If 'force' is used, include as programs in FATAL state
		if force: states = (program.state_enum.STOPPED,program.state_enum.FATAL)
		else: states = (program.state_enum.STOPPED,)

		for p in l:
			if p.state not in states: continue
			self.start_seq.add(p)		

		self.__startstop_pad_next(True)


	def stop_program(self, pfilter=None, force=False):
		'''
		Stop processes that are RUNNING and STARTING
		@param force: If True then it interrupts any concurrently running start/stop sequence.
		'''
		if force:
			self.start_seq = None
			self.restart_seq = None
			self.stop_seq = None

		else:
			if self.start_seq is not None or self.stop_seq is not None or self.restart_seq is not None:
				raise svrcall_error("There is already start/stop sequence running - please wait and try again later.")

		l = self.filter_roaster_iter(pfilter)

		L.debug("Initializing stop sequence")
		self.stop_seq = sequence_controller()

		for p in l:
			if p.state not in (program.state_enum.RUNNING, program.state_enum.STARTING): continue
			self.stop_seq.add(p)		

		self.__startstop_pad_next(False)


	def restart_program(self, pfilter=None, force=False):
		'''Restart processes that are RUNNING, STARTING, STOPPED and (forced) FATAL'''
		if self.start_seq is not None or self.stop_seq is not None or self.restart_seq is not None:
			raise svrcall_error("There is already start/stop sequence running - please wait and try again later.")

		L.debug("Initializing restart sequence")
		
		l = self.filter_roaster_iter(pfilter)

		self.stop_seq = sequence_controller()
		self.restart_seq = sequence_controller()

		# If 'force' is used, include as programs in FATAL state
		if force: start_states = (program.state_enum.STOPPED,program.state_enum.FATAL)
		else: start_states = (program.state_enum.STOPPED,)

		for p in l:
			if p.state in (program.state_enum.RUNNING, program.state_enum.STARTING):
				self.stop_seq.add(p)
				self.restart_seq.add(p)
			elif p.state in start_states:
				self.restart_seq.add(p)

		self.__startstop_pad_next(False)



	def __startstop_pad_next(self, start=True):
		pg = self.start_seq.next() if start else self.stop_seq.next()
		if pg is None:
			if start:
				self.start_seq = None
				L.debug("Start sequence completed.")
			else:
				self.stop_seq = None

				if self.restart_seq is None or self.termstatus is not None:
					L.debug("Stop sequence completed.")
					return

				else:
					L.debug("Restart sequence enters starting phase")
					self.start_seq = self.restart_seq
					self.restart_seq = None
					self.__startstop_pad_next(True)
					return

		else:
			# Start/stop all programs in the active set
			map(program.start if start else program.stop, pg)


	def on_terminate_program(self, pid, status):
		for p in self.roaster:
			if pid != p.pid: continue
			return p.on_terminate(status)
		else:
			L.warning("Unknown program died (pid={0}, status={1})".format(pid, status))


	def on_tick(self):
		'''Periodic check of program states'''
		now = time.time()
		for p in self.roaster:
			p.on_tick(now)

		if self.start_seq is not None:
			r = self.start_seq.check(program.state_enum.STARTING, program.state_enum.RUNNING)
			if r is None:
				L.warning("Start sequence aborted due to program error")
				self.start_seq = None
				assert self.restart_seq is None
			elif r:
				self.__startstop_pad_next(True)

		if self.stop_seq is not None:
			r = self.stop_seq.check(program.state_enum.STOPPING, program.state_enum.STOPPED)
			if r is None:
				if self.restart_seq is None:
					L.warning("Stop sequence aborted due to program error")
					self.stop_seq = None
					assert self.start_seq is None
					assert self.restart_seq is None
				else:
					L.warning("Restart sequence aborted due to program error")
					self.restart_seq = None
					self.stop_seq = None
					assert self.start_seq is None

			elif r:
				self.__startstop_pad_next(False)

		if (self.termstatus is not None) and (self.stop_seq is None):
			# Special care for server terminating condition 
			not_running_states=frozenset([program.state_enum.STOPPED, program.state_enum.FATAL, program.state_enum.CFGERROR])
			ready_to_stop = True
			for p in self.roaster: # Seek for running programs
				if p.state not in not_running_states:
					ready_to_stop = False
					break

			if ready_to_stop: # Happy-flow (stop sequence finished and there is no program running - we can stop looping and exit)
				for p in self.roaster:
					if p.state in (program.state_enum.FATAL, program.state_enum.CFGERROR):
						L.warning("Process in error condition during exit: {0}".format(p))
				self.stop_loop()
			else:
				L.warning("Restarting stop sequence due to exit request.")
				self.stop_program(force=True)
