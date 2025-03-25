import os

from django import forms
from django.utils import simplejson

from .models import Submission, Attachment, exercises


class WTEMForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ('answers',)

    def __init__(self, *args, **kwargs):
        super(WTEMForm, self).__init__(*args, **kwargs)
        for exercise in exercises:
            if exercise['type'] != 'file_upload':
                continue
            self.fields['attachment_for_' + str(exercise['id'])] = forms.FileField(required = False)

    def save(self):
        submission = super(WTEMForm, self).save()
        for name, file in self.files.items():
            exercise_id = int(name.split('_')[-1])
            try:
                attachment = Attachment.objects.get(submission = submission, exercise_id = exercise_id)
            except Attachment.DoesNotExist:
                attachment = Attachment(submission = submission, exercise_id = exercise_id)
            attachment.file = file
            attachment.save()

