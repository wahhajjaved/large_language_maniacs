# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from urwid import (AttrMap, Divider, Padding, Pile, Text,
                   WidgetWrap)

from cloudinstall.maas import satisfies
from cloudinstall.state import CharmState
from cloudinstall.placement.ui.service_widget import ServiceWidget

log = logging.getLogger('cloudinstall.placement.ui')


class ServicesList(WidgetWrap):

    """A list of services (charm classes) with flexible display options.

    Note that not all combinations of display options make sense. YMMV.

    controller - a PlacementController

    actions - a list of tuples describing buttons. Passed to
    ServiceWidget.

    machine - a machine instance to query for constraint checking. If
    None, no constraint checking is done. If set, only services whose
    constraints are satisfied by 'machine' are shown.

    ignore_assigned - bool, whether or not to display services that
    have already been assigned to a machine (but not yet deployed)

    ignore_deployed - bool, whether or not to display services that
    have already been deployed

    deployed_only - bool, only show deployed services

    show_constraints - bool, whether or not to display the constraints
    for the various services

    show_type - string, one of 'all', 'required' or 'non-required',
    controls which charm states should be shown. default is 'all'.

    trace_updates - bool, enable verbose update logging

    """

    def __init__(self, controller, actions, subordinate_actions,
                 machine=None, ignore_assigned=False,
                 ignore_deployed=False, assigned_only=False,
                 deployed_only=False, show_type='all',
                 show_constraints=False, show_placements=False,
                 title="Services", trace_updates=False):
        self.controller = controller
        self.actions = actions
        self.subordinate_actions = subordinate_actions
        self.service_widgets = []
        self.machine = machine
        self.ignore_assigned = ignore_assigned
        self.ignore_deployed = ignore_deployed
        self.assigned_only = assigned_only
        self.deployed_only = deployed_only
        self.show_type = show_type
        self.show_constraints = show_constraints
        self.show_placements = show_placements
        self.title = title
        self.trace = trace_updates
        w = self.build_widgets()
        self.update()
        super().__init__(w)

    def selectable(self):
        # overridden to ensure that we can arrow through the buttons
        # shouldn't be necessary according to documented behavior of
        # Pile & Columns, but discovered via trial & error.
        return True

    def build_widgets(self):
        self.service_pile = Pile([Text(self.title),
                                  Divider(' ')] +
                                 self.service_widgets)
        return self.service_pile

    def find_service_widget(self, cc):
        return next((sw for sw in self.service_widgets if
                     sw.charm_class.charm_name == cc.charm_name), None)

    def update(self):

        def trace(cc, s):
            if self.trace:
                log.debug("{}: {} {}".format(self.title, cc, s))

        for cc in self.controller.charm_classes():
            if self.machine:
                if not satisfies(self.machine, cc.constraints)[0] \
                   or not (self.controller.is_assigned_to(cc, self.machine) or
                           self.controller.is_deployed_to(cc, self.machine)):
                    self.remove_service_widget(cc)
                    trace(cc, "removed because machine doesn't match")
                    continue

            if self.ignore_assigned and self.assigned_only:
                raise Exception("Can't both ignore and only show assigned.")

            if self.ignore_assigned:
                n = self.controller.assignment_machine_count_for_charm(cc)
                if n == cc.required_num_units() \
                   and self.controller.is_assigned(cc):
                    self.remove_service_widget(cc)
                    trace(cc, "removed because max units are "
                          "assigned")
                    continue
            elif self.assigned_only:
                if not self.controller.is_assigned(cc):
                    self.remove_service_widget(cc)
                    trace(cc, "removed because it is not assigned and "
                          "assigned_only is True")
                    continue

            if self.ignore_deployed and self.deployed_only:
                raise Exception("Can't both ignore and only show deployed.")

            if self.ignore_deployed:
                n = self.controller.deployment_machine_count_for_charm(cc)
                if n == cc.required_num_units() \
                   and self.controller.is_deployed(cc):
                    self.remove_service_widget(cc)
                    trace(cc, "removed because the required number of units"
                          " has been deployed")
                    continue
            elif self.deployed_only:
                if not self.controller.is_deployed(cc):
                    self.remove_service_widget(cc)
                    continue

            state, _, _ = self.controller.get_charm_state(cc)
            if self.show_type == 'required':
                if state != CharmState.REQUIRED:
                    self.remove_service_widget(cc)
                    continue
            elif self.show_type == 'non-required':
                if state == CharmState.REQUIRED:
                    self.remove_service_widget(cc)
                    trace(cc, "removed because show_type is 'non-required' and"
                          "state is REQUIRED.")
                    continue
                if not cc.allow_multi_units and \
                   not (self.controller.is_assigned(cc) or
                        self.controller.is_deployed(cc)):
                    self.remove_service_widget(cc)
                    trace(cc, "removed because it doesn't allow multiple units"
                          " and is not assigned or deployed.")
                    continue

            sw = self.find_service_widget(cc)
            if sw is None:
                sw = self.add_service_widget(cc)
                trace(cc, "added widget")
            sw.update()

    def add_service_widget(self, charm_class):
        if charm_class.subordinate:
            actions = self.subordinate_actions
        else:
            actions = self.actions
        sw = ServiceWidget(charm_class, self.controller, actions,
                           self.show_constraints,
                           show_placements=self.show_placements)
        self.service_widgets.append(sw)
        options = self.service_pile.options()
        self.service_pile.contents.append((sw, options))
        self.service_pile.contents.append((AttrMap(Padding(Divider('\u23bc'),
                                                           left=2, right=2),
                                                   'label'), options))
        return sw

    def remove_service_widget(self, charm_class):
        sw = self.find_service_widget(charm_class)

        if sw is None:
            return
        self.service_widgets.remove(sw)
        sw_idx = 0
        for w, opts in self.service_pile.contents:
            if w == sw:
                break
            sw_idx += 1

        c = self.service_pile.contents[:sw_idx] + \
            self.service_pile.contents[sw_idx + 2:]
        self.service_pile.contents = c
