from django.shortcuts import render
import os
import datetime
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search

# Create your views here.

es = Elasticsearch([os.environ['ESURI']])

def index(request):
	yesterdayindex = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d-") + '*'

	allscanscount = Search(using=es, index=yesterdayindex).query().count()

	scantypecount = len(es.indices.get_alias(yesterdayindex))

	s = Search(using=es, index=yesterdayindex).query().source(['domain'])
	domainmap = {}
	for i in s.scan():
	        domainmap[i.domain] = 1
	domaincount = len(domainmap)

	context = {
		'num_domains': domaincount,
		'num_scantypes': scantypecount,
		'num_scans': allscanscount,
	}
	return render(request, "index.html", context=context)

def search(request):
	query = request.GET.get('q')
	scantype = request.GET.get('scantype')
	date = request.GET.get('date')

	if date == None:
		index = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d-") + '*'
	else:
		index = date

	s = Search(using=es, index=index).query()
	context = {
		'search_results': s,
		'scantypes': XXX,
		'dates': XXX,
	}
	return render(request, "search.html", context=context)
