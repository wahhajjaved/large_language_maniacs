import os
from urllib import urlencode

from django.conf import settings
from django.shortcuts import render, render_to_response
from django.http import HttpResponse, Http404
from django.core.paginator import Paginator, InvalidPage, EmptyPage, PageNotAnInteger
from django.template import RequestContext
from django.shortcuts import redirect

from oxex.models import DocTitle, Doc, Bibliography, SourceDescription, DocSearch
from oxex.forms import DocSearchForm

from eulcommon.djangoextras.http.decorators import content_negotiation
from eulexistdb.query import escape_string
from eulexistdb.exceptions import DoesNotExist
 
def docs(request):
  docs =DocTitle.objects.only('id', 'title', 'date', 'author').order_by('date')
  number_of_results = 26
  context = {}

  if 'subject' in request.GET:
    context['subject'] = DocTitle.objects.only('id', 'title', 'date', 'author').order_by('date')
  
  docs_paginator = Paginator(list(docs), number_of_results)
  try:
    page = int(request.GET.get('page', '1'))
  except ValueError:
    page = 1
  try:
    docs_page = docs_paginator.page(page)
  except (EmptyPage, InvalidPage):
    docs_page = docs_paginator.page(paginator.num_pages)

  context['docs_paginated'] = docs_page
  return render_to_response('docs.html', context, context_instance=RequestContext(request))
  #return render(request, 'docs.html', {'docs_paginated' : docs_page, 'context':context})
  #context_instance=RequestContext(request)

def doc_display(request, doc_id):
  "Display the contents of a single document."
  if 'keyword' in request.GET:
    search_terms = request.GET['keyword']
    url_params = '?' + urlencode({'keyword': search_terms})
    highlighter = {'highlight': search_terms}
  else:
    url_params = ''
    highlighter = {}   
  try:
    #doc = DocTitle.objects.get(id__exact=doc_id)
    doc = DocTitle.objects.filter(**highlighter).get(id=doc_id)
    format = doc.xsl_transform(filename=os.path.join(settings.BASE_DIR, '..', 'oxex', 'xslt', 'form.xsl'))
    return render(request, 'doc_display.html', {'doc': doc, 'format': format.serialize()})
  except DoesNotExist:
    raise Http404

def doc_xml(request, doc_id):
  "Display the original TEI XML for a single document."
  try:
    doc = DocTitle.objects.get(id__exact=doc_id)
    xml_tei = doc.serialize(pretty=True)
    #return render(request, 'doc_xml.html', {'doc':doc, 'xml_tei':xml_tei}, content_type="tei+xml")
    return render(request, 'doc_xml.html', {'doc':doc})
  except DoesNotExist:
    raise Http404

def doc_down(request, doc_id):
  "Download the original TEI XML for a single document."
  try:
    doc = DocTitle.objects.get(id__exact=doc_id)
    xml_tei = doc.serialize(pretty=True)
    return HttpResponse(xml_tei, mimetype='application/tei+xml')
  except DoesNotExist:
    raise Http404
    
def overview(request):
   "About the Oxford Experience."
   return render(request, 'overview.html')
 
def searchbox(request):
    "Search documents by keyword/title/author/date"
    form = DocSearchForm(request.GET)
    response_code = None
    context = {'searchbox': form}
    search_opts = {}
    number_of_results = 10
    
    if form.is_valid():
        if 'title' in form.cleaned_data and form.cleaned_data['title']:
            search_opts['title__fulltext_terms'] = '%s' % form.cleaned_data['title']
        if 'author' in form.cleaned_data and form.cleaned_data['author']:
            search_opts['author__fulltext_terms'] = '%s' % form.cleaned_data['author']
        if 'keyword' in form.cleaned_data and form.cleaned_data['keyword']:
            search_opts['fulltext_terms'] = '%s' % form.cleaned_data['keyword']
        if 'date' in form.cleaned_data and form.cleaned_data['date']:
            search_opts['date__fulltext_terms'] = '%s' % form.cleaned_data['date']

        docs = DocTitle.objects.only('id', 'title', 'date', 'author').filter(**search_opts).order_by('title')
        if 'keyword' in form.cleaned_data and form.cleaned_data['keyword']:
            docs = docs.only_raw(line_matches='%%(xq_var)s//text[ft:query(., "%s")]' \
                                    % escape_string(form.cleaned_data['keyword']))

        searchbox_paginator = Paginator(list(docs), number_of_results)
        try:
            page = int(request.GET.get('page', '1'))
        except ValueError:
            page = 1
        # If page request (9999) is out of range, deliver last page of results.
        try:
            searchbox_page = searchbox_paginator.page(page)
        except (EmptyPage, InvalidPage):
            searchbox_page = searchbox_paginator.page(paginator.num_pages)

        context['docs_paginated'] = searchbox_page
        context['keyword'] = form.cleaned_data['keyword']
        context['title'] = form.cleaned_data['title']
        context['author'] = form.cleaned_data['author']
        context['date'] = form.cleaned_data['date']
           
        response = render_to_response('search.html', context, context_instance=RequestContext(request))
    #no search conducted yet, default form
    else:
        response = render(request, 'search.html', {
                    "searchbox": form
            })
       
    if response_code is not None:
        response.status_code = response_code
    return response
