# encoding=utf-8

import json
import re

from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from dict2xml import dict2xml

from microsite.views import DEFAULT_IDS
from microsite.models import Project
from microsite.decorators import project_required
from microsite.barcode import b64_qrcode
from microsite.formhub import (submit_xml_forms_formhub,
                               ErrorUploadingDataToFormhub,
                               ErrorMultipleUploadingDataToFormhub)
from soillab.spid_ssid import generate_ssids


@project_required
def samples_list(request, search_string=None):
    context = {}

    return render(request, 'samples_list.html', context)


@project_required
def sample_detail(request, sample_id):
    context = {}
    
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

    # map field suffixes with IDs in holder
    indexes = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    # initialize holder for each form]
    forms = [{} for x in indexes]

    for field, value in jsform.iteritems():
        # if fields ends in a-h, only add it to the specified form
        match = re.match(r'.*_([a-h])$', field)
        if match:
            # retrieve suffix, form and build target field (without suffix)
            target_suffix = match.groups()[0]
            form = forms[indexes.index(target_suffix)]
            target_field = field.rsplit('_%s' % target_suffix, 1)[0]

            # handle group field differently (parent holding the fields)
            if '/' in field:
                group, real_field = target_field.split('/', 1)
                if not group in form:
                    form[group] = {}
                form[group].update({real_field: value})
            else:
                form.update({field: value})
        # otherwise, it's a common field, add to all
        else:
            for form in forms:
                # handle group field differently (parent holding the fields)
                if '/' in field:
                    group, real_field = field.split('/', 1)
                    if not group in form:
                        form[group] = {}
                    form[group].update({real_field: value})
                else:
                    form.update({field: value})

    del(jsform)

    # we now have a list of json forms each containing their data.
    def json2xform(jsform):
        # changing the form_id to XXX_single
        xml_head = (u"<?xml version='1.0' ?>"
               u"<%(form_id)s id='%(form_id)s'>"
               # u"<formhub><uuid>%(form_uuid)s</uuid></formhub>" 
               % {'form_id': u'%s_single' % jsform.get(u'_xform_id_string')})
        xml_tail = u"</%(form_id)s>"

        for field in jsform.keys():
            # treat field starting with underscore are internal ones.
            # and remove them
            if field.startswith('_'):
                jsform.pop(field)
        
        return xml_head + dict2xml(jsform) + xml_tail

    xforms = [json2xform(form.copy()) for form in forms]

    try:
        submit_xml_forms_formhub(project, xforms, as_bulk=True)
    except (ErrorUploadingDataToFormhub, 
            ErrorMultipleUploadingDataToFormhub) as e:
        with open('/tmp/toto.txt', 'w') as f:
            f.write(u"EE %(intro)s\n%(detail)s" % {'intro': str(e), 
                                                'detail': e.details()})
        return HttpResponse(u"%(intro)s\n%(detail)s" 
                            % {'intro': e,
                               'detail': e.details()}, status=502)
    except Exception as e:
        with open('/tmp/toto.txt', 'w') as f:
            f.write(str(e))
            f.write(e.message)
            f.write('\n\n'.join(xforms))
        return HttpResponse('FAIL', status=500)
        
    with open('/tmp/toto.txt', 'w') as f:
        f.write('success')
    return HttpResponse('OK', status=201)