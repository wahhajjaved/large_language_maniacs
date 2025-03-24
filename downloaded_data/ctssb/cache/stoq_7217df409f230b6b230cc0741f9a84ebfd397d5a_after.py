# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005, 2006 Async Open Source
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU Lesser General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or (at your option) any later version.
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
##
## Author(s):       Evandro Vale Miquelito      <evandro@async.com.br>
##                  Henrique Romano             <henrique@async.com.br>
##
""" Base classes for editors """


from kiwi.ui.delegates import SlaveDelegate

from stoqlib.domain.base import Adapter
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.gui.base.dialogs import BasicWrappingDialog

_ = stoqlib_gettext


class BaseEditorSlave(SlaveDelegate):
    """ Base class for editor slaves inheritance. It offers methods for
    setting up focus sequence, required attributes and validated attrs.

    @cvar gladefile:
    @cvar model_type:
    @cvar model_iface:
    """
    gladefile = None
    model_type = None
    model_iface = None

    def __init__(self, conn, model=None):
        """
        @param conn: a connection
        @param model:
        """

        # The model attribute represents the
        self.conn = conn
        self.edit_mode = model is not None

        model = model or self.create_model(self.conn)
        if not model:
            raise ValueError("Editors must define a model at this point")

        if self.model_iface:
            if not isinstance(model, Adapter):
                model = self.model_iface(model, connection=self.conn)
            elif not self.model_iface.providedBy(model):
                raise TypeError(
                    "%s editor requires a model implementing %s, got a %r" % (
                    self.__class__.__name__, self.model_iface.__name__,
                    model))
            self.model_type = self.model_type or type(model)

        elif self.model_type:
            if not isinstance(model, self.model_type):
                raise TypeError(
                    '%s editor requires a model of type %s, got a %r' % (
                    self.__class__.__name__, self.model_type.__name__,
                    model))
        else:
            raise ValueError("Editors must define a model_type or "
                             "model_iface attributes")

        self.model = model
        SlaveDelegate.__init__(self, gladefile=self.gladefile)
        self.setup_proxies()
        self.setup_slaves()

    def create_model(self, conn):
        """
        It is expected to return a new model, which will be used if a model
        wasn't sent to the object at instantiation time.
        The default behavior is to raise a TypeError, which can
        be overridden in a subclass.
        """
        raise TypeError("%r needs a model, got None. Perhaps you want to "
                        "implement create_model?" % self)

    def setup_proxies(self):
        """
        A subclass can override this
        """

    def setup_slaves(self):
        """
        A subclass can override this
        """

    #
    # Hook methods
    #

    def on_cancel(self):
        """ This is a hook method which must be redefined when some
        action needs to be executed when cancelling in the dialog. """
        return False

    def on_confirm(self):
        """ This is a hook method which must be redefined when some
        action needs to be executed when confirming in the dialog. """
        return self.model

    def validate_confirm(self):
        """ Must be redefined by childs and will perform some validations
        after the click of ok_button. It is interesting to use with some
        special validators that provide some tasks over more than one widget
        value """
        return True


class BaseEditor(BaseEditorSlave):
    """ Base class for editor dialogs. It offers methods of
    BaseEditorSlave, a windows title and OK/Cancel buttons.

    model_name      =  the model type name of the model we are editing.
                       This value will be showed in the title of
                       the editor and can not be merely the attribute
                       __name__ of the object for usability reasons.
                       Callsites will decide what could be the best name
                       applicable in each situation.

    get_title_model_attribute = get a certain model attribute value to
                                allow creating customized editor titles.
                                Subclasses will choose the right attribute
                                acording to the editor features and
                                with usability in mind.
                                The editor title has this format:
                                'Edit "title_model_attr" Details'
    """

    model_name = None
    header = ''
    size = ()
    title = None
    hide_footer = False

    def __init__(self, conn, model=None):
        BaseEditorSlave.__init__(self, conn, model)
        # We can not use self.model for get_title since we will create a new
        # one in BaseEditorSlave if model is None.
        self.main_dialog = BasicWrappingDialog(self,
                                               self.get_title(self.model),
                                               self.header, self.size)
        if self.hide_footer:
            self.main_dialog.hide_footer()
        self.register_validate_function(self.refresh_ok)
        self.force_validation()

    def get_title(self, model):
        if self.title:
            return self.title
        if model:
            if self.model_name and not self.edit_mode:
                return _('Add %s') % self.model_name
            model_attr = self.get_title_model_attribute(model)
            return _('Edit "%s" Details') % model_attr
        else:
            raise ValueError("A model should be defined at this point")

    def get_title_model_attribute(self, model):
        raise NotImplementedError

    def refresh_ok(self, validation_value):
        """ Refreshes ok button sensitivity according to widget validators
        status """
        self.main_dialog.ok_button.set_sensitive(validation_value)

class SimpleEntryEditor(BaseEditor):
    """Editor that offers a generic entry to input a string value."""
    gladefile = "SimpleEntryEditor"

    def __init__(self, conn, model, attr_name, name_entry_label='Name:',
                 title=''):
        self.title = title
        self.attr_name = attr_name
        BaseEditor.__init__(self, conn, model)
        self.name_entry_label.set_text(name_entry_label)

    def on_name_entry__activate(self, entry):
        self.main_dialog.confirm()

    def setup_proxies(self):
        assert self.model
        self.name_entry.set_property('model-attribute', self.attr_name)
        proxy = self.add_proxy(model=self.model, widgets=['name_entry'])

class NoteEditor(BaseEditor):
    """ Simple editor that offers a label and a textview. """
    gladefile = "NoteSlave"
    proxy_widgets = ('notes',)
    size = (500, 200)

    def __init__(self, conn, model, attr_name, title='', label_text=None):
        assert model, ("You must supply a valid model to this editor "
                       "(%r)" % self)
        self.model_type = type(model)
        self.title = title
        self.label_text = label_text
        self.attr_name = attr_name

        BaseEditor.__init__(self, conn, model)
        self._setup_widgets()

    def _setup_widgets(self):
        if self.label_text:
            self.notes_label.set_text(self.label_text)
        self.notes.set_accepts_tab(False)

    #
    # BaseEditor hooks
    #

    def setup_proxies(self):
        self.notes.set_property('model-attribute', self.attr_name)
        proxy = self.add_proxy(self.model, NoteEditor.proxy_widgets)


    def get_title(self, *args):
        return self.title
