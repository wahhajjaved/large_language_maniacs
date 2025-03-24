# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime

from django.shortcuts import render

# Create your views here.


def index(request):
    return render(request, 'index.html')

def history(request):
    return render(request, 'history.html')

def trust(request):
    return render(request, 'trust.html')

def water(request):
    return render(request, 'water.html')

def news(request):
    return render(request, 'news.html')

def location(request):
    return render(request, 'location.html')

def wildlife(request):
    return render(request, 'wildlife.html')
