import logging
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.forms.models import fields_for_model
from avocado.models import DataContext, DataView, DataQuery
from serrano import utils

log = logging.getLogger(__name__)

SHARE_QUERY_EMAIL_TITLE = "'{0}' has been shared with you"
SHARE_QUERY_EMAIL_BODY = """The query named '{0}' has been shared with you.
 You will be notified if this query is later removed."""


class ContextForm(forms.ModelForm):
    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.count_needs_update = kwargs.pop('force_count', None)
        super(ContextForm, self).__init__(*args, **kwargs)

    def clean_json(self):
        json = self.cleaned_data.get('json')

        if self.count_needs_update is None and self.instance:
            existing = self.instance.json
            if existing or json and existing != json or json and self.instance.count is None:
                self.count_needs_update = True
            else:
                self.count_needs_update = False
        return json

    def save(self, commit=True, archive=False):
        instance = super(ContextForm, self).save(commit=False)
        request = self.request

        if hasattr(request, 'user') and request.user.is_authenticated():
            instance.user = request.user
        else:
            instance.session_key = request.session.session_key

        # Only recalculated count if conditions exist. This is to
        # prevent re-counting the entire dataset. An alternative
        # solution may be desirable such as pre-computing and
        # caching the count ahead of time.
        if self.count_needs_update:
            instance.count = instance.apply().distinct().count()
            self.count_needs_update = False
        else:
            instance.count = None

        if commit:
            instance.save()
            if archive:
                # Should this be a signal?
                instance.archive()
        return instance

    class Meta(object):
        model = DataContext
        fields = ('name', 'description', 'keywords', 'json', 'session')


class ViewForm(forms.ModelForm):
    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.count_needs_update = kwargs.pop('force_count', None)
        super(ViewForm, self).__init__(*args, **kwargs)

    def clean_json(self):
        json = self.cleaned_data.get('json')

        if self.count_needs_update is None:
            existing = self.instance.json
            if existing or json and existing != json or json and self.instance.count is None:
                self.count_needs_update = True
            else:
                self.count_needs_update = False
        return json

    def save(self, commit=True, archive=False):
        instance = super(ViewForm, self).save(commit=False)
        request = self.request

        if hasattr(request, 'user') and request.user.is_authenticated():
            instance.user = request.user
        else:
            instance.session_key = request.session.session_key

        if commit:
            instance.save()
            if archive:
                # Should this be a signal?
                instance.archive()
        return instance

    class Meta(object):
        model = DataView
        fields = ('name', 'description', 'keywords', 'json', 'session')

class QueryForm(forms.ModelForm):
    # A list of the usernames or email addresses of the User's who the query
    # should be shared with. This is a string where each email/username is
    # separated by a '|'.
    usernames_or_emails = forms.CharField(widget=forms.Textarea,
        required=False)

    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.count_needs_update = kwargs.pop('force_count', None)
        super(QueryForm, self).__init__(*args, **kwargs)

    def clean_context_json(self):
        json = self.cleaned_data.get('context_json')
        if self.count_needs_update is None:
            existing = self.instance.context_json
            if existing or json and existing != json or json and self.instance.count is None:
                self.count_needs_update = True
            else:
                self.count_needs_update = False
        return json

    def clean_view_json(self):
        json = self.cleaned_data.get('view_json')
        if self.count_needs_update is None:
            existing = self.instance.view_json
            if existing or json and existing != json or json and self.instance.count is None:
                self.count_needs_update = True
            else:
                self.count_needs_update = False
        return json

    def clean_usernames_or_emails(self):
        """
        Cleans and validates the list of usernames and email address. This
        method returns a list of email addresses containing the valid emails
        and emails of valid users in the cleaned_data value for the
        usernames_or_emails field.
        """
        user_labels = self.cleaned_data.get('usernames_or_emails')
        emails = set()
        for label in user_labels.split('|'):
            try:
                validate_email(label)
                emails.add(label)
            except ValidationError:
                # If this user lookup label is not an email address, try to
                # find the user with the supplied username and get the
                # email that way. If no user with this username is found
                # then give up since we only support email and username
                # lookups.
                try:
                    user = User.objects.get(username=label)
                    all_emails.add(user.email)
                except User.DoesNotExist:
                    log.warning("Unable to share query with {0}. It is not a \
                        valid email or username.")

        return emails

    def save(self, commit=True, archive=False):
        instance = super(QueryForm, self).save(commit=False)
        request = self.request

        if hasattr(request, 'user') and request.user.is_authenticated():
            instance.user = request.user
        else:
            instance.session_key = request.session.session_key

        if commit:
            instance.save()

            all_emails = self.cleaned_data.get('usernames_or_emails')

            # Get the list of existing email addresses for users this query is
            # already shared with. We only want to email users the first time
            # a query is shared with them so we get the existing list of email
            # addresses to avoid repeated emails to users about the same query.
            existing_emails = set(instance.shared_users.all().values_list(
                'email', flat=True))
            new_emails = all_emails - existing_emails

            # Email and register all the new email addresses
            utils.send_mail(new_emails,
                SHARE_QUERY_EMAIL_TITLE.format(instance.name),
                SHARE_QUERY_EMAIL_BODY.format(instance.name))
            for email in new_emails:
                instance.share_with_user(email)

            # Find and remove users who have had their query share revoked
            removed_emails = existing_emails - all_emails
            for user in User.objects.filter(email__in=removed_emails):
                instance.shared_users.remove(user)

            self.save_m2m()

            if archive:
                # Should this be a signal?
                instance.archive()
        return instance

    class Meta(object):
        model = DataQuery
        fields = ('name', 'description', 'keywords', 'context_json',
                'view_json', 'session')
