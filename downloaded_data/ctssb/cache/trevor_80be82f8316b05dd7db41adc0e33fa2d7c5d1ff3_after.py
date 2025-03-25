import os
import urllib2
from datetime import datetime

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from whatever import models

url = "http://api.scraperwiki.com/api/1.0/datastore/getdata?key=e1599319b01d876281589c630ca87826&format=json&name=upcoming-premiership-fixtures"

def getOrMakeTeam(name):
    try:
        team = models.Team.objects.get(name=name)
    except models.Team.DoesNotExist:
        team = models.Team(name=name)
        team.save()
    return team    

class Command(BaseCommand):
    def handle(self, *args, **options):
        if not args or (args and args[0] not in ('load')):
            raise CommandError("USAGE: ./manage.py %s load" % \
                    os.path.basename(__file__).split('.')[0])

        transaction.enter_transaction_management()
        transaction.managed(True)

        request = urllib2.Request(url)
        request.add_header("User-Agent",
                           "WhateverTrevor/0.1 +http://whatevertrevor.com")

        opener = urllib2.build_opener()
        fixtures = eval(opener.open(request).read())
        for fixture in fixtures:
            date = datetime.strptime("%Y-%m-%d %H:%M:00", fixture['date'])
            #home, created =
            #models.Team.objects.get_or_create(name=name)
            home = fixture['home'].replace("Man ", "Manchester ")\
                   .replace("Utd", "United")
            away = fixture['away'].replace("Man ", "Manchester ")\
                   .replace("Utd", "United")
            home = models.Team.objects.get(name__icontains=home)
            away = models.Team.objects.get(name__icontains=away)
            print models.Fixture.objects.get_or_create(date=date,
                                                       home=home,
                                                       away=away)
        transaction.commit()
