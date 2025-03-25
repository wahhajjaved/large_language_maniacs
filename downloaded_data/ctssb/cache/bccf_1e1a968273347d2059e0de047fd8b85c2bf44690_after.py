import logging
import json

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from mezzanine.utils.models import upload_to

from form_utils.forms import BetterForm
from formable.builder.models import FormStructure, FormPublished, Question
from bccf.models import BCCFTopic
from bccf.settings import MEDIA_ROOT
from bccf.widgets import AdvancedFileInput

log = logging.getLogger(__name__)


class FormStructureForm(forms.ModelForm):
    """
    Form form Creating from structures
    """
    structure = forms.CharField(widget=forms.HiddenInput(attrs={'id':'form_structure_data'}))

    class Meta:
        model = FormStructure
        fields = ['title', 'structure']

class FormPublishForm(forms.ModelForm):
    """
    Form for creating a new form structure.
    """
    class Meta:
        model = FormPublished
        widgets = {
            'status': forms.RadioSelect,
            'image': AdvancedFileInput,
            'user': forms.HiddenInput,
            'form_structure': forms.HiddenInput
        }
        fields = ('user', 'form_structure', 'title', 'status', 'content', 'page_for', 'bccf_topic', 'featured', 'image')

    def __init__(self, hide, *args, **kwargs):
        super(FormPublishForm, self).__init__(*args, **kwargs)
        if hide:
            self.widget['status'] = forms.HiddenInput()

    def handle_upload(self):
        image_path = 'uploads/childpage/'+self.files['image'].name
        destination = open(MEDIA_ROOT+'/'+image_path, 'wb+')
        for chunk in self.files['image'].chunks():
            destination.write(chunk)
        destination.close()
        return image_path

    def is_valid(self):
        if not 'title' in self.data:
            return False
        if not 'content' in self.data:
            return False
        return True

    def save(self, **kwargs):
        form_published = super(FormPublishForm, self).save(**kwargs)
        if 'image' in self.files:
            form_published.image = self.handle_upload()
            form_published.save()

        return form_published

class CloneFormForm(forms.Form):
    """
    Creates a dropdown containing the created form structures
    """
    def __init__(self, user, *args, **kwargs):
        super(CloneFormForm, self).__init__(*args, **kwargs)
        self.form_structure = forms.ChoiceField(FormStructure.objects.filter(Q(user=None) | Q(user=user)).order_by('user').values_list('id', 'title'))


class ViewFormForm(BetterForm):
    """
    Creates a form based on the saved form structure. Parses the JSON and creates
    a new form structure that can be rendered by Django.
    """
    base_fieldsets = None

    def __init__(self, fieldsets, fields, *args, **kwargs):
        self.base_fieldsets = fieldsets
        super(ViewFormForm, self).__init__(*args, **kwargs)
        self.fields = fields
