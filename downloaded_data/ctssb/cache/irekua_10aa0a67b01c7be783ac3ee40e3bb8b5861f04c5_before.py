from django.shortcuts import render
from django import forms

from django.contrib.auth.decorators import login_required

from database.models import User


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'institution']


def get_summary_context(user):
    collections = user.collection_users.order_by('-created_on')
    sites = user.site_set.order_by('-created_on')
    devices = user.physicaldevice_set.order_by('-created_on')
    sampling_events = user.sampling_event_created_by.order_by('-created_on')
    items = user.item_created_by.order_by('-created_on')

    try:
        latest_collection = collections.all().first().name
    except AttributeError:
        latest_collection = '-'

    try:
        latest_site = sites.all().first().created_on
    except AttributeError:
        latest_site = '-'

    try:
        latest_device = devices.all().first().created_on
    except AttributeError:
        latest_device = '-'

    try:
        latest_sampling_event = sampling_events.all().first().created_on
    except AttributeError:
        latest_sampling_event = '-'
    try:
        latest_item = items.all().first().created_on
    except AttributeError:
        latest_item = '-'

    context = {
        'user_collections': collections.all().count(),
        'user_sites': sites.all().count(),
        'user_devices': devices.all().count(),
        'user_sampling_events': sampling_events.all().count(),
        'user_items': items.all().count(),
        'latest_collection': latest_collection,
        'latest_device': latest_device,
        'latest_site': latest_site,
        'latest_sampling_event': latest_sampling_event,
        'latest_item': latest_item,
    }
    return context


@login_required(login_url='registration:login')
def user_home(request):
    if request.method == "POST":
        form = UserForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()

    context = {'user_form': UserForm(instance=request.user)}
    context.update(get_summary_context(request.user))
    return render(request, 'selia/user/home.html', context)
