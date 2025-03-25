from django.template import loader
from django.http import HttpResponse
from .models import Fault, Object
from django.http import Http404
from .forms import FaultForm
from django.contrib.auth import authenticate
from django.http import HttpResponseRedirect
from django.contrib import auth
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .backends import InvbookBackend
from django.contrib.auth import get_user_model


def test(request):
    template = loader.get_template('cti/test.html')

    invbook = InvbookBackend()
    try:
        tmp = invbook.get_or_create_object('1000019856')

        context = {'object_number': tmp.object_number,
                   'object_name': tmp.object_name,
                   'created_at': tmp.created_at,
                   'room': tmp.room,
                   'status': tmp.status,
                   'price': tmp.price,
                   'comments': tmp.comments}
    except Object.DoesNotExist:
        context = {'object_number': 'dupa',
                   'object_name': 'dupa',
                   'created_at': 'dupa',
                   'room': 'dupa',
                   'status': 'dupa',
                   'price': 'dupa',
                   'comments': 'dupa'}

    return HttpResponse(template.render(context, request))


def login(request):
    template = loader.get_template('cti/login.html')

    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                auth.login(request, user)

                return HttpResponseRedirect(reverse('cti:index'))
            else:
                messages.warning(request, 'your account has been disabled')
        else:
            messages.error(request, 'invalid login or password')

    return HttpResponse(template.render(request=request))


def logout(request):
    template = loader.get_template('cti/logout.html')

    auth.logout(request)

    return HttpResponse(template.render(request=request))


@login_required
def index(request):
    template = loader.get_template('cti/index.html')

    faults = Fault.objects.filter(is_visible=True, status__in=[0, 1]).order_by('-updated_at')

    context = {'faults': faults,
               'header': 'all faults'}

    return HttpResponse(template.render(context, request))


@login_required
def my_faults(request):
    template = loader.get_template('cti/index.html')

    faults = Fault.objects.filter(issuer=request.user.get_username(), is_visible=True).order_by('-updated_at')

    context = {'faults': faults,
               'header': 'my faults'}

    return HttpResponse(template.render(context, request))


@login_required
def resolved_faults(request):
    template = loader.get_template('cti/index.html')

    faults = Fault.objects.filter(is_visible=True, status=2).order_by('-updated_at')

    context = {'faults': faults,
               'header': 'resolved faults'}

    return HttpResponse(template.render(context, request))


@login_required
def sorted_faults(request, order_by):
    template = loader.get_template('cti/index.html')

    faults = Fault.objects.filter(is_visible=True, status__in=[0, 1]).order_by(order_by)

    context = {'faults': faults,
               'header': 'sorted faults'}

    return HttpResponse(template.render(context, request))


@login_required
def add_fault(request):
    template = loader.get_template('cti/add_fault.html')

    if request.method == "POST":
        form = FaultForm(request.POST)

        if form.is_valid():
            fault = form.save(commit=False)
            fault.issuer = request.user
            fault.save()

            invbook = InvbookBackend()
            invbook.get_or_create_object(fault.object_number)

            messages.success(request, "fault added successful")
        else:
            messages.warning(request, "fault not added {}".format(form.errors))
    else:
        form = FaultForm()

    context = {'form': form,
               'header': 'new fault'}

    return HttpResponse(template.render(context, request))


@login_required
def edit_fault(request, fault_id):
    template = loader.get_template('cti/edit_fault.html')

    try:
        fault = Fault.objects.get(pk=fault_id)
        form = FaultForm(request.POST or None, instance=fault)

        if request.method == "POST":
            if form.is_valid():
                fault = form.save(commit=False)
                fault.save()
                messages.success(request, "fault edited successful")

        context = {'form': form}

        return HttpResponse(template.render(context, request))

    except Fault.DoesNotExist:
        raise Http404("fault does not exist")


@login_required
def delete_fault(request, fault_id):
    template = loader.get_template('cti/index.html')

    try:
        fault = Fault.objects.get(pk=fault_id)

        if fault.is_visible:
            fault.is_visible = False
            fault.save()
            messages.success(request, "fault deleted successful")

        faults = Fault.objects.filter(is_visible=True, status__in=[0, 1])

        context = {'faults': faults,
                   'fields': Fault().get_fields()}

        return HttpResponse(template.render(context, request))

    except Fault.DoesNotExist:
        raise Http404("fault does not exist")


@login_required
def fault_details(request, fault_id):
    template = loader.get_template('cti/fault_details.html')

    try:
        fault = Fault.objects.get(pk=fault_id)
        context = {'fault': fault,
                   'header': 'fault\'s details'}
    except Fault.DoesNotExist:
        raise Http404("fault does not exist")

    return HttpResponse(template.render(context, request))


@login_required
def object_details(request, object_id):
    template = loader.get_template('cti/object_details.html')

    try:
        object = Object.objects.get(object_number=object_id)
        context = {'object': object,
                   'header': 'object\'s details'}
    except Object.DoesNotExist:
        raise Http404("object does not exist")

    return HttpResponse(template.render(context, request))


@login_required
def user_details(request):
    template = loader.get_template('cti/user_details.html')

    User = get_user_model()

    try:
        user = User.objects.get(username__exact=request.user)
        context = {'user': user,
                   'header': 'user\'s details'}
    except User.DoesNotExist:
        raise Http404("user does not exist")

    return HttpResponse(template.render(context, request))


@login_required
def assign_to_me(request, fault_id):
    template = loader.get_template('cti/index.html')

    try:
        fault = Fault.objects.get(pk=fault_id)

        if fault.handler == '0' or fault.handler == '':
            fault.handler = request.user.get_username()
            fault.status = 1
            fault.save()
            messages.success(request, "fault assigned successful")
        else:
            messages.warning(request, "fault is already assigned")

        faults = Fault.objects.filter(is_visible=True, status__in=[0, 1])

        context = {'faults': faults,
                   'fields': Fault().get_fields(), }

        return HttpResponse(template.render(context, request))

    except Fault.DoesNotExist:
        raise Http404("fault does not exist")


@login_required
def change_password(request):
    template = loader.get_template('cti/change_password.html')

    if request.method == "POST":
        old_password = request.POST['old_password']
        new_password = request.POST['new_password']
        new_password_repeat = request.POST['new_password_repeat']

        user = User.objects.get(username__exact=request.user)

        if new_password != new_password_repeat:
            messages.warning(request, 'new password fields are different! ')

        if not user.check_password(old_password):
            messages.warning(request, 'old password is wrong')

        if user.check_password(old_password) and new_password == new_password_repeat:
            user.set_password(new_password)
            user.save()
            user = authenticate(username=request.user, password=new_password)
            auth.login(request, user)
            messages.success(request, 'password has been changed')

            return HttpResponseRedirect(reverse('cti:index'))

    return HttpResponse(template.render(request))
