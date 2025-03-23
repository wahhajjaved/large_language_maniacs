# browsershots.org - Test your web design in different browsers
# Copyright (C) 2007 Johann C. Rocholl <johann@browsershots.org>
#
# Browsershots is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Browsershots is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
Factory views.
"""

__revision__ = "$Rev$"
__date__ = "$Date$"
__author__ = "$Author$"

from psycopg import IntegrityError
from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django import newforms as forms
from django.newforms.util import ErrorList
from shotserver04 import settings
from shotserver04.common import last_poll_timeout, error_page
from shotserver04.common.preload import preload_foreign_keys
from shotserver04.factories.models import Factory, ScreenSize, ColorDepth
from shotserver04.screenshots.models import Screenshot, ProblemReport
from shotserver04.browsers.models import Browser
from shotserver04.browsers import views as browsers_views


FACTORY_NAME_CHAR_FIRST = 'abcdefghijklmnopqrstuvwxyz'
FACTORY_NAME_CHAR = FACTORY_NAME_CHAR_FIRST + '0123456789_-'


def overview(http_request):
    """
    List all screenshot factories.
    """
    factory_table_header = Factory.table_header()
    factory_list = Factory.objects.select_related().filter(
        last_poll__gt=last_poll_timeout()).order_by('-uploads_per_day')
    if not len(factory_list):
        return error_page(http_request, _("out of service"),
            _("No active screenshot factories."),
            _("Please try again later."))
    return render_to_response('factories/overview.html', locals(),
        context_instance=RequestContext(http_request))


class ScreenSizeForm(forms.Form):
    """
    Add or remove screen resolutions for a factory.
    """

    width = forms.IntegerField(widget=forms.TextInput(attrs={'size': 3}))
    height = forms.IntegerField(widget=forms.TextInput(attrs={'size': 3}))

    def clean_width(self):
        """
        Check that the screen width is within sensible limits.
        """
        width = self.cleaned_data['width']
        if width < 640:
            raise forms.ValidationError(_("Value %d is too small.") % width)
        if width > 1600:
            raise forms.ValidationError(_("Value %d is too big.") % width)
        return width

    def clean_height(self):
        """
        Check that the screen height is within sensible limits.
        """
        height = self.cleaned_data['height']
        if height < 480:
            raise forms.ValidationError(_("Value %d is too small.") % height)
        if height > 1200:
            raise forms.ValidationError(_("Value %d is too big.") % height)
        return height


class ColorDepthForm(forms.Form):
    """
    Add or remove color depths for a factory.
    """
    depth = forms.IntegerField(widget=forms.TextInput(attrs={'size': 2}))

    def clean_depth(self):
        """
        Check that the color depth within sensible limits.
        """
        depth = self.cleaned_data['depth']
        if depth < 1:
            raise forms.ValidationError(_("Value %d is too small.") % depth)
        if depth > 32:
            raise forms.ValidationError(_("Value %d is too big.") % depth)
        return depth


class InvalidRequest(Exception):
    """Not a valid post request."""
    title = _("invalid request")


class PermissionDenied(InvalidRequest):
    """User not logged in as factory admin."""
    title = _("permission denied")


def get_browser(http_request, id):
    """
    Get browser from POST data, and check admin permissions.
    """
    try:
        browser_id = int(id)
    except (KeyError, ValueError):
        raise InvalidRequest("You must specify a numeric browser ID.")
    # Get browser from database
    try:
        browser = Browser.objects.get(id=browser_id)
    except Browser.DoesNotExist:
        raise InvalidRequest(
            "Browser with id=%d does not exist." % browser_id)
    # Permission check
    if browser.factory.admin_id != http_request.user.id:
        raise PermissionDenied(
            "You don't have permission to edit this browser.")
    return browser


def deactivate_browser(http_request, id):
    """
    Deactivate the specified browser.
    """
    try:
        browser = get_browser(http_request, id)
        if not browser.active:
            raise InvalidRequest(_("This browser is already inactive."))
    except InvalidRequest, error:
        return error_page(http_request, error.title, error.args[0])
    browser.update_fields(active=False)
    return HttpResponseRedirect(browser.factory.get_absolute_url())


def activate_browser(http_request, id):
    """
    Activate the specified browser.
    """
    try:
        browser = get_browser(http_request, id)
        if browser.active:
            raise InvalidRequest("This browser is already active.")
    except InvalidRequest, error:
        return error_page(http_request, error.title, error.args[0])
    data = dict((field.name, getattr(browser, field.name))
                for field in Browser._meta.fields)
    browsers_views.delete_or_deactivate_similar_browsers(data, exclude=browser)
    browser.update_fields(active=True)
    return HttpResponseRedirect(browser.factory.get_absolute_url())


def details_post(http_request, factory,
                 factory_form, screensize_form, colordepth_form):
    """
    Process a post request to the details page,
    e.g. to add or remove a screen size or color depth.
    """
    if factory_form.is_valid():
        factory.update_fields(
            hardware=factory_form.cleaned_data['hardware'],
            operating_system=factory_form.cleaned_data['operating_system'])
        return HttpResponseRedirect(factory.get_absolute_url())
    if screensize_form.is_valid():
        try:
            ScreenSize.objects.create(factory=factory,
                width = screensize_form.cleaned_data['width'],
                height = screensize_form.cleaned_data['height'])
            return HttpResponseRedirect(
                factory.get_absolute_url() + '#screensizes')
        except IntegrityError, e:
            transaction.rollback()
            if 'duplicate' in str(e).lower():
                screensize_form.errors['width'] = [_("Duplicate.")]
            else:
                screensize_form.errors['width'] = [_("Invalid data.")]
    if colordepth_form.is_valid():
        try:
            ColorDepth.objects.create(factory=factory,
                bits_per_pixel = colordepth_form.cleaned_data['depth'])
            return HttpResponseRedirect(
                factory.get_absolute_url() + '#colordepths')
        except IntegrityError, e:
            transaction.rollback()
            if 'duplicate' in str(e).lower():
                colordepth_form.errors['depth'] = [_("Duplicate.")]
            else:
                colordepth_form.errors['depth'] = [_("Invalid data.")]
    for action in http_request.POST:
        parts = action.split('_')
        if len(parts) == 3:
            if parts[0] == 'remove' and parts[1] == 'size':
                width_height = parts[2].split('x')
                assert len(width_height) == 2
                width = int(width_height[0])
                height = int(width_height[1])
                ScreenSize.objects.filter(
                    factory=factory, width=width, height=height).delete()
                return HttpResponseRedirect(
                    factory.get_absolute_url() + '#screensizes')
            if parts[0] == 'remove' and parts[1] == 'depth':
                depth = int(parts[2])
                ColorDepth.objects.filter(
                    factory=factory, bits_per_pixel=depth).delete()
                return HttpResponseRedirect(
                    factory.get_absolute_url() + '#colordepths')
            if parts[0] == 'activate' and parts[1] == 'browser':
                return activate_browser(http_request, int(parts[2]))
            if parts[0] == 'deactivate' and parts[1] == 'browser':
                return deactivate_browser(http_request, int(parts[2]))


def details(http_request, name):
    """
    Get detailed information about a screenshot factory.
    """
    factory = get_object_or_404(Factory, name=name)
    factory_form = forms.form_for_instance(
        factory, fields=('hardware', 'operating_system'))(
        'submit_details' in http_request.POST and http_request.POST or None)
    screensize_form = ScreenSizeForm(
        'add_size' in http_request.POST and http_request.POST or None)
    colordepth_form = ColorDepthForm(
        'add_depth' in http_request.POST and http_request.POST or None)
    if http_request.POST:
        response = details_post(http_request, factory,
            factory_form, screensize_form, colordepth_form)
        if response:
            return response
    browser_list = list(Browser.objects.filter(factory=factory.id))
    preload_foreign_keys(browser_list,
                         browser_group=True,
                         engine=True,
                         javascript=True,
                         java=True,
                         flash=True)
    browser_list.sort(key=lambda browser: (unicode(browser), browser.id))
    screensize_list = factory.screensize_set.all()
    colordepth_list = factory.colordepth_set.all()
    screenshot_list = Screenshot.objects.filter(factory=factory,
        website__profanities__lte=settings.PROFANITIES_ALLOWED)
    screenshot_list = screenshot_list.order_by('-id')[:10]
    preload_foreign_keys(screenshot_list, browser=browser_list)
    admin_logged_in = http_request.user.id == factory.admin_id
    show_commands = admin_logged_in and True in [
        bool(browser.command) for browser in browser_list]
    problems_list = ProblemReport.objects.filter(
        screenshot__factory=factory)[:10]
    return render_to_response('factories/details.html', locals(),
        context_instance=RequestContext(http_request))


class FactoryBase(forms.BaseForm):
    """
    Special methods for FactoryForm (created below using form_for_model).
    """

    def clean_name(self):
        """
        Check that the factory name is sensible.
        """
        name = self.cleaned_data['name']
        if name[0] not in FACTORY_NAME_CHAR_FIRST:
            raise forms.ValidationError(unicode(
                _("Name must start with a lowercase letter.")))
        for index in range(len(name)):
            if name[index] not in FACTORY_NAME_CHAR:
                raise forms.ValidationError(unicode(
_("Name may contain only lowercase letters, digits, underscore, hyphen.")))
        if name in 'localhost server factory shotfactory add'.split():
            raise forms.ValidationError(unicode(
                _("This name is reserved.")))
        return name

    def create_factory(self, admin):
        """
        Try to create the factory in the database.
        Return None if the factory name is already taken.
        """
        factory = self.save(commit=False)
        factory.admin = admin
        try:
            factory.save()
            return factory
        except IntegrityError, e:
            transaction.rollback()
            if 'duplicate' in str(e).lower():
                self.errors['name'] = ErrorList([
                    _("This name is already taken.")])
            else:
                self.errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([str(e)])


FactoryForm = forms.form_for_model(Factory, form=FactoryBase,
    fields=('name', 'hardware', 'operating_system'))


@login_required
def add(http_request):
    """
    Add a new screenshot factory.
    """
    factory = None
    form = FactoryForm(http_request.POST or None)
    if form.is_valid():
        factory = form.create_factory(http_request.user)
    if not factory:
        form_title = _("register a new screenshot factory")
        form_submit = _("register")
        form_javascript = "document.getElementById('id_name').focus()"
        return render_to_response('form.html', locals(),
            context_instance=RequestContext(http_request))
    return HttpResponseRedirect(factory.get_absolute_url())
