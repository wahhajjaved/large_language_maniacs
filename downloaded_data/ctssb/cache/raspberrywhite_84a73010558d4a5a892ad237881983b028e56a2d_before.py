from django.contrib import auth
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as logout_user
from django.core import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.shortcuts import render
from django_sse.redisqueue import RedisQueueView
from django_sse.redisqueue import send_event

from server import models
import json

def logout(request):
    logout_user(request)
    return HttpResponseRedirect("/accounts/login/")

def login(request):
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        next_page = request.POST.get('next', '/playlist')
        user = auth.authenticate(username=username, password=password)
        if user is not None and user.is_active:
            models.Player.objects.get_or_create(user=user)
            auth.login(request, user)
            return HttpResponseRedirect(next_page)
        else:
            return HttpResponseRedirect("/account/invalid/")
    else:
        next_page = request.GET.get('next', '/playlist')
        return render(request, 'server/login.html', {'next':next_page})

def register(request):
    if request.method == 'POST':
        firstname = request.POST.get('firstname', '')
        lastname = request.POST.get('lastname', '')
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        try:
            User.objects.get(username=username)
        except:
            user = User.objects.create_user(username=username,
                                    password=password, first_name=firstname,
                                    last_name=lastname)
            user.save()
            models.Player.objects.get_or_create(user=user)
        return render(request, 'server/login.html')
    return render(request, 'server/register.html')

@login_required
def search_songs(request):
    if request.method == 'GET':
        page = request.GET.get('page')
        q = request.GET.get('term', '')
        songs = models.Song.songs.query(q)
        paginator = Paginator(songs, 2)
        try:
            songs = paginator.page(page)
        except PageNotAnInteger:
            songs = paginator.page(1)
        except EmptyPage:
            songs = paginator.page(paginator.num_pages)
        paginated_results = {'total_pages' : paginator.num_pages}
        results = []
        for song in songs:
            song_json = {}
            song_json['id'] = song.pk
            song_json['artist'] = song.artist
            song_json['title'] = song.title
            results.append(song_json)
        paginated_results['results'] = results
        data = json.dumps(paginated_results)
        return HttpResponse(data, 'application/json')

@login_required
def get_current_playlist(request):
    if request.method == 'GET':
        requests = models.Request.requests.all()
        results = []
        for request in requests:
            song_json = {}
            song_json['artist'] = request.song.artist
            song_json['title'] = request.song.title
            song_json['now_play'] = request.now_play
            results.append(song_json)
        data = json.dumps(results)
    else:
        data = 'fail'
    mimetype = 'application/json'
    return HttpResponse(data, mimetype)

@login_required
def playlist(request):
    return render(request, 'server/playlist.html')

@login_required
def songrequest(request):
    if request.method == 'POST':
        id_song = request.POST.get('id_song', 123)
        song = models.Song.songs.get(pk=id_song)
        if song.can_play():
            return HttpResponse(json.dumps({'status':'Song recently played'}),
                'application/json', status=405)
        song.play()
        user = models.Player.objects.get_or_create(user=request.user)[0]
        models.Request.requests.create(user=user, song=song)
        send_event('newsong', "ok", channel="foo")
        return HttpResponse(json.dumps({'status':'{0} added!'.format(song.title)}),
            'application/json', status=201)
    elif request.method == 'GET':
        return render(request, 'server/request.html')

def get_next_song(request):
    if request.method == 'GET':
        try:
            next_request = models.Request.requests.next()
        except ObjectDoesNotExist:
            return HttpResponse(json.dumps({'status':'Request not found'}),
                'application/json', status=404)
        path = next_request.song.path
        send_event('newsong', "ok", channel="foo")
        return HttpResponse(json.dumps({'path':path}), 'application/json')

class SSE(RedisQueueView):
    def get_redis_channel(self):
        ch = self.redis_channel
        return ch
