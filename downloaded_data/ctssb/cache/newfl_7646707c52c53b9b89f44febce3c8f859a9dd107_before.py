from django.shortcuts import render
from django.http import HttpResponse
from django.template import RequestContext, loader
from .models import Newman, Oldmen, SHB
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout, login, authenticate
# Create your views here.
def logout_view(request):
	logout(request)
	context = {}
	return render(request, 'registration/logout.html', context)
def login_view(request):
	username = request.POST['username']
	password = request.POST['password']
	user = authenticate(username=username, password=password)
	all_newmen_list = Newman.objects.all()
	newmen_point_list = all_newmen_list.order_by('-points')[:10]
	context = {	'all_newmen_list': all_newmen_list, 'newmen_point_list': newmen_point_list}
	if user:
		login(request, user)
		return render(request, 'shb/newfl.html', context)
	else:
		return render(request, 'registration/login.html', context)
@login_required
def home(request):
	all_newmen_list = Newman.objects.all()
	newmen_point_list = all_newmen_list.order_by('-points')[:10]
	context = {	'all_newmen_list': all_newmen_list, 'newmen_point_list': newmen_point_list}
	return render(request, 'shb/newfl.html', context)
@login_required
def mySHB(request):
	full_name = request.user.get_full_name()
	team_list = []
	person = None
	for oldmen in Oldmen.objects.all():
			if full_name == oldmen.team_owner:
				team_list = oldmen.newman_set.all()
				person = oldmen
				person.team_total()
	for newman in team_list:
		newman.section()
	for each_new in Newman.objects.all():
		thing.calc_points()
	ww_list = team_list.filter(woodwind=True)
	sax_list = team_list.filter(saxophone=True)
	hb_list = team_list.filter(highbrass=True)
	lb_list = team_list.filter(lowbrass=True)
	p_list = team_list.filter(perc=True)
	context = {'team_list': team_list, 'person': person, 'ww_list': ww_list, 'sax_list':sax_list, 'hb_list': hb_list, 'lb_list':lb_list, 'p_list':p_list}
	return render(request, 'shb/mySHB.html', context)
@login_required
def standings(request):
	oldmen_list = Oldmen.objects.order_by('-team_points')
	person = None
	full_name = request.user.get_full_name()
	for oldmen in oldmen_list:
		if full_name == oldmen.team_owner:
			person = oldmen
	context = {'oldmen_list': oldmen_list, 'person': person}
	return render(request, 'shb/standings.html', context)
@login_required
def freeagents(request):
	free_agents = Newman.objects.filter(owner = None)
	context = {'free_agents': free_agents}
	for newman in Newman.objects.all():
		newman.section()
	return render(request, 'shb/freeagents.html', context)
@login_required
def oldman_detail(request, oldman_id):
	oldman = Oldmen.objects.filter(id=oldman_id)[0]
	context  = {'oldman': oldman}
	return render(request, 'shb/oldman_detail.html', context)
@login_required
def add(request, newman_id):
	full_name = request.user.get_full_name()
	for oldmen in Oldmen.objects.all():
			if full_name == oldmen.team_owner:
				person = oldmen
	person.add_newman(newman_id)
	return mySHB(request)
def remove(request, newman_id):
	full_name = request.user.get_full_name()
	for oldmen in Oldmen.objects.all():
			if full_name == oldmen.team_owner:
				person = oldmen
	person.remove_newman(newman_id)
	return mySHB(request)
