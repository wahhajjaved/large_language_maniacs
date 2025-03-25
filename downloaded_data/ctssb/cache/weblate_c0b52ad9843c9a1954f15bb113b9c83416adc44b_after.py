# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
from trans.models import Check


class Command(BaseCommand):
    help = 'lists top ignored checks'
    option_list = BaseCommand.option_list + (
        make_option(
            '--count',
            type='int',
            dest='count',
            default=100,
            help='Number of top checks to list',
        ),
    )

    def handle(self, *args, **options):
        results = {}
        checks = Check.objects.filter(ignore=True)
        for check in checks:
            units = check.get_related_units()
            if not units.exists():
                continue
            name = '%s-%s' % (check.check, check.checksum)
            if name in results:
                results[name]['count'] += 1
            else:
                results[name] = {
                    'count': 1,
                    'check': check.check,
                    'source': units[0].source,
                }
        results = sorted(results.values(), key=lambda x: -x['count'])
        for result in results[:options['count']]:
            print '%(count)5d %(check)20s %(source)s' % result
