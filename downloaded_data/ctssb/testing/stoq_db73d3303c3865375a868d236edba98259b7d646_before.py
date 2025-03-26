# -*- Mode: Python; coding: iso-8859-1 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
## USA.
##
## Author(s):   Evandro Vale Miquelito      <evandro@async.com.br>
##
"""
stoq/gui/wizards/purchase.py:

    Purchase wizard definition
"""

import gettext

import gtk
from kiwi.datatypes import currency
from kiwi.ui.widgets.list import Column, SummaryLabel
from stoqlib.gui.wizards import BaseWizardStep, BaseWizard
from stoqlib.gui.dialogs import run_dialog
from stoqlib.gui.lists import AdditionListSlave
from stoqlib.exceptions import DatabaseInconsistency

from stoq.lib.validators import get_price_format_str, format_quantity
from stoq.lib.defaults import INTERVALTYPE_MONTH
from stoq.gui.wizards.person import run_person_role_dialog
from stoq.gui.editors.person import SupplierEditor, TransporterEditor
from stoq.gui.editors.product import ProductEditor, ProductItemEditor
from stoq.gui.slaves.purchase import PurchasePaymentSlave
from stoq.gui.slaves.sale import DiscountChargeSlave
from stoq.domain.payment.base import AbstractPaymentGroup
from stoq.domain.product import Product, FancyProduct
from stoq.domain.person import Person
from stoq.domain.purchase import PurchaseOrder, PurchaseItem
from stoq.domain.interfaces import (ISupplier, IBranch, ITransporter,
                                    ISellable, IPaymentGroup)

_ = gettext.gettext


#
# Wizard Steps
#


class FinishPurchaseStep(BaseWizardStep):
    gladefile = 'FinishPurchaseStep'
    model_type = PurchaseOrder
    proxy_widgets = ('salesperson_name', 
                     'receival_date',
                     'transporter',
                     'notes')

    def __init__(self, wizard, previous, conn, model):
        BaseWizardStep.__init__(self, conn, wizard, model, previous)

    def _setup_transporter_entry(self):
        table = Person.getAdapterClass(ITransporter)
        transporters = table.get_active_transporters(self.conn)
        names = [t.get_adapted().name for t in transporters]
        self.transporter.set_completion_strings(names, list(transporters))

    def _setup_focus(self):
        self.salesperson_name.grab_focus()
        self.notes.set_accepts_tab(False)

    #
    # WizardStep hooks
    #

    def has_next_step(self):
        return False

    def post_init(self):
        self.register_validate_function(self.wizard.refresh_next)
        self.force_validation()

    def setup_proxies(self):
        self._setup_transporter_entry()
        self.proxy = self.add_proxy(self.model, self.proxy_widgets)

    #
    # Kiwi callbacks
    #

    def on_transporter_button__clicked(self, *args):
        if run_person_role_dialog(TransporterEditor, self, self.conn, 
                                  self.model.transporter):
            self.conn.commit()
            self._setup_transporter_entry()


class PurchasePaymentStep(BaseWizardStep):
    gladefile = 'PurchasePaymentStep'
    model_iface = IPaymentGroup
    payment_widgets = ('method_combo',)
    order_widgets = ('subtotal_lbl',
                     'total_lbl')

    def __init__(self, wizard, previous, conn, model):
        self.order = model
        pg = IPaymentGroup(model, connection=conn)
        if pg:
            model = pg
        else:
            method = AbstractPaymentGroupPurchaseOrder.METHOD_BILL
            interval_type = INTERVALTYPE_MONTH
            model = model.addFacet(IPaymentGroup, default_method=method,
                                   intervals=1, 
                                   interval_type=interval_type,
                                   connection=conn)
        self.slave = None
        self.discount_charge_slave = None
        BaseWizardStep.__init__(self, conn, wizard, model, previous)

    def _setup_widgets(self):
        table = self.model_type
        items = [(_('Bill'), table.METHOD_BILL),
                 (_('Check'), table.METHOD_CHECK),
                 (_('Money'), table.METHOD_MONEY)]
        self.method_combo.prefill(items)
        format_str = get_price_format_str()
        self.subtotal_lbl.set_data_format(format_str)
        self.total_lbl.set_data_format(format_str)

    def _update_payment_method_slave(self):
        holder_name = 'method_slave_holder'
        if self.get_slave(holder_name):
            self.detach_slave(holder_name)
        if not self.slave:
            self.slave = PurchasePaymentSlave(self.conn, self.model)
        if self.model.default_method == self.model_type.METHOD_MONEY:
            self.slave.get_toplevel().hide()
            return
        self.slave.get_toplevel().show()
        self.attach_slave('method_slave_holder', self.slave)

    def _update_totals(self, *args):
        for field_name in ('purchase_subtotal', 'purchase_total'):
            self.order_proxy.update(field_name)

    #
    # WizardStep hooks
    #

    def next_step(self):
        return FinishPurchaseStep(self.wizard, self, self.conn, 
                                  self.order)

    def post_init(self):
        self.method_combo.grab_focus()
        self.main_box.set_focus_chain([self.payment_method_hbox,
                                       self.method_slave_holder])
        self.payment_method_hbox.set_focus_chain([self.method_combo])
        self.register_validate_function(self.wizard.refresh_next)
        self.force_validation()

    def setup_proxies(self):
        self._setup_widgets()
        self.order_proxy = self.add_proxy(self.order,
                                          PurchasePaymentStep.order_widgets)
        self.proxy = self.add_proxy(self.model,
                                    PurchasePaymentStep.payment_widgets)

    def setup_slaves(self):
        self._update_payment_method_slave()
        slave_holder = 'discount_charge_slave'
        if self.get_slave(slave_holder):
            return
        if not self.wizard.edit_mode:
            self.order.reset_discount_and_charge()
        self.discount_charge_slave = DiscountChargeSlave(self.conn, self.order,
                                                         PurchaseOrder)
        self.attach_slave(slave_holder, self.discount_charge_slave)
        self.discount_charge_slave.connect('discount-changed', 
                                           self._update_totals)
        self._update_totals()

    #
    # callbacks
    #

    def on_method_combo__changed(self, *args):
        self._update_payment_method_slave()


class PurchaseProductStep(BaseWizardStep):
    gladefile = 'PurchaseProductStep'
    model_type = PurchaseOrder
    proxy_widgets = ('product',)
    widgets = ('add_item_button',
               'product_button',
               'product_hbox') + proxy_widgets

    def __init__(self, wizard, previous, conn, model):
        self.table = Product.getAdapterClass(ISellable)
        BaseWizardStep.__init__(self, conn, wizard, model, previous)
        self._update_widgets()

    def _setup_product_entry(self):
        products = self.table.get_available_sellables(self.conn)
        descriptions = [p.description for p in products]
        self.product.set_completion_strings(descriptions, list(products))

    def _get_columns(self):
        return [Column('sellable.description', title=_('Description'), 
                       data_type=str, expand=True, searchable=True),
                Column('quantity', title=_('Quantity'), data_type=float,
                       width=90, format_func=format_quantity,
                       editable=True),
                Column('sellable.unit', title=_('Unit'), data_type=str, 
                       width=90),
                Column('cost', title=_('Cost'), data_type=currency, 
                       editable=True, width=90),
                Column('total', title=_('Total'), data_type=currency,
                       width=100)]

    def _update_widgets(self):
        has_product_str = self.product.get_text() != ''
        self.add_item_button.set_sensitive(has_product_str)

    def _get_product_by_code(self, code):
        product = self.table.selectBy(code=code, connection=self.conn)
        qty = product.count()
        if not qty:
            msg = _("The product with code '%s' doesn't exists" % code)
            self.product.set_invalid(msg)
            return
        if qty != 1:
            raise DatabaseInconsistency('You should have only one '
                                        'product with code %s' 
                                        % code)
        return product[0]

    def _update_total(self, *args):
        self.summary.update_total()

    def _add_item(self):
        if (self.proxy.model and self.proxy.model.product):
            product = self.proxy.model.product
        else:
            product = None
        self.add_item_button.set_sensitive(False)
        if not product:
            code = self.product.get_text()
            product = self._get_product_by_code(code)
        if not product:
            return
        products = [s.sellable for s in self.slave.klist]
        if product in products:
            msg = _("The product '%s' was already added to the order" 
                    % product.description)
            self.product.set_invalid(msg)
            return
        purchase_item = PurchaseItem(connection=self.conn,
                                     sellable=product, order=self.model,
                                     cost=product.cost)
        self.slave.klist.append(purchase_item)
        self._update_total()
        self.product.set_text('')

    #
    # WizardStep hooks
    #

    def next_step(self):
        return PurchasePaymentStep(self.wizard, self, self.conn, 
                                   self.model)

    def post_init(self):
        self.product.grab_focus()
        self.product_hbox.set_focus_chain([self.product, 
                                           self.add_item_button])
        self.register_validate_function(self.wizard.refresh_next)
        self.force_validation()

    def setup_proxies(self):
        self._setup_product_entry()
        self.product_model = FancyProduct()
        self.proxy = self.add_proxy(self.product_model,
                                    PurchaseProductStep.proxy_widgets)

    def setup_slaves(self):
        products = list(self.model.get_items())
        self.slave = AdditionListSlave(self.conn, ProductItemEditor,
                                       self._get_columns(), products)
        self.slave.hide_add_button()
        self.slave.register_editor_kwargs(model_type=PurchaseItem,
                                          value_attr='cost')
        self.slave.connect('before-delete-items', self._before_delete_items)
        self.slave.connect('after-delete-items', self._update_total)
        self.slave.connect('on-edit-item', self._update_total)
        value_format = '<b>%s</b>' % get_price_format_str()
        self.summary = SummaryLabel(klist=self.slave.klist, column='total',
                                    label='<b>Subtotal:</b>',
                                    value_format=value_format)
        self.summary.show()
        self.slave.list_vbox.pack_start(self.summary, expand=False)
        self.attach_slave('list_holder', self.slave)

    #
    # callbacks
    #

    def _before_delete_items(self, slave, items):
        for item in items:
            PurchaseItem.delete(item.id, connection=self.conn)

    def on_product_button__clicked(self, *args):
        if self.proxy.model and self.proxy.model.product:
            product = self.proxy.model.product.get_adapted()
        else:
            product = None
        if run_dialog(ProductEditor, self, self.conn, product):
            self.conn.commit()
            self._setup_product_entry()

    def on_add_item_button__clicked(self, *args):
        self._add_item()

    def on_product__activate(self, *args):
        if not self.add_item_button.get_property('sensitive'):
            return
        self._add_item()

    def on_product__changed(self, *args):
        self.product.set_valid()

    def after_product__changed(self, *args):
        self._update_widgets()


class StartPurchaseStep(BaseWizardStep):
    gladefile = 'StartPurchaseStep'
    model_type = PurchaseOrder
    proxy_widgets = ('open_date', 
                     'order_number',
                     'supplier',
                     'branch',
                     'freight')

    def __init__(self, wizard, conn, model):
        BaseWizardStep.__init__(self, conn, wizard, model)
        self._update_widgets()

    def _setup_supplier_entry(self):
        table = Person.getAdapterClass(ISupplier)
        suppliers = table.get_active_suppliers(self.conn)
        names = [s.get_adapted().name for s in suppliers]
        self.supplier.set_completion_strings(names, list(suppliers))

    def _setup_widgets(self):
        self._setup_supplier_entry()
        table = Person.getAdapterClass(IBranch)
        branches = table.get_active_branches(self.conn)
        items = [(s.get_adapted().name, s) for s in branches]
        self.branch.prefill(items)
        self.freight.set_data_format(get_price_format_str())

    def _update_widgets(self):
        has_freight = self.fob_radio.get_active()
        self.freight.set_sensitive(has_freight)

    #
    # WizardStep hooks
    #

    def post_init(self):
        self.open_date.grab_focus()
        self.table.set_focus_chain([self.open_date, self.order_number,
                                    self.branch, self.supplier, 
                                    self.radio_hbox, self.freight])
        self.radio_hbox.set_focus_chain([self.cif_radio, self.fob_radio])
        self.register_validate_function(self.wizard.refresh_next)
        self.force_validation()

    def next_step(self):
        if self.cif_radio.get_active():
            self.model.freight_type = self.model_type.FREIGHT_CIF
        else:
            self.model.freight_type = self.model_type.FREIGHT_FOB
        return PurchaseProductStep(self.wizard, self, self.conn, 
                                   self.model)

    def has_previous_step(self):
        return False

    def setup_proxies(self):
        self._setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    StartPurchaseStep.proxy_widgets)

    #
    # Kiwi callbacks
    #

    def on_cif_radio__toggled(self, *args):
        self._update_widgets()

    def on_fob_radio__toggled(self, *args):
        self._update_widgets()

    def on_supplier_button__clicked(self, *args):
        if run_person_role_dialog(SupplierEditor, self, self.conn, 
                                  self.model.supplier):
            self.conn.commit()
            self._setup_supplier_entry()


#
# Main wizard
#


class PurchaseWizard(BaseWizard):
    size = (600, 400)
    
    def __init__(self, conn, model=None, edit_mode=False):
        title = self._get_title(model)
        model = model or self._create_model(conn)
        if model.status != PurchaseOrder.ORDER_PENDING:
            raise ValueError('Invalid order status. It should '
                             'be ORDER_PENDING')
        first_step = StartPurchaseStep(self, conn, model)
        BaseWizard.__init__(self, conn, first_step, model, title=title,
                            edit_mode=edit_mode)

    def _get_title(self, model=None):
        if not model:
            return _('New Order')
        return _('Edit Order')

    def _create_model(self, conn):
        status = PurchaseOrder.ORDER_PENDING
        return PurchaseOrder(supplier=None, branch=None, status=status,
                             connection=conn)

    #
    # WizardStep hooks
    #

    def finish(self):
        self.model.set_valid()
        self.retval = self.model
        self.close()
