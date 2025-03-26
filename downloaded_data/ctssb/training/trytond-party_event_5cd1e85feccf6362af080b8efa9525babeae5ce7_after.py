#This file is part party_event module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.

from trytond import backend
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
import datetime

__all__ = ['PartyEvent']

_TYPES = [
    ('phone', 'Phone'),
    ('mobile', 'Mobile'),
    ('fax', 'Fax'),
    ('email', 'E-Mail'),
    ('skype', 'Skype'),
    ('irc', 'IRC'),
    ('jabber', 'Jabber'),
    ('other', 'Other'),
]


class PartyEvent(ModelSQL, ModelView):
    'Party Event'
    __name__ = 'party.event'
    _order_name = 'date'

    type = fields.Selection(_TYPES, 'Type', required=True, sort=False)
    event_date = fields.DateTime('Date', required=True)
    subject = fields.Char('Subject', required=True)
    description = fields.Text('Description')
    party = fields.Many2One('party.party', 'Party', required=True)
    resource = fields.Reference('Resource', selection='get_resource')
    employee = fields.Many2One('company.employee', 'Employee')

    @classmethod
    def __setup__(cls):
        super(PartyEvent, cls).__setup__()
        cls._order.insert(0, ('event_date', 'DESC'))
        cls._error_messages.update({
            'no_subject': 'No subject',
        })

    @classmethod
    def __register__(cls, module_name):
        super(PartyEvent, cls).__register__(module_name)
        User = Pool().get('res.user')
        cursor = Transaction().cursor
        TableHandler = backend.get('TableHandler')
        table = TableHandler(cursor, cls, module_name)
        # Migration from 2.8: user to employee
        if table.column_exist('user'):
            cursor.execute('''
                UPDATE
                    "%s"
                SET
                    employee = "%s".employee
                FROM
                    "%s"
                WHERE
                    "%s".id = "%s".user
                ''' %
                (cls._table, User._table, User._table, User._table,
                    cls._table))
            table.column_rename('user', 'user_deprecated')

    @staticmethod
    def default_type():
        return 'email'

    @staticmethod
    def default_event_date():
        return datetime.datetime.now()

    @staticmethod
    def default_employee():
        User = Pool().get('res.user')
        if Transaction().context.get('employee'):
            return Transaction().context['employee']
        else:
            user = User(Transaction().user)
            if user.employee:
                return user.employee.id

    @classmethod
    def get_resource(cls):
        'Return list of Model names for resource Reference'
        return [[None, '']]

    def get_rec_name(self, name):
        return (self.subject or unicode(self.id))

    @classmethod
    def create_event(self, party, resource, values={}):
        """
        Create event at party from details
        :param party: party ID
        :param resource: str (object,id) Eg: 'electrinic.mail,1'
        :param values: Dicc {subject:, date:, description:} (optional)
        """
        User = Pool().get('res.user')
        Party = Pool().get('party.party')
        PartyEvent = Pool().get('party.event')

        now = datetime.datetime.now()
        user = User(Transaction().user)

        party_event = PartyEvent()
        party_event.event_date = values.get('date') or now
        party_event.subject = values.get('subject') or \
                self.raise_user_error('no_subject',raise_exception=False)
        party_event.description = values.get('description','')
        party_event.party = Party(party)
        party_event.resource = resource
        party_event.employee = user.employee or None
        party_event.save()
