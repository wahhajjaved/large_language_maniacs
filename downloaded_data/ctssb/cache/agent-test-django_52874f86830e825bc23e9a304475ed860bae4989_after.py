# encoding: utf-8
'''
Created on 2015-05-05

@author: xiaowei
'''

from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from utils.helper import encrypt
import hashlib
import requests
# import urllib
# import urllib2


def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        print request.POST
        user = authenticate(username=username, password=password)
        print user
        if user is not None:
            print user.is_active
            if user.is_active:
                login(request, user)
                print reverse('home')
                return redirect(reverse('home'))
            else:
                return render(request, 'login.html',
                              {'error_msg': u'The user is not active.'})
        else:
            return render(request, 'login.html',
                          {'error_msg': u'Username or Password is error.'})
    else:
        return render(request, 'login.html', {})


def user_logout(request):
    logout(request)
    return redirect(reverse('login'))


@login_required
def home(request):
    url = 'http://10.18.103.31:8888/api/home/agent-user-login/'
    params = "email=%s&phone=%s&uid=%s&uname=%s" % ('test@test.com', 13312341234, request.user.id, request.user.username)
    private_key = settings.PRIVATE_KEY
    sign = hashlib.md5('%s%s' % (params, private_key)).hexdigest()
    signed_request = "%s.%s" % (sign, encrypt(params, private_key))
    data = {'signed_request': signed_request}
    # params = urllib.urlencode(params)
    # req = urllib2.Request(url, params)
    # # urllib2.urlopen(req)
    # response = urllib2.urlopen(req)
    # result = response.read()
    r = requests.post(url, data=data)
    print r.text
    return render(request, 'home.html', {})
