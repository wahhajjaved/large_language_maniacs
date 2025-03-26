import copy
import datetime
import itertools
import json
import operator
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from courselib.auth import requires_role, NotFoundResponse
from django.shortcuts import get_object_or_404, get_list_or_404, render
from django.db import transaction

from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.http import StreamingHttpResponse
from django.http import HttpResponseBadRequest
from django.core.exceptions import PermissionDenied

from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template.base import Template
from django.template.context import Context
from courselib.search import find_userid_or_emplid

from coredata.models import Person, Unit, Role, Member, CourseOffering, Semester
from grad.models import Supervisor
from ra.models import RAAppointment

from faculty.models import CareerEvent, MemoTemplate, Memo, EventConfig, FacultyMemberInfo
from faculty.models import Grant, TempGrant, GrantOwner
from faculty.models import EVENT_TYPES, EVENT_TYPE_CHOICES, EVENT_TAGS, ADD_TAGS
from faculty.forms import MemoTemplateForm, MemoForm, AttachmentForm, ApprovalForm, GetSalaryForm, TeachingSummaryForm, DateRangeForm
from faculty.forms import SearchForm, EventFilterForm, EventFlagForm, GrantForm, GrantImportForm, UnitFilterForm
from faculty.forms import AvailableCapacityForm, CourseAccreditationForm
from faculty.forms import FacultyMemberInfoForm, TeachingCreditOverrideForm
from faculty.processing import FacultySummary
from templatetags.event_display import fraction_display
from faculty.util import ReportingSemester, make_csv_writer_response
from faculty.event_types.base import Choices
from faculty.event_types.awards import FellowshipEventHandler
from faculty.event_types.career import AccreditationFlagEventHandler
from faculty.event_types.career import SalaryBaseEventHandler

def _get_faculty_or_404(allowed_units, userid_or_emplid):
    """
    Get the Person who has Role[role=~"faculty"] if we're allowed to see it, or raise Http404.
    """
    sub_unit_ids = Unit.sub_unit_ids(allowed_units)
    person = get_object_or_404(Person, find_userid_or_emplid(userid_or_emplid))
    roles = get_list_or_404(Role, role='FAC', unit__id__in=sub_unit_ids, person=person)
    units = set(r.unit for r in roles)
    return person, units


def _get_event_or_404(units, **kwargs):
    subunit_ids = Unit.sub_unit_ids(units)
    instance = get_object_or_404(CareerEvent, unit__id__in=subunit_ids, **kwargs)
    return instance

def _get_tempgrants(units, **kwargs):
    subunit_ids = Unit.sub_unit_ids(units)
    grants = TempGrant.objects.filter(unit__id__in=subunit_ids, **kwargs)

def _get_grants(units, **kwargs):
    subunit_ids = Unit.sub_unit_ids(units)
    grants = Grant.objects.active().filter(unit__id__in=subunit_ids, **kwargs)
    return grants

def _get_Handler_or_404(handler_slug):
    handler_slug = handler_slug.upper()
    if handler_slug in EVENT_TYPES:
        return EVENT_TYPES[handler_slug]
    else:
        raise Http404('Unknown event handler slug')


def _get_event_types():
    types = [{
        'slug': key.lower(),
        'name': Handler.NAME,
        'is_instant': Handler.IS_INSTANT,
        'affects_teaching': 'affects_teaching' in Handler.FLAGS,
        'affects_salary': 'affects_salary' in Handler.FLAGS
    } for key, Handler in EVENT_TYPE_CHOICES]
    return sorted(types, key=operator.itemgetter('name'))


###############################################################################
# Top-level views (management, etc. Not specific to a faculty member)

@requires_role('ADMN')
def index(request):
    sub_units = Unit.sub_units(request.units)
    fac_roles = Role.objects.filter(role='FAC', unit__in=sub_units).select_related('person', 'unit').order_by('person')
    fac_roles = itertools.groupby(fac_roles, key=lambda r: r.person)
    fac_roles = [(p, [r.unit for r in roles], CareerEvent.current_ranks(p)) for p, roles in fac_roles]

    editor = get_object_or_404(Person, userid=request.user.username)
    events = CareerEvent.objects.filter(status='NA').only_subunits(request.units)
    events = [e.get_handler() for e in events]
    events = [h for h in events if h.can_approve(editor)]
    filterform = UnitFilterForm(sub_units)

    context = {
        'fac_roles': fac_roles,
        'queued_events': len(events),
        'filterform': filterform,
    }
    return render(request, 'faculty/index.html', context)


@requires_role('ADMN')
def search_index(request):
    editor = get_object_or_404(Person, userid=request.user.username)
    event_types = _get_event_types()
    return render(request, 'faculty/search_index.html', {
        'event_types': event_types,
        'editor': editor,
        'person': editor,
    })


@requires_role('ADMN')
def search_events(request, event_type):
    Handler = _get_Handler_or_404(event_type)
    viewer = get_object_or_404(Person, userid=request.user.username)
    unit_choices = [('', u'\u2012',)] + [(u.id, u.name) for u in Unit.sub_units(request.units)]
    filterform = UnitFilterForm(Unit.sub_units(request.units))

    results = []

    if request.GET:
        form = SearchForm(request.GET)
        form.fields['unit'].choices = unit_choices
        rules = Handler.get_search_rules(request.GET)

        if form.is_valid() and Handler.validate_all_search(rules):
            events = CareerEvent.objects.only_subunits(request.units).by_type(Handler).not_deleted()

            # TODO: Find a better place for this initial filtering logic
            if form.cleaned_data['start_date']:
                events = events.filter(start_date__gte=form.cleaned_data['start_date'])
            if form.cleaned_data['end_date']:
                events = events.filter(end_date__lte=form.cleaned_data['end_date'])
            if form.cleaned_data['unit']:
                events = events.filter(unit=form.cleaned_data['unit'])
            if form.cleaned_data['only_current']:
                events = events.effective_now()

            results = Handler.filter(events, rules=rules, viewer=viewer)
    else:
        form = SearchForm()
        form.fields['unit'].choices = unit_choices
        rules = Handler.get_search_rules()

    context = {
        'event_type': Handler.NAME,
        'form': form,
        'search_rules': rules,
        'results_columns': Handler.get_search_columns(),
        'results': results,
        'filterform': filterform,
    }
    return render(request, 'faculty/search_form.html', context)


@requires_role('ADMN')
def salary_index(request):
    """
    Salaries of all faculty members
    """
    form = GetSalaryForm()

    if request.GET:
        form = GetSalaryForm(request.GET)

        if form.is_valid():
            date = form.cleaned_data['date']
        else:
            date = datetime.date.today()

    else:
        date = datetime.date.today()
        initial = { 'date': date }
        form = GetSalaryForm(initial=initial)

    fac_roles_pay = _salary_index_data(request, date)

    context = {
        'form': form,
        'fac_roles_pay': fac_roles_pay,
        'date': date,
        'filterform': UnitFilterForm(Unit.sub_units(request.units)),
    }
    return render(request, 'faculty/reports/salary_index.html', context)


def _salary_index_data(request, date):
    sub_unit_ids = Unit.sub_unit_ids(request.units)
    fac_roles_pay = Role.objects.filter(role='FAC', unit__id__in=sub_unit_ids).select_related('person', 'unit')
    fac_roles_pay = itertools.groupby(fac_roles_pay, key=lambda r: r.person)
    fac_pay_summary = []
    for person, roles in fac_roles_pay:

        salary_events = copy.copy(FacultySummary(person).salary_events(date))
        add_salary_total = add_bonus_total = 0
        salary_fraction_total = 1

        for event in salary_events:
            event.add_salary, event.salary_fraction, event.add_bonus = FacultySummary(person).salary_event_info(event)
            add_salary_total += event.add_salary
            salary_fraction_total = salary_fraction_total*event.salary_fraction
            add_bonus_total += event.add_bonus

        #get most recent step and rank from base_salary
        recent_salary_update = FacultySummary(person).recent_salary(date)
        if recent_salary_update != None:
            try:
                step = recent_salary_update.config["step"]
            except KeyError:
                step = "-"
            try:
                handler = recent_salary_update.get_handler()
                rank = handler.get_display('rank')
            except KeyError:
                rank = "-"
        else:
            step = "-"
            rank = "-"

        current_salary = FacultySummary(person).salary(date)

        fac_pay_summary += [(person, ' , '.join(r.unit.label for r in roles), current_salary, add_salary_total, salary_fraction_total, add_bonus_total, step, rank)]

    # TODO: below line should only select pay from units the user can see
    return fac_pay_summary


@requires_role('ADMN')
def salary_index_csv(request):
    if request.GET:
        form = GetSalaryForm(request.GET)
        if form.is_valid():
            date = form.cleaned_data['date']
        else:
            date = datetime.date.today()

    else:
        date = datetime.date.today()

    filename = 'salary_summary_{}.csv'.format(date.isoformat())
    csv, response = make_csv_writer_response(filename)
    csv.writerow([
        'Name',
        'Rank',
        'Step',
        'Unit',
        'Total Salary',
        'Multiplier',
        'Bonus',
        'Total Pay',
    ])

    for person, units, pay, salary, fraction, bonus, step, rank in _salary_index_data(request, date):
        csv.writerow([
            person.name(),
            rank,
            step,
            units,
            salary,
            _csvfrac(fraction),
            bonus,
            pay,
        ])

    return response


@requires_role('ADMN')
def fallout_report(request):
    """
    Fallout Report
    """
    form = DateRangeForm()

    if request.GET:
        form = DateRangeForm(request.GET)

        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
        else:
            end_date = datetime.date.today()
            start_date = datetime.date(end_date.year, 1, 1)

    else:
        end_date = datetime.date.today()
        start_date = datetime.date(end_date.year, 1, 1)
        initial = { 'start_date': start_date,
                    'end_date': end_date }
        form = DateRangeForm(initial=initial)

    sub_unit_ids = Unit.sub_unit_ids(request.units)
    fac_roles = Role.objects.filter(role='FAC', unit__id__in=sub_unit_ids).select_related('person', 'unit')
    fac_roles = itertools.groupby(fac_roles, key=lambda r: r.person)
    table = []
    tot_fallout = 0
    for p, roles in fac_roles:
        salary = FacultySummary(p).base_salary(end_date)
        units = ' , '.join(r.unit.label for r in roles)
        # TODO: below line should only select pay from units the user can see
        salary_events = CareerEvent.objects.not_deleted().overlaps_daterange(start_date, end_date).filter(person=p).filter(flags=CareerEvent.flags.affects_salary).filter(status='A')
        for event in salary_events:
            if event.event_type == 'LEAVE' or event.event_type == 'STUDYLEAVE':
                days = event.get_duration_within_range(start_date, end_date)
                fraction = FacultySummary(p).salary_event_info(event)[1]
                d = fraction.denominator
                n = fraction.numerator
                fallout = Decimal((salary - salary*n/d)*days/365).quantize(Decimal('.01'), rounding=ROUND_DOWN)
                tot_fallout += fallout

                table += [(units, p, event, days, salary, fraction, fallout )]
    # table, tot_fallout = _fallout_report_data(request, start_date, end_date)

    context = {
        'form': form,
        'table': table,
        # 'tot_fallout': tot_fallout, not using this at the moment
        'start_date': start_date,
        'end_date': end_date,
        'filterform': UnitFilterForm(Unit.sub_units(request.units)),
    }
    return render(request, 'faculty/reports/fallout_report.html', context)


def _fallout_report_data(request, start_date, end_date):
    sub_unit_ids = Unit.sub_unit_ids(request.units)
    fac_roles = Role.objects.filter(role='FAC', unit__id__in=sub_unit_ids).select_related('person', 'unit')
    fac_roles = itertools.groupby(fac_roles, key=lambda r: r.person)
    table = []
    tot_fallout = 0
    for p, roles in fac_roles:
        salary = FacultySummary(p).base_salary(end_date)
        units = ' , '.join(r.unit.label for r in roles)
        # TODO: below line should only select pay from units the user can see
        salary_events = CareerEvent.objects.not_deleted().overlaps_daterange(start_date, end_date).filter(person=p).filter(flags=CareerEvent.flags.affects_salary).filter(status='A')
        for event in salary_events:
            if event.event_type == 'LEAVE' or event.event_type == 'STUDYLEAVE':
                days = event.get_duration_within_range(start_date, end_date)
                fraction = FacultySummary(p).salary_event_info(event)[1]
                d = fraction.denominator
                n = fraction.numerator
                fallout = Decimal((salary - salary*n/d)*days/365).quantize(Decimal('.01'), rounding=ROUND_DOWN)
                tot_fallout += fallout

                table += [(units, p, event, days, salary, fraction, fallout )]
    return table

@requires_role('ADMN')
def fallout_report_csv(request):
    if request.GET:
        form = DateRangeForm(request.GET)

        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
        else:
            end_date = datetime.date.today()
            start_date = datetime.date(end_date.year, 1, 1)

    else:
        end_date = datetime.date.today()
        start_date = datetime.date(end_date.year, 1, 1)

    filename = 'fallout_report_{}-{}.csv'.format(start_date.isoformat(), end_date.isoformat())
    csv, response = make_csv_writer_response(filename)
    csv.writerow([
        'Unit',
        'Name',
        'Event',
        'Days',
        'Base',
        'Fraction',
        'Fallout'
    ])

    for units, p, event, days, salary, fraction, fallout in _fallout_report_data(request, start_date, end_date):
        csv.writerow([
            units,
            p.name(),
            event.get_handler().short_summary(),
            days,
            salary,
            _csvfrac(fraction),
            fallout,
        ])

    return response


@requires_role('ADMN')
def status_index(request):
    """
    Status list of for all yet-to-be approved events.
    """
    editor = get_object_or_404(Person, userid=request.user.username)
    events = CareerEvent.objects.filter(status='NA').only_subunits(request.units)
    events = [e for e in events if e.get_handler().can_view(editor)]
    context = {
        'events': events,
        'editor': editor,
    }
    return render(request, 'faculty/status_index.html', context)


@requires_role('ADMN')
def salary_summary(request, userid):
    """
    Shows all salary career events at a date
    """
    person, member_units = _get_faculty_or_404(request.units, userid)
    form = GetSalaryForm()

    if request.GET:
        form = GetSalaryForm(request.GET)

        if form.is_valid():
            date = request.GET.get('date', None)

    else:
        date = datetime.date.today()
        initial = { 'date': date }
        form = GetSalaryForm(initial=initial)

    # TODO: below code should return only salary in units user is allowed to see
    pay_tot = FacultySummary(person).salary(date)

    salary_events = copy.copy(FacultySummary(person).salary_events(date))
    add_salary_total = add_bonus_total = 0
    salary_fraction_total = 1

    for event in salary_events:
        event.add_salary, event.salary_fraction, event.add_bonus = FacultySummary(person).salary_event_info(event)
        add_salary_total += event.add_salary
        salary_fraction_total = salary_fraction_total*event.salary_fraction
        add_bonus_total += event.add_bonus

    context = {
        'form': form,
        'date': date,
        'person': person,
        'pay_tot': pay_tot,
        'salary_events': salary_events,
        'add_salary_total': add_salary_total,
        'salary_fraction_total': salary_fraction_total,
        'add_bonus_total': add_bonus_total,
    }

    return render(request, 'faculty/reports/salary_summary.html', context)


def _teaching_capacity_data(unit, semester):
    people = set(role.person for role in Role.objects.filter(role='FAC', unit=unit))

    for person in sorted(people):
        summary = FacultySummary(person)
        credits, load = summary.teaching_credits(semester)

        # -load: we're showing "expected teaching load"
        # -capacity: if this is negative, then we have available capacity
        yield person, credits, -load, -(credits + load)


@requires_role('ADMN')
def teaching_capacity(request):
    sub_units = Unit.sub_units(request.units)

    form = AvailableCapacityForm(request.GET or {'semester': Semester.current().name})
    collected_units = []

    context = {
        'form': form,
        'units': collected_units,
        'filterform': UnitFilterForm(Unit.sub_units(request.units)),
    }

    if form.is_valid():
        semester = ReportingSemester(form.cleaned_data['semester'])

        for unit in sub_units:
            entries = []
            total_capacity = 0

            for person, credits, load, capacity in _teaching_capacity_data(unit, semester):
                total_capacity += capacity
                entries.append((person, credits, load, capacity))

            collected_units.append((unit, entries, total_capacity))

        context['semester'] = semester

    return render(request, 'faculty/reports/teaching_capacity.html', context)


@requires_role('ADMN')
def teaching_capacity_csv(request):
    sub_units = Unit.sub_units(request.units)

    form = AvailableCapacityForm(request.GET)

    if form.is_valid():
        semester = ReportingSemester(form.cleaned_data['semester'])

        filename = 'teaching_capacity_{}.csv'.format(semester.code)
        csv, response = make_csv_writer_response(filename)
        csv.writerow([
            'Unit',
            'Person',
            'Expected teaching load',
            'Teaching credits',
            'Available capacity',
        ])

        for unit in sub_units:
            for person, credits, load, capacity in _teaching_capacity_data(unit, semester):
                csv.writerow([
                    unit.label,
                    person.name(),
                    _csvfrac(load),
                    _csvfrac(credits),
                    _csvfrac(capacity),
                ])

        return response

    return HttpResponseBadRequest(form.errors)


def _matched_flags(operator, selected_flags, instructor_flags):
    if operator == 'AND':
        # Instructor must have all flags
        if selected_flags <= instructor_flags:
            return selected_flags
        else:
            return None
    elif operator == 'OR':
        # Instructor must have at least one of the flags
        common = selected_flags & instructor_flags
        if common:
            return common
        else:
            return None
    elif operator == 'NONE_OF':
        # Instructor must have none of the flags
        if not selected_flags & instructor_flags:
            return instructor_flags - selected_flags
        else:
            return None
    else:
        # No filtering
        return instructor_flags


def _get_visible_flags(viewer, offering, instructor):
    return set(event.config['flag']
               for event in CareerEvent.objects.not_deleted()
                                               .by_type(AccreditationFlagEventHandler)
                                               .filter(unit=offering.owner)
                                               .filter(person=instructor)
                                               .overlaps_semester(offering.semester)
                                               .filter(status='A')
               if event.get_handler().can_view(viewer))


def _course_accreditation_data(viewer, units, semesters, operator, selected_flags):
    # Get all offerings that fall within the selected semesters.
    offerings = (CourseOffering.objects.filter(semester__in=semesters, owner__in=units)
                                       .order_by('owner', '-semester'))

    for offering in offerings:
        for instructor in offering.instructors():
            # Get flags for instructor that were active during this offering's semester
            flags = _get_visible_flags(viewer, offering, instructor)

            # Only show offering if there's a flag match
            matched_flags = _matched_flags(operator, selected_flags, flags)
            if matched_flags is not None:
                yield offering, instructor, matched_flags


@requires_role('ADMN')
def course_accreditation(request):
    viewer = get_object_or_404(Person, userid=request.user.username)
    units = Unit.sub_units(request.units)
    courses = defaultdict(list)

    # Gather all visible accreditation flags for viewer from all units
    ecs = EventConfig.objects.filter(unit__in=units,
                                     event_type=AccreditationFlagEventHandler.EVENT_TYPE)
    flag_choices = Choices(*itertools.chain(*[ec.config.get('flags', []) for ec in ecs]))

    form = CourseAccreditationForm(request.GET, flags=flag_choices)

    if form.is_valid():
        start_code = form.cleaned_data.get('start_semester')
        end_code = form.cleaned_data.get('end_semester')
        operator = form.cleaned_data.get('operator')
        selected_flags = set(form.cleaned_data.get('flag'))

        # Since CourseOfferings require actual Semesters, ignore any semesters in the
        # input range that do not "exist".
        semester_codes = [semester.code
                          for semester in ReportingSemester.range(start_code, end_code)]
        semesters = Semester.objects.filter(name__in=semester_codes)

        # Group offerings by course
        found = _course_accreditation_data(viewer, units, semesters, operator, selected_flags)
        for offering, instructor, matched_flags in found:
            presentation_flags = ((flag, flag_choices[flag]) for flag in matched_flags)
            courses[offering.course.full_name()].append((offering,
                                                         instructor,
                                                         presentation_flags))

    context = {
        'courses': dict(courses),
        'form': form,
        'filterform': UnitFilterForm(Unit.sub_units(request.units)),
    }
    return render(request, 'faculty/reports/course_accreditation.html', context)


@requires_role('ADMN')
def course_accreditation_csv(request):
    viewer = get_object_or_404(Person, userid=request.user.username)
    units = Unit.sub_units(request.units)

    # Gather all visible accreditation flags for viewer from all units
    ecs = EventConfig.objects.filter(unit__in=units,
                                     event_type=AccreditationFlagEventHandler.EVENT_TYPE)
    flag_choices = Choices(*itertools.chain(*[ec.config.get('flags', []) for ec in ecs]))

    form = CourseAccreditationForm(request.GET, flags=flag_choices)

    if form.is_valid():
        start_code = form.cleaned_data.get('start_semester')
        end_code = form.cleaned_data.get('end_semester')
        operator = form.cleaned_data.get('operator')
        selected_flags = set(form.cleaned_data.get('flag'))

        # Since CourseOfferings require actual Semesters, ignore any semesters in the
        # input range that do not "exist".
        semester_codes = [semester.code
                          for semester in ReportingSemester.range(start_code, end_code)]
        semesters = Semester.objects.filter(name__in=semester_codes)

        # Set up for CSV shenanigans
        filename = 'course_accreditation_{}-{}.csv'.format(start_code, end_code)
        csv, response = make_csv_writer_response(filename)
        csv.writerow([
            'unit',
            'semester',
            'course',
            'course title',
            'instructor',
            'flags',
        ])

        found = _course_accreditation_data(viewer, units, semesters, operator, selected_flags)
        for offering, instructor, matched_flags in found:
            csv.writerow([
                offering.owner.label,
                offering.semester.name,
                offering.name(),
                offering.title,
                instructor.name(),
                ','.join(matched_flags),
            ])

        return response

    return HttpResponseBadRequest(form.errors)


###############################################################################
# Display/summary views for a faculty member

@requires_role('ADMN')
def summary(request, userid):
    """
    Summary page for a faculty member.
    """
    person, _ = _get_faculty_or_404(request.units, userid)
    editor = get_object_or_404(Person, userid=request.user.username)
    career_events = CareerEvent.objects.not_deleted().only_subunits(request.units).filter(person=person)
    filterform = EventFilterForm()

    context = {
        'person': person,
        'editor': editor,
        'career_events': career_events,
        'filterform': filterform,
    }
    return render(request, 'faculty/summary.html', context)


@requires_role('ADMN')
def teaching_summary(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    form = TeachingSummaryForm()

    credit_balance = 0
    start_label = end_label = ''
    events = []

    if request.GET:
        form = TeachingSummaryForm(request.GET)

        if form.is_valid():
            start = form.cleaned_data['start_semester']
            end = form.cleaned_data['end_semester']
            start_semester = ReportingSemester(start)
            end_semester = ReportingSemester(end)
            start_label = start_semester.full_label
            end_label = end_semester.full_label

            curr_semester = start_semester
            while curr_semester <= end_semester:
                cb, event = _teaching_events_data(person, curr_semester)
                credit_balance += cb
                events += event

                curr_semester = curr_semester.next()

    else:
        start_semester = end_semester = ReportingSemester(datetime.date.today())
        start = end = start_semester.code
        start_label = end_label = start_semester.full_label
        initial = { 'start_semester': start,
                    'end_semester': end }
        form = TeachingSummaryForm(initial=initial)
        credit_balance, events = _teaching_events_data(person, start_semester)

    cb_mmixed = fraction_display(credit_balance)
    context = {
        'form': form,
        'start_label': start_label,
        'end_label': end_label,
        'person': person,
        'credit_balance': cb_mmixed,
        'events': events,
    }
    return render(request, 'faculty/reports/teaching_summary.html', context)

def _teaching_events_data(person, semester):
    cb = 0
    e = []
    courses = Member.objects.filter(role='INST', person=person, added_reason='AUTO', offering__semester__name=semester.code) \
        .exclude(offering__component='CAN').exclude(offering__flags=CourseOffering.flags.combined) \
        .select_related('offering', 'offering__semester')
    for course in courses:
        credits, reason = course.teaching_credit_with_reason()
        e += [(semester.code, course, course.offering.title, credits, reason, '')]
        cb += course.teaching_credit()

    # TODO: should filter only user-visible events
    teaching_events = FacultySummary(person).teaching_events(semester)
    for event in teaching_events:
        credits, load_decrease = FacultySummary(person).teaching_event_info(event)
        if load_decrease:
            e += [(semester.code, event.get_event_type_display(), event.get_handler().short_summary(), load_decrease, '', event)]
        if credits:
            e += [(semester.code, event.get_event_type_display(), event.get_handler().short_summary(), credits, '', event)]
        cb += credits + load_decrease

    return cb, e


@requires_role('ADMN')
def teaching_summary_csv(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    events = []

    if request.GET:
        form = TeachingSummaryForm(request.GET)

        if form.is_valid():
            start = form.cleaned_data['start_semester']
            end = form.cleaned_data['end_semester']
            start_semester = ReportingSemester(start)
            end_semester = ReportingSemester(end)

            curr_semester = start_semester
            while curr_semester <= end_semester:
                cb, event = _teaching_events_data(person, curr_semester)
                events += event
                curr_semester = curr_semester.next()

    else:
        start_semester = end_semester = ReportingSemester(datetime.date.today())
        start = end = start_semester.code
        cb, events = _teaching_events_data(person, start_semester)

    filename = 'teaching_summary_{}-{}.csv'.format(start, end)
    csv, response = make_csv_writer_response(filename)
    csv.writerow([
        'Semester',
        'Course/Event',
        'Credits/Load Effect',
        'Credit Reason',
    ])

    for semester, course, summary, credits, reason, event in events:
        if event:
            csv.writerow([
                semester,
                event.get_handler().short_summary(),
                _csvfrac(credits),
            ])
        else:
            csv.writerow([
                semester,
                course.offering.name(),
                _csvfrac(credits),
                reason,
            ])

    return response


@requires_role('ADMN')
def study_leave_credits(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    form = TeachingSummaryForm()
    slc_total = 0
    start_label = end_label = ''
    events = []
    end_semester = ReportingSemester(datetime.date.today())
    start_semester = end_semester.prev()
    finish_semester = end_semester

    if request.GET:
        form = TeachingSummaryForm(request.GET)

        if form.is_valid():
            start = form.cleaned_data['start_semester']
            end = form.cleaned_data['end_semester']
            start_semester = ReportingSemester(start)
            end_semester = ReportingSemester(end)
            start_label = start_semester.full_label
            end_label = end_semester.full_label

            slc_total, events, finish_semester = _all_study_events(person, start_semester, end_semester)

    else:
        start = start_semester.code
        end = end_semester.code
        start_label = start_semester.full_label
        end_label = end_semester.full_label
        initial = { 'start_semester': start,
                    'end_semester': end }
        form = TeachingSummaryForm(initial=initial)

        slc_total, events, finish_semester = _all_study_events(person, start_semester, end_semester)

    context = {
        'form': form,
        'start_label': start_label,
        'end_label': end_label,
        'person': person,
        'study_credits': fraction_display(slc_total),
        'events': events,
        'finish_semester': finish_semester.full_label,
    }
    return render(request, 'faculty/reports/study_leave_credits.html', context)


def _csvfrac(f):
    return "%.3f" % (f)

def _study_credit_events_data(person, semester, show_in_table, running_total):
    # Study credit events for one semester
    slc = 0
    e = []
    courses = Member.objects.filter(role='INST', person=person, added_reason='AUTO', offering__semester__name=semester.code) \
        .exclude(offering__component='CAN').exclude(offering__flags=CourseOffering.flags.combined) \
        .select_related('offering', 'offering__semester')
    for course in courses:
        tc = course.teaching_credit()
        running_total += tc
        if show_in_table and tc:
            e += [(semester.code, course.offering.name(), _csvfrac(tc), _csvfrac(tc), _csvfrac(running_total))]

    # TODO: should filter only user-visible events
    teaching_events = FacultySummary(person).teaching_events(semester)
    for event in teaching_events:
        # only want to account for the study leave event once
        if event.event_type == 'STUDYLEAVE':
            handler = event.get_handler()
            if ReportingSemester.start_and_end_dates(semester.code)[0] <= event.start_date:
                slc = handler.get_study_leave_credits()
                running_total -= slc
                if show_in_table:
                    e += [(semester.code, 'Begin Study Leave', '', _csvfrac(-slc) , _csvfrac(running_total))]
            if event.end_date and ReportingSemester.start_and_end_dates(semester.code)[1] >= event.end_date:
                tot = handler.get_credits_carried_forward()
                if tot != None:
                    running_total = tot
                if show_in_table:
                    e += [(semester.code, 'End Study Leave', '', '' , _csvfrac(running_total))]
        else:
            credits, load_decrease = FacultySummary(person).teaching_event_info(event)
            running_total += credits
            if show_in_table and credits:
                    e += [(semester.code, event.get_event_type_display(), _csvfrac(credits), _csvfrac(credits), _csvfrac(running_total))]


    return e, running_total

def _all_study_events(person, start_semester, end_semester):
    # Constructs table of study credits events for a range of semesters
    slc_total = 0
    events = []
    finish_semester = ReportingSemester(max(end_semester.code, ReportingSemester(datetime.date.today()).code)) # in case we want to look into future semesters
    curr_semester = ReportingSemester('0651')
    while curr_semester <= finish_semester:
        if curr_semester >= start_semester and curr_semester <= end_semester:
            event, slc_total = _study_credit_events_data(person, curr_semester, True, slc_total)
        else:
            event, slc_total = _study_credit_events_data(person, curr_semester, False, slc_total)

        if curr_semester == start_semester.prev():
            events += [('', 'Study Leave Credits prior to '+start_semester.code, '', _csvfrac(slc_total) , _csvfrac(slc_total))]

        events += event
        curr_semester = curr_semester.next()

    return slc_total, events, finish_semester


@requires_role('ADMN')
def study_leave_credits_csv(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    events = []
    end_semester = ReportingSemester(datetime.date.today())
    start_semester = end_semester.prev()

    if request.GET:
        form = TeachingSummaryForm(request.GET)

        if form.is_valid():
            start = form.cleaned_data['start_semester']
            end = form.cleaned_data['end_semester']
            start_semester = ReportingSemester(start)
            end_semester = ReportingSemester(end)

            events = _all_study_events(person, start_semester, end_semester)[1]

    else:
        start = start_semester.code
        end = end_semester.code

        events = _all_study_events(person, start_semester, end_semester)[1]

    filename = 'study_credit_report_{}-{}.csv'.format(start, end)
    csv, response = make_csv_writer_response(filename)
    csv.writerow([
        'Semester',
        'Course/Event Type',
        'Teaching Credits',
        'Study Leave Credits',
        'Running Total',
    ])

    for semester, course, tc, slc, slc_tot in events:
        csv.writerow([
            semester,
            course,
            tc,
            slc,
            slc_tot,
        ])

    return response


@requires_role('ADMN')
def otherinfo(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    # TODO: should some or all of these be limited by request.units?

    # collect teaching history
    instructed = Member.objects.filter(role='INST', person=person, added_reason='AUTO') \
            .exclude(offering__component='CAN').exclude(offering__flags=CourseOffering.flags.combined) \
            .select_related('offering', 'offering__semester')

    # collect grad students
    supervised = Supervisor.objects.filter(supervisor=person, supervisor_type__in=['SEN','COS','COM'], removed=False) \
            .select_related('student', 'student__person', 'student__program', 'student__start_semester', 'student__end_semester')


    # RA appointments supervised
    ras = RAAppointment.objects.filter(deleted=False, hiring_faculty=person) \
            .select_related('person', 'project', 'account')

    context = {
        'person': person,
        'instructed': instructed,
        'supervised': supervised,
        'ras': ras,
    }
    return render(request, 'faculty/otherinfo.html', context)


@requires_role('ADMN')
def view_event(request, userid, event_slug):
    """
    Change existing career event for a faculty member.
    """
    person, member_units = _get_faculty_or_404(request.units, userid)
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    editor = get_object_or_404(Person, userid=request.user.username)
    memos = Memo.objects.filter(career_event=instance)
    templates = MemoTemplate.objects.filter(unit__in=Unit.sub_units(request.units), event_type=instance.event_type, hidden=False)

    handler = instance.get_handler()

    if not handler.can_view(editor):
        raise PermissionDenied("'%s' not allowed to view this event" % editor)

    # TODO: can editors change the status of events to something else?
    # TODO: For now just assuming editor who is allowed to approve event is also allowed to
    # delete event, in essence change the status of the event to anything they want.
    approval = None
    if handler.can_approve(editor):
        approval = ApprovalForm(instance=instance)

    context = {
        'person': person,
        'editor': editor,
        'handler': handler,
        'event': instance,
        'memos': memos,
        'templates': templates,
        'approval_form': approval,
    }
    return render(request, 'faculty/view_event.html', context)


@requires_role('ADMN')
def timeline(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    return render(request, 'faculty/reports/timeline.html', {'person': person})


@requires_role('ADMN')
def timeline_json(request, userid):
    person, _ = _get_faculty_or_404(request.units, userid)
    viewer = get_object_or_404(Person, userid=request.user.username)

    payload = {
        'timeline': {
            'type': 'default',
            'startDate': '{:%Y,%m,%d}'.format(datetime.date.today()),
            'date': [],
            'era': [],
        },
    }
    semesters = set()

    # Populate events
    events = (CareerEvent.objects.not_deleted()
                         .only_subunits(request.units)
                         .filter(person=person, status='A')
                         .exclude(event_type=SalaryBaseEventHandler.EVENT_TYPE))
    for event in events:
        handler = event.get_handler()

        if handler.can_view(viewer):
            blurb = {
                'startDate': '{:%Y,%m,%d}'.format(handler.event.start_date),
                'headline': handler.short_summary(),
                'text': u'<a href="{}">more information</a>'.format(handler.event.get_absolute_url()),
            }

            if handler.event.end_date is not None:
                payload['endDate'] = '{:%Y,%m,%d}'.format(handler.event.end_date)

            payload['timeline']['date'].append(blurb)

            # Show all semesters that the event covers, if possible.
            if event.end_date is not None:
                for semester in ReportingSemester.range(event.start_date, event.end_date):
                    semesters.add(semester)
            else:
                semesters.add(ReportingSemester(event.start_date))

    # Populate semesters
    for semester in semesters:
        payload['timeline']['era'].append({
            'startDate': '{:%Y,%m,%d}'.format(semester.start_date),
            'endDate': '{:%Y,%m,%d}'.format(semester.end_date),
            'headline': semester.short_label,
        })

    return HttpResponse(json.dumps(payload), mimetype='application/json')


@requires_role('ADMN')
def faculty_member_info(request, userid):
    #viewer = get_object_or_404(Person, userid=request.user.username)
    person, _ = _get_faculty_or_404(request.units, userid)
    info = FacultyMemberInfo.objects.filter(person=person).first()

    # TODO: are there people who should be able to only view?
    can_modify = True
    can_view_emergency = True

    context = {
        'person': person,
        'info': info,
        'can_modify': can_modify,
        'can_view_emergency': can_view_emergency,
    }
    return render(request, 'faculty/faculty_member_info.html', context)


@requires_role('ADMN')
def edit_faculty_member_info(request, userid):
    #viewer = get_object_or_404(Person, userid=request.user.username)
    person, _ = _get_faculty_or_404(request.units, userid)

    info = (FacultyMemberInfo.objects.filter(person=person).first()
            or FacultyMemberInfo(person=person))

    if request.POST:
        form = FacultyMemberInfoForm(request.POST, instance=info)

        if form.is_valid():
            new_info = form.save()
            person.set_title(new_info.title)
            person.save()
            messages.success(request, 'Contact information was saved successfully.')
            return HttpResponseRedirect(new_info.get_absolute_url())
    else:
        form = FacultyMemberInfoForm(instance=info)

    context = {
        'person': person,
        'form': form,
    }
    return render(request, 'faculty/edit_faculty_member_info.html', context)


@requires_role('ADMN')
def teaching_credit_override(request, userid, course_slug):
    person, _ = _get_faculty_or_404(request.units, userid)
    course = get_object_or_404(Member, person=person, offering__slug=course_slug)

    context = {
        'person': person,
        'course':course,
        'course_slug': course_slug,
    }

    if request.POST:
        form = TeachingCreditOverrideForm(request.POST)
        if form.is_valid():
            course.set_teaching_credit(form.cleaned_data['teaching_credits'])
            course.set_teaching_credit_reason(form.cleaned_data['reason'])
            course.save()
            return HttpResponseRedirect(reverse(teaching_summary, kwargs={'userid':userid}))

        else:
            context.update({'form': form})
            return render(request, 'faculty/override_teaching_credit.html', context)

    else:
        credits, reason = course.teaching_credit_with_reason()
        initial = { 'teaching_credits': credits,
                    'reason': reason }
        form = TeachingCreditOverrideForm(initial=initial)
        context.update({'form': form})
        return render(request, 'faculty/override_teaching_credit.html', context)


###############################################################################
# Creation and editing of CareerEvents

@requires_role('ADMN')
def event_type_list(request, userid):
    types = _get_event_types()
    person, _ = _get_faculty_or_404(request.units, userid)
    editor = get_object_or_404(Person, userid=request.user.username)
    context = {
        'event_types': types,
        'person': person,
        'editor': editor,
    }
    return render(request, 'faculty/event_type_list.html', context)


@requires_role('ADMN')
@transaction.atomic
def create_event(request, userid, event_type):
    """
    Create new career event for a faculty member.
    """
    person, member_units = _get_faculty_or_404(request.units, userid)
    editor = get_object_or_404(Person, userid=request.user.username)

    Handler = _get_Handler_or_404(event_type.upper())

    tmp = Handler.create_for(person)
    if not tmp.can_edit(editor):
        raise PermissionDenied("'%s' not allowed to create this event" %(event_type))

    context = {
        'person': person,
        'editor': editor,
        'handler': Handler,
        'name': Handler.NAME,
        'event_type': Handler.EVENT_TYPE
    }

    if request.method == "POST":
        form = Handler.get_entry_form(editor=editor, units=member_units, data=request.POST)
        if form.is_valid():
            handler = Handler.create_for(person=person, form=form)
            handler.save(editor)
            handler.set_status(editor)
            return HttpResponseRedirect(handler.event.get_absolute_url())
        else:
            context.update({"event_form": form})
    else:
        # Display new blank form
        form = Handler.get_entry_form(editor=editor, person=person, units=member_units)
        context.update({"event_form": form})

    return render(request, 'faculty/career_event_form.html', context)


@requires_role('ADMN')
@transaction.atomic
def change_event(request, userid, event_slug):
    """
    Change existing career event for a faculty member.
    """
    person, member_units = _get_faculty_or_404(request.units, userid)
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    editor = get_object_or_404(Person, userid=request.user.username)

    Handler = _get_Handler_or_404(instance.event_type)
    handler = Handler(instance)

    context = {
        'person': person,
        'editor': editor,
        'event': instance,
        'event_type': Handler.EVENT_TYPE,
    }
    if not handler.can_edit(editor):
        return HttpResponseForbidden(request, "'%s' not allowed to edit this event" % editor)
    if request.method == "POST":
        form = Handler.get_entry_form(editor, member_units, handler=handler, data=request.POST)
        if form.is_valid():
            handler.load(form)
            handler.save(editor)
            context.update({"event": handler.event,
                            "event_form": form})
            return HttpResponseRedirect(handler.event.get_absolute_url())
        else:
            context.update({"event_form": form})

    else:
        # Display form from db instance
        form = Handler.get_entry_form(editor, member_units, handler=handler)
        context.update({"event_form": form})

    return render(request, 'faculty/career_event_form.html', context)


@require_POST
@requires_role('ADMN')
def change_event_status(request, userid, event_slug):
    """
    Change status of event, if the editor has such privileges.
    """
    person, member_units = _get_faculty_or_404(request.units, userid)
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    editor = get_object_or_404(Person, userid=request.user.username)

    handler = instance.get_handler()
    if not handler.can_approve(editor):
        raise PermissionDenied("You cannot change status of this event")
    form = ApprovalForm(request.POST, instance=instance)
    if form.is_valid():
        event = form.save(commit=False)
        event.save(editor)
        return HttpResponseRedirect(event.get_absolute_url())

@requires_role('ADMN')
def faculty_wizard(request, userid):
    """
    Initial wizard for a user, set up basic events (appointment, base salary, normal teaching load).
    """
    person, member_units = _get_faculty_or_404(request.units, userid)
    editor = get_object_or_404(Person, userid=request.user.username)

    Handler_appoint = _get_Handler_or_404('APPOINT')
    Handler_salary = _get_Handler_or_404('SALARY')
    Handler_load = _get_Handler_or_404('NORM_TEACH')

    tmp1 = Handler_appoint.create_for(person)
    if not tmp1.can_edit(editor):
        raise PermissionDenied("not allowed to create events")

    context = {
        'person': person,
        'editor': editor,
        'handler': Handler_appoint,
        'name': Handler_appoint.NAME,
    }

    if request.method == "POST":
        form_appoint = Handler_appoint.get_entry_form(editor=editor, units=member_units, data=request.POST, prefix='appoint')
        form_salary = Handler_salary.get_entry_form(editor=editor, units=member_units, data=request.POST, prefix='salary')
        form_load = Handler_load.get_entry_form(editor=editor, units=member_units, data=request.POST, prefix='load')

        # Nuke unwanted fields
        del form_appoint.fields['end_date'], form_salary.fields['end_date'], form_load.fields['end_date']
        del form_salary.fields['start_date'], form_load.fields['start_date']
        del form_salary.fields['unit'], form_load.fields['unit']
        del form_appoint.fields['leaving_reason']

        if form_appoint.is_valid() and form_salary.is_valid() and form_load.is_valid():
            handler_appoint = Handler_appoint.create_for(person=person, form=form_appoint)
            handler_appoint.save(editor)
            handler_appoint.set_status(editor)

            handler_salary = Handler_salary.create_for(person=person, form=form_salary)
            handler_salary.event.start_date = handler_appoint.event.start_date
            handler_salary.event.unit = handler_appoint.event.unit
            handler_salary.save(editor)
            handler_salary.set_status(editor)

            handler_load = Handler_load.create_for(person=person, form=form_load)
            handler_load.event.start_date = handler_appoint.event.start_date
            handler_load.event.unit = handler_appoint.event.unit
            handler_load.save(editor)
            handler_load.set_status(editor)
            return HttpResponseRedirect(reverse(summary, kwargs={'userid':userid}))
        else:
            form_list = [form_appoint, form_salary, form_load]
            context.update({"event_form": form_list})
    else:
        # Display new blank form
        form_appoint = Handler_appoint.get_entry_form(editor=editor, units=member_units, prefix='appoint')
        form_salary = Handler_salary.get_entry_form(editor=editor, units=member_units, prefix='salary')
        form_load = Handler_load.get_entry_form(editor=editor, units=member_units, prefix='load')

        # Nuke unwanted fields
        del form_appoint.fields['end_date'], form_salary.fields['end_date'], form_load.fields['end_date']
        del form_salary.fields['start_date'], form_load.fields['start_date']
        del form_salary.fields['unit'], form_load.fields['unit']
        del form_appoint.fields['leaving_reason']

        form_list = [form_appoint, form_salary, form_load]
        context.update({"event_form": form_list})

    return render(request, 'faculty/faculty_wizard.html', context)


###############################################################################
# Management of DocumentAttachments and Memos
@requires_role('ADMN')
def new_attachment(request, userid, event_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    event = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    editor = get_object_or_404(Person, userid=request.user.username)

    form = AttachmentForm()
    context = {"event": event,
               "person": person,
               "attachment_form": form}

    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.career_event = event
            attachment.created_by = editor
            upfile = request.FILES['contents']
            filetype = upfile.content_type
            if upfile.charset:
                filetype += "; charset=" + upfile.charset
            attachment.mediatype = filetype
            attachment.save()
            return HttpResponseRedirect(event.get_absolute_url())
        else:
            context.update({"attachment_form": form})

    return render(request, 'faculty/document_attachment_form.html', context)


@requires_role('ADMN')
def view_attachment(request, userid, event_slug, attach_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    event = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    viewer = get_object_or_404(Person, userid=request.user.username)

    attachment = get_object_or_404(event.attachments.all(), slug=attach_slug)

    handler = event.get_handler()
    if not handler.can_view(viewer):
       raise PermissionDenied(" Not allowed to view this attachment")

    filename = attachment.contents.name.rsplit('/')[-1]
    resp = StreamingHttpResponse(attachment.contents.chunks(), content_type=attachment.mediatype)
    resp['Content-Disposition'] = 'inline; filename="' + filename + '"'
    resp['Content-Length'] = attachment.contents.size
    return resp

@requires_role('ADMN')
def download_attachment(request, userid, event_slug, attach_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    event = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    viewer = get_object_or_404(Person, userid=request.user.username)

    attachment = get_object_or_404(event.attachments.all(), slug=attach_slug)

    handler = event.get_handler()
    if not handler.can_view(viewer):
        raise PermissionDenied("aNot allowed to download this attachment")

    filename = attachment.contents.name.rsplit('/')[-1]
    resp = StreamingHttpResponse(attachment.contents.chunks(), content_type=attachment.mediatype)
    resp['Content-Disposition'] = 'attachment; filename="' + filename + '"'
    resp['Content-Length'] = attachment.contents.size
    return resp


###############################################################################
# Creating and editing Memo Templates

@requires_role('ADMN')
def manage_event_index(request):
    types = [
        {'slug': key.lower(), 'name': Handler.NAME, 'is_instant': Handler.IS_INSTANT,
         'affects_teaching': 'affects_teaching' in Handler.FLAGS,
         'affects_salary': 'affects_salary' in Handler.FLAGS}
        for key, Handler in EVENT_TYPE_CHOICES]

    context = {
               'events': types,
               }
    return render(request, 'faculty/manage_events_index.html', context)

@requires_role('ADMN')
def memo_templates(request, event_type):
    templates = MemoTemplate.objects.filter(unit__in=Unit.sub_units(request.units), event_type=event_type.upper(), hidden=False)
    event_type_object = next((key, Hanlder) for (key, Hanlder) in EVENT_TYPE_CHOICES if key.lower() == event_type)

    if event_type == "fellow":
        ecs = EventConfig.objects.filter(event_type=FellowshipEventHandler.EVENT_TYPE, unit__in=Unit.sub_units(request.units))
    else: 
        ecs = None

    context = {
               'templates': templates,
               'event_type_slug':event_type,
               'event_name': event_type_object[1].NAME,
               'flags': ecs,
               }
    return render(request, 'faculty/memo_templates.html', context)

@requires_role('ADMN')
def new_event_flag(request, event_type):
    unit_choices = [(u.id, u.name) for u in Unit.sub_units(request.units)]
    in_unit = list(request.units)[0] # pick a unit this user is in as the default owner
    event_type_object = next((key, Handler) for (key, Handler) in EVENT_TYPE_CHOICES if key.lower() == event_type)

    if request.method == 'POST':
        form = EventFlagForm(request.POST)
        form.fields['unit'].choices = unit_choices
        if form.is_valid():
            unit_obj = Unit.objects.get(id=request.POST.get("unit"))
            ec, _ = EventConfig.objects.get_or_create(unit=unit_obj, event_type='FELLOW')
            if 'fellowships' in ec.config:
                ec.config['fellowships'] = ec.config['fellowships'] + [(request.POST.get("flag_short"), request.POST.get("flag"), 'ACTIVE')]
            else:
                ec.config = {'fellowships': [(request.POST.get("flag_short"), request.POST.get("flag"), 'ACTIVE')]}
            ec.save()
            return HttpResponseRedirect(reverse(memo_templates, kwargs={'event_type':event_type}))       
    else:
        form = EventFlagForm(initial={'unit': in_unit})
        form.fields['unit'].choices = unit_choices

    context = {
               'form': form,
               'event_type_slug': event_type,
               'event_name': event_type_object[1].NAME
               }
    return render(request, 'faculty/event_flag.html', context)

@requires_role('ADMN')
def delete_event_flag(request, event_type, unit, flag):
    unit_obj = Unit.objects.get(label=unit)
    ec, _ = EventConfig.objects.get_or_create(unit=unit_obj, event_type='FELLOW')
    list_flags = ec.config['fellowships']
    for i, (flag_short, flag_long, status) in enumerate(list_flags):
        if flag_short == flag:
            list_flags[i] = (flag_short, flag_long, 'DELETED')
            break
    ec.config['fellowships'] = list_flags
    ec.save()

    return HttpResponseRedirect(reverse(memo_templates, kwargs={'event_type':event_type})) 

@requires_role('ADMN')
def new_memo_template(request, event_type):
    person = get_object_or_404(Person, find_userid_or_emplid(request.user.username))
    unit_choices = [(u.id, u.name) for u in Unit.sub_units(request.units)]
    in_unit = list(request.units)[0] # pick a unit this user is in as the default owner
    event_type_object = next((key, Handler) for (key, Handler) in EVENT_TYPE_CHOICES if key.lower() == event_type)

    if request.method == 'POST':
        form = MemoTemplateForm(request.POST)
        form.fields['unit'].choices = unit_choices
        if form.is_valid():
            f = form.save(commit=False)
            f.created_by = person
            f.event_type = event_type.upper()
            f.save()
            messages.success(request, "Created memo template %s for %s." % (form.instance.label, form.instance.unit))
            return HttpResponseRedirect(reverse(memo_templates, kwargs={'event_type':event_type}))
    else:
        form = MemoTemplateForm(initial={'unit': in_unit})
        form.fields['unit'].choices = unit_choices

    tags = sorted(EVENT_TAGS.iteritems())
    event_handler = event_type_object[1].CONFIG_FIELDS
    #get additional tags for specific event
    add_tags = {}
    for tag in event_handler:
        try:
            add_tags[tag] = ADD_TAGS[tag]
        except KeyError:
            add_tags[tag] = tag.replace("_", " ")

    add = sorted(add_tags.iteritems())
    lt = tags + add

    context = {
               'form': form,
               'event_type_slug': event_type,
               'EVENT_TAGS': lt,
               'event_name': event_type_object[1].NAME
               }
    return render(request, 'faculty/memo_template_form.html', context)

@requires_role('ADMN')
def manage_memo_template(request, event_type, slug):
    person = get_object_or_404(Person, find_userid_or_emplid(request.user.username))
    unit_choices = [(u.id, u.name) for u in Unit.sub_units(request.units)]
    memo_template = get_object_or_404(MemoTemplate, slug=slug)
    event_type_object = next((key, Hanlder) for (key, Hanlder) in EVENT_TYPE_CHOICES if key.lower() == event_type)

    if request.method == 'POST':
        form = MemoTemplateForm(request.POST, instance=memo_template)
        if form.is_valid():
            f = form.save(commit=False)
            f.created_by = person
            f.event_type = event_type.upper()
            f.save()
            messages.success(request, "Updated %s template for %s." % (form.instance.label, form.instance.unit))
            return HttpResponseRedirect(reverse(memo_templates, kwargs={'event_type':event_type}))
    else:
        form = MemoTemplateForm(instance=memo_template)
        form.fields['unit'].choices = unit_choices

    tags = sorted(EVENT_TAGS.iteritems())
    event_handler = event_type_object[1].CONFIG_FIELDS
    #get additional tags for specific event
    add_tags = {}
    for tag in event_handler:
        try:
            add_tags[tag] = ADD_TAGS[tag]
        except KeyError:
            add_tags[tag] = tag.replace("_", " ")

    add = sorted(add_tags.iteritems())
    lt = tags + add

    context = {
               'form': form,
               'memo_template': memo_template,
               'event_type_slug':event_type,
               'EVENT_TAGS': lt,
               'event_name': event_type_object[1].NAME
               }
    return render(request, 'faculty/memo_template_form.html', context)

###############################################################################
# Creating and editing Memos

@requires_role('ADMN')
def new_memo(request, userid, event_slug, memo_template_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    template = get_object_or_404(MemoTemplate, slug=memo_template_slug, unit__in=Unit.sub_units(request.units))
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    author = get_object_or_404(Person, find_userid_or_emplid(request.user.username))

    ls = instance.memo_info()

    if request.method == 'POST':
        form = MemoForm(request.POST)
        if form.is_valid():
            f = form.save(commit=False)
            f.created_by = author
            f.career_event = instance
            f.unit = template.unit
            f.config.update(ls)
            f.template = template;
            f.save()
            messages.success(request, "Created new %s memo." % (form.instance.template.label,))
            return HttpResponseRedirect(reverse(view_event, kwargs={'userid':userid, 'event_slug':event_slug}))
    else:
        initial = {
            'date': datetime.date.today(),
            'subject': '%s %s\n%s ' % (person.get_title(), person.name(), template.subject),
            'to_lines': person.letter_name()
        }
        form = MemoForm(initial=initial)

    context = {
               'form': form,
               'template' : template,
               'person': person,
               'event': instance,
               }
    return render(request, 'faculty/new_memo.html', context)

@requires_role('ADMN')
def manage_memo(request, userid, event_slug, memo_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    memo = get_object_or_404(Memo, slug=memo_slug, career_event=instance)

    handler = instance.get_handler()
    if not handler.can_view(person):
        return HttpResponseForbidden(request, "Not allowed to view this memo")

    if request.method == 'POST':
        form = MemoForm(request.POST, instance=memo)
        if form.is_valid():
            f = form.save(commit=False)
            f.career_event = instance
            f.save()
            messages.success(request, "Updated memo.")
            return HttpResponseRedirect(reverse(view_event, kwargs={'userid':userid, 'event_slug':event_slug}))
    else:
        form = MemoForm(instance=memo)

    context = {
               'form': form,
               'person': person,
               'event': instance,
               'memo': memo,
               }
    return render(request, 'faculty/manage_memo.html', context)

@requires_role('ADMN')
def get_memo_text(request, userid, event_slug, memo_template_id):
    """ Get the text from memo template """
    person, member_units = _get_faculty_or_404(request.units, userid)
    event = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    lt = get_object_or_404(MemoTemplate, id=memo_template_id, unit__in=Unit.sub_units(request.units))
    temp = Template(lt.template_text)
    ls = event.memo_info()
    text = temp.render(Context(ls))

    return HttpResponse(text, content_type='text/plain')

@requires_role('ADMN')
def get_memo_pdf(request, userid, event_slug, memo_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    memo = get_object_or_404(Memo, slug=memo_slug, career_event=instance)

    handler = instance.get_handler()
    if not handler.can_view(person):
        raise PermissionDenied("Not allowed to view this memo")

    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = 'inline; filename="%s.pdf"' % (memo_slug)

    memo.write_pdf(response)
    return response

@requires_role('ADMN')
def view_memo(request, userid, event_slug, memo_slug):
    person, member_units = _get_faculty_or_404(request.units, userid)
    instance = _get_event_or_404(units=request.units, slug=event_slug, person=person)
    memo = get_object_or_404(Memo, slug=memo_slug, career_event=instance)

    handler = instance.get_handler()
    if not handler.can_view(person):
        raise PermissionDenied("Not allowed to view this memo")

    context = {
               'memo': memo,
               'event': instance,
               'person': person,
               }
    return render(request, 'faculty/view_memo.html', context)


###############################################################################
# Creating and editing Grants

@requires_role('ADMN')
def grant_index(request):
    editor = get_object_or_404(Person, userid=request.user.username)
    temp_grants = TempGrant.objects.filter(creator=editor)
    grants = _get_grants(request.units)
    import_form = GrantImportForm()
    context = {
        "grants": grants,
        "editor": editor,
        "temp_grants": temp_grants,
        "import_form": import_form,
    }
    return render(request, "faculty/grant_index.html", context)

@require_POST
@requires_role('ADMN')
def import_grants(request):
    editor = get_object_or_404(Person, userid=request.user.username)
    form = GrantImportForm(request.POST, request.FILES)
    if form.is_valid():
        csvfile = form.cleaned_data["file"]
        created, failed = TempGrant.objects.create_from_csv(csvfile, editor)
        if failed:
            messages.error(request, "Created %d grants, %d failed" % (len(created), len(failed)))
        else:
            messages.info(request, "Created %d grants" % (len(created)))
    return HttpResponseRedirect(reverse("grants_index"))


@transaction.atomic
@requires_role('ADMN')
def convert_grant(request, gid):
    tmp = get_object_or_404(TempGrant, id=gid)
    editor = get_object_or_404(Person, userid=request.user.username)
    sub_unit_ids = Unit.sub_unit_ids(request.units)
    units = Unit.objects.filter(id__in=sub_unit_ids)
    form = GrantForm(units, initial=tmp.grant_dict())
    context = {
        "temp_grant": tmp,
        "grant_form": form,
        "editor": editor,
    }
    if request.method == "POST":
        form = GrantForm(units, request.POST)
        if form.is_valid():
            grant = form.save(commit=False)
            grant.label = tmp.label
            grant.project_code = tmp.project_code
            grant.save()
            GrantOwner.objects.filter(grant=grant).delete()
            for p in form.cleaned_data['owners']:
                GrantOwner(grant=grant, person=p).save()

            try:
                balance = Decimal(tmp.config["cur_balance"])
                this_month = Decimal(tmp.config["cur_month"])
                ytd_actual = Decimal(tmp.config["ytd_actual"])
                gb = grant.update_balance(balance, this_month, ytd_actual)
            except (KeyError, InvalidOperation):
                pass
            else:
                # Delete the temporary grant
                tmp.delete()
                return HttpResponseRedirect(reverse("grants_index"))
        else:
            context.update({"grant_form": form})
    return render(request, "faculty/convert_grant.html", context)


@requires_role('ADMN')
def delete_grant(request, gid):
    tmp = get_object_or_404(TempGrant, id=gid)
    tmp.delete()
    return HttpResponseRedirect(reverse("grants_index"))


#@requires_role('ADMN')
#def new_grant(request):
#    editor = get_object_or_404(Person, userid=request.user.username)
#    sub_unit_ids = Unit.sub_unit_ids(request.units)
#    units = Unit.objects.filter(id__in=sub_unit_ids)
#    form = GrantForm(units)
#    context = {
#        "grant_form": form,
#        "editor": editor,
#    }
#    if request.method == "POST":
#        form = GrantForm(units, request.POST)
#        if form.is_valid():
#            grant = form.save()
#            GrantOwner.objects.filter(grant=grant).delete()
#            for p in form.cleaned_data['owners']:
#                GrantOwner(grant=grant, person=p).save()
#        else:
#            context.update({"grant_form": form})
#    return render(request, "faculty/new_grant.html", context)


@requires_role('ADMN')
def edit_grant(request, unit_slug, grant_slug):
    editor = get_object_or_404(Person, userid=request.user.username)
    sub_unit_ids = Unit.sub_unit_ids(request.units)
    units = Unit.objects.filter(id__in=sub_unit_ids)
    grant = get_object_or_404(Grant, unit__slug=unit_slug, slug=grant_slug)
    if grant.unit.id not in sub_unit_ids:
        raise PermissionDenied("Not allowed to edit this grant")
    form = GrantForm(units, instance=grant)
    context = {
        "grant": grant,
        "grant_form": form,
        "editor": editor,
    }
    if request.method == "POST":
        form = GrantForm(units, request.POST, instance=grant)
        if form.is_valid():
            grant = form.save(commit=False)
            grant.save()
            GrantOwner.objects.filter(grant=grant).delete()
            for p in form.cleaned_data['owners']:
                GrantOwner(grant=grant, person=p).save()

            return HttpResponseRedirect(reverse("grants_index"))

        else:
            context.update({"grant_form": form})
    return render(request, "faculty/edit_grant.html", context)


@requires_role('ADMN')
def view_grant(request, unit_slug, grant_slug):
    # TODO: should other faculties be able to view grants not in their unit?
    grant = get_object_or_404(Grant, unit__slug=unit_slug, slug=grant_slug)
    context = {
        "grant": grant,
    }
    return render(request, "faculty/view_grant.html", context)
