import re
from paypal.standard.forms import PayPalPaymentsForm
from django.shortcuts import render, render_to_response, redirect
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template import RequestContext
from .models import AuthKey, Sponsor
from .forms import LoginForm, AuthKeyForm, SignupForm, PasswordResetRequestForm, PasswordResetForm
from .helpers import check_password, hash_password, check_complexity, send_reset_email

def payment(request):

    paypal_dict = {
        "business": settings.PAYPAL_RECEIVER_EMAIL,
        "amount": "10.00",
        "item_name": "Goo.IM Sponsor Account",
        "notify_url": "https://www.goo.im" + reverse('paypal-ipn'),
        "return_url": "https://www.goo.im/confirmation",
        "cancel_return": "https://www.goo.im/sponsorcancel",
    } 
	
    # Create Form Instance
    form = PayPalPaymentsForm(initial=paypal_dict)
    context = {"form": form}
    return render(request, "sponsor/signup.html", context)

def authkey_view(request):

    if request.method == "GET":
        if 'token' in request.GET:
            token = request.GET.get('token')

            try:
                auth_key = AuthKey.objects.get(token=token)
            except:
                messages.add_message(request, messages.ERROR, 'Auth Key Not Valid', extra_tags="danger")
                return HttpResponseRedirect(request.path)

            request.session['auth_key'] = token		
            return redirect('sponsor_signup2')

        else:
            form = AuthKeyForm
            return render(request, "sponsor/authkey.html", {"form": form}) 
		
def complete_signup(request):

    if request.method == "GET":
        if not 'auth_key' in request.session:
            messages.error(request, 'Did not receive auth key.  Please check that cookies are enabled and re-enter your auth key.')
            return redirect('sponsor_auth')
        else:
            auth_key = request.session['auth_key']
            form = SignupForm(initial={'auth_key': auth_key})
            return render(request, "sponsor/signup2.html", {"form": form})

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            confirm_password = form.cleaned_data['confirm_password']
            auth_key = form.cleaned_data['auth_key']

            try:
                user = Sponsor.objects.get(username=username)
            except:
                pass
            else:
                messages.add_message(request, messages.ERROR, "This username is already taken; try another", extra_tags="danger")
                return HttpResponseRedirect(request.path)

            if check_complexity(password) == False:
                messages.add_message(request, messages.ERROR, "Your password was too simple; must have eight or more characters, and include at least one number.  Please try again.", extra_tags="danger")
                return HttpResponseRedirect(request.path)

            if password == confirm_password:
                s_password, s_salt = hash_password(password)
            else:
                request.session['auth_key'] = auth_key
                messages.add_message(request, messages.ERROR, "Your passwords did not match; please try again", extra_tags="danger")
                redirect(request.path)

            auth_instance = AuthKey.objects.get(token=auth_key)
            txn_id = auth_instance.payment_id
            email = auth_instance.email

            new_sponsor = Sponsor(username=username, password=s_password, salt=s_salt, email=email, payment_id=auth_instance.payment_id)
            new_sponsor.save()
            auth_instance.delete()
            request.session['sponsor'] = username
            del request.session['auth_key']
            return redirect('index')
			

def login_view(request):

    if request.method == "GET":
        if 'sponsor' in request.session:
            return render(request, "sponsor/alreadyloggedin.html")

        form = LoginForm
        d = {"form": form}
        return render(request, "sponsor/login.html", d)
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            try:
                sponsor = Sponsor.objects.get(username=username)
            except Sponsor.DoesNotExist:
                messages.add_message(request, messages.ERROR, 'Username or Password not recognized.', extra_tags="danger")
                return HttpResponseRedirect(request.path)

            salt = sponsor.salt

            if sponsor.migrated:
                pw_correct = check_password(username, password, salt)
            else:
                pw_correct = check_password(username, password,  old=True)

          
            if pw_correct:
                request.session['sponsor'] = username
                return redirect('index')

            messages.add_message(request, messages.ERROR, 'Username or Password not recognized.', extra_tags="danger")
            return HttpResponseRedirect(request.path)

def logout_view(request):
    
    if 'sponsor' in request.session:
        del request.session['sponsor']

    return redirect('index')

def password_reset_request_view(request):

    if request.method == "GET":
        form = PasswordResetRequestForm
        return render(request, "sponsor/passwordreset.html", {"form": form})

    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data['username']

        # Try Email First
        if re.match(r"[^@]+@[^@]+\.[^@]+", query):
            try:
                s = Sponsor.objects.get(email=query)
            except Sponsor.MultipleObjectsReturned:
                messages.add_message(request, messages.ERROR, 'There are multiple accounts with this email address.  Please use your username, or contact support@snipanet.com for assistance', extra_tags="danger")
                return HttpResponseRedirect(request.path)
            except Sponsor.DoesNotExist:
                messages.add_message(request, messages.ERROR, 'Could not find this email address.  Please try again with your username, or contact support@snipanet.com for assistance', extra_tags="danger")
                return HttpResponseRedirect(request.path)

        else:
            try:
                s = Sponsor.objects.get(username=query)
            except Sponsor.MultipleObjectsReturned:
                messages.add_message(request, messages.ERROR, 'There are multiple accounts with this username.  This should not happen!  Please contact support@snipanet.com for assistance.', extra_tags="danger")
                return HttpResponseRedirect(request.path)
            except Sponsor.DoesNotExist:
                messages.add_message(request, messages.ERROR, 'Could not find this username.  Please try again, or contact support@snipanet.com for assistance.', extra_tags="danger")
                return HttpResponseRedirect(request.path)

        if s.status == False:
            messages.add_message(request, messages.ERROR, 'Your sponsor account is disabled! Please contact support@snipanet.com for more information.', extra_tags="danger")
            return HttpResponseRedirect(request.path)

        send_reset_email(s)
        
        messages.add_message(request, messages.SUCCESS, 'Password reset instructions have been sent to your email.')
        return redirect('index')       
        
def password_reset_view(request):
    if request.method == "GET":
        if 'token' in request.GET:
            token = request.GET.get('token')
            sponsor_id = cache.get('reset_%s' % token)

            request.session
            
            if sponsor_id == None:
                messages.add_message(request, messages.ERROR, 'Could not find your reset request.  Please attempt another password reset, or contact support@snipanet.com for assistance', extra_tags="danger")
                return redirect('index')

            form = PasswordResetForm(initial={"token": token})
            d = {'form': form}
            return render(request, "sponsor/passwordreset.html", d)
            
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['password']
            confirm_password = form.cleaned_data['confirm_password']
            token = form.cleaned_data['token']

            sponsor_id = cache.get('reset_%s' % token)
            s = Sponsor.objects.get(id=sponsor_id)
        
            if check_complexity(password) == False:
                messages.add_message(request, messages.ERROR, "Your password was too simple; must have eight or more characters, and include at least one number.  Please try again.", extra_tags="danger")
                return HttpResponseRedirect(request.get_full_path())

            if password == confirm_password:
                s.password, s.salt = hash_password(password)
                s.migrated = True
                s.save()
                messages.add_message(request, messages.SUCCESS, "Your password has been changed! Please login to receive subscriber perks.")
                cache.delete('reset_%s' % token)
                return redirect('index')
            else:
                messages.add_message(request, messages.ERROR, "Your passwords did not match; please try again", extra_tags="danger")
                return HttpResponseRedirect(request.get_full_path())

