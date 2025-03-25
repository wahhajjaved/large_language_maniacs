import random
import string

from django.db import models

from contact.models import Contact


DEBUG_KEY = '12345'

class Submission(models.Model):
    contact = models.ForeignKey(Contact, null = True)
    key = models.CharField(max_length = 30, unique = True)
    first_name = models.CharField(max_length = 100)
    last_name = models.CharField(max_length = 100)
    email = models.EmailField(max_length = 100, unique = True)
    answers = models.CharField(max_length = 65536, null = True, blank = True)

    @classmethod
    def generate_key(cls):
        key = ''
        while not key and key in [record['key'] for record in cls.objects.values('key')]:
            key = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for i in range(30))
        return key

    @classmethod
    def create(cls, first_name, last_name, email, key = None, contact = None):
        submission = cls(
            contact = contact,
            key = key if key else Submission.generate_key(),
            first_name = first_name,
            last_name = last_name,
            email = email
        )

        submission.save()
        return submission


class Attachment(models.Model):
    submission = models.ForeignKey(Submission)
    name = models.CharField(max_length=100)
    file = models.FileField(upload_to = 'wtem/attachment')