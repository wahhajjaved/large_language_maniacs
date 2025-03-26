import random
import string
from amsel import wordings
from django.conf import settings
from django.db import models

def id_generator(size=4, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


class Patient(models.Model):

    uid = models.CharField(max_length=20, db_index=True, unique = True, default=id_generator)
    first_name = models.CharField(max_length=250, blank=True, null=True)
    last_name = models.CharField(max_length=250, blank=True, null=True)
    moh_id = models.CharField("MOH-ID", max_length=250, blank=True, null=True)
    enter_name = models.CharField('Case Investigator name', max_length=250, blank=True, null=True)
    enter_number = models.CharField('Case Investigator number', max_length=250, blank=True, null=True)
    caregiver_number = models.CharField('Next of kin number', max_length=250, blank=True, null=True)

    etu = models.CharField(max_length=250, blank=True, null=True)

    PATIENT_STATUS=(
        ("S", "Stable"),
        ("C", "Condition not improving"),
        ("G", "Getting better"),
        ("D", 'You will receive a call from the doctor'),
        ("O", "Discharged"),
    )

    status = models.CharField(choices=PATIENT_STATUS, max_length=1, blank=True, null=True )

    json = models.TextField(editable=False)

    line_listing = models.TextField(editable=False, blank=True, null=True)


    def save(self, *args, **kwargs):
        #Check if the etu field has changed.
        if self.caregiver_number:

            if self.pk is not None:
                oldItem = Patient.objects.get(pk=self.pk)

                if oldItem.etu != self.etu:
                    #If the etu has changed send out a message to the caregiver
                    mapping = {
                        'first_name':self.first_name,
                        'second_name':self.last_name,
                        'h_facility':self.etu
                    }

                    text = wordings.patient_location % mapping
                    settings.SMS_BACKEND(self.caregiver_number, text)

                if oldItem.status != self.status:
                    #If the status has changed send out a message to the caregiver
                    mapping = {
                        'first_name':self.first_name,
                        'second_name':self.last_name,
                        'status':self.get_status_display()
                    }

                    text = wordings.patient_status % mapping
                    settings.SMS_BACKEND(self.caregiver_number, text)

            else:
                #Send the text messages
                mapping = {
                    'first_name':self.first_name,
                    'second_name':self.last_name,
                    'unfo_code':self.uid
                }

                text = wordings.patient_info % mapping

                if self.enter_number:
                    settings.SMS_BACKEND(self.enter_number, text)

                if self.caregiver_number:
                    settings.SMS_BACKEND(self.caregiver_number, text)


                settings.SMS_BACKEND(self.caregiver_number, wordings.inital_message)

                if self.etu:
                    mapping = {
                        'first_name':self.first_name,
                        'second_name':self.last_name,
                        'h_facility':self.etu
                    }

                    text = wordings.patient_location % mapping
                    settings.SMS_BACKEND(self.caregiver_number, text)

                if self.status:
                    mapping = {
                        'first_name':self.first_name,
                        'second_name':self.last_name,
                        'status':self.get_status_display()
                    }

                    text = wordings.patient_status % mapping
                    settings.SMS_BACKEND(self.caregiver_number, text)


        super(Patient, self).save(*args, **kwargs) # Call the "real" save() method.
