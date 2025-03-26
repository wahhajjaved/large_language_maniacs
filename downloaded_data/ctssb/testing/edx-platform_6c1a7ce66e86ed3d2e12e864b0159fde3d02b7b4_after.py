# Create your views here.
from djangomako.shortcuts import render_to_response, render_to_string
from django.shortcuts import redirect
import os
from django.conf import settings
from django.http import Http404

def index(request, page=0): 
    if not request.user.is_authenticated():
        return redirect('/')
    return render_to_response('staticbook.html',{'page':int(page)})
