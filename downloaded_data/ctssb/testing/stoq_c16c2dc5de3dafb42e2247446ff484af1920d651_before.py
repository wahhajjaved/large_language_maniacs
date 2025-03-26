# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005, 2006 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
##  Author(s):      Bruno Rafael Garcia     <brg@async.com.br>
##                  Evandro Vale Miquelito  <evandro@async.com.br>
##
##
""" User editor slaves implementation.  """

import gtk
from sqlobject.sqlbuilder import func
from kiwi.datatypes import ValidationError

from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.lib.parameters import sysparam
from stoqlib.lib.validators import validate_password
from stoqlib.exceptions import DatabaseInconsistency
from stoqlib.gui.base.editors import BaseEditorSlave
from stoqlib.gui.base.dialogs import run_dialog
from stoqlib.gui.editors.profileeditor import UserProfileEditor
from stoqlib.domain.profile import UserProfile
from stoqlib.domain.person import Person, LoginInfo
from stoqlib.domain.interfaces import IUser


_ = stoqlib_gettext


class UserStatusSlave(BaseEditorSlave):
    gladefile = 'UserStatusSlave'
    model_iface = IUser
    proxy_widgets = ('active_check',)

    def setup_proxies(self):
        self.proxy = self.add_proxy(self.model,
                                    UserStatusSlave.proxy_widgets)


class PasswordEditorSlave(BaseEditorSlave):
    """ A slave for asking (and confirming) password; Optionally, this slave
    can be used just to ask the password once, i.e, not displaying the entry
    for confirmation (see confirm_password parameter).
    """
    gladefile = 'PasswordEditorSlave'
    model_type = LoginInfo
    proxy_widgets = ('password',
                     'confirm_password')
    size_group_widgets = ('password_lbl',
                          'confirm_password_lbl')

    def __init__(self, conn, model=None, confirm_password=False):
        BaseEditorSlave.__init__(self, conn, model)
        self._confirm_password = confirm_password
        self._setup_widgets()

    def _setup_widgets(self):
        if not self._confirm_password:
            self.confirm_password_lbl.hide()
            self.confirm_password.hide()

    #
    # Hooks
    #

    def set_password_labels(self, password_lbl, confirm_password):
        self.password_lbl.set_text(password_lbl)
        self.confirm_password_lbl.set_text(confirm_password)

    #
    # BaseEditorSlave Hooks
    #

    def create_model(self, conn):
        return LoginInfo()

    def setup_proxies(self):
        self.proxy = self.add_proxy(self.model,
                                    PasswordEditorSlave.proxy_widgets)

    def validate_confirm(self):
        callback = lambda msg: self.password.set_invalid(msg)
        new_passwd = self.model.new_password
        if not validate_password(new_passwd, callback):
            return False
        if not self._confirm_password:
            return True

        callback = lambda msg: self.confirm_password.set_invalid(msg)
        confirm_passwd = self.model.confirm_password
        if not validate_password(confirm_passwd, callback):
            return False

        if confirm_passwd != new_passwd:
            msg = _(u"New password and confirm password don't match")
            self.password.set_invalid(msg)
            return False
        return True


class UserDetailsSlave(BaseEditorSlave):
    gladefile = 'UserDetailsSlave'
    model_iface = IUser
    proxy_widgets = ('username',
                     'profile')

    size_group_widgets = ('username_lbl',
                          'profile_lbl') + proxy_widgets

    def __init__(self, conn, model, show_password_fields=True,
                 visual_mode=False):
        self.show_password_fields = show_password_fields
        self.max_results = sysparam(conn).MAX_SEARCH_RESULTS
        BaseEditorSlave.__init__(self, conn, model, visual_mode=visual_mode)

    def _setup_size_group(self, size_group, widgets, obj):
        for widget_name in widgets:
            widget = getattr(obj, widget_name)
            size_group.add_widget(widget)

    def _setup_widgets(self):
        if self.show_password_fields:
            self._attach_slaves()
            size_group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
            self._setup_size_group(size_group,
                                   UserDetailsSlave.size_group_widgets,
                                   self)
            self._setup_size_group(size_group,
                                   self.password_slave.size_group_widgets,
                                   self.password_slave)
        self._setup_entry_completion()

    def _setup_entry_completion(self):
        profiles = [profile for profile in
                    UserProfile.select(connection=self.conn)]
        profiles = profiles[:self.max_results]
        items = [(profile.name, profile) for profile in profiles]
        self.profile.prefill(items)

    def _attach_slaves(self):
        klass = PasswordEditorSlave
        self.password_slave = klass(self.conn, visual_mode=self.visual_mode)
        self.attach_slave('password_holder', self.password_slave)

    #
    # BaseEditorSlave Hooks
    #

    def setup_proxies(self):
        self._setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    UserDetailsSlave.proxy_widgets)

    def validate_confirm(self):
        if self.show_password_fields:
            return self.password_slave.validate_confirm()
        return True

    def on_confirm(self):
        if self.show_password_fields:
            self.model.password = self.password_slave.model.new_password

    #
    # Kiwi handlers
    #

    def after_profile__content_changed(self, widget):
        # This could be wrriten in this way:
        # sensitive = bool(widget.get_text()) and widget.is_valid()
        # but if widget.get_text() returns "" sensitive will be False
        sensitive = True
        if widget.get_text():
            sensitive = widget.is_valid()
        self.profile_button.set_sensitive(sensitive)

    def on_username__validate(self, widget, value):
        user_table = Person.getAdapterClass(IUser)
        query = func.UPPER(user_table.q.username) == value.upper()
        users = Person.iselect(IUser, query, connection=self.conn)
        users_count = users.count()
        if not users_count:
            return
        if users_count > 1:
            raise DatabaseInconsistency('Duplicated value. You cannot have '
                                        'users with the same username')
        if self.model.username != value:
            return ValidationError('Username already exist')

    def on_profile_button__clicked(self, *args):
        if not self.profile.get_text():
            self.model.profile = None
        user_profile = self.model.profile
        if run_dialog(UserProfileEditor, self, self.conn, user_profile):
            self._setup_entry_completion()
            self.proxy.update('profile')
