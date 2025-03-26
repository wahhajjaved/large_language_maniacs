# -*- coding: utf-8 -*-

from logging import getLogger
log = getLogger('seantis.reservation')

from datetime import time
from DateTime import DateTime
from five import grok

from plone.dexterity.interfaces import IDexterityFTI
from zope.component import queryUtility
from zope.interface import Interface

from z3c.form import field
from z3c.form import button
from z3c.form.browser.radio import RadioFieldWidget
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from zope.browserpage.viewpagetemplatefile import ViewPageTemplateFile
from zope.schema import Choice, List

from seantis.reservation.throttle import throttled
from seantis.reservation.interfaces import (
    IResourceBase,
    IReservation,
    IGroupReservation,
    IRemoveReservation,
    IApproveReservation,
)

from seantis.reservation.error import DirtyReadOnlySession
from seantis.reservation import _
from seantis.reservation import db
from seantis.reservation import utils
from seantis.reservation import plone_session
from seantis.reservation.form import (
    ResourceBaseForm,
    AllocationGroupView,
    ReservationListView,
    extract_action_data
)

from seantis.reservation.overview import OverviewletManager
from seantis.reservation.error import NoResultFound


class ReservationUrls(object):
    """ Mixin class to create admin URLs for a specific reservation. """

    def remove_all_url(self, token, context=None):
        context = context or self.context
        base = context.absolute_url()
        return base + u'/remove-reservation?reservation=%s' % token

    def approve_all_url(self, token, context=None):
        context = context or self.context
        base = context.absolute_url()
        return base + u'/approve-reservation?reservation=%s' % token

    def deny_all_url(self, token, context=None):
        context = context or self.context
        base = context.absolute_url()
        return base + u'/deny-reservation?reservation=%s' % token


class ReservationSchemata(object):
    """ Mixin to use with plone.autoform and IResourceBase which makes the
    form it is used on display the formsets defined by the user.

    A formset is a Dexterity Type defined through the admin interface or
    code which has the behavior IReservationFormset.

    """

    @property
    def additionalSchemata(self):
        scs = []
        self.fti = dict()

        for ptype in self.context.formsets:
            fti = queryUtility(IDexterityFTI, name=ptype)
            if fti:
                schema = fti.lookupSchema()
                scs.append((ptype, fti.title, schema))

                self.fti[ptype] = (fti.title, schema)

        return scs


class SessionFormdataMixin(ReservationSchemata):

    def email(self, form_data=None):

        if not form_data or not form_data.get('email'):
            email = plone_session.get_email(self.context)
        else:
            email = form_data['email']
            plone_session.set_email(self.context, email)

        return email

    def merge_formdata(self, existing, new):

        for form in new:
            existing[form] = new[form]

        return existing

    def additional_data(self, form_data=None):

        if not form_data:
            data = plone_session.get_additional_data(self.context)
        else:
            data = plone_session.get_additional_data(self.context) or dict()

            # merge the formdata for session use only, committing the
            # reservation only forms defined in the resource are
            # stored with the reservation to get proper separation
            data = self.merge_formdata(
                plone_session.get_additional_data(self.context) or dict(),
                utils.additional_data_dictionary(form_data, self.fti)
            )

            plone_session.set_additional_data(self.context, data)

        return data

    def session_id(self):
        return plone_session.get_session_id(self.context)


class YourReservationsData(object):
    """ Mixin providing functions to deal with 'your' reservations. """

    def reservations(self):
        """ Returns all reservations in the user's session """
        session_id = plone_session.get_session_id(self.context)
        return db.reservations_by_session(session_id).all()

    @property
    def has_reservations(self):
        session_id = plone_session.get_session_id(self.context)
        return bool(db.reservations_by_session(session_id).first())

    def confirm_reservations(self, token=None):
        # Remove session_id from all reservations in the current session.
        self.scheduler.confirm_reservations_for_session(
            plone_session.get_session_id(self.context), token
        )

    def remove_reservation(self, token):
        session_id = plone_session.get_session_id(self.context)
        self.scheduler.remove_reservation_from_session(session_id, token)

    def reservation_data(self):
        """ Prepares data to be shown in the my reservation's table """
        reservations = []

        for reservation in self.reservations():
            resource = utils.get_resource_by_uuid(reservation.resource)

            if resource is None:
                log.warn('Invalid UUID %s' % str(reservation.resource))
                continue

            resource = resource.getObject()

            data = {}

            data['title'] = utils.get_resource_title(resource)

            timespans = []
            for start, end in reservation.timespans():
                timespans.append(u'◆ ' + utils.display_date(start, end))

            data['time'] = '<br />'.join(timespans)
            data['quota'] = utils.get_reservation_quota_statement(
                reservation.quota
            ) if reservation.quota > 1 else u''

            data['url'] = resource.absolute_url()
            data['remove-url'] = ''.join((
                resource.absolute_url(),
                '/your-reservations?remove=',
                reservation.token.hex
            ))
            reservations.append(data)

        return reservations

    def redirect_to_your_reservations(self):
        self.request.response.redirect(
            self.context.absolute_url() + '/your-reservations'
        )


class ReservationBaseForm(ResourceBaseForm):

    def your_reservation_defaults(self, defaults):
        """ Extends the given dictionary containing field defaults with
        the defaults found in your-reservations.

        """

        default_email = self.email()
        if default_email:
            defaults['email'] = self.email()

        data = self.additional_data()

        if not data:
            return defaults

        for form in data:
            for field in data[form]['values']:
                defaults["%s.%s" % (form, field['key'])] = field['value']

        return defaults

    def run_reserve(
        self, data, autoapprove, start=None, end=None, group=None, quota=1
    ):

        assert (start and end) or group
        assert not (start and end and group)

        email = self.email(data)
        additional_data = self.additional_data(data)
        session_id = self.session_id()

        # only store forms defined in the formsets list
        additional_data = dict(
            (
                form, additional_data[form]
            ) for form in self.context.formsets if form in additional_data
        )

        if start and end:
            token = self.scheduler.reserve(
                email, (start, end),
                data=additional_data, session_id=session_id, quota=quota
            )
        else:
            token = self.scheduler.reserve(
                email, group=group,
                data=additional_data, session_id=session_id, quota=quota
            )

        if autoapprove:
            self.scheduler.approve_reservation(token)
            self.flash(_(u'Reservation successful'))
        else:
            self.flash(_(u'Added to waitinglist'))


class ReservationForm(
        ReservationBaseForm,
        SessionFormdataMixin,
        YourReservationsData
):

    permission = 'seantis.reservation.SubmitReservation'

    grok.name('reserve')
    grok.require(permission)

    context_buttons = ('reserve', )

    fields = field.Fields(IReservation)
    label = _(u'Resource reservation')

    fti = None

    autoGroups = True
    enable_form_tabbing = True
    default_fieldset_label = _(u'General Information')

    @property
    def hidden_fields(self):
        hidden = ['id']

        try:
            allocation = self.allocation(self.id)

            if allocation:

                if allocation.reservation_quota_limit == 1:
                    hidden.append('quota')

                if allocation.whole_day:
                    hidden.append('start_time')
                    hidden.append('end_time')

        except DirtyReadOnlySession:
            pass

        return hidden

    @property
    def disabled_fields(self):
        disabled = ['day']
        try:
            allocation = self.allocation(self.id)

            if allocation:

                if allocation.partly_available:
                    disabled.append('start_time')
                    disabled.append('end_time')

        except DirtyReadOnlySession:
            pass

        return disabled

    def defaults(self, **kwargs):
        return self.your_reservation_defaults(dict(id=self.id, quota=1))

    def allocation(self, id):
        if not id:
            return None

        return self.scheduler.allocation_by_id(id)

    def strptime(self, value):
        if not value:
            return None

        if not isinstance(value, basestring):
            return value

        dt = DateTime(value)
        return time(dt.hour(), dt.minute())

    def validate(self, data):
        try:
            start, end = utils.get_date_range(
                data['day'], data['start_time'], data['end_time']
            )
            if not self.allocation(data['id']).contains(start, end):
                utils.form_error(_(u'Reservation out of bounds'))

            return start, end
        except (NoResultFound, TypeError):
            utils.form_error(_(u'Invalid reservation request'))

    @button.buttonAndHandler(_(u'Reserve'))
    @extract_action_data
    def reserve(self, data):

        allocation = self.allocation(data['id'])

        start, end = self.validate(data)
        autoapprove = not allocation.approve
        quota = int(data['quota'])

        # whole day allocations don't show the start / end time which is to
        # say the data arrives with 00:00 - 00:00. we align that to the day
        if allocation.whole_day:
            assert start == end
            start, end = utils.align_range_to_day(start, end)

        def reserve():
            self.run_reserve(
                data=data, autoapprove=autoapprove,
                start=start, end=end, quota=quota
            )

        action = throttled(reserve, self.context, 'reserve')
        utils.handle_action(
            action=action, success=self.redirect_to_your_reservations
        )

    @button.buttonAndHandler(_(u'Cancel'))
    def cancel(self, action):
        self.redirect_to_context()

    def customize_fields(self, fields):
        """ This function is called by ResourceBaseForm every time fields are
        created from the schema by z3c. This allows for changes before the
        fields are properly integrated into the form.

        Here, we want to make sure that all formset schemas have sane widgets.

        """

        for field in fields.values():

            field_type = type(field.field)

            if field_type is List:
                field.widgetFactory = CheckBoxFieldWidget

            elif field_type is Choice:
                field.widgetFactory = RadioFieldWidget


class GroupReservationForm(
        ReservationBaseForm,
        AllocationGroupView,
        SessionFormdataMixin,
        YourReservationsData
):
    permission = 'seantis.reservation.SubmitReservation'

    grok.name('reserve-group')
    grok.require(permission)

    context_buttons = ('reserve', )

    fields = field.Fields(IGroupReservation)
    label = _(u'Recurrance reservation')

    template = ViewPageTemplateFile('templates/reserve_group.pt')

    ignore_requirements = True

    autoGroups = True
    enable_form_tabbing = True
    default_fieldset_label = _(u'General Information')

    @property
    def hidden_fields(self):
        hidden = ['group']

        try:
            allocation = self.group and self.scheduler.allocations_by_group(
                self.group
            ).first()

            if allocation.reservation_quota_limit == 1:
                hidden.append('quota')

        except DirtyReadOnlySession:
            pass

        return hidden

    def defaults(self, **kwargs):
        return self.your_reservation_defaults(dict(group=self.group, quota=1))

    @button.buttonAndHandler(_(u'Reserve'))
    @extract_action_data
    def reserve(self, data):

        autoapprove = not self.scheduler.allocations_by_group(data['group']) \
            .first().approve

        def reserve():
            self.run_reserve(
                data=data, autoapprove=autoapprove,
                group=data['group'], quota=data['quota']
            )

        action = throttled(reserve, self.context, 'reserve')
        utils.handle_action(
            action=action, success=self.redirect_to_your_reservations
        )

    @button.buttonAndHandler(_(u'Cancel'))
    def cancel(self, action):
        self.redirect_to_context()


class YourReservations(ResourceBaseForm, YourReservationsData):

    permission = "seantis.reservation.SubmitReservation"

    grok.name('your-reservations')
    grok.require(permission)

    context_buttons = ('finish', )

    grok.context(Interface)

    css_class = 'seantis-reservation-form'

    template = grok.PageTemplateFile('templates/your_reservations.pt')

    @button.buttonAndHandler(_(u'Submit Reservations'), name="finish")
    def finish(self, data):
        self.confirm_reservations()
        self.request.response.redirect(self.context.absolute_url())
        self.flash(_(u'Reservations Successfully Submitted'))

    @button.buttonAndHandler(_(u'Reserve More'), name="proceed")
    def proceed(self, data):
        # Don't do anything, reservations stay in the session.
        self.request.response.redirect(self.context.absolute_url())

    def update(self):
        if 'remove' in self.request and utils.is_uuid(self.request['remove']):
            self.remove_reservation(self.request['remove'])

            self.request.response.redirect(self.context.absolute_url())

        super(YourReservations, self).update()


class YourReservationsViewlet(grok.Viewlet, YourReservationsData):
    grok.context(Interface)
    grok.name('seantis.reservation.YourReservationsviewlet')
    grok.require('zope2.View')
    grok.viewletmanager(OverviewletManager)

    grok.order(0)

    template = grok.PageTemplateFile('templates/your_reservations_viewlet.pt')

    def available(self):
        return self.has_reservations

    def finish_url(self):
        return self.context.absolute_url() + '/your-reservations'


class ReservationDecisionForm(ResourceBaseForm, ReservationListView,
                              ReservationUrls):
    """ Base class for admin's approval / denial forms. """

    grok.baseclass()

    fields = field.Fields(IApproveReservation)

    hidden_fields = ['reservation']
    ignore_requirements = True

    template = ViewPageTemplateFile('templates/decide_reservation.pt')

    show_links = False
    data = None

    @property
    def reservation(self):
        data = self.data
        return self.request.get(
            'reservation', (data and data['reservation'] or None)
        )

    def defaults(self):
        return dict(
            reservation=unicode(self.reservation)
        )


class ReservationApprovalForm(ReservationDecisionForm):

    permission = 'seantis.reservation.ApproveReservations'

    grok.name('approve-reservation')
    grok.require(permission)

    context_buttons = ('approve', )

    label = _(u'Approve reservation')

    @property
    def hint(self):
        if not self.pending_reservations():
            return _(u'No such reservation')

        return _(u'Do you really want to approve the following reservations?')

    @button.buttonAndHandler(_(u'Approve'))
    @extract_action_data
    def approve(self, data):

        self.data = data

        def approve():
            self.scheduler.approve_reservation(data['reservation'])
            self.flash(_(u'Reservation confirmed'))

        utils.handle_action(action=approve, success=self.redirect_to_context)

    @button.buttonAndHandler(_(u'Cancel'))
    def cancel(self, action):
        self.redirect_to_context()


class ReservationDenialForm(ReservationDecisionForm):

    permission = 'seantis.reservation.ApproveReservations'

    grok.name('deny-reservation')
    grok.require(permission)

    context_buttons = ('deny', )

    label = _(u'Deny reservation')

    @property
    def hint(self):
        if not self.pending_reservations():
            return _(u'No such reservation')

        return _(u'Do you really want to deny the following reservations?')

    @button.buttonAndHandler(_(u'Deny'))
    @extract_action_data
    def deny(self, data):

        self.data = data

        def deny():
            self.scheduler.deny_reservation(data['reservation'])
            self.flash(_(u'Reservation denied'))

        utils.handle_action(action=deny, success=self.redirect_to_context)

    @button.buttonAndHandler(_(u'Cancel'))
    def cancel(self, action):
        self.redirect_to_context()


class ReservationRemoveForm(ResourceBaseForm, ReservationListView,
                            ReservationUrls):

    permission = 'seantis.reservation.ApproveReservations'

    grok.name('remove-reservation')
    grok.require(permission)

    context_buttons = ('delete', )

    fields = field.Fields(IRemoveReservation)
    template = ViewPageTemplateFile('templates/remove_reservation.pt')

    label = _(u'Remove reservation')

    hidden_fields = ['reservation', 'start', 'end']
    ignore_requirements = True

    show_links = False

    @property
    def reservation(self):
        return self.request.get('reservation')

    def defaults(self):
        return dict(
            reservation=unicode(self.reservation),
            start=self.start,
            end=self.end
        )

    @property
    def hint(self):
        if not self.approved_reservations():
            return _(u'No such reservation')

        if self.reservation and not all((self.start, self.end)):
            return _(
                u'Do you really want to remove the following reservations?'
            )

        if self.reservation and all((self.start, self.end)):
            return _(u'Do you really want to remove '
                     u'the following timespans from the reservation?')

    @button.buttonAndHandler(_(u'Delete'))
    @extract_action_data
    def delete(self, data):

        def delete():
            self.scheduler.remove_reservation(
                data['reservation'], data['start'], data['end']
            )
            self.flash(_(u'Reservation removed'))

        utils.handle_action(action=delete, success=self.redirect_to_context)

    @button.buttonAndHandler(_(u'Cancel'))
    def cancel(self, action):
        self.redirect_to_context()


class ReservationList(grok.View, ReservationListView, ReservationUrls):

    permission = "seantis.reservation.ViewReservations"

    grok.name('reservations')
    grok.require(permission)

    grok.context(IResourceBase)

    template = grok.PageTemplateFile('templates/reservations.pt')

    @property
    def id(self):
        return utils.request_id_as_int(self.request.get('id'))

    @property
    def group(self):
        if 'group' in self.request:
            return unicode(self.request['group'].decode('utf-8'))
        else:
            return u''
