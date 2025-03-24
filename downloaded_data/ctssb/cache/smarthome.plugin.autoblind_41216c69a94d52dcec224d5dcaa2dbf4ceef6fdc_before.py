#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2014-2015 Thomas Ernst                       offline@gmx.net
#########################################################################
#  This file is part of SmartHome.py.
#
#  SmartHome.py is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHome.py is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHome.py. If not, see <http://www.gnu.org/licenses/>.
#########################################################################
from . import AutoBlindTools
from . import AutoBlindConditionSets
from . import AutoBlindLogger
from . import AutoBlindActions


# Class representing an object state, consisting of name, conditions to be met and configured actions for state
class AbState:
    # Return id of state (= id of defining item)
    @property
    def id(self):
        return self.__item.id()

    # Return name of state
    @property
    def name(self):
        return self.__name

    # Constructor
    # smarthome: instance of smarthome
    # item_state: item containing configuration of state
    # logger: Instance of AbLogger to write log messages to
    def __init__(self, smarthome, item_state, item_autoblind, abitem_object, logger: AutoBlindLogger.AbLogger):
        self.__sh = smarthome
        self.__item = item_state
        self.__name = ""
        self.__enterConditionSets = AutoBlindConditionSets.AbConditionSets(self.__sh)
        self.__leaveConditionSets = AutoBlindConditionSets.AbConditionSets(self.__sh)
        self.__actions = AutoBlindActions.AbActions(self.__sh)

        logger.info("Init state {}", item_state.id())
        self.__fill(self.__item, 0, item_autoblind, abitem_object, logger)

    # Check conditions if state can be entered
    # logger: Instance of AbLogger to write log messages to
    # returns: True = At least one enter condition set is fulfulled, False = No enter condition set is fulfilled
    def can_enter(self, logger: AutoBlindLogger.AbLogger):
        logger.info("Check if state '{0}' ('{1}') can be entered:", self.id, self.name)
        logger.increase_indent()
        result = self.__enterConditionSets.one_conditionset_matching(logger)
        logger.decrease_indent()
        if result:
            logger.info("State can be entered")
        else:
            logger.info("State can not be entered")
        return result

    # Check conditions if state can be left
    # logger: Instance of AbLogger to write log messages to
    # returns: True = At least one leave condition set is fulfulled, False = No leave condition set is fulfilled
    def can_leave(self, logger: AutoBlindLogger.AbLogger):
        logger.info("Check if state '{0}' ('{1}') can be left:", self.id, self.name)
        logger.increase_indent()
        result = self.__leaveConditionSets.one_conditionset_matching(logger)
        logger.decrease_indent()
        if result:
            logger.info("State can be left")
        else:
            logger.info("State can not be left")
        return result

    # log state data
    # logger: Instance of AbLogger to write log messages to
    def write_to_log(self, logger: AutoBlindLogger.AbLogger):
        logger.info("State {0}:", self.id)
        logger.increase_indent()
        logger.info("Name: {0}", self.__name)
        if self.__enterConditionSets.count() > 0:
            logger.info("Condition sets to enter state:")
            logger.increase_indent()
            self.__enterConditionSets.write_to_logger(logger)
            logger.decrease_indent()
        if self.__leaveConditionSets.count() > 0:
            logger.info("Condition sets to leave state:")
            logger.increase_indent()
            self.__leaveConditionSets.write_to_logger(logger)
            logger.decrease_indent()
        if self.__actions.count() > 0:
            logger.info("Actions to perform if state becomes active:")
            logger.increase_indent()
            self.__actions.write_to_logger(logger)
            logger.decrease_indent()
        logger.decrease_indent()

    # activate state
    def activate(self, logger: AutoBlindLogger.AbLogger):
        logger.increase_indent()
        self.__actions.execute(logger)
        logger.decrease_indent()

    # Read configuration from item and populate data in class
    # item_state: item to read from
    # recursion_depth: current recursion_depth (recursion is canceled after five levels)
    # item_autoblind: AutoBlind-Item defining items for conditions
    # abitem_object: Related AbItem instance for later determination of current age and current delay
    # logger: Instance of AbLogger to write log messages to
    def __fill(self, item_state, recursion_depth, item_autoblind, abitem_object, logger: AutoBlindLogger.AbLogger):
        if recursion_depth > 5:
            logger.error("{0}/{1}: to many levels of 'use'", self.__item.id(), item_state.id())
            return

        # Import data from other item if attribute "use" is found
        if "as_use" in item_state.conf:
            use_item = self.__sh.return_item(item_state.conf["as_use"])
            if use_item is not None:
                self.__fill(use_item, recursion_depth + 1, item_autoblind, abitem_object, logger)
            else:
                logger.error("{0}: Referenced item '{1}' not found!", item_state.id(), item_state.conf["use"])
        elif "use" in item_state.conf:
            AutoBlindTools.log_obsolete(item_state,"use","as_use")
            use_item = self.__sh.return_item(item_state.conf["use"])
            if use_item is not None:
                self.__fill(use_item, recursion_depth + 1, item_autoblind, abitem_object, logger)
            else:
                logger.error("{0}: Referenced item '{1}' not found!", item_state.id(), item_state.conf["use"])

        # Get condition sets
        parent_item = item_state.return_parent()
        items_conditionsets = item_state.return_children()
        for item_conditionset in items_conditionsets:
            condition_name = AutoBlindTools.get_last_part_of_item_id(item_conditionset)
            if condition_name == "enter" or condition_name.startswith("enter_"):
                self.__enterConditionSets.fill(condition_name, item_conditionset, parent_item, logger)
            elif condition_name == "leave" or condition_name.startswith("leave_"):
                self.__leaveConditionSets.fill(condition_name, item_conditionset, parent_item, logger)

        # This was the blind position for this item
        if "position" in item_state.conf:
            logger.error("State '{0}': Attribute 'position' is no longer supported!".format(item_state.id()))

        for attribute in item_state.conf:
            self.__actions.update(item_state, attribute)

        # if an item name is given, or if we do not have a name after returning from all recursions,
        # use item name as state name
        if str(item_state) != item_state.id() or (self.__name == "" and recursion_depth == 0):
            self.__name = str(item_state)

        # Complete condition sets and actions at the end
        if recursion_depth == 0:
            self.__enterConditionSets.complete(item_state, abitem_object, logger)
            self.__leaveConditionSets.complete(item_state, abitem_object, logger)
            self.__actions.complete(item_state)
