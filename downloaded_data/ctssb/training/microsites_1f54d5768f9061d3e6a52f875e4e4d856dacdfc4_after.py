# encoding=utf-8

import json
import re

from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from dict2xml import dict2xml
from django.core.paginator import EmptyPage, PageNotAnInteger
from microsite.digg_paginator import FlynsarmyPaginator

from microsite.views import DEFAULT_IDS
from microsite.models import Project
from microsite.decorators import project_required
from microsite.barcode import b64_qrcode
from microsite.formhub import (submit_xml_forms_formhub,
                               ErrorUploadingDataToFormhub,
                               ErrorMultipleUploadingDataToFormhub)
from microsite.bamboo import Bamboo, get_bamboo_dataset_id, get_bamboo_url

from soillab.spid_ssid import generate_ssids
from soillab.result_logic import soil_results

DEFAULT_PROJECT = Project.objects.get(slug='soildoc')


@project_required(guests=DEFAULT_PROJECT)
def samples_list(request, search_string=None):
    context = {}

    lookup = request.GET.get('lookup', None)

    # for now, look up will just forward to detail view
    if lookup:
        return sample_detail(request, lookup.strip())

    # init bamboo with user's URL
    project = request.user.project
    bamboo = Bamboo(get_bamboo_url(project))
    main_dataset = get_bamboo_dataset_id(project)

    submissions_list = bamboo.query(main_dataset, 
                                    cache=True, cache_expiry=60 * 15)
    submissions_list.sort(key=lambda x: x['end'], reverse=True)

    from pprint import pprint as pp ; pp(submissions_list)

    paginator = FlynsarmyPaginator(submissions_list, 20, adjacent_pages=2)

    page = request.GET.get('page')
    try:
        submissions = paginator.page(page)
    except PageNotAnInteger:
        submissions = paginator.page(1)
    except EmptyPage:
        submissions = paginator.page(paginator.num_pages)

    context.update({'samples': submissions,
                    'lookup': lookup})

    return render(request, 'samples_list.html', context)


@project_required(guests=DEFAULT_PROJECT)
def sample_detail(request, sample_id):
    context = {}

    project = request.user.project
    bamboo = Bamboo(get_bamboo_url(project))
    main_dataset = get_bamboo_dataset_id(project)
    try:
        sample = bamboo.query(main_dataset,
                              query={'sample_id_sample_barcode_id': sample_id},
                              last=True, cache=True, cache_expiry=2592000)
    except:
        try:
            sample = bamboo.query(main_dataset, last=True,
                                  query={'sample_id_sample_manual_id': 
                                  sample_id},
                                  cache=True, cache_expiry=2592000)
        except:
            raise Http404(u"Requested Sample (%(sample)s) does not exist." 
                          % {'sample': sample_id})

    from collections import OrderedDict
    sorted_sample = OrderedDict([(key, sample[key]) for key in sorted(sample.iterkeys())])

    from pprint import pprint as pp ; pp(sample)

    results = soil_results(sample)

    context.update({'sample': sorted_sample,
                    'results': results})
    
    return render(request, 'sample_detail.html', context)


def idgen(request, nb_ids=DEFAULT_IDS):

    context = {'category': 'idgen'}

    # hard-coded max number of IDs to gen.
    try:
        nb_ids = 100 if int(nb_ids) > 100 else int(nb_ids)
    except ValueError:
        nb_ids = DEFAULT_IDS

    all_ids = []
    
    # for i in xrange(0, nb_ids):
    for ssid in generate_ssids('NG'):
        # this is a tuple of (ID, B64_QRPNG)
        all_ids.append((ssid, b64_qrcode(ssid)))

    context.update({'generated_ids': all_ids})

    return render(request, 'idgen.html', context)


@require_POST
@csrf_exempt
def form_splitter(request, project_slug='soildoc'):
    ''' Master XForm to Sub XFrom

        1. Receives a grouped JSON POST from formhub containing A-Z sample data
        2. Extract and transform data for each sample into a new XForm
        3. Submits the resulting XForms to formhub. '''

    # we need a project to guess formhub URL
    try:
        project = Project.objects.get(slug=project_slug)
    except:
        project = Project.objects.all()[0]

    try:
        jsform = json.loads(request.raw_post_data)
    except:
        return HttpResponse(u"Unable to parse JSON data", status=400)

    def field_splitter(field):
        match = re.match(r'.*_([a-h])$', field)
        if match:
            try:
                suffix = match.groups()[0]
            except:
                suffix = None
            if suffix:
                field = field.rsplit('_%s' % suffix, 1)[0]
            return (field, suffix)
        else:
            return (field, None)

    # name of a field which if None marks the form as empty
    # we don't submit empty forms to formhub.
    # must be a suffixed field!
    AVAIL_SUFFIXES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    # empty_trigger = 'sample_id_$$/sample_manual_id_$$'

    # map field suffixes with IDs in holder
    # we exclude forms with no data on trigger field so it won't be process
    # nor sent to formhub
    indexes = [l for l in AVAIL_SUFFIXES 
                 if (jsform.get('sample_id_$$/sample_barcode_id_$$'.replace('$$', l), None) 
                     or jsform.get('sample_id_$$/sample_manual_id_$$'.replace('$$', l), None))]

    # initialize holder for each form]
    forms = [{'single_letter': l} for l in indexes]

    for field, value in jsform.iteritems():
        # if fields ends in a-h, only add it to the specified form
        target_field, target_suffix = field_splitter(field)

        if target_suffix in indexes:
            # retrieve suffix, form and build target field (without suffix)
            form = forms[indexes.index(target_suffix)]

            # handle group field differently (parent holding the fields)
            if '/' in target_field:
                group, real_field = target_field.split('/', 1)
                real_group, group_suffix = field_splitter(group)
                if not real_group in form:
                    form[real_group] = {}
                form[real_group].update({real_field: value})
            else:
                form.update({target_field: value})
        # otherwise, it's a common field, add to all
        else:
            for form in forms:
                # handle group field differently (parent holding the fields)
                if '/' in target_field:
                    group, real_field = target_field.split('/', 1)
                    real_group, group_suffix = field_splitter(group)
                    if not real_group in form:
                        form[real_group] = {}
                    form[real_group].update({real_field: value})
                else:
                    form.update({target_field: value})

    del(jsform)

    # we now have a list of json forms each containing their data.
    def json2xform(jsform):
        # changing the form_id to XXX_single
        dd = {'form_id': u'%s_single' % jsform.get(u'_xform_id_string')}
        xml_head = u"<?xml version='1.0' ?><%(form_id)s id='%(form_id)s'>" % dd
        xml_tail = u"</%(form_id)s>" % dd

        for field in jsform.keys():
            # treat field starting with underscore are internal ones.
            # and remove them
            if field.startswith('_'):
                jsform.pop(field)
        
        return xml_head + dict2xml(jsform) + xml_tail

    xforms = [json2xform(forms[indexes.index(i)].copy()) for i in indexes]

    try:
        submit_xml_forms_formhub(project, xforms, as_bulk=False)
    except (ErrorUploadingDataToFormhub, 
            ErrorMultipleUploadingDataToFormhub) as e:
        return HttpResponse(u"%(intro)s\n%(detail)s" 
                            % {'intro': e,
                               'detail': e.details()}, status=502)
    except Exception as e:
        return HttpResponse(str(e), status=500)

    return HttpResponse('OK', status=201)