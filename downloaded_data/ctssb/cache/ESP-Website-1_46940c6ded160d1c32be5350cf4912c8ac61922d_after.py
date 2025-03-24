

from esp.users.models import User, UserBit, ESPUser_Profile
from esp.users.forms.user_reg import UserRegForm, EmailUserForm
from esp.web.util.main import render_to_response
from esp.datatree.models import GetNode
from esp.mailman import add_list_member
from esp.middleware.esperrormiddleware import ESPError
from django.contrib.auth import login, authenticate
from django.http import HttpResponseRedirect
from django.template import loader, Context
from django.core.mail import send_mail
from django.contrib.sites.models import Site
import hashlib
import random
from esp import settings

__all__ = ['join_emaillist','user_registration']

def join_emaillist(request):
    """
    View to join our email list.
    """

    if request.user.is_authenticated():
        return render_to_response('registration/already_logged_in.html',
                                  request, request.get_node('Q/Web/myesp'), {})


    if request.method == 'POST':
        form = EmailUserForm(request.POST, request=request)


        if form.is_valid():
            # create the user
            User.objects.get_or_create(email    = form.cleaned_data['email'],
                                       username = form.cleaned_data['email'],
                                       password = 'emailuser')

            add_list_member('announcements', form.cleaned_data['email'])

            return HttpResponseRedirect('/')
    else:
        form = EmailUserForm(request=request)    

    return render_to_response('registration/emailuser.html',
                              request, request.get_node('Q/Web/myesp'), {'form':form})

            

def user_registration(request):
    """
    Registration view -- takes care of users who want to create a
    new account.
    """

    if request.user.is_authenticated():
        return render_to_response('registration/already_logged_in.html',
                                  request, request.get_node('Q/Web/myesp'), {})

    if request.method == 'POST':
        form = UserRegForm(request.POST)

        if form.is_valid():         
            ## First, check to see if we have any users with the same e-mail
            if not 'do_reg_no_really' in request.POST:
                existing_accounts = User.objects.filter(email=form.cleaned_data['email']).exclude(password='emailuser')
                if len(existing_accounts) != 0:
                    return render_to_response('registration/newuser.html',
                                              request, request.get_node('Q/Web/myesp'),
                                              { 'accounts': existing_accounts, 'form': form, 'site': Site.objects.get_current() })                
            
            try:
                user = User.objects.get(email=form.cleaned_data['email'],
                                        password = 'emailuser')
            except User.DoesNotExist:
                user = User(email = form.cleaned_data['email'])

            user.username   = form.cleaned_data['username']
            user.last_name  = form.cleaned_data['last_name']
            user.first_name = form.cleaned_data['first_name']

            user.set_password(form.cleaned_data['password'])
            userkey = random.randint(0,2**31 - 1)
            user.password += "$%d" % userkey
            user.is_active = False

            user.save()
            ESPUser_Profile.objects.get_or_create(user = user)

            role_verb = GetNode('V/Flags/UserRole/%s' % form.cleaned_data['initial_role'])

            role_bit  = UserBit.objects.create(user = user,
                                               verb = role_verb,
                                               qsc  = request.get_node('Q'),
                                               recursive = False)

            #user = authenticate(username=form.cleaned_data['username'],
            #                    password=form.cleaned_data['password'])
            #
            #login(request, user)
            #return HttpResponseRedirect('/myesp/profile/')

            t = loader.get_template('registration/activation_email.txt')
            c = Context({'user': user, 'activation_key': userkey, 'site': Site.objects.get_current()})

            send_mail("Account Activation", t.render(c), settings.SERVER_EMAIL, [user.email], fail_silently = False)

            return render_to_response('registration/account_created_activation_required.html',
                                      request, request.get_node('Q/Web/myesp'),
                                      {'user': user, 'activation_key': hashlib.md5(user.username).hexdigest()})
    else:
        form = UserRegForm()

    return render_to_response('registration/newuser.html',
                              request, request.get_node('Q/Web/myesp'),{'form':form})



def activate_account(request):
    if not 'username' in request.GET or not 'key' in request.GET:
        raise ESPError(), "Invalid account activation information.  Please try again.  If this error persists, please contact us using the contact information on the top or bottom of this page."

    try:
        u = User.objects.get(username = request.GET['username'])
    except:
        raise ESPError(), "Invalid account username.  Please try again.  If this error persists, please contact us using the contact information on the top or bottom of this page."

    if not u.password.endswith("$%s" % request.GET['key']):
        raise ESPError(), "Invalid account activation key.  Please try again.  If this error persists, please contact us using the contact information on the top or bottom of this page."

    u.password = u.password[:-(len("$%s" % request.GET['key']))]
    u.is_active = True
    u.save()

    return HttpResponseRedirect('/myesp/profile/')

