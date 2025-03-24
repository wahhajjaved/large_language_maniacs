from django.urls import reverse
from django.views.generic import TemplateView
from django.shortcuts import render, redirect
from django.core import serializers
import annotator

import os
import json

data_dir = 'tmp' # the directory store texts 
dump_file = 'annotation.json'
log_file = 'log'
if os.path.isfile(log_file) :
    log = json.load(open(log_file, 'r'))
else:        
    log = {}

def paper_annotate(request, paper_name):
    log[paper_name]['visited'] += 1
    file = os.path.join(data_dir, paper_name)
    texts = []
    with open(file, 'r') as f:
        for line in f:
            texts.append({'text':line})
    return render(request, 'paper.html', {'texts': texts})


def dump_db(request):
    qs = annotator.models.Annotation.objects.all()
    qs_json = serializers.serialize('json', qs)
    json.dump(qs_json, open(dump_file, 'w'))
    return redirect(reverse('index'))

def index(request):
    '''
    Scan data_dir and display file names
    '''
    files = [name for name in os.listdir(data_dir) if not name.startswith(".")]
    papers, texts = [], []
    for file in files:
        try:
            gene, variance = file.split('with')
        except:
            gene, variance = '<unk>', '<unk>'
        if file not in log.keys():
            log[file] = { 'name': file,
                          'visited':0,
                          'gene': gene,
                          'variance': variance
                          }
        papers.append(log[file])
    return render(request, 'index.html', {'papers':papers})
        
        

class DemoView(TemplateView):
    template_name = "demo.html"

