from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

# Decorator to use built-in authentication system
from django.contrib.auth.decorators import login_required

# Used to create and manually log in a user
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate

# Django transaction system so we can use @transaction.atomic
from django.db import transaction

from socialnetwork.models import *
from socialnetwork.forms import *
from studyroom.forms import *
from socialnetwork.s3 import s3_upload, s3_delete

# Used to generate a one-time-use token to verify a user's email address
from django.contrib.auth.tokens import default_token_generator

# Used to send mail from within Django
from django.core.mail import send_mail

from django.core import serializers
from django.http import HttpResponse

# Create your views here.

def get_default_context(request):
    user_id = request.user.id
    student = Student.objects.get(user=request.user)
    context = {}
    context['notifications'] = student.notifications
    context['classes'] = student.classes.all()
    if(len(student.notifications.all()) > 0):
        context['notif_count'] = len(student.notifications.all())
    return context

@login_required
def home(request):
    # # Sets up list of just the logged-in user's (request.user's) items
    user_id = request.user.id
    student = Student.objects.get(user=request.user)
    context = get_default_context(request)
    context["user_id"] = user_id
    context["student"] = student
    context["classes"] = student.classes.all()
    context['studygroupform'] = StudyGroupForm()
    context['notifications'] = student.notifications
    # # For now we'll use 15437
    # current_class = "15437"
    # context = {'user_id' : user_id, 'current_class' : current_class, "classes" : student.classes.all()}
    # context['form'] = PostForm()
    # context['comment_form'] = CommentForm()
    # return render(request, 'socialnetwork/index.html', context)
    return render(request, "socialnetwork/map.html", context)

@login_required
def change_class(request, name):
    user_id = request.user.id
    student = Student.objects.get(user=request.user)
    posts = Classroom.objects.get(name=name).posts.all()
    current_class = name
    try:
        current_post = posts[:1].get()
    except Exception:
        current_post = "Welcome to the Classroom " #+ name + ". This is a place of learning. Life is short."
    # context = {'current_post' : current_post, 'current_class' : current_class, 'user_id' : user_id, 'current_class' : name, "classes" : student.classes.all(), "posts" : posts}
    # context['form'] = PostForm()
    # context['comment_form'] = CommentForm()
    return show_post(request, current_post.id)


@login_required
@transaction.atomic
def upvotePost(request, id, upvote):

    post = Post.objects.get(id=id)
    print post.upvoters.all()
    student = Student.objects.get(user=request.user)
    if (student not in post.upvoters.all()) and int(upvote) == 1:
        post.upvoters.add(student)
        post.upvotes += int(upvote)
    elif student not in post.downvoters.all() and int(upvote) == -1:        
        post.downvoters.add(student)
        post.upvotes += int(upvote)
    elif student in post.upvoters.all() and int(upvote) == -1:
        post.upvoters.remove(student)
        post.upvotes += int(upvote)
    elif student in post.downvoters.all() and int(upvote) == 1:
        post.downvoters.remove(student)
        post.upvotes += int(upvote)
    
    post.save()
    return show_post(request, id)

@login_required
def show_post(request, id):
    user_id = request.user.id
    student = Student.objects.get(user=request.user)
    current_post = Post.objects.get(id=id)
    posts = current_post.classroom.posts.order_by('-date')
    current_class = current_post.classroom
    context = get_default_context(request)
    context['current_post'] = current_post
    context['current_class'] = current_class
    print current_class
    context['user_id'] = user_id
    context['posts'] = posts
    # context = {'current_post' : current_post, 'current_class' : current_class, 'user_id' : user_id, "classes" : student.classes.all(), "posts" : posts}
    context['form'] = PostForm()
    context['comment_form'] = CommentForm()
    context['students'] = current_class.students
    if current_post.attachment_url:
        context['attachment_url'] = current_post.attachment_url
        context['attachment_name'] = current_post.attachment_name
        print current_post.attachment_url
    return render(request, 'socialnetwork/index.html', context)


@login_required
def map(request):
    return render(request, "socialnetwork/map.html", {})

@transaction.atomic
def register(request):
    context = {}

    # Just display the registration form if this is a GET request
    if request.method == 'GET':
        context['form'] = RegistrationForm()
        return render(request, 'socialnetwork/register.html', context)

    form = RegistrationForm(request.POST)
    context['form'] = form

    errors = []
    context['errors'] = errors

    # Checks the validity of the form data
    if not form.is_valid():
        return render(request, 'socialnetwork/register.html', context)

    # Creates the new user from the valid form data
    new_user = User.objects.create_user(username=form.cleaned_data['email'],
                                        password=form.cleaned_data['password1'],
                                        first_name=form.cleaned_data['first_name'],
                                        last_name=form.cleaned_data['last_name'],
                                        email=form.cleaned_data['email'])
    
    # Mark the user as inactive to prevent login before email confirmation.
    new_user.is_active = True
    new_user.save()
    new_user = authenticate(username=form.cleaned_data['email'], \
                            password=form.cleaned_data['password1'])
    
    new_profile = Student(user=new_user, age=0,
                        school=form.cleaned_data['school'],
                        major=form.cleaned_data['major'])
    new_profile.save()

    # Logs in the new user
    login(request, new_user)

    # return render(request, 'socialnetwork/index.html', context)
    return redirect(reverse('home'))

@login_required
def profile(request, id):
    context=get_default_context(request)
    user = get_object_or_404(User, id=id)
    context['full_name'] = user.get_full_name()
    student = Student.objects.get(user=request.user)
    context['student'] = student
    prof_student = Student.objects.get(user_id=id)
    context['prof_student'] = prof_student
    context['school'] = prof_student.school
    context['major'] = prof_student.major
    context['user_id'] = request.user.id
    context['prof_id'] = user.id
    context['prof_classes'] = prof_student.classes.all()
    context['is_student'] = (student.id == int(id))
    friends = prof_student.friends
    context['is_friend'] = (student in friends.all())
    context['prof_classes'] = prof_student.classes.all()
    context['picture_url'] = prof_student.picture_url
    context['my_friends'] = student.friends
    return render(request, 'socialnetwork/profile.html', context)

@login_required
@transaction.atomic
def edit(request):
    context = get_default_context(request)
    context['user_id'] = request.user.id
    context['picture_url'] = Student.objects.get(user=request.user).picture_url
    profile = Student.objects.get(user=request.user)
    form = EditForm()
    try:
        if request.method == 'GET':
            context['profile'] = profile
            context['form'] = EditForm()
            print "in GET"
            return render(request, 'socialnetwork/edit.html', context)
            
        context['profile'] = Student.objects.get(user=request.user)
        form = EditForm(request.POST, request.FILES)
        context['form'] = form
        #print form
        if not form.is_valid():
            print form.errors
            print "NOT VALID"
            context['form'] = EditForm()
            return render(request, 'socialnetwork/edit.html', context)
        #profile = form.save()

        # Update first and last name of the User
        user = request.user
        if form.cleaned_data['first_name']:
            user.first_name = form.cleaned_data['first_name']
        if form.cleaned_data['last_name']:
            user.last_name = form.cleaned_data['last_name']
        student = Student.objects.get(user=user)
        if form.cleaned_data['school']:
            student.school = form.cleaned_data['school']
        if form.cleaned_data['major']:
            student.major = form.cleaned_data['major']
        
        if form.cleaned_data['picture']:
            url = s3_upload(form.cleaned_data['picture'], student.id)
            student.picture_url = url
            student.save()
        student.save()
        user.save()
        

        # form = EditForm(instance=entry)
        context['message'] = 'Profile updated.'
        context['profile'] = profile
        context['form'] = form
        context['first_name'] = user.first_name
        context['last_name'] = user.last_name
        context['user_id'] = request.user.id
        context['classes'] = Student.objects.get(user=request.user).classes.all()
        context['picture_url'] = student.picture_url
        #return render(request, 'socialnetwork/profile.html', context)

        return redirect('/socialnetwork/profile/' + str(request.user.id))
    except Student.DoesNotExist:
        print 'FUCK'
        context = { 'message': 'Record with id={0} does not exist'.format(id) }
        return render(request, 'socialnetwork/edit.html', context)

@login_required
def map(request):
    # Sets up list of just the logged-in user's (request.user's) items
    return home(request)
    user_id = request.user.id
    student = Student.objects.get(user=request.user)
    return render(request, 'socialnetwork/map.html', {'user_id' : user_id, "classes" : student.classes.all(), "notifications" : student.notifications})

@login_required
@transaction.atomic
def add_class(request):
    try:
        student = Student.objects.get(user=request.user)
        classObj = Classroom.objects.get(name=request.POST['course_id'])
        classObj.students.add(student)
        return change_class(request, classObj)
    except Classroom.DoesNotExist:
        new_class = Classroom(name=request.POST['course_id'])
        new_class.save()
        student = Student.objects.get(user=request.user)
        new_class.students.add(student)
        instructions = "Welome to the Class. No Posts exist yet. Add some posts using the button on the left!"
        post = Post(text=instructions, title="Instructions")
        post.classroom = new_class
        post.student = student
        post.upvotes = 0
        post.save()
        new_class.save()
        return change_class(request, new_class)
	# if not (Classroom.objects.filter(name=request.POST['course_id']).count):
	# 	new_class = Classroom(name=request.POST['course_id'])
	# 	new_class.save()
	# 	new_class.students.add(student)
	# 	return redirect(reverse('home'))
	# student = Student.objects.get(user=request.user)
	# classObj = Classroom.objects.get(name=request.POST['course_id']).students.add(student)
	# return redirect(reverse('home'))


@login_required
@transaction.atomic
def remove_class(request, name):
    student = Student.objects.get(user = request.user)
    classObj = Classroom.objects.get(name=name)
    classObj.students.remove(student)
    classObj.save()
    return map(request)

@login_required
@transaction.atomic
def add_post(request, name):
    errors = []
    form = PostForm(request.POST, request.FILES)
    if(form.is_valid()):
        post = Post(text=form.cleaned_data['text'], title=form.cleaned_data['title'])
        student = Student.objects.get(user=request.user)
        classroom = Classroom.objects.get(name=name)
        post.classroom = classroom
        post.student = student
        post.upvotes = 0
        post.save()
        if form.cleaned_data['attachment']:
            url = s3_upload(form.cleaned_data['attachment'], post.id)
            post.attachment_url = url
            if form.cleaned_data['attachment_name']:
                post.attachment_name = form.cleaned_data['attachment_name']
            else:
                post.attachment_name = post.title
            post.save()
        return show_post(request, post.id)
    else:
        print 'FORM NOT VALID'
    return change_class(request, name)

@login_required
@transaction.atomic
def add_comment(request, id):
    errors = []
    form = CommentForm(request.POST)
    post = Post.objects.get(id=id)
    student = Student.objects.get(user=request.user)
    #form.cleaned_data["text"]
    form.is_valid()
    new_comment = Comment(text=form.cleaned_data["text"], student=student, upvotes=0)
    new_comment.save()
    post.comments.add(new_comment)
    post.save()
    class_name = post.classroom

    # Notification function
    notif_text = request.user.get_full_name() + " commented on your post"
    notif_link = '/socialnetwork/show_post/' + str(post.id)
    notify(request, post.student.id, notif_text, notif_link)

    return show_post(request, post.id)

@login_required
@transaction.atomic
def friend(request, id):
    user = get_object_or_404(User, id=id)
    student = Student.objects.get(user=request.user)
    prof_student = Student.objects.select_for_update().get(user=user)
    prof_student.friends.add(student)
    prof_student.save()

    #Notification function
    notif_text = request.user.get_full_name() + " has friended you!"
    notif_link = '/socialnetwork/profile/' + str(request.user.id)
    notify(request, id, notif_text, notif_link)
    return redirect('/socialnetwork/profile/' + str(user.id))
    
@login_required
@transaction.atomic
def unfriend(request, id):
    user = get_object_or_404(User, id=id)
    student = Student.objects.get(user=request.user)
    prof_student = Student.objects.select_for_update().get(user=user)
    prof_student.friends.remove(student)
    prof_student.save()

    return redirect('/socialnetwork/profile/' + str(user.id))

@login_required
@transaction.atomic
def notify(request, id, notif_text, notif_link):
    print "NOTIFICATION AHHH"    
    picture_url = Student.objects.get(user=request.user).picture_url
    new_notification = Notification(text=notif_text, link=notif_link, picture_url=picture_url)
    new_notification.save()
    user = get_object_or_404(User, id=id)
    prof_student = Student.objects.select_for_update().get(user=user)
    prof_student.notifications.add(new_notification)
    return

@login_required
@transaction.atomic
def clear_notifications(request):
    print "TRUUUU"
    student = Student.objects.get(user=request.user)
    student.notifications.all().delete()
        
    return HttpResponse()
