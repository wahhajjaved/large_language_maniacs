# coding=utf-8
#
# Copyright 2015, Abando.com.br
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and limitations under the License.
#
from importlib import import_module
from logging import getLogger
from pkgutil import walk_packages
from django.db.models import QuerySet

from django.http import HttpResponse, HttpRequest

from ..models import Transaction, Subscription, payment_names

log = getLogger(__name__)

_payment_methods = {}
get_payment = _payment_methods.get


def load_submodules():
    if _payment_methods:
        return
    for loader, modname, ispkg in walk_packages(__path__):
        log.info('Found sub%s %s' % ('package' if ispkg else 'module', modname))
        try:
            module = import_module('.'.join((__name__, modname)))
            log.debug('Imported payment module: %s', modname)
            if hasattr(module, 'Payment'):
                subclass = module.Payment
                assert issubclass(subclass, PaymentBase)
                _payment_methods[subclass.CODE] = subclass
                payment_names[subclass.CODE] = subclass.TITLE
                log.info('Loaded payment module %s: code=%d, title=%s', modname, subclass.CODE, subclass.TITLE)
            else:
                log.warn('Missing class Payment in module: %s', modname)
        except ImportError:
            log.warn('Failed to import payment module: %s', modname)


class PaymentBase:
    CODE = 0
    TITLE = ''

    _subscription = None
    _transaction = None

    def __init__(self, subscription_or_transaction):
        if not subscription_or_transaction:
            pass  # nothing to do
        elif isinstance(subscription_or_transaction, Subscription):
            self.subscription = subscription_or_transaction
        elif isinstance(subscription_or_transaction, Transaction):
            self.transaction = subscription_or_transaction
        else:
            raise ValueError

    def transactions(self, **criteria) -> QuerySet:
        return self.subscription.transaction_set.filter(**criteria)

    @property
    def transaction(self) -> Transaction:
        if self._transaction is None:
            self._transaction = Transaction(subscription=self._subscription, method=self.CODE)
        return self._transaction

    @transaction.setter
    def transaction(self, value):
        if isinstance(value, Transaction):
            self._transaction = value
        elif value:
            self._transaction = Transaction.objects.get(id=int(value))
        else:
            self._transaction = None
        if self._transaction:
            self._subscription = self._transaction.subscription

    @property
    def subscription(self) -> Subscription:
        return self._subscription

    @subscription.setter
    def subscription(self, value):
        if isinstance(value, Subscription):
            self._subscription = value
        elif value:
            self._subscription = Subscription.objects.get(id=int(value))
        else:
            self._subscription = None
            self._transaction = None
        if self._subscription and self._transaction:
            if not self._transaction.id:
                self._transaction.subscription = self._subscription
            else:
                raise ValueError('Invalid change of subscription with saved transaction. tid=%d, sid=%d' %
                                 (self._transaction.id, self._subscription.id))

    def start_payment(self, request, amount) -> HttpResponse:
        raise NotImplementedError

    @classmethod
    def class_view(cls, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError
