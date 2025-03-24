# ###################################################
# Copyright (C) 2012 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import logging

from horizons.world.production.productionline import ProductionLine
from horizons.world.production.production import Production, SingleUseProduction
from horizons.constants import PRODUCTION
from horizons.scheduler import Scheduler
from horizons.util.shapes.circle import Circle
from horizons.util.shapes.point import Point
from horizons.world.component.storagecomponent import StorageComponent
from horizons.world.component import Component
from horizons.world.status import ProductivityLowStatus, DecommissionedStatus, InventoryFullStatus
from horizons.world.production.unitproduction import UnitProduction
from horizons.command.unit import CreateUnit

class Producer(Component):
	"""Class for objects, that produce something.
	@param auto_init: bool. If True, the producer automatically adds one production
					  for each production_line.
	"""
	log = logging.getLogger("world.production")

	NAME = "producer"
	DEPENDENCIES = [StorageComponent]

	production_class = Production

	# INIT
	def __init__(self, auto_init=True, start_finished=False, productionlines={}, **kwargs):
		super(Producer, self).__init__(**kwargs)
		self.__auto_init = auto_init
		self.__start_finished = start_finished
		self.production_lines = productionlines

	def __init(self):
		# we store productions in 2 dicts, one for the active ones, and one for the inactive ones.
		# the inactive ones won't get considered for needed_resources and such.
		# the production_line id is the key in the dict (=> a building must not have two identical
		# production lines)
		self._productions = {}
		self._inactive_productions = {}


	def initialize(self):
		self.__init()
		# add production lines as specified in db.
		if self.__auto_init:
			for prod_line, attributes in self.production_lines.iteritems():
				if 'enabled_by_default' in attributes and not attributes['enabled_by_default']:
					continue  # It's set to false, don't add
				prod = self.create_production(prod_line)
				self.add_production(prod)
				prod.start()
		if self.__start_finished:
			self.finish_production_now()

	def get_production_lines_by_level(self, level):
		prod_lines = []
		for key, data in self.production_lines.iteritems():
			if 'level' in data and level in data['level']:
				prod_lines.append(key)
		return prod_lines


	def create_production(self, id):
		data = self.production_lines[id]
		production_class = self.production_class
		owner_inventory = self.instance._get_owner_inventory()
		return production_class(inventory = self.instance.get_component(StorageComponent).inventory, \
		                        owner_inventory=owner_inventory, prod_id=id, prod_data=data)

	def add_production_by_id(self, production_line_id, start_finished=False):
		"""Convenience method.
		@param production_line_id: Production line from db
		"""
		production_class = self.production_class
		owner_inventory = self.instance._get_owner_inventory()
		self.add_production(production_class(self.instance.get_component(StorageComponent).inventory, owner_inventory, \
		                                     production_line_id, self.production_lines[production_line_id], start_finished=start_finished))

	@property
	def capacity_utilisation(self):
		total = 0
		productions = self.get_productions()
		if not productions:
			return 0 # catch the border case, else there'll be a div by 0
		for production in productions:
			state_history = production.get_state_history_times(False)
			total += state_history[PRODUCTION.STATES.producing.index]
		return total / len(productions)

	def capacity_utilisation_below(self, limit):
		"""Returns whether the capacity utilisation is below a value.
		It is equivalent to "foo.capacity_utilisation <= value, but faster."""
		# idea: retrieve the value, then check how long it has to take until the limit
		# can be reached (from both sides). Within this timespan, don't check again.
		cur_tick = Scheduler().cur_tick
		if not hasattr(self, "_old_capacity_utilisation") or \
		   self._old_capacity_utilisation[0] < cur_tick or \
		   self._old_capacity_utilisation[1] != limit:
			capac = self.capacity_utilisation
			diff = abs(limit - capac)
			# all those values are relative values, so we can just do this:
			interval = diff * PRODUCTION.STATISTICAL_WINDOW
			self._old_capacity_utilisation = (cur_tick + interval, # expiration date
			                                  limit, capac < limit )
		return self._old_capacity_utilisation[2]


	def load(self, db, worldid):
		# Call this before super, because we have to make sure this is called before the
		# ConcreteObject's callback which is added during loading
		Scheduler().add_new_object(self._on_production_change, self, run_in = 0)
		super(Producer, self).load(db, worldid)
		# load all productions
		self.__init()
		lines_to_load = db("SELECT prod_line_id FROM production WHERE owner=?", worldid)
		for line_id,  in lines_to_load:
			production = self.create_production(line_id)
			assert isinstance(production, Production)
			production.load(db, worldid)
			self.add_production(production)
			# Listener has been removed in the productions.load(), because the
			# changelistener's load is called
			production.add_change_listener(self._on_production_change, call_listener_now=False)

	def save(self, db):
		super(Producer, self).save(db)
		for production in self.get_productions():
			production.save(db, self.instance.worldid)

	def load_production(self, db, worldid):
		return self.production_class.load(db, worldid)

	# INTERFACE
	def add_production(self, production):
		assert isinstance(production, Production)
		self.log.debug('%s: added production line %s', self, production.get_production_line_id())
		if production.is_paused():
			self.log.debug('%s: added production line %s is paused', self, production.get_production_line_id())
			self._inactive_productions[production.get_production_line_id()] = production
		else:
			self.log.debug('%s: added production line %s is active', self, production.get_production_line_id())
			self._productions[production.get_production_line_id()] = production
		production.add_change_listener(self._on_production_change, call_listener_now=False)
		self.instance._changed()

	def finish_production_now(self):
		"""Cheat, makes current production finish right now (and produce the resources).
		Useful to make trees fully grown at game start."""
		for production in self._productions.itervalues():
			production.finish_production_now()

	def has_production_line(self, prod_line_id):
		"""Checks if this instance has a production with a certain production line id"""
		return bool( self._get_production(prod_line_id) )

	def remove_production(self, production):
		"""Removes a production instance.
		@param production: Production instance"""
		production.remove() # production "destructor"
		if self.is_active(production):
			del self._productions[production.get_production_line_id()]
		else:
			del self._inactive_productions[production.get_production_line_id()]

	def remove_production_by_id(self, prod_line_id):
		"""
		Convenience method. Assumes, that this production line id has been added to this instance.
		@param prod_line_id: production line id to remove
		"""
		self.remove_production( self._get_production(prod_line_id) )

	def alter_production_time(self, modifier, prod_line_id=None):
		"""Multiplies the original production time of all production lines by modifier
		@param modifier: a numeric value
		@param prod_line_id: id of production line to alter. None means every production line"""
		if prod_line_id is None:
			for production in self.get_productions():
				production.alter_production_time(modifier)
		else:
			self._get_production(prod_line_id).alter_production_time(modifier)

	def remove(self):
		super(Producer, self).remove()
		Scheduler().rem_all_classinst_calls(self)
		for production in self.get_productions():
			self.remove_production(production)
		assert len(self.get_productions()) == 0 , 'Failed to remove %s ' % self.get_productions()


	# PROTECTED METHODS
	def _get_current_state(self):
		"""Returns the current state of the producer. It is the most important
		state of all productions combined. Check the PRODUCTION.STATES constant
		for list of states and their importance."""
		current_state = PRODUCTION.STATES.none
		for production in self.get_productions():
			state = production.get_animating_state()
			if state is not None and current_state < state:
				current_state = state
		return current_state

	def get_productions(self):
		"""Returns all productions, inactive and active ones, as list"""
		return self._productions.values() + self._inactive_productions.values()

	def get_production_lines(self):
		"""Returns all production lines that have been added.
		@return: a list of prodline ids"""
		return self._productions.keys() + self._inactive_productions.keys()

	def _get_production(self, prod_line_id):
		"""Returns a production of this producer by a production line id.
		@return: instance of Production or None"""
		if prod_line_id in self._productions:
			return self._productions[prod_line_id]
		elif prod_line_id in self._inactive_productions:
			return self._inactive_productions[prod_line_id]
		else:
			return None

	def is_active(self, production=None):
		"""Checks if a production, or the at least one production if production is None, is active"""
		if production is None:
			for production in self.get_productions():
				if not production.is_paused():
					return True
			return False
		else:
			assert production.get_production_line_id() in self._productions or \
			       production.get_production_line_id() in self._inactive_productions
			return not production.is_paused()

	def set_active(self, production=None, active=True):
		"""Pause or unpause a production (aka set it active/inactive).
		see also: is_active, toggle_active
		@param production: instance of Production. if None, we do it to all productions.
		@param active: whether to set it active or inactive"""
		if production is None:
			for production in self.get_productions():
				self.set_active(production, active)
			return

		line_id = production.get_production_line_id()
		if active:
			if not self.is_active(production):
				self.log.debug("ResHandler %s: reactivating production %s", self.instance.worldid, line_id)
				self._productions[line_id] = production
				del self._inactive_productions[line_id]
				production.pause(pause=False)
		else:
			if self.is_active(production):
				self.log.debug("ResHandler %s: deactivating production %s", self.instance.worldid, line_id)
				self._inactive_productions[line_id] = production
				del self._productions[line_id]
				production.pause()

		self.instance._changed()

	def toggle_active(self, production=None):
		if production is None:
			for production in self.get_productions():
				self.toggle_active(production)
		else:
			active = self.is_active(production)
			self.set_active(production, active = not active)

	def _on_production_change(self):
		"""Makes the instance act according to the producers
		current state"""
		state = self._get_current_state()
		if (state is PRODUCTION.STATES.waiting_for_res or\
			state is PRODUCTION.STATES.paused or\
			state is PRODUCTION.STATES.none):
			self.instance.act("idle", repeating=True)
		elif state is PRODUCTION.STATES.producing:
			self.instance.act("work", repeating=True)
		elif state is PRODUCTION.STATES.inventory_full:
			self.instance.act("idle_full", repeating=True)

		if self.instance.has_status_icon:
			full = state is PRODUCTION.STATES.inventory_full
			if full and not hasattr(self, "_producer_status_icon"):
				affected_res = set() # find them:
				for prod in self.get_productions():
					affected_res = affected_res.union( prod.get_unstorable_produced_res() )
				self._producer_status_icon = InventoryFullStatus(affected_res)
				self.instance._registered_status_icons.append( self._producer_status_icon )

			if not full and hasattr(self, "_producer_status_icon"):
				self.instance._registered_status_icons.remove( self._producer_status_icon )
				del self._producer_status_icon

	def get_status_icons(self):
		l = super(Producer, self).get_status_icons()
		if self.capacity_utilisation_below(ProductivityLowStatus.threshold):
			l.append( ProductivityLowStatus() )
		if not self.is_active():
			l.append( DecommissionedStatus() )
		return l

	def __str__(self):
		return "Producer(owner: " + str(self.instance) + ")"

	def get_production_progress(self):
		"""Returns the current progress of the active production."""
		for production in self._productions.itervalues():
			# Always return first production
			return production.progress
		for production in self._inactive_productions.itervalues():
			# try inactive ones, if no active ones are found
			# this makes e.g. the boatbuilder's progress bar constant when you pause it
			return production.progress
		return 0 # No production available


class QueueProducer(Producer):
	"""The QueueProducer stores all productions in a queue and runs them one
	by one. """

	production_class = SingleUseProduction


	def __init__(self, **kwargs):
		super(QueueProducer, self).__init__(auto_init=False, **kwargs)
		self.__init()

	def __init(self):
		self.production_queue = [] # queue of production line ids

	def save(self, db):
		super(QueueProducer, self).save(db)
		for i in enumerate(self.production_queue):
			position, prod_line_id = i
			db("INSERT INTO production_queue (object, position, production_line_id) VALUES(?, ?, ?)",
			   self.worldid, position, prod_line_id)

	def load(self, db, worldid):
		super(QueueProducer, self).load(db, worldid)
		self.__init()
		for (prod_line_id,) in db("SELECT production_line_id FROM production_queue WHERE object = ? ORDER by position", worldid):
			self.production_queue.append(prod_line_id)

	def add_production_by_id(self, production_line_id):
		"""Convenience method.
		@param production_line_id: Production line from db
		"""
		self.production_queue.append(production_line_id)
		if not self.is_active():
			# Remove all calls to start_next_production
			# These might still be scheduled if the last production finished
			# in the same tick as this one is being added in
			Scheduler().rem_call(self, self.start_next_production)

			self.start_next_production()

	def load_production(self, db, worldid):
		prod = self.production_class.load(db, worldid)
		prod.add_production_finished_listener(self.on_queue_element_finished)
		return prod

	def check_next_production_startable(self):
		# See if we can start the next production,  this only works if the current
		# production is done
		#print "Check production"
		state = self._get_current_state()
		return (state is PRODUCTION.STATES.done or\
				state is PRODUCTION.STATES.none or\
		        state is PRODUCTION.STATES.paused) and\
			   (len(self.production_queue) > 0)

	def on_queue_element_finished(self, production):
		"""Callback used for the SingleUseProduction"""
		self.remove_production(production)
		Scheduler().add_new_object(self.start_next_production, self)

	def start_next_production(self):
		"""Starts the next production that is in the queue, if there is one."""
		if self.check_next_production_startable():
			self._productions.clear() # Make sure we only have one production active
			production_line_id = self.production_queue.pop(0)
			prod = self.create_production(production_line_id)
			prod.add_production_finished_listener(self.on_queue_element_finished)
			self.add_production( prod )
			self.instance.set_active(production=prod, active=True)
		else:
			self.set_active(active=False)

	def cancel_all_productions(self):
		self.production_queue = []
		self.cancel_current_production()

	def cancel_current_production(self):
		"""Cancels the current production and proceeds to the next one, if there is one"""
		# Remove current productions, loose all progress and resources
		for production in self._productions.copy().itervalues():
			self.remove_production(production)
		for production in self._inactive_productions.copy().itervalues():
			self.remove_production(production)
		if self.production_queue:
			self.start_next_production()
		else:
			self.set_active(active=False)

	def remove_from_queue(self, index):
		"""Remove the index'th element from the queue. First element is 0"""
		self.production_queue.pop(index)
		self.instance._changed()


class UnitProducer(QueueProducer):
	"""The QueueProducer stores all productions in a queue and runs them one
	by one. """

	production_class = UnitProduction

	def get_unit_production_queue(self):
		"""Returns a list unit type ids that are going to be produced.
		Does not include the currently produced unit. List is in order."""
		queue = []
		for prod_line_id in self.production_queue:
			prod_line = ProductionLine(prod_line_id, self.production_lines[prod_line_id])
			units = prod_line.unit_production.keys()
			if len(units) > 1:
				print 'WARNING: unit production system has been designed for 1 type per order'
			queue.append(units[0])
		return queue

	def on_queue_element_finished(self, production):
		self.__create_unit()
		super(UnitProducer, self).on_queue_element_finished(production)

	def __create_unit(self):
		"""Create the produced unit now."""
		productions = self._productions.values()
		for production in productions:
			assert isinstance(production, UnitProduction)
			self.instance.on_building_production_finished(production.get_produced_units())
			for unit, amount in production.get_produced_units().iteritems():
				for i in xrange(0, amount):
					radius = 1
					found_tile = False
					# search for free water tile, and increase search radius if none is found
					while not found_tile:
						for coord in Circle(self.instance.position.center(), radius).tuple_iter():
							point = Point(coord[0], coord[1])
							if self.instance.island.get_tile(point) is None:
								tile = self.instance.session.world.get_tile(point)
								if tile is not None and tile.is_water and coord not in self.instance.session.world.ship_map:
									# execute bypassing the manager, it's simulated on every machine
									CreateUnit(self.instance.owner.worldid, unit, point.x, point.y)(issuer=self.instance.owner)
									found_tile = True
									break
						radius += 1
