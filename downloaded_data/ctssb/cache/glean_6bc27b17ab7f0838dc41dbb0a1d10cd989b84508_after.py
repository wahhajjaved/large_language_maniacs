# Create your views here.
import csv

from django import forms

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group

from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.db.models import Q
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import generic

from constants import VERMONT_COUNTIES
from memberorgs.models import MemOrg
from gleaning.customreg import ExtendedRegistrationForm

from userprofile.models import (Profile,
                                ProfileForm,
                                UserForm,
                                LoginForm,
                                EmailForm,
                                EditProfileForm,
                                UniPromoteForm,
                                PromoteForm,
                                AdminProfileForm)


@login_required
def userDetailEntry(request):
    if request.method == "POST":
        form = ProfileForm(request.POST)
        if form.is_valid():
            if not Profile.objects.filter(user=request.user).exists():
                new_save = form.save(commit=False)
                new_save.user = request.user
                new_save.save()
            else:
                form = ProfileForm(
                    request.POST,
                    Profile.objects.filter(user=request.user).get()
                )
            return HttpResponseRedirect(reverse('home'))
        else:
            return render(request,
                          'userprofile/userdetailentry.html',
                          {'form': form, 'error': "form wasn't valid"})
    else:
        form = ProfileForm
        return render(request,
                      'userprofile/userdetailentry.html',
                      {'form': form, 'error': ''})


@login_required
def selfEdit(request):
    if request.method == "POST":
        instance = Profile.objects.get(user=request.user)
        if request.user.has_perm('userprofile.auth'):
            form = AdminProfileForm(request.POST, instance=instance)
        else:
            form = EditProfileForm(request.POST, instance=instance)
        if form.is_valid():
            new_save = form.save(commit=False)
            #new_save.member_organization = instance.member_organization
            form.save_m2m()
            new_save.save()
            return HttpResponseRedirect(reverse('home'))
        else:
            return render(
                request,
                'userprofile/userEdit.html',
                {
                    'form': form,
                    'error': "form wasn't valid (try filling in more stuff)",
                    'editmode': True
                }
            )
    else:
        if Profile.objects.filter(user=request.user).exists():
            profile = Profile.objects.get(user=request.user)
            if request.user.has_perm('userprofile.auth'):
                form = AdminProfileForm(instance=profile)
            else:
                form = EditProfileForm(instance=profile)
            return render(
                request,
                'userprofile/userEdit.html',
                {'form': form, 'error': '', 'editmode': True}
            )
        else:
            if request.user.has_perm('userprofile.auth'):
                form = AdminProfileForm()
            else:
                form = EditProfileForm()
            return render(
                request,
                'userprofile/userEdit.html',
                {'form': form, 'error': '', 'editmode': True}
            )


@permission_required('userprofile.auth')
def userLists(request):
    if request.user.has_perm('userprofile.uniauth'):
        users = Profile.objects.all().order_by(
            'member_organization',
            'last_name')
    else:
        member_organization = request.user.profile.member_organization
        user_objects = member_organization.volunteers.all().order_by(
            '-last_name')
        users = []
        for user_object in user_objects:
            users.append(user_object.profile)

    return render(
        request,
        'userprofile/userLists.html',
        {'users': users})


class UserProfileDelete(generic.DeleteView):
    model = User
    template_name = "userprofile/delete.html"
    success_url = reverse_lazy("userprofile:userlists")


@permission_required('userprofile.auth')
def userProfile(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    member_organization = request.user.profile.member_organization
    if request.user.has_perm('userprofile.uniauth'):
        pass
    elif user not in member_organization.volunteers.all():
        return HttpResponseRedirect(reverse('home'))
    person = Profile.objects.get(user=user)
    return render(request, 'userprofile/detail.html', {'person': person})


class UserProfileDetailView(generic.DetailView):
    model = User
    template_name = "userprofile/detail.html"

    def get_success_url(self):
        return reverse_lazy(
            'userprofile:userprofile', args=(self.kwargs["pk"],))

    def get_object(self, *args, **kwargs):
        obj = super(
            UserProfileDetailView,
            self
        ).get_object(*args, **kwargs)
        return obj.profile


@permission_required('userprofile.auth')
def userEdit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    target_memorg = user.profile.member_organization
    memorg = request.user.profile.member_organization
    if target_memorg != memorg and not request.user.has_perm(
            'userprofile.uniauth'):
        return HttpResponseRedirect(reverse('home'))
    person = Profile.objects.get(user=user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, person)
        if form.is_valid():
            new_save = form.save(commit=False)
            new_save.user = user
            new_save.id = person.id
            new_save.member_organization = person.member_organization
            new_save.save()
            form.save_m2m()
            return HttpResponseRedirect(
                reverse('userprofile:userprofile', args=(user_id,)))
        else:
            return render(
                request,
                'userprofile/adminedit.html',
                {'person': person, 'profile': person, 'form': form})

    else:
        form = ProfileForm(instance=person)
        return render(
            request,
            'userprofile/adminedit.html',
            {'person': person, 'profile': person, 'form': form})


def emailEdit(request):
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            request.user.email = form.cleaned_data['email']
            request.user.save()
            return HttpResponseRedirect(reverse('home'))
        else:
            form = EmailForm()
            return render(
                request,
                'userprofile/emailedit.html',
                {'error': "That's not a valid address", 'form': form})
    else:
        form = EmailForm()
        return render(request, 'userprofile/emailedit.html', {'form': form})


@permission_required('userprofile.auth')
def download(request):
    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename=user_profiles.csv'

    # Create the CSV writer using the HttpResponse as the "file."
    writer = csv.writer(response)
    writer.writerow([
        'Username',
        'Email',
        'First Name',
        'Last Name',
        'Address',
        'Address (line two)',
        'City',
        'State',
        'Counties',
        'Age Bracket',
        'Phone',
        'Phone Type',
        'Member Org',
        'Contact Method',
        "Join Date",
        'EC First',
        'EC Last',
        'EC Phone',
        'EC Relationship',
        'Accepts Email',
    ])

    if request.user.has_perm('userprofile.uniauth'):
        profiles = User.objects.all()
    else:
        profiles = request.user.profile.member_organization.volunteers.all()
    for person in profiles:
            profile = person.profile
            writer.writerow([
                profile.user.username,
                profile.user.email,
                profile.first_name,
                profile.last_name,
                profile.address_one,
                profile.address_two,
                profile.city,
                profile.state,
                profile.counties.all(),
                profile.age,
                profile.phone,
                profile.get_phone_type_display(),
                person.member_organizations.all(),
                profile.get_preferred_method_display(),
                profile.joined,
                profile.ecfirst_name,
                profile.eclast_name,
                profile.ecphone,
                profile.ecrelationship,
                profile.accepts_email,
                ])

    return response


@permission_required('userprofile.auth')
def newUser(request):
    notice = ''
    if request.method == 'POST':
        form = ExtendedRegistrationForm(request.POST)
        if form.is_valid():
            new_user = User.objects.create_user(
                form.cleaned_data['username'],
                form.cleaned_data['email'],
                form.cleaned_data['password1']
            )
            profile = Profile(
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                address_one=form.cleaned_data['address_one'],
                address_two=form.cleaned_data['address_two'],
                city=form.cleaned_data['city'],
                state=form.cleaned_data['state'],
                age=form.cleaned_data['age'],
                phone=form.cleaned_data['phone'],
                phone_type=form.cleaned_data['phone_type'],
                preferred_method=form.cleaned_data['preferred_method'],
                ecfirst_name=form.cleaned_data['ecfirst_name'],
                eclast_name=form.cleaned_data['eclast_name'],
                ecrelationship=form.cleaned_data['ecrelationship'],
                user=new_user,
                waiver=form.cleaned_data['waiver'],
                agreement=form.cleaned_data['agreement'],
                photo_release=form.cleaned_data['photo_release'],
                opt_in=form.cleaned_data['opt_in'],
            )
            profile.save()

            for county in form.cleaned_data['vt_counties']:
                profile.counties.add(county)
                county.affix_to_memorgs(new_user)
            for county in form.cleaned_data['ny_counties']:
                profile.counties.add(county)
                county.affix_to_memorgs(new_user)
            notice = ('New Volunteer ' + profile.first_name +
                      ' ' + profile.last_name + ' has been created.')
            form = ExtendedRegistrationForm()
    else:
        form = ExtendedRegistrationForm()
    if request.user.has_perm('userprofile.uniauth'):
        users = User.objects.all().order_by('-date_joined')[:20]
    else:
        users = request.user.profile.member_organization.volunteers.order_by(
            '-date_joined')[:20]
    return render(
        request,
        'userprofile/newuser.html',
        {'form': form, 'users': users, 'notice': notice})


@permission_required('userprofile.auth')
def userPromote(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    profile = user.profile
    rq_memorg = request.user.profile.member_organization
    ed = Group.objects.get(name="Member Organization Executive Director")
    memc = Group.objects.get(name="Member Organization Glean Coordinator")
    sal = Group.objects.get(name="Salvation Farms Administrator")
    salc = Group.objects.get(name="Salvation Farms Coordinator")
    #return HttpResponse(ed in user.groups.all())
    executive = ed in user.groups.all() or sal in user.groups.all()

    admin = executive or memc in user.groups.all() or salc in user.groups.all()
    data = {'member_organization': profile.member_organization,
            'executive': executive,
            'promote': admin}
    member_organization = forms.ModelChoiceField(
        queryset=MemOrg.objects.all(),
        label="Member Organization",
        empty_label=None)

    if request.user.has_perm('userprofile.uniauth'):
        if request.method == 'POST':
            form = UniPromoteForm(request.POST)
            if form.is_valid():
                user.groups.clear()
                profile.member_organization = form.cleaned_data[
                    'member_organization']
                if user not in profile.member_organization.volunteers.all():
                    profile.member_organization.volunteers.add(user)
                profile.save()
                if form.cleaned_data['promote']:
                    if form.cleaned_data['member_organization'] == rq_memorg:
                        if form.cleaned_data['executive']:
                            user.groups.add(sal)
                        else:
                            user.groups.add(salc)
                    else:
                        if form.cleaned_data['executive']:
                            user.groups.add(ed)
                        else:
                            user.groups.add(memc)
                    return HttpResponseRedirect(
                        reverse(
                            'userprofile:userprofile', args=(user_id,)))
                else:
                    return HttpResponseRedirect(
                        reverse(
                            'userprofile:userprofile', args=(user_id,)))
            else:
                return render(
                    request,
                    'userprofile/user_promote.html',
                    {'form': form})
        else:
            form = UniPromoteForm(data)

    else:
        if request.method == 'POST':
            form = PromoteForm(request.POST)
            if form.is_valid():
                if executive is False:
                    user.groups.clear()
                    if form.cleaned_data['promote']:
                        user.groups.add(memc)
                else:
                    return HttpResponseRedirect(
                        reverse('userprofile:userprofile', args=(user.id,)))
            return HttpResponseRedirect(
                reverse('userprofile:userprofile', args=(user_id,)))
        else:
            form = PromoteForm({'promote': admin})
    return render(request, 'userprofile/user_promote.html', {'form': form})


def newAdmin(request, memorg_id):
    pass


@permission_required('userprofile.auth')
def reaccept(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    profile = Profile.objects.filter(user=user).get()
    if not profile.accepts_email:
        profile.accepts_email = True
        profile.save()
    return HttpResponseRedirect(
        reverse('userprofile:userprofile', args=(user_id,)))
