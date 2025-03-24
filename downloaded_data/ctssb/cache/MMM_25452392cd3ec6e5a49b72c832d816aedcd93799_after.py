from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail, BadHeaderError
from models import *
import hashlib

HOMEPAGE_URL = '/'
LOGIN_URL = '/login_form/'
REGISTER_URL = '/register_form/'

def landing(request):
    if request.user.is_authenticated():
        # get user info
        userInfo = UserInfo.objects.get(user=request.user)
        # set loggined
        loggined = True
    else:
        # set not loggined
        loggined = False
    
    # get all proejcts
    projects = Project.objects.filter(status='OP').order_by('-date_posted')

    # get all tags
    category_top_list = Category_top.objects.all().order_by('name')
    category_list = []
    for category_top in category_top_list:
        category = {}
        category['category_top'] = category_top
        category['category_sub_list'] = Category_sub.objects.filter(category_top=category_top)
        category_list.append(category)

    # category_sub = Category_sub.objects.all().order_by('name')

    return render(request, 'landing.html', {'current': 'home', 'loggined': loggined, 'projects': projects, 'category_list': category_list})

def user_register_form(request):
    if request.method == 'GET':
        if request.GET.get('next'):
            next = request.GET['next']
        else:
            next = HOMEPAGE_URL
        if request.user.is_authenticated():
            return redirect(next)
        else:
            return render(request, 'register_form.html', {'next': next})
    else:
        return redirect(REGISTER_URL)

def user_register(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        uniqname = request.POST['uniqname']
        name = request.POST['name']
        if not (username and password and uniqname):
            return render(request, 'register_form.html', {'username': username, 'uniqname': uniqname, 'name': name, 'position': position})
        if User.objects.filter(username=username).exists():
            return render(request, 'register_form.html', {'username': username, 'uniqname': uniqname, 'name': name, 'position': position})
        # TODO: Check legitimate username, password, uniqname, etc.
        email = uniqname + '@umich.edu'
        user = User.objects.create_user(username=username, password=password, email=email, first_name=name)
        user.is_active = False
        send_verify_email(request, username, email)
        user.save()
        return redirect('/thankyou/')
    else:
        return redirect(REGISTER_URL)

def send_verify_email(request, username, email):
    activation_code = generate_actication_code(username)
    send_mail('User Verification', request.build_absolute_uri('/activate/' + username + '/' + activation_code), 'mmm.umich@gmail.com', [email], fail_silently=False)

def user_activate(request, username, activation_code):
    if activation_code == generate_actication_code(username):
        user = User.objects.get(username=username)
        user.is_active = True
        user.save()
        return redirect(LOGIN_URL)
    else:
        return redirect(REGISTER_URL)

def generate_actication_code(username):
    return hashlib.sha256(username[0] + username[-1] + username).hexdigest()

def user_login_form(request):
    if request.method == 'GET':
        if request.GET.get('next'):
            next = request.GET['next']
        else:
            next = HOMEPAGE_URL
        if request.user.is_authenticated():
            return redirect(next)
        else:
            return render(request, 'login.html', {'next': next})


def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        if request.POST['next']:
            next = request.POST['next']
        else:
            next = HOMEPAGE_URL
        if not (username and password):
            return render(request, 'login_form.html', {'next': next, 'username': username, 'error': 'Fields cannot be empty'})
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect(next);
            else:
                # Return a 'disabled account' error message
                return render(request, 'login_form.html', {'next': next, 'username': username, 'error': 'Account Disabled!'})
        else:
            # Return an 'invalid login' error message.
            return render(request, 'login_form.html', {'next': next, 'username': username, 'error': 'Login Invalid'})
    else:
        return redirect(LOGIN_URL)

def user_logout(request):
    logout(request)
    # redirect to homepage
    return redirect(HOMEPAGE_URL)

@login_required
def profile_form(request):
    # userInfo = UserInfo.objects.get(user=request.user)
    # if userInfo.is_sponsor:
    #     # query sponsor info
    #     sponsorInfo = Sponsor.objects.get(user=request.user)
    # else:
    #     sponsorInfo = []
    # if userInfo.is_developer:
    #     # query developer info
    #     developerInfo = Developer.objects.get(user=request.user)
    # else:
    #     developerInfo = []
    # render()
    return render(request, 'profile.html')

@login_required
def update_profile(request):
    # redirect()
    pass

@login_required
def settings_form(request):
    userInfo = UserInfo.objects.get(user=request.user)

    # render()

@login_required
def update_settings(request):
    pass

@login_required
def new_project_form(request):
    userInfo = UserInfo.objects.get(user=request.user)
    tags = Category_sub.objects.all().order_by('top')
    # render()

@login_required
def new_project(request):
    pass

@login_required
def project_form(request, proj_id):
    # redirect()
    pass
    
@login_required
def edit_project(request, proj_id):
    projectInfo = Project.obejcts.get(id=proj_id)
    developers = proejctInfo.developers.all()
    tags = projectInfo.category_subs.all().order_by('top')
    comments = Comment.objects.filter(proejct=proj_id)

    # render()

def gallery(request):
	pass


