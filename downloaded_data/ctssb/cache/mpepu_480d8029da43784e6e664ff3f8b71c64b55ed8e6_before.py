from django.contrib import admin

from edc.subject.consent.admin import BaseConsentModelAdmin, BaseConsentUpdateModelAdmin, BaseConsentUpdateInlineAdmin

from ..models import MaternalConsent, MaternalConsentUpdate
from ..forms import MaternalConsentForm, MaternalConsentUpdateForm


class MaternalConsentUpdateInlineAdmin(BaseConsentUpdateInlineAdmin):
    model = MaternalConsentUpdate
    form = MaternalConsentUpdateForm


class MaternalConsentUpdateAdmin(BaseConsentUpdateModelAdmin):

    form = MaternalConsentUpdateForm
    consent_name = 'maternal_consent'

admin.site.register(MaternalConsentUpdate, MaternalConsentUpdateAdmin)


class MaternalConsentAdmin(BaseConsentModelAdmin):

    form = MaternalConsentForm
    inlines = [MaternalConsentUpdateInlineAdmin, ]

    def __init__(self, *args, **kwargs):
        super(MaternalConsentAdmin, self).__init__(*args, **kwargs)
        # remove these fields from admin fields list, default values should apply
        for fld in ['witness_name', 'is_literate', 'guardian_name']:
            self.fields.remove(fld)

admin.site.register(MaternalConsent, MaternalConsentAdmin)
