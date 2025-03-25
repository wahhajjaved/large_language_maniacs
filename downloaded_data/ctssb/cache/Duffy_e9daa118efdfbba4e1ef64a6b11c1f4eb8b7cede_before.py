import os, sys
parentPath = os.path.join(os.path.split(os.path.abspath(__file__))[0], "..")
if parentPath not in sys.path:
    sys.path.insert(0, parentPath)

import django
django.setup()
import smskeeper
from django.db.models.query import QuerySet
from smskeeper.forms import UserIdForm, SmsContentForm, PhoneNumberForm, SendSMSForm
from smskeeper.models import User, Note, NoteEntry, Message, MessageMedia, Entry
from peanut.settings import constants
from pprint import PrettyPrinter
import json


from smskeeper import async

from django.core.serializers.json import DjangoJSONEncoder

def printDjango(obj):
    model._meta.get_all_field_names()

def main(argv):
    for note in Note.objects.all():
        print "migrating: %s/%s" % (note.user.phone_number, note.label)
        for noteEntry in NoteEntry.objects.filter(note=note):
            #print(noteEntry.__dict__)
            #create a new entry object
            entry = Entry.createEntry(note.user, noteEntry.keeper_number, note.label, noteEntry.text, noteEntry.img_url, noteEntry.remind_timestamp)

            if entry.remind_timestamp:
                async.processReminder.apply_async([entry.id], eta=entry.remind_timestamp)

if __name__ == "__main__":
    main(sys.argv[1:])
