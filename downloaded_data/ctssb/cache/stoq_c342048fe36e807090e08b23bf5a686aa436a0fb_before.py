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
stoq/gui/slaves/payment.py

    Slaves for payment management
"""

import gettext
from datetime import datetime

from kiwi.utils import gsignal
from sqlobject.sqlbuilder import AND
from stoqlib.gui.editors import BaseEditorSlave

from stoq.lib.defaults import interval_types
from stoq.lib.parameters import sysparam
from stoq.lib.validators import (get_price_format_str, get_formatted_price,
                                 compare_float_numbers)
from stoq.domain.account import BankAccount
from stoq.domain.interfaces import (ICheckPM, IBillPM, IInPayment)
from stoq.domain.payment.base import Payment
from stoq.domain.payment.methods import (BillCheckGroupData, CheckData, 
                                         CreditProviderGroupData, 
                                         DebitCardDetails, CreditCardDetails,
                                         CardInstallmentsStoreDetails,
                                         CardInstallmentsProviderDetails,
                                         FinanceDetails, 
                                         PaymentMethodDetails)

_ = gettext.gettext



class PaymentListSlave(BaseEditorSlave):
    """A basic payment list slave. Each element of this list is a payment
    method slave which hold informations about payments. Available slaves
    are: BillDataSlave and CheckDataSlave

    Notes:
        - update_widget_handler: is a callback function which is called 
                                 right after a slave is added or removed 
                                 in the list.
        - get_payment_slave: is a hook method which must be defined in
                             parents. The result of this function must 
                             be a BaseEditorSlave instance.
        - on_remove_item: is a hook method which must be defined in parent
                          and will be called right after remove slaves from 
                          the list
        - get_interest_total: a hook method defined in parents which must
                              return the total amount of interest
    """

    gladefile = 'PaymentListSlave'
    widgets = ('list_vbox',
               'scrolled_window',
               'add_button',
               'remove_button',
               'status_label',
               'total_label')

    gsignal('remove-slave')
    gsignal('add-slave')

    def __init__(self, parent, conn, payment_method, sale_total):
        self.parent = parent
        self.payment_method = payment_method
        self.sale_total = sale_total
        self.max_installments_number = None
        # This dict stores a reference of each toplevel widget with its own
        # kiwi object, the slave.
        self.payment_slaves = {}
        BaseEditorSlave.__init__(self, conn)
        self._update_view()

    def _update_view(self):
        children_number = self.get_children_number()
        can_remove = children_number > 1
        max = self.max_installments_number or 0
        can_add = children_number < max
        self.remove_button.set_sensitive(can_remove)
        self.add_button.set_sensitive(can_add)
        self.update_total_label()

    def _remove_payment_slave(self, widget):
        slave = self.payment_slaves[widget]
        del self.payment_slaves[widget]
        self.list_vbox.remove(widget)
        self._update_view()
        self.parent.on_remove_item(slave)

    def get_total_difference(self):
        """Get the difference for the total of check payments invoiced. If
        the difference is zero the entire sale total value is invoiced.
        If the difference is greater than zero, there is an outstanding
        amount to invoice. If the value is negative, there is a overpaid 
        value."""
        slaves = self.payment_slaves.values()
        values = [s.get_payment_value() for s in slaves 
                        if s.get_payment_value() is not None]
        slaves_total = sum(values)
        interest_total = self.parent.get_interest_total()
        slaves_total -= interest_total
        if compare_float_numbers(slaves_total, self.sale_total):
            return 0.0
        return self.sale_total - slaves_total

    def update_total_label(self):
        difference = self.get_total_difference()
        if not difference:
            label_name = difference = ''
        elif difference < 0:
            difference *= -1 
            label_name = _('Overpaid:')
        else:
            label_name = _('Outstanding:')
        if difference:
            difference = get_formatted_price(difference)
        self.total_label.set_text(difference)
        self.status_label.set_text(label_name)

    def get_children_number(self):
        vbox_children = self.list_vbox.get_children()
        return len(vbox_children)

    def register_max_installments_number(self, inst_number):
        self.max_installments_number = inst_number

    def clear_list(self):
        for widget in self.list_vbox.get_children()[:]:
            self._remove_payment_slave(widget)

    def update_payment_list(self, installments_number):
        installments_number = installments_number or 0
        children_number = self.get_children_number()
        difference = installments_number - children_number
        if not difference:
            return
        if difference > 0:
            for i in range(difference):
                self.add_slave()
        else:
            difference *= -1
            for i in range(difference):
                self.remove_last_payment_slave()

    def add_slave(self, slave=None):
        if not self.max_installments_number:
            raise ValueError('You call register_max_installments_number '
                             'before start adding slaves')
        if self.get_children_number() > self.max_installments_number:
            return
        slave = slave or self.parent.get_payment_slave()
        widget = slave.get_toplevel()
        self.payment_slaves[widget] = slave
        children_number = self.get_children_number() + 1
        slave.set_frame_label('# %d' % children_number)
        self.list_vbox.pack_start(widget, False)
        # Scroll to the bottom of the scrolled window
        vadj = self.scrolled_window.get_vadjustment()
        vadj.set_value(vadj.upper)
        widget.show()
        self._update_view()

    def remove_last_payment_slave(self):
        vbox_children = self.list_vbox.get_children()
        if not vbox_children:
            return
        widget = vbox_children[-1]
        self._remove_payment_slave(widget)



    #
    # Kiwi callbacks
    #



    def on_add_button__clicked(self, *args):
        self.add_slave()
        self.emit('add-slave')

    def on_remove_button__clicked(self, *args):
        self.remove_last_payment_slave()
        self.emit('remove-slave')


class BankDataSlave(BaseEditorSlave):
    gladefile = 'BankDataSlave'
    model_type = BankAccount
    widgets = ('bank',
               'branch')



    #
    # BaseEditorSlave hooks
    #



    def setup_proxies(self):
        self.add_proxy(self.model, BankDataSlave.widgets)



class BillDataSlave(BaseEditorSlave):
    """A slave to set payment information of bill payment method"""

    gladefile = 'BillDataSlave'
    model_type = Payment
    payment_widgets = ('due_date',
                       'value',
                       'payment_number')
    widgets = ('payment_number_label',) + payment_widgets
    gsignal('paymentvalue-changed')

    def __init__(self, conn, payment_group, due_date, value, model=None):
        self._payment_group = payment_group
        self._due_date = due_date
        self._value = value
        BaseEditorSlave.__init__(self, conn, model)

    def _setup_widgets(self):
        self.value.set_data_format(get_price_format_str())
        self.payment_number_label.set_bold(True)
        self.payment_number_label.set_size('small')

    def set_frame_label(self, label_name):
        self.payment_number_label.set_text(label_name)

    def get_payment_value(self):
        return self.model.value



    #
    # BaseEditorSlave hooks
    #



    def create_model(self, conn):
        base_method = sysparam(conn).BASE_PAYMENT_METHOD
        bill_method = IBillPM(base_method)
        inpayment = bill_method.create_inpayment(self._payment_group,
                                                 self._due_date,
                                                 self._value)
        return inpayment.get_adapted()

    def setup_proxies(self):
        self._setup_widgets()
        self.add_proxy(self.model, BillDataSlave.payment_widgets)


    
    #
    # Kiwi callbacks
    #



    def after_value__changed(self, *args):
        self.emit('paymentvalue-changed')


class CheckDataSlave(BillDataSlave):
    """A slave to set payment information of check payment method."""
    slave_holder = 'bank_data_slave'
    model_type = CheckData



    #
    # BaseEditorSlave hooks
    #



    def get_payment_value(self):
        return self.model.payment.value

    def create_model(self, conn):
        base_method = sysparam(conn).BASE_PAYMENT_METHOD
        check_method = ICheckPM(base_method)
        inpayment = check_method.create_inpayment(self._payment_group,
                                                  self._due_date,
                                                  self._value)
        adapted = inpayment.get_adapted()
        return check_method.get_check_data_by_payment(adapted)

    def setup_slaves(self):
        bank_data_slave = BankDataSlave(self.conn, self.model.bank_data)
        if self.get_slave(self.slave_holder):
            self.detach_slave(self.slave_holder)
        self.attach_slave(self.slave_holder, bank_data_slave)

    def setup_proxies(self):
        self._setup_widgets()
        self.add_proxy(self.model, BillDataSlave.payment_widgets)


class BasePaymentMethodSlave(BaseEditorSlave):
    """A base payment method slave for Bill and Check methods."""

    gladefile = 'BillCheckMethodSlave'
    model_type = BillCheckGroupData
    slave_holder = 'bill_check_data_list'
    widgets = ('interest',
               'interval_type_combo',
               'intervals',
               'first_duedate',
               'reset_button',
               'installments_number')
    # This attribute must be defined in child. It can assume two
    # value: CheckDataSlave, BillDataSlave
    _data_slave_class = None

    def __init__(self, wizard, parent, conn, sale_obj, payment_method):
        self.sale = sale_obj
        self.wizard = wizard
        self.method = payment_method
        # This is very useful when calculating the total amount outstanding
        # or overpaid of the payments
        self.interest_total = 0.0
        self.payment_group = self.wizard.get_payment_group()
        self.payment_list = None
        self.reset_btn_validation_ok = True
        BaseEditorSlave.__init__(self, conn)
        self.register_validate_function(self._refresh_next)
        self.parent = parent
        self._setup_widgets()
        self.update_view()

    def _refresh_next(self, validation_ok=True):
        if validation_ok and self.payment_list:
            total_difference = self.payment_list.get_total_difference()
            validation_ok = total_difference == 0.0
        self.wizard.refresh_next(validation_ok)

    def update_view(self):
        attrs = [self.model.installments_number, self.model.first_duedate,
                 self.model.intervals]
        self.reset_button.set_sensitive((None not in attrs) and
                                        self.reset_btn_validation_ok)
        self._refresh_next()

    def _setup_monthly_interest(self):
        # XXX Humm... if the interest charge is mandatory we can not allow
        # users go to the last step if the total value of installments
        # doesn't match with subtotal + interest_total
        interest = self.method.monthly_interest
        if interest:
            self.interest.set_range(1, interest)
            self.model.interest = interest
            self.proxy.update('interest')
        param = sysparam(self.conn).MANDATORY_INTEREST_CHARGE
        self.interest.set_sensitive(param)

    def _setup_widgets(self):
        self._setup_monthly_interest()
        max = self.method.get_max_installments_number()
        self.installments_number.set_range(1, max)
        items = [(label, constant) for constant, label 
                                in interval_types.items()]
        self.interval_type_combo.prefill(items)

        total = self.sale.get_total_sale_amount()
        self.payment_list = PaymentListSlave(self, self.conn, 
                                             self.method, total)
        self.payment_list.connect('add-slave',
                                  self.update_installments_number)
        self.payment_list.connect('remove-slave',
                                  self.update_installments_number)
        self.payment_list.register_max_installments_number(max)
        if self.get_slave(BasePaymentMethodSlave.slave_holder):
            self.detach_slave(BasePaymentMethodSlave.slave_holder)
        self.attach_slave(BasePaymentMethodSlave.slave_holder,
                          self.payment_list)
        created_inpayments = self.get_created_inpayments()
        if created_inpayments:
            self.fill_slave_list(created_inpayments)
        else:
            # Adding the first payment
            slave = self.get_payment_slave()
            self.payment_list.add_slave(slave)

    def get_created_inpayments(self):
        group = self.wizard.get_payment_group()
        q1 = Payment.q.methodID == self.method.id
        q2 = Payment.q.groupID == group.id
        q3 = Payment.q.status == Payment.STATUS_PREVIEW
        query = AND(q1, q2, q3)
        payments = Payment.select(query, connection=self.conn)
        inpayments = []
        for payment in payments:
            inpayment = IInPayment(payment, connection=self.conn)
            if inpayment:
                inpayments.append(inpayment)
        return inpayments

    def _setup_payments(self):
        group = self.wizard.get_payment_group()
        total = self.sale.get_total_sale_amount()
        inst_number = self.model.installments_number
        due_date = self.model.first_duedate
        interval_type = self.model.interval_type
        intervals = self.model.intervals
        interest = self.model.interest
        self.payment_list.clear_list()
        method = self.method
        inpayments, interest = method.setup_inpayments(group, inst_number,
                                                       due_date, 
                                                       interval_type,
                                                       intervals, 
                                                       total, interest)
        # This is very useful when calculating the total amount outstanding
        # or overpaid of the payments
        self.interest_total = interest
        self.fill_slave_list(inpayments)

    def fill_slave_list(self, inpayments):
        for inpayment in inpayments:
            slave = self.get_slave_by_inpayment(inpayment)
            self.payment_list.add_slave(slave)

    def get_slave_by_inpayment(self, inpayment):
        raise NotImplementedError
      


    #
    # PaymentListSlave hooks and callbacks
    #



    def get_interest_total(self):
        return self.interest_total
    
    def get_payment_slave(self, model=None):
        if not self._data_slave_class:
            raise ValueError('Child classes must define a data_slave_class '
                             'attribute')
        group = self.wizard.get_payment_group()
        due_date = datetime.today()
        if not self.payment_list.get_children_number():
            total = self.sale.get_total_sale_amount()
        else:
            total = 0.0
        slave = self._data_slave_class(self.conn, group, due_date, total,
                                       model)
        slave.connect('paymentvalue-changed', 
                      self._on_slave__paymentvalue_changed)
        return slave

    def _on_slave__paymentvalue_changed(self, slave):
        self.update_view()
        self.payment_list.update_total_label()

    def update_installments_number(self, *args):
        inst_number = self.payment_list.get_children_number()
        self.model.installments_number = inst_number
        self.proxy.update('installments_number')

    def on_remove_item(self, slave):
        if not isinstance(slave.model, slave.model_type):
            raise TypeError('Slave model attribute should be of type '
                            '%s, got %s' % (slave.model_type, 
                                            type(slave.model)))
        
        if isinstance(slave.model, CheckData):
            payment = slave.model.payment
        else:
            payment = slave.model
        inpayment = IInPayment(payment)
        assert inpayment, ('This payment should have a IInPayment facet '
                           'at this point')
        self.method.delete_inpayment(inpayment)



    #
    # PaymentMethodStep hooks
    #


    
    def finish(self):
        # Since payments are created during this step there is no need to
        # perform tasks here
        return




    #
    # BaseEditor Slave hooks
    #   



    def setup_proxies(self):
        self.proxy = self.add_proxy(self.model,
                                    BasePaymentMethodSlave.widgets)

    def create_model(self, conn):
        check_group = self.method.get_check_group_data(self.sale)
        if check_group:
            return check_group
        group = self.wizard.get_payment_group()
        return BillCheckGroupData(connection=conn, group=group,
                                  first_duedate=datetime.today())

    

    #
    # Kiwi callbacks
    #



    def after_installments_number__value_changed(self, *args):
        # Call this callback *after* the value changed because we need to
        # have the same value for the length of the payments list 
        inst_number = self.model.installments_number
        if self.payment_list:
            self.payment_list.update_payment_list(inst_number)
        self.update_view()
        
    def after_first_duedate__changed(self, *args):
        self.update_view()
    
    def on_intervals__value_changed(self, *args):
        self.update_view()

    def on_interval_type_combo__changed(self, *args):
        self.update_view()
    
    def on_reset_button__clicked(self, *args):
        self._setup_payments()

    def on_intervals__validation_changed(self, widget, is_valid):
        self.reset_btn_validation_ok = is_valid
        self.update_view()

    def on_first_duedate__validation_changed(self, widget, is_valid):
        self.reset_btn_validation_ok = is_valid
        self.update_view()

    def on_installments_number__validation_changed(self, widget, is_valid):
        self.reset_btn_validation_ok = is_valid
        self.update_view()


class CheckMethodSlave(BasePaymentMethodSlave):
    _data_slave_class = CheckDataSlave

    def get_slave_by_inpayment(self, inpayment):
        adapted = inpayment.get_adapted()
        check_data = self.method.get_check_data_by_payment(adapted)
        return self.get_payment_slave(check_data)


class BillMethodSlave(BasePaymentMethodSlave):
    _data_slave_class = BillDataSlave


    def get_slave_by_inpayment(self, inpayment):
        adapted = inpayment.get_adapted()
        return self.get_payment_slave(adapted)
    

class CreditProviderMethodSlave(BaseEditorSlave):
    """A base payment method slave for card and finance methods.
   
   Available slaves are: CardMethodSlave, FinanceMethodSlave 
    """
    gladefile = 'CreditProviderMethodSlave'
    model_type = CreditProviderGroupData
    widgets = ('payment_type',
               'credit_provider',
               'installments_number')
    _payment_types = None

    def __init__(self, wizard, parent, conn, sale_obj, payment_method):
        self.sale = sale_obj
        self.wizard = wizard
        self.method = payment_method
        self.payment_group = self.wizard.get_payment_group()
        self._pmdetails_objs = None
        BaseEditorSlave.__init__(self, conn)
        self.register_validate_function(self._refresh_next)
        self.parent = parent
        # this will be properly updated after changing data in payment_type
        # widget
        self.installments_number.set_range(1, 1)

    def _refresh_next(self, validation_ok=True):
        validation_ok = validation_ok and self.model.installments_number
        self.wizard.refresh_next(validation_ok)

    def _setup_max_installments(self):
        selected = self.payment_type.get_selected_data()
        max = selected.get_max_installments_number()
        self.installments_number.set_range(1, max)

    def update_view(self):
        # This is for PaymentMethodStep compatibility.
        # FIXME We need to change PaymentMethodDetails to use signals
        # instead of calling methods of parents and slaves directly
        pass

    def _get_credit_providers(self):
        raise NotImplementedError

    def _get_payment_types(self, credit_provider):
        if self._pmdetails_objs:
            return self._pmdetails_objs
        objs = PaymentMethodDetails.selectBy(providerID=credit_provider.id,
                                             connection=self.conn)
        if not objs.count():
            raise ValueError('You must have payment information objs '
                             'stored in the database before start doing '
                             'sales')
        payment_info = objs[0]
        pmdetails_objs = [obj for obj in objs 
                                if obj.is_active and 
                                    isinstance(obj, self._payment_types)]
        if not pmdetails_objs:
            raise ValueError('You must have payment_types information '
                             'stored in the database before start doing '
                             'sales')
        # This is useful to avoid multiple database selects when calling
        # kiwi combobox content changed signal
        self._pmdetails_objs = pmdetails_objs
        return self._pmdetails_objs

    def _setup_payment_types(self):
        raise NotImplementedError

    def _setup_widgets(self):
        providers = self._get_credit_providers()
        items = [(p.short_name, p) for p in providers]
        self.credit_provider.prefill(items)
        self._setup_payment_types()
        self._setup_max_installments()

    def _setup_payments(self):
        group = self.wizard.get_payment_group()
        total = self.sale.get_total_sale_amount()
        inst_number = self.model.installments_number
        payment_type = self.model.payment_type
        first_due_date = self.sale.open_date
        payment_type.setup_inpayments(group, inst_number, first_due_date,
                                      total)



    #
    # PaymentMethodStep hooks
    #


    
    def finish(self):
        self._setup_payments()



    #
    # BaseEditor Slave hooks
    #   



    def setup_proxies(self):
        self._setup_widgets()
        self.proxy = self.add_proxy(self.model,
                                    CreditProviderMethodSlave.widgets)

    def create_model(self, conn):
        providers = self._get_credit_providers()
        if not providers.count():
            raise ValueError('You must have credit providers information '
                             'stored in the database before start doing '
                             'sales')
        provider = providers[0]
        payment_type = self._get_payment_types(provider)[0]
        group = self.wizard.get_payment_group()
        return CreditProviderGroupData(connection=conn, group=group,
                                       payment_type=payment_type,
                                       provider=provider)

    

    #
    # Kiwi callbacks
    #



    def on_payment_type__content_changed(self, *args):
        self._setup_max_installments()
        
    def on_credit_provider__content_changed(self, *args):
        self._setup_payment_types()


class CardMethodSlave(CreditProviderMethodSlave):
        
    _payment_types = (CardInstallmentsStoreDetails,
                      CardInstallmentsProviderDetails, DebitCardDetails,
                      CreditCardDetails)
        
    def _get_credit_providers(self):
        return self.method.get_credit_card_providers()
        
    def _setup_payment_types(self):
        self.payment_type.clear()
        selected = self.credit_provider.get_selected_data()
        payment_types = self._get_payment_types(selected)
        items = [(p.payment_type_name, p) for p in payment_types]
        self.payment_type.prefill(items)


class FinanceMethodSlave(CreditProviderMethodSlave):
    _payment_types = FinanceDetails,
        
    def _get_credit_providers(self):
        return self.method.get_finance_companies()
        
    def _setup_payment_types(self):
        self.payment_type.clear()
        selected = self.credit_provider.get_selected_data()
        payment_types = self._get_payment_types(selected)
        if len(payment_types) != 1:
            raise ValueError('It should have only one payment type for '
                             'finance payment method. Found %d' %
                             len(payment_types))
        payment_type = payment_types[0]
        names = payment_type.payment_type_names
        self.payment_type.prefill([(name, payment_type) for name in names])


class MultipleMethodSlave:
    gladefile = 'MultipleMethodSlave'
    widgets = ('method_combo','payment_number')
    # Bug 2161 will implement this class
    # XXX We must clean all the payments created for this payment group when
    # creating this slave since there is no way to filter them by payment
    # method after create payments here.
