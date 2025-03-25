# -*- coding: utf-8 -*-

# Import django libs
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response,render
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.template import RequestContext
from django.contrib.sessions.models import Session

# Import tools
from itertools import chain
from haystack.query import SearchQuerySet
import datetime
import mimetypes
from unicodedata import normalize

from tastypie.models import ApiKey

# Import openNews datas
from forms import *
from models import *


# Define your views here

def home(request):
	"""The default view"""
	# sess = request.session['_auth_user_id']
	foo = request.GET
	user = request.user
	categories = Category.objects.all()
	return render(request, "index.html", locals())


def login_user(request):
	"""The view for login user"""
	# Already logged In ? => go Home
	if request.user.is_authenticated():
		return HttpResponseRedirect("/")

	# If you come from login required page, get the page url in "next"
	next = request.GET.get('next')

	# If form had been send
	if len(request.POST) > 0:
		# make a login form with the POST values
		form = login_form(request.POST)
		
		if form.is_valid():
			# If form is valid, try to authenticate the user with the POST datas
			s_user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password'])

			if s_user is not None:
				# If the user exist, log him
				login(request, s_user)
				request.session['user_id'] = s_user.id
				if next is not None:
					# If you come from a login required page, redirect to it
					return HttpResponseRedirect(next)
				else:
					# Else go Home
					return HttpResponseRedirect("/")
			else:
				# If user does not exist, return to the login page & send the next params et the formular
				return render_to_response("login.html", {'form': form, 'next':next}, context_instance=RequestContext(request))
		else:
			# If form is not valid, return to the login page & send the next params et the formular
			return render_to_response("login.html", {'form': form, 'next':next}, context_instance=RequestContext(request))
	else:
		# If form is not send, it's the first visit.
		# Make an empty login form and send it to login template
		form = login_form()
		return render_to_response("login.html", {'form': form, 'next':next}, context_instance=RequestContext(request))


def logout_user(request):
	"""The view for logout user"""
	logout(request)
	return HttpResponseRedirect('/')


def register(request):
	"""The views for register new user"""
	# If form had been send
	if len(request.POST) > 0:
		# make a user registration form with the POST values
		form = user_create_form(request.POST)
		
		if form.is_valid():
			# If form is valid, create and try to authenticate the user with the POST datas
			user = form.save()
			# Get the password from the POST values
			pwd = form.cleaned_data['password1']
			# Try to authenticate the user
			s_user = authenticate(username=user.username, password=pwd)
			if s_user is not None:
				# If user exist, log him and go to his account management panel
				login(request, s_user)
				return HttpResponseRedirect('preferences')
			else:
				# if he does not exist, return to user registration page with form filled by the POST values
				return render_to_response("register.html", {'form': form}, context_instance=RequestContext(request))
		else:
			# if form is not valid, return to registration page
			return render_to_response("register.html", {'form': form}, context_instance=RequestContext(request))
	else:
		# if its you first visit, make an empty user registration form and send it
		form = user_create_form()
		return render_to_response("register.html", {'form': form}, context_instance=RequestContext(request))



@login_required(login_url='/login/') # You need to be logged for this page
def preferences(request):
	"""The view where logged user can modify their property"""
	api_key = ApiKey.objects.filter(user=request.user)
	if len(api_key) == 0:
		api_key = ApiKey(user=request.user)
		api_key.save()
	else:
		api_key = api_key[0]

	# If form had been send
	if len(request.POST) > 0:
		# make a user preference form with the POST values
		form = user_preferences_form(request.POST)
		
		if form.is_valid():
			# If form is valid, save the user preferences and go Home
			form.save(request.user)
			return HttpResponseRedirect('/')
		else:
			# If not, send the preference form and the post datas
			return render_to_response("preferences.html", {'form': form, 'api_key': api_key}, context_instance=RequestContext(request))
	else:
		# if the form is not send try to find the member from the logged user
		try:
			member = request.user.member
		except Member.DoesNotExist:
			member = None
		
		if member is not None:
			# if member is not none, create preference form with user's datas
			form = user_preferences_form(instance=request.user.member)
			return render_to_response("preferences.html", {'form': form, 'api_key': api_key}, context_instance=RequestContext(request))
		else:
			# If member does not exist, send an empty form
			form = user_preferences_form()
			return render_to_response("preferences.html", {'form': form, 'api_key': api_key}, context_instance=RequestContext(request))	



def get_profile(request, userId):
	"""Show the public profile of a user. Get it by his id"""
	user = User.objects.filter(id=userId)[0]
	return render_to_response("public_profile.html", {'user': user})



def read_article(request, IDarticle):
	"""The view for reading an article"""
	# Get the article from the IDarticle params
	article = Article.objects.get(id=IDarticle)
	# Get the tags of the article
	tags = article.tags.all()
	if article.media:
		# If there is a media linked to the article, get the mime of it and the type of media
		mime = mimetypes.guess_type(article.media.url)[0]
		mediaType = mime[0:3]
	else:
		# If there is not, set False to mime et mediaType
		mime = False
		mediaType = False
	return render_to_response("article.html", {'article': article, 'mediaType': mediaType, 'mime': mime, 'tags': tags})


@login_required(login_url='/login/') # You need to be logged for this page
def write_article(request):
	"""The view for writing an article"""
	# Get the member from the request user
	member = Member.objects.get(user=request.user)

	# If form had been send
	if len(request.POST) > 0:
		# make a article form with the POST values
		form = article_form(request.POST, request.FILES)		
		if form.is_valid():
			# save the tags
			tags = request.POST['tagInput'].split(',')
			# If the form is correctly filled, check the geoloc status of the author
			if member.geoloc is not False:
				# Get coord from POST (an hidden input from template, filled by js)
				coordonnee = request.POST['coordonnee']
				# Save the article with the coord
				article = form.save(m_member=member, coord=coordonnee)
			else:
				# Save the article without the coord
				article = form.save(m_member=member)
			for tag in request.POST['tagInput'].split(','):
				if tag.isdigit():
					tagQuery = Tag.objects.get(id=tag)
					article.tags.add(tagQuery)
				else:
					qs = Tag(tag=tag)
					qs.save()
					article.tags.add(qs)
			article.save()
			return HttpResponseRedirect('/categories')
		else:
			# If it's not valid, send the form with POST datas
			return render_to_response("write.html", {'form': form, 'member':member}, context_instance=RequestContext(request))
	else:
		# If it's not valid, send an empty form
		form = article_form()
		return render_to_response("write.html", {'form': form, 'member':member}, context_instance=RequestContext(request))



def list_article(request, categorie):
	"""The view for listing the articles, depends on categorie"""
	# Get the category and put the name in a list
	categoriesQuerySet = Category.objects.all()
	categories = []
	for cat in categoriesQuerySet:
		categories.append(cat)
	
	if not Category.objects.filter(url=categorie):
		return render_to_response("liste.html", {'categories': categories, 'error': "Cette catégorie n'existe pas"})

	# Filter articles by category name
	if categorie == "all":
		articles = Article.objects.all()
		catActive = False
	else:
		articles = Article.objects.filter(category=Category.objects.filter(url=categorie)) # Here, .title() is to put the first letter in upperCase
		catActive = categorie

	# Return the articles list, the categories list and the active categorie
	return render_to_response("liste.html", {'articles': articles, 'categories': categories, 'catActive': catActive})

# def search(request, words, categorie):
# 	"""The search view"""
# 	categoriesList = Category.objects.all()
# 	categories = []
# 	for cat in categoriesList:
# 		categories.append(cat.name)

	
# 	if len(request.POST) > 0:
# 		form = searchForm(request.POST)
# 		if form.is_valid():
# 			words = form.cleaned_data['searchWords'].split(' ')
# 		else:	
# 			return render_to_response("search.html", {'form': form, 'categories': categories, 'catActive': categorie.title()})
# 	else:
# 		form = searchForm()
# 		words = words.split('_')

# 	articles = []

# 	if categorie == "all":
# 		for word in words:
# 			articles = list(chain(articles, Article.objects.filter(Q(title__contains = word) | Q(text__contains = word))))
# 			tmp = Tag.objects.filter(tag = word )
# 			if len(tmp) is not 0:
# 				articles += tmp[0].article_set.all()

# 	else:
# 		for word in words:
# 			articles = list(chain(articles, Article.objects.filter(Q(category=Category.objects.filter(name=categorie.title())) & (Q(title__contains = word) | Q(text__contains = word)) )))
# 			tmp = Tag.objects.filter(tag = word)
# 			if len(tmp) is not 0:
# 				articles += tmp[0].article_set.all()
			

# 	return render_to_response("search.html", {'form': form, 'words': words, 'articles': list(set(articles)), 'categories': categories, 'catActive': categorie.title()})


