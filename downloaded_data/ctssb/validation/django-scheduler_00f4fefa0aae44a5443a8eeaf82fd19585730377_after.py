from django.shortcuts import render_to_response, get_object_or_404
from django.views.generic.create_update import delete_object
from django.http import HttpResponseRedirect, Http404, HttpResponse
from django.template import RequestContext
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.generic.create_update import delete_object
from django.conf import settings
import datetime

from schedule.forms import EventForm, OccurrenceForm
from schedule.models import *
from schedule.periods import weekday_names

def calendar(request, calendar_slug, template='schedule/calendar.html'):
    """
    This view returns a calendar.  This view should be used if you are
    interested in the meta data of a calendar, not if you want to display a
    calendar.  It is suggested that you use calendar_by_periods if you would
    like to display a calendar.
    
    Context Variables:
    
    ``calendar``
        The Calendar object designated by the ``calendar_slug``.
    """
    calendar = get_object_or_404(Calendar, slug=calendar_slug)
    return render_to_response(template, {
        "calendar": calendar,
    }, context_instance=RequestContext(request))

def calendar_by_periods(request, calendar_slug, periods=None,
    template_name="schedule/calendar_by_period.html"):
    """
    This view is for getting a calendar, but also getting periods with that
    calendar.  Which periods you get, is designated with the list periods. You
    can designate which date you the periods to be initialized to by passing
    a date in request.GET. See the template tag ``query_string_for_date``
    
    Context Variables
    
    ``date``
        This was the date that was generated from the query string.
    
    ``periods``
        this is a dictionary that returns the periods from the list you passed
        in.  If you passed in Month and Day, then your dictionary would look
        like this
        
        {
            'month': <schedule.periods.Month object>
            'day':   <schedule.periods.Day object>
        }
        
        So in the template to access the Day period in the context you simply
        use ``periods.day``.
    
    ``calendar``
        This is the Calendar that is designated by the ``calendar_slug``.
    
    ``weekday_names``
        This is for convenience. It returns the local names of weekedays for
        internationalization.
        
    """
    calendar = get_object_or_404(Calendar, slug=calendar_slug)
    date = coerce_date_dict(request.GET)
    if date:
        try:
            date = datetime.datetime(**date)
        except ValueError:
            raise Http404
    else:
        date = datetime.datetime.now()
    period_objects = dict([(period.__name__.lower(), period(calendar.events.all(), date)) for period in periods])
    return render_to_response(template_name,{
            'date': date,
            'periods': period_objects,
            'calendar': calendar,
            'weekday_names': weekday_names,
        },context_instance=RequestContext(request),)

def event(request, event_id, template_name="schedule/event.html"):
    """
    This view is for showing an event. It is important to remember that an 
    event is not an occurrence.  Events define a set of reccurring occurrences.
    If you would like to display an occurrence (a single instance of a 
    recurring event) use occurrence.
    
    Context Variables:
    
    event
        This is the event designated by the event_id
    
    back_url
        this is the url that referred to this view.
    """
    event = get_object_or_404(Event, id=event_id)
    back_url = request.META.get('HTTP_REFERER', None)
    try:
        cal = event.calendar_set.get()
    except:
        cal = None
    return render_to_response(template_name, {
        "event": event,
        "back_url" : back_url,
    }, context_instance=RequestContext(request))

def occurrence(request, event_id,
    template_name="schedule/occurrence.html", *args, **kwargs):
    """
    This view is used to display an occurrence.
    
    Context Variables:
    
    ``event``
        the event that produces the occurrence
    
    ``occurrence`` 
        the occurrence to be displayed
    
    ``back_url``
        the url from which this request was refered
    """
    event, occurrence = get_occurrence(event_id, *args, **kwargs)
    back_url = request.META.get('HTTP_REFERER', None)
    return render_to_response(template_name, {
        'event': event,
        'occurrence': occurrence,
        'back_url': back_url,
    }, context_instance=RequestContext(request))


def edit_occurrence(request, event_id, 
    template_name="schedule/edit_occurrence.html", *args, **kwargs):
    event, occurrence = get_occurrence(event_id, *args, **kwargs)
    form = OccurrenceForm(data=request.POST or None, instance=occurrence)
    if form.is_valid():
        occurrence = form.save(commit=False)
        occurrence.event = event
        occurrence.save()
        next = kwargs.get('next', None) or occurrence.get_absolute_url()
        return HttpResponseRedirect(get_next_url(request, next))
    return render_to_response(template_name, {
        'form': form,
        'occurrence': occurrence,
    }, context_instance=RequestContext(request))

def cancel_occurrence(request, event_id, 
    template_name='schedule/cancel_occurrence.html', *args, **kwargs):
    """
    This view is used to cancel an occurrence. If it is called with a POST it
    will cancel the view. If it is called with a GET it will ask for
    conformation to cancel.
    """
    event, occurrence = get_occurrence(event_id, *args, **kwargs)
    if request.method != "POST":
        return render_to_response(template_name, {
            "occurrence": occurrence
        }, context_instance=RequestContext(request))
    occurrence.cancel()
    next = kwargs.get('next',None) or occurrence.event.get_absolute_url()
    return HttpResponseRedirect(get_next_url(request, next))
    
    

def get_occurrence(event_id, occurrence_id=None, year=None, month=None,
    day=None, hour=None, minute=None, second=None):
    """
    Because occurrences don't have to be persisted, there must be two ways to
    retrieve them. both need an event, but if its persisted the occurrence can
    be retrieved with an id. If it is not persisted it takes a date to
    retrieve it.  This function returns an event and occurrence regardless of
    which method is used.
    """
    if(occurrence_id):
        occurrence = get_object_or_404(Occurrence, id=occurrence_id)
        event = occurrence.event
    elif(all((year, month, day, hour, minute, second))):
        event = get_object_or_404(Event, id=event_id)
        occurrence = event.get_occurrence(
            datetime.datetime(int(year), int(month), int(day), int(hour), 
                int(minute), int(second)))
        if occurrence is None:
            raise Http404
    else:
        raise Http404
    return event, occurrence


@login_required
def create_or_edit_event(request, calendar_slug, event_id=None, next=None,
    template_name='schedule/create_event.html'):
    """
    This function, if it receives a GET request or if given an invalid form in a
    POST request it will generate the following response

    Template:
        schedule/create_event.html
    
    Context Variables:
        
    form:
        an instance of EventForm
    
    calendar: 
        a Calendar with id=calendar_id

    if this function gets a GET request with ``year``, ``month``, ``day``,
    ``hour``, ``minute``, and ``second`` it will auto fill the form, with
    the date specifed in the GET being the start and 30 minutes from that
    being the end.

    If this form receives an event_id it will edit the event with that id, if it
    recieves a calendar_id and it is creating a new event it will add that event
    to the calendar with the id calendar_id

    If it is given a valid form in a POST request it will redirect with one of
    three options, in this order

    # Try to find a 'next' GET variable
    # If the key word argument redirect is set
    # Lastly redirect to the event detail of the recently create event
    """
    date = coerce_date_dict(request.GET)
    initial_data = None
    if date:
        try:
            start = datetime.datetime(**date)
            initial_data = {
                "start": start,
                "end": start + datetime.timedelta(minutes=30)
            }
        except TypeError:
            raise Http404
        except ValueError:
            raise Http404
    
    instance = None
    if event_id is not None:
        instance = get_object_or_404(Event, id=event_id)
    
    calendar = get_object_or_404(Calendar, slug=calendar_slug)
    
    form = EventForm(data=request.POST or None, instance=instance, 
        hour24=True, initial=initial_data)
    
    if form.is_valid():
        event = form.save(commit=False)
        if instance is None:
            event.creator = request.user
            event.calendar = calendar
        event.save()
        next = next or reverse('event', args=[event.id])
        if 'next' in request.GET:
            next = check_next_url(request.GET['next']) or next
        return HttpResponseRedirect(next)
    
    return render_to_response(template_name, {
        "form": form,
        "calendar": calendar
    }, context_instance=RequestContext(request))


def delete_event(request, event_id, next=None, login_required=True):
    """
    After the event is deleted there are three options for redirect, tried in
    this order:

    # Try to find a 'next' GET variable
    # If the key word argument redirect is set
    # Lastly redirect to the event detail of the recently create event
    """
    event = get_object_or_404(Event, id=event_id)
    next = next or reverse('day_calendar', args=[event.calendar.slug])
    if 'next' in request.GET:
        next = _check_next_url(request.GET['next']) or next
    return delete_object(request,
                         model = Event,
                         object_id = event_id,
                         post_delete_redirect = next,
                         template_name = "schedule/delete_event.html",
                         login_required = login_required
                        )

def check_next_url(next):
    """
    Checks to make sure the next url is not redirecting to another page.
    Basically it is a minimal security check.
    """
    if '://' in next:
        return None
    return next
    
def coerce_date_dict(date_dict):
    """
    given a dictionary (presumed to be from request.GET) it returns a tuple 
    that represents a date. It will return from year down to seconds until one
    is not found.  ie if year, month, and seconds are in the dictionary, only 
    year and month will be returned, the rest will be returned as min. If none
    of the parts are found return an empty tuple.
    """
    keys = ['year', 'month', 'day', 'hour', 'minute', 'second']
    retVal = {
                'year': 1,
                'month': 1,
                'day': 1,
                'hour': 0,
                'minute': 0,
                'second': 0}
    modified = False
    for key in keys:
        try:
            retVal[key] = int(date_dict[key])
            modified = True
        except KeyError:
            break
    return modified and retVal or {}

def get_next_url(request, default):
    next = default
    if hasattr(settings, 'OCCURRENCE_CANCEL_REDIRECT'):
        next = settings.OCCURRENCE_CANCEL_REDIRECT
    if 'next' in request.GET and check_next_url(request.GET['next']) is not None:
        next = request.GET['next']
    return next
