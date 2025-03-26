# This file is part of csv_import_getmail module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from datetime import datetime
from trytond.pool import Pool, PoolMeta
from trytond.model import ModelSQL, ModelView, fields
import logging

__all__ = ['CSVProfile', 'CSVProfileParty', 'CSVImport']
__metaclass__ = PoolMeta


class CSVProfile(ModelSQL, ModelView):
    __name__ = 'csv.profile'
    parties = fields.Many2Many('csv.profile-party.party',
        'profile', 'party', 'Parties')


class CSVProfileParty(ModelSQL):
    'Profile - Party'
    __name__ = 'csv.profile-party.party'
    _table = 'csv_profile_party_rel'
    profile = fields.Many2One('csv.profile', 'CSV Profile', ondelete='CASCADE',
            required=True, select=True)
    party = fields.Many2One('party.party', 'Party',
        ondelete='CASCADE', required=True, select=True)


class CSVImport:
    __name__ = 'csv.import'

    @classmethod
    def getmail(cls, messages, attachments=None):
        pool = Pool()
        GetMail = pool.get('getmail.server')
        CSVArchive = pool.get('csv.archive')
        CSVProfile = pool.get('csv.profile')

        for (_, message) in messages:
            if not attachments:
                break

            sender = GetMail.get_email(message.sender)
            party, _ = GetMail.get_party_from_email(sender)
            if not party:
                continue
            csv_profiles = CSVProfile.search([('parties', 'in', [party.id])])
            if not csv_profiles:
                continue
            csv_profile = csv_profiles[0]

            logging.getLogger('CSV Import Get Mail').info(
                'Process email: %s' % (message.messageid))

            for attachment in message.attachments:
                if attachment[0][-3:].upper() == 'CSV':
                    csv_archive = CSVArchive()
                    csv_archive.profile = csv_profile
                    csv_archive.data = attachment[1]
                    csv_archive.archive_name = (
                        csv_archive.on_change_profile()['archive_name'])
                    csv_archive.save()
                    comment = (message.date + '\n' + message.title + '\n' +
                        message.sender + '\n\n' + message.body)
                    vals = {
                        'create_date': datetime.now(),
                        'record': None,
                        'status': 'done',
                        'comment': comment,
                        'archive': csv_archive,
                    }
                    cls.create([vals])
                    CSVArchive().import_csv([csv_archive])

        return True
