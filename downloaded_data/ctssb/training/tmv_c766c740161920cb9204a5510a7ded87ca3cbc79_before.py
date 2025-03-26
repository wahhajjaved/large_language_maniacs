from django.shortcuts import render, render_to_response
import os, time, math, itertools, csv, random
from itertools import chain
from django.db.models import Max
from django.db.models import Q, Count, Func, F, Sum, Value as V
from django.db.models.functions import Concat
from django.core import serializers
from django.core.serializers import serialize
import short_url
import datetime

from django.forms.models import model_to_dict

from cities.models import *
from tmv_app.models import *
# Create your views here.

from django.utils import formats

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.template import loader, RequestContext
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.decorators import user_passes_test
import json
from django.apps import apps
import difflib
from sklearn.metrics import cohen_kappa_score
from django.core import management
from django.shortcuts import render

from django_tables2 import RequestConfig

from .models import *

from .forms import *

from .tables import *

from .tasks import *
from tmv_app.tasks import *

import time

def super_check(user):
    return user.groups.filter(name__in=['superuser'])


@login_required
def switch_mode(request):

    if request.session['appmode']=='scoping':
        request.session['appmode']='snowballing'
        return HttpResponseRedirect(reverse('scoping:snowball'))
    else:
        request.session['appmode']='scoping'
        return HttpResponseRedirect(reverse('scoping:index'))



########################################################
## Homepage - list the queries, form for adding new ones


@login_required
def index(request):

    if request.method == "POST":
        newproj=ProjectForm(request.POST)
        if newproj.is_valid():
            project = newproj.save(commit=False)
            project.save()
            obj, created = ProjectRoles.objects.get_or_create(
                project=project,user=request.user)
            obj.role = "OW"
            obj.save()

    template = loader.get_template('scoping/index.html')

    myproj = Project.objects.filter(users=request.user,projectroles__role="OW")

    for p in myproj:
        p.role = ProjectRoles.objects.get(project=p,user=request.user).get_role_display()


    myproj = ProjectTable(myproj, order_by="id")
    RequestConfig(request).configure(myproj)


    newproj= ProjectForm()

    acproj = Project.objects.filter(users=request.user)
    for p in acproj:
        p.role = ProjectRoles.objects.get(project=p,user=request.user).get_role_display()

    pids = acproj.values_list('id',flat=True)

    update_projs.delay(list(pids))

    acproj = ProjectTable(acproj, order_by="id")
    RequestConfig(request).configure(acproj)

    context = {
        'myproj': myproj,
        'acproj': acproj,
        'newproj': newproj
    }

    return HttpResponse(template.render(context, request))

@login_required
def project(request, pid):
    deleteForm = ValidatePasswordForm(user=request.user)
    delete = "hidden"
    p = Project.objects.get(pk=pid)
    if request.method == "POST":
        if "role" in request.POST:
            form=ProjectRoleForm(request.POST)
            if form.is_valid() :
                print(form.data)
                u = form.cleaned_data['user']
                role = form.cleaned_data['role']
                obj, created = ProjectRoles.objects.get_or_create(
                    project_id=pid,user=u)
                obj.role = role
                obj.save()
        else:
            form = ValidatePasswordForm(request.POST,user=request.user)
            if form.is_valid():
                up = ProjectRoles.objects.get(user=request.user,project=p)
                if up.role in ["OW","AD"]:
                    p.delete()
                    return HttpResponseRedirect(reverse('scoping:index'))
            else:
                deleteForm = form
                delete = ""


            #print("delete")


    template = loader.get_template('scoping/project.html')

    p = Project.objects.get(pk=pid)
    ars = ['OW','AD']
    try:
        if ProjectRoles.objects.get(project=p,user=request.user).role in ars:
            admin="true"
        else:
            admin="false"
    except:
        return HttpResponseRedirect(reverse('scoping:index'))

    updateRoles = []
    projUsers = User.objects.filter(project=p)
    for u in projUsers:
        ur = ProjectRoles.objects.get(project=p,user=u).role
        f = ProjectRoleForm(initial={'user': u, 'role': ur})
        f.fields["user"].queryset = User.objects.filter(pk=u.id)
        updateRoles.append(f)
        u.f = f
        u.queries = Query.objects.filter(
            creator=u,
            project=p
        ).count()
        u.ratings = u.docownership_set.filter(
            relevant__gt=0,
            query__project=p
        ).count()

    newRole = ProjectRoleForm()
    newRole.fields["user"].queryset = User.objects.exclude(
        id__in=projUsers.values_list('id',flat=True)
    )

    queries = Query.objects.filter(
        project=p
    )
    if queries.count() == 0:
        queries = Query.objects.all()

    query = queries.last()



    context = {
        'newRole': newRole,
        'delete': delete,
        'deleteForm': deleteForm,
        'updateRoles': updateRoles,
        'admin': admin,
        'project': p,
        'projectUsers': projUsers,
        'query': query,
        'qid': query.id
    }

    return HttpResponse(template.render(context, request))


@login_required
def queries(request, pid):
    request.session['DEBUG'] = False
    request.session['appmode']='scoping'

    template = loader.get_template('scoping/queries.html')

    if int(pid) == 0:
        queries = Query.objects.filter(
            project__isnull=True
        ).order_by('-id')

        users = User.objects.all().order_by('username')

        technologies  = Technology.objects.all()
        p = None

    else:
        p = Project.objects.get(pk=pid)

        queries = Query.objects.filter(
            project=p,
            creator=request.user
        ).order_by('-id')
        users = User.objects.filter(
            projectroles__project=p
        ).order_by('username')

        technologies  = Technology.objects.filter(
            project=p
        )

    query = queries.last()

    if query is None:
        query = Query.objects.last()

    for q in queries:
        q.tech = q.technology
        if q.technology==None:
            q.tech="None"
        else:
            q.tech=q.technology.name
        #print(q.tech)

    if request.user.username in ["galm","rogers","nemet"]:
        extended=True
    else:
        extended=False


    context = {
      'queries'      : queries,
      'query'        : query,
      'users'        : users,
      'active_users' : users.filter(username=request.user.username),
      'techs'        : technologies,
      'appmode'      : request.session['appmode'],
      'extended'     : extended,
      'innovations'  : Innovation.objects.all(),
      'project'      : p,
    }

    return HttpResponse(template.render(context, request))

@login_required
def query_table(request, pid):
    template = loader.get_template('scoping/snippets/query_table.html')
    p = Project.objects.get(pk=pid)

    users = request.GET.getlist('users[]',None)
    techs = request.GET.getlist('techs[]',None)
    if 'None' in techs:
        techs = [t for t in techs if t !='None']
        queries = Query.objects.filter(
            project=p,
            creator__id__in=users
        ).filter(
            Q(technology__isnull=True) | Q(technology__in=techs)
        ).order_by('-id')
    else:
        queries = Query.objects.filter(
            project=p,
            creator__id__in=users,
            technology__in=techs
        ).order_by('-id')

    technologies  = Technology.objects.filter(
        project=p
    )




    context = {
      'queries': queries,
      'project': p,
      'techs': technologies
    }

    return HttpResponse(template.render(context, request))


########################################################
## Tech Homepage - list the technologies, form for adding new ones

@login_required
def technologies(request, pid):

    template = loader.get_template('scoping/tech.html')

    project = Project.objects.get(pk=pid)


    if request.method=="POST":
        catform = CategoryForm(request.POST)
        if catform.is_valid():
            x = catform
            cat = catform.save()
            cat.project = project
            cat.save()


    technologies = Technology.objects.filter(project=pid).order_by('id')

    users = User.objects.all()
    refresh = False
    update_techs.delay(project.id)
    #subprocess.Popen(["python3", "/home/galm/software/tmv/BasicBrowser/update_techs.py"], stdout=subprocess.PIPE)
    for t in technologies:
        t.queries = t.query_set.count()
        tdocs = Doc.objects.filter(technology=t)
        if refresh==True:
            tdocs = Doc.objects.filter(technology=t)
            itdocs = Doc.objects.filter(query__technology=t,query__type="default")
            tdocs = tdocs | itdocs
            t.docs = tdocs.distinct().count()
            t.nqs = t.queries
            t.ndocs = t.docs
            t.save()
        else:
            t.docs = t.ndocs
        t.form = CategoryForm(instance=t)

    catform = CategoryForm()

    context = {
      'techs'    : technologies,
      'users'    : users,
      'project'  : project,
      'form'     :  catform
    }

    return HttpResponse(template.render(context, request))

########################################################
## edit query technology or innovation
@login_required
def update_thing(request):
    thing1 = request.GET.get('thing1', None)
    thing2 = request.GET.get('thing2', None)
    id1 = request.GET.get('id1', None)
    id2 = request.GET.get('id2', None)
    method = request.GET.get('method', None)

    try:
        t1 = apps.get_model(
            app_label='scoping',model_name=thing1
        ).objects.get(pk=id1)
    except:
        t1 = None

    if id2=="None":
        t2 = None
    else:
        try:
            t2 = apps.get_model(
                app_label='scoping',model_name=thing2
            ).objects.get(pk=id2)
        except:
            t2 = id2

    if method=="add":
        getattr(t1,thing2.lower()).add(t2)
    if method=="remove":
        getattr(t1,thing2.lower()).remove(t2)
    if method=="update":
        setattr(t1,thing2.lower(),t2)

    t1.save()
    return HttpResponse()

########################################################
## Snowballing homepage
@login_required
def snowball(request):
    request.session['DEBUG'] = True
    request.session['appmode']='snowballing'

    template        = loader.get_template('scoping/snowball.html')

    # Get SBS information
    sb_sessions     = SnowballingSession.objects.all().order_by('-id')

    # Get latest step associated with each SB sessions
    sb_session_last = sb_sessions.last()

    for sbs in sb_sessions:
        try:
            sb_qs = sbs.query_set.all().order_by('id')
            seedquery = sb_qs.first()
            step  = "1"
            nbdocsel = 0
            nbdoctot = 0
            nbdocrev = 0
            sbs.ns = sb_qs.aggregate(Max('step'))['step__max']
            sbs.lq = sb_qs.last().id
            sbs.rc = sb_qs.last().r_count
            sbs.ndsel = Doc.objects.filter(docownership__query__snowball=sbs,docownership__relevant=1).distinct().count()
            sbs.ndtot = DocRel.objects.filter(seedquery=seedquery).count()
            sbs.ndrev = Doc.objects.filter(docownership__query__snowball=sbs,docownership__relevant=0).distinct().count()
        except:
            pass
            # Get technologies

    technologies = Technology.objects.all()

    context = {
        'sb_sessions'    : sb_sessions,
        'sb_session_last': sb_session_last,
        'techs'          : technologies
    }
    return HttpResponse(template.render(context, request))


########################################################
## Add the technology
@login_required
def add_tech(request):
    tname = request.POST['tname']
    tdesc  = request.POST['tdesc']
    pid = int(request.POST['pid'])
    #  create a new query record in the database
    t = Technology(
        name=tname,
        description=tdesc,
        project_id=pid
    )
    t.save()
    return HttpResponseRedirect(reverse('scoping:technologies', kwargs={"pid": pid}))

########################################################
## update the technology
@login_required
def update_tech(request,tid):
    t = Technology.objects.get(pk=tid)
    form = CategoryForm(request.POST,instance=t)
    if form.is_valid():
        t = form.save()
    return HttpResponseRedirect(reverse('scoping:technologies', kwargs={'pid': t.project.id}))



#########################################################
## Do the query
import subprocess
import sys
@login_required
def doquery(request, pid):

    #ssh_test()

    qtitle = request.POST['qtitle']
    qdb    = request.POST['qdb']
    qtype  = request.POST['qtype']
    qtext  = request.POST['qtext']

    p = Project.objects.get(pk=pid)

    pr = ProjectRoles.objects.get(project=p,user=request.user).role

    if pr in ['OW', 'AD']:
        admin = True
    else: # STOP! and go back with a good message
        admin = False
        return HttpResponseRedirect(reverse('scoping:queries', kwargs={'pid': pid}))

    #  create a new query record in the database
    q = Query(
        title=qtitle,
        type=qtype,
        text=qtext,
        project=p,
        creator = request.user,
        date = timezone.now(),
        database = qdb
    )
    q.save()

    # Do internal queries
    if qdb=="intern":
        args = qtext.split(" ")
        # Original one for combining qs
        if "manually uploaded" in qtext:
            print("manually uploaded")
        elif args[1].strip() in ["AND", "OR", "NOT"]:
            q1 = set(Doc.objects.filter(query=args[0]).values_list('id',flat=True))
            op = args[1]
            q2 = set(Doc.objects.filter(query=args[2]).values_list('id',flat=True))
            if op =="AND":
                ids = q1 & q2
            elif op =="OR":
                ids = q1 | q2
            elif op == "NOT":
                ids = q1 - q2
            combine = Doc.objects.filter(id__in=ids)
        else:
            # more complicated filters
            if args[0].strip()=="*":
                q1 = Doc.objects.all()
                q1ids = None
                cids = q1ids
            else:
                q1 = Doc.objects.filter(query=args[0])
                q1ids = q1.values_list('id',flat=True)
                cids = q1ids
            for a in range(1,len(args)):
                parts = args[a].split(":")
                print(parts)
                # Deal WITH tech filters
                if parts[0] == "TECH":
                    tech, tdocs, tobj = get_tech_docs(parts[1])
                    tids = tdocs.values_list('id',flat=True)
                    if q1ids is not None:
                        cids = list(set(q1ids).intersection(set(tids)))
                    else:
                        cids = tids
                    q1ids = cids
                    combine = Doc.objects.filter(pk__in=cids)
                # Deal with relevance filters
                if parts[0] == "IS":
                    if parts[1] == "RELEVANT":
                        combine = Doc.objects.filter(
                            pk__in=cids,
                            docownership__relevant=1
                        ) | Doc.objects.filter(
                            pk__in=cids,
                            technology__isnull=False
                        )
                    if parts[1] == "TRELEVANT":
                        combine = Doc.objects.filter(
                            pk__in=cids,
                            docownership__relevant=1,
                            docownership__query__technology=tobj
                        ) | Doc.objects.filter(
                            pk__in=cids,
                            technology=tobj
                        )


        for d in combine.distinct('id'):
            d.query.add(q)
        q.r_count = len(combine.distinct('id'))
        q.save()

        return HttpResponseRedirect(reverse('scoping:doclist', kwargs={'pid': pid, 'qid': q.id }))


    else:
        # write the query into a text file
        fname = "/queries/"+str(q.id)+".txt"
        with open(fname,encoding='utf-8',mode="w") as qfile:
            qfile.write(qtext.encode("utf-8").decode("utf-8"))


        time.sleep(1)

    # run "scrapeQuery.py" on the text file in the background
    if request.user.username=="galm":
        subprocess.Popen(["python3", "/home/galm/software/scrapewos/bin/scrapeQuery.py","-lim","200000","-s", qdb, fname])
    else:
        subprocess.Popen(["python3", "/home/galm/software/scrapewos/bin/scrapeQuery.py","-s", qdb, fname])

    return HttpResponseRedirect(reverse(
        'scoping:querying',
        kwargs={'qid': q.id, 'substep': 0, 'docadded': 0, 'q2id': 0}
    ))

#########################################################
## Start snowballing
import subprocess
import sys
@login_required
def start_snowballing(request):

    # Get form content
    qtitle = request.POST['sbs_name']
    qtext  = request.POST['sbs_initialpearls']
    qdb    = request.POST['qdb']
    qtech  = request.POST['sbs_technology']

    curdate = timezone.now()

    # Get technology
    t = Technology.objects.get(pk=qtech)

    # Create new snowballing session
    sbs = SnowballingSession(
      name = qtitle,
      database = qdb,
      initial_pearls = qtext,
      date=curdate,
      status=0,
      technology=t
    )
    sbs.save()
    if request.session['DEBUG']:
        print("start_snowballing: New SBS successfully created.")


    #  create 2 new query records in the database (one for the bakward search and one for the forward search)
    q = Query(
        title=qtitle+"_backward_1_1",
        database=qdb,
        type='backward',
        text=qtext,
        date=curdate,
        snowball=sbs,
        step=1,
        substep=1,
        technology=t
    )
    q.save()
    if request.session['DEBUG']:
        print("start_snowballing: New backward query #"+str(q.id)+" successfully created.")

    # write the query into a text file
    fname = "/queries/"+str(q.id)+".txt"
    with open(fname,"w") as qfile:
        qfile.write(qtext)

    # run "scrapeQuery.py" on the text file in the background
    if request.session['DEBUG']:
        print("start_snowballing: starting scraping process on "+q.database+" (backward query).")
    subprocess.Popen(["python3", "/home/galm/software/scrapewos/bin/scrapeQuery.py","-s", qdb, fname])

    #####
    ## This bit starts up the forward snowballing

    q2 = Query(
        title=qtitle+"_forward_1_2",
        database=qdb,
        type='forward',
        text=qtext,
        date=curdate,
        snowball=sbs,
        step=1,
        substep=2,
        technology=t
    )
    q2.save()
    if request.session['DEBUG']:
        print("start_snowballing: New forward query #"+str(q2.id)+" successfully created.")

    # write the query into a text file
    fname = "/queries/"+str(q2.id)+".txt"
    with open(fname,"w") as qfile:
        qfile.write(qtext)

    time.sleep(1)

    # run "scrapeQuery.py" on the text file in the background
    if request.session['DEBUG']:
        print("start_snowballing: starting scraping process on "+q2.database+" (forward query).")
    subprocess.Popen(["python3", "/home/galm/software/scrapewos/bin/snowball_fast.py", "-s", qdb, fname])

    return HttpResponseRedirect(reverse('scoping:snowball_progress', kwargs={'sbs': sbs.id}))

#########################################################
## Start snowballing
import subprocess
import sys
@login_required
def do_snowballing(request,qid,q2id):

    #ssh_test()

    curdate = timezone.now()

    # Backward query
    # Get current query
    query_b = Query.objects.get(id=qid)

    qtitle  = str.split(query_b.title,"_")[0]
    qtype   = 'backward'
    qstep   = query_b.step
    qdb     = "WoS"
    sbsid   = query_b.snowball

    # Generate query from selected documents
    #TODO: Tag?
    docs    = DocOwnership.objects.filter(query_id=qid, user_id=request.user, relevant=1)
    docdois = []
    for doc in docs:
        docdoi = WoSArticle.objects.get(doc_id=doc.doc_id)
        docdois.append(docdoi.di)
    doiset  = set(docdois)
    if (len(doiset) > 0):
        # Generate query
        qtext   = 'DO = ("' + '" OR "'.join(doiset) + '")'

        print(qtext)

        #  create a new query record in the database
        q_b = Query(
            title=qtitle+"_backward_"+str(qstep+1)+"_1",
            database=qdb,
            type=qtype,
            text=qtext,
            date=curdate,
            snowball=sbsid,
            step=qstep+1,
            substep=1
        )
        q_b.save()

        qid = q_b.id

        # write the query into a text file
        fname = "/queries/"+str(q_b.id)+".txt"
        with open(fname,"w") as qfile:
            qfile.write(qtext)

        time.sleep(1)

        # run "scrapeQuery.py" on the text file in the background
        p_b = subprocess.Popen(["python3", "/home/galm/software/scrapewos/bin/scrapeQuery.py","-s", qdb, fname])

        #return HttpResponseRedirect(reverse('scoping:querying', kwargs={'qid': q.id, 'substep': 1, 'docadded': 0, 'q2id': 0}))

    else :
        p_b = subprocess.Popen(["ls"])
        qid = 0
        print("No document to do backward query.")
        #return HttpResponseRedirect(reverse('scoping:query', kwargs={'qid': q.id}))


    # Forward query
    # Get current query
    query_f = Query.objects.get(id=q2id)

    qtitle  = str.split(query_f.title,"_")[0]
    qtype   = 'forward'
    qstep   = query_f.step
    qdb     = "WoS"
    sbsid   = query_f.snowball

    # Generate query from selected documents
    #TODO: Tag?
    docs    = DocOwnership.objects.filter(query_id=q2id, user_id=request.user, relevant=1)
    docdois = []
    for doc in docs:
        docdoi = WoSArticle.objects.get(doc_id=doc.doc_id)
        docdois.append(docdoi.di)
    doiset  = set(docdois)
    if (len(doiset) > 0):
        # Generate query
        qtext   = 'DO = ("' + '" OR "'.join(doiset) + '")'

        print(qtext)

        #  create a new query record in the database
        q_f = Query(
            title=qtitle+"_forward_"+str(qstep+1)+"_2",
            database=qdb,
            type=qtype,
            text=qtext,
            date=curdate,
            snowball=sbsid,
            step=qstep+1,
            substep=1
        )
        q_f.save()


        # write the query into a text file
        fname = "/queries/"+str(q_f.id)+".txt"
        with open(fname,"w") as qfile:
            qfile.write(qtext)

        time.sleep(1)

        # run "scrapeQuery.py" on the text file in the background
        p_f = subprocess.Popen(["python3", "/home/hilj/python_apsis_libs/scrapeWoS/bin/snowball_fast.py","-s", qdb, fname])

        q2id = q_f.id

    else :
        p_f = subprocess.Popen(["ls"])
        q2id = 0
        print("No document to do forward query.")

    exit_codes = [p.wait() for p in [p_b, p_f]]

    return HttpResponseRedirect(reverse('scoping:querying', kwargs={'qid': qid, 'substep': 1, 'docadded': 0, 'q2id': q2id}))



#########################################################
## Delete the query
@login_required
def delete_query(request, qid):
    try:
        q = Query.objects.get(pk=qid)
        q.delete()
        title = str(qid.id)
        shutil.rmtree("/queries/"+title)
        os.remove("/queries/"+title+".txt")
        os.remove("/queries/"+title+".log")
    except:
        pass
    return HttpResponseRedirect(reverse('scoping:index'))

#########################################################
## Delete the query
@login_required
def delete_tag(request, qid, tid):
    try:
        t = Tag.objects.get(pk=tid)
        t.delete()
    except:
        pass
    return HttpResponseRedirect(reverse('scoping:query', kwargs={'qid': qid}))

#########################################################
## Delete the query
@login_required
def delete_sbs(request, sbsid):
    try:
        sbs = SnowballingSession.objects.get(pk=sbsid)

        # Get associated queries
        qs = Query.objects.filter(snowball=sbsid)

        # Delete SB session
        sbs.delete()

        # Delete asociated queries and files
        #TODO: Could be better handled by cascade function in postgres DB
        for qid in qs :
            q = Query.objects.get(pk=qid)
            q.delete()

            title = str(qid)
            shutil.rmtree("/queries/"+title)
            os.remove("/queries/"+title+".txt")
            os.remove("/queries/"+title+".log")
    except:
        pass
    return HttpResponseRedirect(reverse('scoping:snowball'))

#########################################################
## Add the documents to the database
@login_required
def dodocadd(request,qid):
    q = Query.objects.get(pk=qid)

    if q.dlstat != "NOREC":
        management.call_command('upload', qid, True, 1)
        time.sleep(2)

    #return HttpResponse(upload)
    return HttpResponseRedirect(reverse('scoping:querying', kwargs={'qid': qid}))

#########################################################
## Page views progress of query scraping
@login_required
def querying(request, qid, substep=0, docadded=0, q2id=0):

    template = loader.get_template('scoping/query_progress.html')

    query = Query.objects.get(pk=qid)

    # How many docs are there already added?
    doclength = Doc.objects.filter(query__id=qid).count()

    if doclength == 0: # if we've already added the docs, we don't need to show the log
        logfile = "/queries/"+str(query.id)+".log"

        wait = True
        # wait up to 15 seconds for the log file, then go to a page which displays its contents
        for i in range(10):
            try:
                with open(logfile,"r") as lfile:
                    log = lfile.readlines()
                break
            except:
                log = ["oops, there seems to be some kind of problem, I can't find the log file. Try refreshing a couple of times before you give up and start again."]
                time.sleep(1)

        finished = False
        if "done!" in log[-1]:
            finished = True
    else:
        log=False
        finished=True

    context = {
        'log': log,
        'finished': finished,
        'doclength': doclength,
        'query': query,
        'project': query.project
    }

    return HttpResponse(template.render(context, request))

def snowball_progress(request,sbs):
    template = loader.get_template('scoping/snowball_progress.html')
    do_backward_query = False
    do_forward_query  = False
    stop = False

    sbs = SnowballingSession.objects.get(id=sbs)

    sqs = sbs.query_set.all()

    a = sqs.values()

    seed_query = sqs.get(type='backward',step=1,substep=1)

    # Query 1: Backward / References
    # Check if query is defined
    try:
        query_b = sqs.filter(type='backward').last()
        if query_b.database.lower() == "scopus":
            rfile = "s_results.txt"
        do_backward_query = True

        logfile_b = "/queries/"+str(query_b.id)+".log"
        rstfile_b = "/queries/"+str(query_b.id)+"/"+rfile
        if request.session['DEBUG']:
            print("querying: (backward query) logfile -> "+str(logfile_b)+", result file -> "+str(rstfile_b))
    except:
        query_b = 0

    # Query 2: Forward / Citations
    try:
        query_f = sqs.filter(type='forward').last()
        do_forward_query  = True

        logfile_f = "/queries/"+str(query_f.id)+".log"
        rstfile_f = "/queries/"+str(query_f.id)+"/results.txt"
        if request.session['DEBUG']:
            print("querying: (forward query) logfile -> "+str(logfile_f)+", result file -> "+str(rstfile_f))
    except:
        query_f = 0

    finished   = False
    finished_b = False
    finished_f = False

    request.session['DEBUG'] = False

    if do_backward_query and do_forward_query:
        if request.session['DEBUG']:
            print("querying: Default case with backward query #"+str(query_b.id)+" and forward query #"+str(query_f.id))

        # Check if query result files exist
        if request.session['DEBUG']:
            print("querying: check existence of result files:")
            print("querying:   - backward query rstfile_b -> "+str(os.path.isfile(rstfile_b)))
            print("querying:   - forward query rstfile_f -> "+str(os.path.isfile(rstfile_f)))
        if not os.path.isfile(rstfile_b) and not os.path.isfile(rstfile_f):
            if request.session['DEBUG']:
                print("querying: waiting for query processes to finish.")
            wait = True
            # wait up to 15 seconds for the log file, then go to a page which displays its contents
            for i in range(2):
                try:
                    with open(logfile_b,"r") as lfile:
                        log_b = lfile.readlines()
                    break
                except:
                    log_b = ["oops, there seems to be some kind of problem, I can't find the log file. Try refreshing a couple of times before you give up and start again."]
                    time.sleep(1)

            if query_f.dlstat == "done":
                log_f = ["Citations were all captured in the first substep."]
            else :
                for i in range(2):
                    try:
                        with open(logfile_f,"r") as lfile:
                            log_f = lfile.readlines()
                        break
                    except:
                        log_f = ["oops, there seems to be some kind of problem, I can't find the log file. Try refreshing a couple of times before you give up and start again."]
                        time.sleep(1)

        else:
            if request.session['DEBUG']:
                print("querying: query result files have already been created.")
            with open(logfile_b,"r") as lfile:
                log_b = lfile.readlines()
            with open(logfile_f,"r") as lfile:
                log_f = lfile.readlines()

        ## Check backwards query log for errors or success
        if "couldn't find any records" in log_b[-1]:
            finished_b = True
            query_b.dlstat = "done"
        elif "done!" in log_b[-1]:
            finished_b = True
            query_b.dlstat = "NOREC"
        query_b.save()

        ## Check forwards query log for errors or success
        if "couldn't find any records" in log_f[-1]:
            finished_f = True
            query_f.dlstat = "done"
        elif "done!" in log_f[-1]:
            finished_f = True
            query_f.dlstat = "NOREC"
        query_f.save()

        if request.session['DEBUG']:
            print("querying: finished_b -> "+str(finished_b)+", finished_f -> "+str(finished_f))

        if finished_b == True and finished_f == True:
            finished = True

        # If queries have finished properly then go to next substep directly
        if finished:
            if sqs.count() == 2:
                print("Creating a new query")
                # Create query '2' the next backwards one
                query_b2 = Query(
                    title=str.split(query_b.title, "_")[0]+"_backward_"+str(query_b.step)+"_"+str(query_b.substep+1),
                    database=query_b.database,
                    type="backward",
                    text="",
                    date=timezone.now(),
                    snowball=query_b.snowball,
                    step=query_b.step,
                    substep=query_b.substep+1
                )
                query_b2.save()
                sbs.working = False

        if query_b.text == '':
            branch = Query.objects.get(
                snowball=sbs,step=query_b.step,substep=query_b.substep-1
            )
            log_b = ["Busy checking the references and citations of {} against the database and keywords".format(branch.title)]
            if sbs.working == False:
                background = os.path.abspath(os.path.join(os.path.dirname(__file__),'..','proc_docrefs_scopus.py'))
                subprocess.Popen(["python3", background, str(seed_query.id), str(query_b.id), str(query_f.id)])
                sbs.working = True
                sbs.save()


        if query_b.text !='' and sbs.working == True and os.path.isfile("/queries/"+str(query_b.id)+"/s_results.txt") and query_b.doc_set.all().count() == 0: # if we have scraped all the refs
            log_b = ["Busy checking the references of {} against the database and keywords".format(query_b.title)]
            background = os.path.abspath(os.path.join(os.path.dirname(__file__),'..','proc_docrefs_scopus.py'))
            subprocess.Popen(["python3", background, str(seed_query.id), str(query_b.id), str(0)])
            sbs.working = True
            sbs.save()

        if sbs.working_pb2:
            log_b = ["Busy checking the references of {} against the database and keywords".format(query_b.title)]

        qsum = None
        t = None
        #sqs.filter(type='step_summary').delete()
        if query_b.doc_set.all().count() > 0 and sbs.working==False:
            log_b = ["FINISHED"]
            stop = True
            if sqs.filter(type='step_summary').count() == 0:
                qsum = Query(
                    title=str.split(query_b.title, "_")[0]+"_summary_"+str(query_b.step),
                    database=query_b.database,
                    type="step_summary",
                    text="",
                    date=timezone.now(),
                    snowball=query_b.snowball,
                    step=query_b.step
                )
                qsum.save()
                t = Tag(
                    title = str.split(query_b.title, "_")[0]+"_summary_"+str(query_b.step),
                    text = "",
                    query = qsum
                )
                t.save()
                B2docs = Doc.objects.filter(document__seedquery=seed_query, document__relation=-1,document__indb__gt=0,document__docmatch_q=True).exclude(document__sametech=1)
                F2docs = Doc.objects.filter(document__seedquery=seed_query, document__relation=1,document__indb__gt=0,document__docmatch_q=True)
                C1docs = B2docs | F2docs
                for doc in C1docs:
                    doc.query.add(qsum)
                    doc.tag.add(t)
            else:
                qsum = sqs.filter(type='step_summary').first()
                t = qsum.tag_set.all()[0]


    ## Scrape a query if it needs to be scraped
    if sqs.count() == 3:
        query_b2 = query_b
        if query_b2.text != '': # if the text has been written
            if not os.path.isfile("/queries/"+str(query_b2.id)+"/s_results.txt"): # and there's no file
                log_b = ["Downloading the references from {}".format(query_b2.title)]
                if not sbs.working: # And we're not doing something in the background
                    sbs.working = True
                    sbs.save()
                    fname = "/queries/"+str(query_b2.id)+".txt"
                    with open(fname,encoding='utf-8',mode='w') as qfile:
                        qfile.write(query_b2.text)
                        subprocess.Popen(["python3", "/home/galm/software/scrapewos/bin/scrapeQuery.py", "-s", query_b2.database, fname])

    if not do_backward_query or not do_forward_query:
        if request.session['DEBUG']:
            print("querying: No documents to perform backward or forward queries. Going back to snowball home page...")
        return HttpResponseRedirect(reverse('scoping:snowball'))

    drs = DocRel.objects.filter(seedquery=seed_query)

    summary_stats = [
        ('B1', drs.filter(relation=-1,indb=1,sametech=1).count()),
        ('B2', drs.filter(relation=-1,indb__gt=0,docmatch_q=True).exclude(sametech=1).count()),
        ('B3', drs.filter(relation=-1,indb__gt=0,docmatch_q=False).exclude(sametech=1).count()),
        ('B4', drs.filter(relation=-1,indb=0,timatch_q=True).count()),
        ('B5', drs.filter(relation=-1,indb=0,timatch_q=False).count()),
        ('F1', drs.filter(relation=1,indb=1,sametech=1).count()),
        ('F2', drs.filter(relation=1,indb__gt=0,docmatch_q=True).count()),
        ('F3', drs.filter(relation=1,indb__gt=0,docmatch_q=False).count()),
    ]

    # DocRel.objects.filter(seedquery=599,relation=-1,indb=2,docmatch_q=True)

    C2docs = DocRel.objects.filter(seedquery=seed_query,relation=-1,indb=0,timatch_q=True).order_by('au')
    #C2docs = DocRel.objects.filter(seedquery=seed_query,relation=-1,indb=0).order_by('au')

    summary_stats.append(('C1',summary_stats[1][1]+summary_stats[6][1]))
    summary_stats.append(('C2',summary_stats[3][1]))


    fqs = sqs.filter(type='forward')
    for f in fqs:
        f.r_count = f.doc_set.all().count()

    users = User.objects.all().order_by('username')

    proj_users = users.query

    user_list = []

    if qsum is not None:

        for u in users:
            user_docs = {}
            tdocs = DocOwnership.objects.filter(query=qsum,tag=t,user=u)
            print(tdocs)
            user_docs['tdocs'] = tdocs.count()
            if user_docs['tdocs']==0:
                user_docs['tdocs'] = False
            else:
                user_docs['reldocs']         = tdocs.filter(relevant=1).count()
                user_docs['irreldocs']       = tdocs.filter(relevant=2).count()
                user_docs['maybedocs']       = tdocs.filter(relevant=3).count()
                user_docs['yesbuts']         = tdocs.filter(relevant=4).count()
                user_docs['checked_percent'] = round((user_docs['reldocs'] + user_docs['irreldocs'] + user_docs['maybedocs']) / user_docs['tdocs'] * 100)
            if qsum in u.query_set.all():
                user_list.append({
                    'username': u.username,
                    'email': u.email,
                    'onproject': True,
                    'user_docs': user_docs
                })
            else:
                user_list.append({
                    'username': u.username,
                    'email': u.email,
                    'onproject': False,
                    'user_docs': user_docs
                })

        print(user_list)

    context = {
        'log': True,
        'log_b': log_b,
        'log_f': log_f,
        'doclength': 0,
        'finished': finished,
        'query_b': query_b,
        'query_f': query_f,
        'substep':1,
        'docadded': 0,
        'summary_stats': summary_stats,
        'C2docs': C2docs,
        'fqs': fqs,
        'bqs': sqs.filter(type='backward'),
        'query': qsum,
        'tag': t,
        'users': user_list,
        'stop': stop
    }

    return HttpResponse(template.render(context, request))

############################################################
## SBS - Set default ownership to current user

@login_required
def sbs_allocateDocsToUser(request,qid,q2id):

    DEBUG = False

    #Get queries
    query_b = Query.objects.get(pk=qid)
    query_f = Query.objects.get(pk=q2id)

    if DEBUG:
        print("Getting references query: "+str(query_b.title)+" ("+str(qid)+")")
        print("Getting citations query: " +str(query_f.title)+" ("+str(q2id)+")")

    # Get associated docs
    docs_b = Doc.objects.filter(query=qid)
    docs_f = Doc.objects.filter(query=q2id)

    # Define new tag
    tag_b = Tag(
        title = "sbs_"+str(query_b.title)+"_"+str(request.user),
        text  = "",
        query = query_b
    )
    tag_b.save()
    tag_f = Tag(
        title = "sbs_"+str(query_f.title)+"_"+str(request.user),
        text  = "",
        query = query_f
    )
    tag_f.save()

    # Population Docownership table
    for doc in docs_b:
        docown = DocOwnership(
            doc      = doc,
            user     = request.user,
            query    = query_b,
            tag      = tag_b,
            relevant = 1    # Set all documents to keep status by default
        )
        docown.save()

    for doc in docs_f:
        docown = DocOwnership(
            doc      = doc,
            user     = request.user,
            query    = query_f,
            tag      = tag_f,
            relevant = 1    # Set all documents to keep status by default
        )
        docown.save()

    return HttpResponseRedirect(reverse('scoping:doclist', kwargs={'qid': query_b.id, 'q2id': query_f.id, 'sbsid': query_b.snowball}))


############################################################
## SBS - Set default ownership to current user

@login_required
def sbs_setAllQDocsToIrrelevant(request,qid,q2id,sbsid):

    DEBUG = True

    #Get query
    query_b = Query.objects.get(pk=qid)
    query_f = Query.objects.get(pk=q2id)

    if DEBUG:
        print("Getting references query: "+str(query_b.title)+" ("+str(qid)+")")
        print("Getting citations query: " +str(query_f.title)+" ("+str(q2id)+")")

    # get latest tag
    tag_b = Tag.objects.filter(query=qid).last()
    tag_f = Tag.objects.filter(query=q2id).last()

    if DEBUG:
        print("Getting references tag: "+str(tag_b.title)+" ("+str(tag_b.text)+")")
        print("Getting citations tag: "+str(tag_f.title)+" ("+str(tag_f.text)+")")

    # Get associated docs
    docs_b = DocOwnership.objects.filter(query=qid, tag=tag_b.id, user=request.user)
    docs_f = DocOwnership.objects.filter(query=q2id, tag=tag_f.id, user=request.user)
    # Population Docownership table
    for doc in docs_b:
        doc.relevant = 2
        doc.save()

    for doc in docs_f:
        doc.relevant = 2
        doc.save()

    return HttpResponseRedirect(reverse('scoping:doclist', kwargs={'qid': qid, 'q2id': q2id, 'sbsid': sbsid}))

############################################################
## Query homepage - manage tags and user-doc assignments

def query_dev(request, qid):
    template = loader.get_template('scoping/query_dev.html')
    query=Query.objects.get(pk=qid)

    tags = query.tag_set.all()
    tagtable = TagTable(tags)

    context = {
        'query':query,
        'project': query.project,
        'tags': tagtable
    }

    return HttpResponse(template.render(context, request))

@login_required
def query(request,qid,q2id='0',sbsid='0'):
    template = loader.get_template('scoping/query.html')

    if 'appmode' not in request.session:
        request.session['appmode'] = "scoping"

    if request.session['appmode'] != "snowballing":

        query = Query.objects.get(pk=qid)

        tags = Tag.objects.filter(query=query)

        tags = tags.values()

        for tag in tags:
            dt = "doc"
            tag['doctype'] = "documents"
            tdocs = Doc.objects.filter(tag=tag['id'])
            tdos = DocOwnership.objects.filter(tag=tag['id'])
            tpars = DocPar.objects.filter(tag=tag['id'])
            if tpars.count() > 0:
                tdocs = tpars
                tag['doctype'] = "paragraphs"
                dt = "docpar"
            tag['docs'] = tdocs.distinct().count()

            tag['a_docs'] = len(set(tdos.values_list(dt,flat=True)))

            if tag['a_docs'] != 0:
                tag['seen_docs']  = DocOwnership.objects.filter(tag=tag['id'],relevant__gt=0).count()
                tag['rel_docs']   = DocOwnership.objects.filter(tag=tag['id'],relevant=1).count()
                tag['irrel_docs'] = DocOwnership.objects.filter(tag=tag['id'],relevant=2).count()
                try:
                    tag['relevance'] = round(tag['rel_docs']/(tag['rel_docs']+tag['irrel_docs'])*100)
                except:
                    tag['relevance'] = 0
                tusers = User.objects.filter(docownership__tag=tag['id']).distinct()
                tag['users'] = tusers.count()
                scores = []
                for u in tusers:
                    scores.append([])
                tdocs = Doc.objects.filter(tag=tag['id']).distinct()
                for u in tusers:
                    tdocs = tdocs.filter(
                        docownership__user=u,
                        docownership__relevant__gt=0,
                        docownership__tag=tag['id']
                    )
                i = 0
                for u in tusers:
                    l = tdocs.filter(
                        docownership__user=u,
                        docownership__relevant__gt=0,
                        docownership__tag=tag['id']
                    ).distinct('pk').order_by('pk').values_list('docownership__relevant', flat=True)
                    scores[i] = list(l)
                    i+=1
                dscores = [None] + scores

                if len(scores) == 2:
                    tag['ratio'] = round(difflib.SequenceMatcher(*dscores).ratio(),2)
                    tag['cohen_kappa'] = cohen_kappa_score(*scores)
                else:
                    tag['cohen_kappa'] = "NA"
                    tag['ratio'] = "NA"

            #print(tag['ratio'])

        qusers = User.objects.filter(docownership__query=query).distinct()
        query.nusers = qusers.count()
        scores = []
        for u in qusers:
            scores.append([])
        qdocs = Doc.objects.filter(query=query).distinct()
        for u in qusers:
            qdocs = qdocs.filter(docownership__user=u,docownership__query=query)

        query.ndocs = query.r_count
        query.tms = RunStats.objects.filter(query=query).count()

        i = 0
        for u in qusers:
            l = qdocs.filter(
                docownership__user=u
            ).distinct('pk').order_by('pk').values_list('docownership__relevant', flat=True)
            scores[i] = list(l)
            i+=1
        dscores = [None] + scores


        if len(scores) == 2:
            query.ratio = round(difflib.SequenceMatcher(*dscores).ratio(),2)
            query.cohen_kappa = cohen_kappa_score(*scores)
        else:
            query.cohen_kappa = "NA"
            query.ratio = "NA"


        untagged = Doc.objects.filter(query=query).count() - Doc.objects.filter(query=query,tag__query=query).distinct().count()



        users = User.objects.filter(project=query.project)

        proj_users = users.query

        user_list = []

        for u in users:
            user_docs = {}
            tdocs = DocOwnership.objects.filter(query=query,user=u)
            user_docs['tdocs'] = tdocs.count()
            if user_docs['tdocs']==0:
                user_docs['tdocs'] = False
            else:
                user_docs['reldocs']         = tdocs.filter(relevant=1).count()
                user_docs['irreldocs']       = tdocs.filter(relevant=2).count()
                user_docs['maybedocs']       = tdocs.filter(relevant=3).count()
                user_docs['yesbuts']         = tdocs.filter(relevant=4).count()
                user_docs['checked_percent'] = round((user_docs['reldocs'] + user_docs['irreldocs'] + user_docs['maybedocs']) / user_docs['tdocs'] * 100)
            if query in u.query_set.all():
                user_list.append({
                    'username': u.username,
                    'email': u.email,
                    'onproject': True,
                    'user_docs': user_docs
                })
            else:
                user_list.append({
                    'username': u.username,
                    'email': u.email,
                    'onproject': False,
                    'user_docs': user_docs
                })

        if DocPar.objects.filter(doc__query=query).count() > 0:
            pars = True
        else:
            pars = False
        context = {
            'query': query,
            'project': query.project,
            'tags': list(tags),
            'untagged': untagged,
            'users': user_list,
            'user': request.user,
            'pars': pars
        }
    else:
        sbs    = SnowballingSession.objects.get(pk=sbsid)
        query  = Query.objects.get(pk=qid)
        query2 = Query.objects.get(pk=q2id)

        tags = Tag.objects.filter(query=query) | Tag.objects.filter(query=query2)

        tags = tags.values()

        for tag in tags:
            tag['docs']       = Doc.objects.filter(tag=tag['id']).distinct().count()
            tag['a_docs']     = Doc.objects.filter(docownership__tag=tag['id']).distinct().count()
            tag['seen_docs']  = DocOwnership.objects.filter(doc__tag=tag['id'],relevant__gt=0).count()
            tag['rel_docs']   = DocOwnership.objects.filter(doc__tag=tag['id'],relevant=1).count()
            tag['irrel_docs'] = DocOwnership.objects.filter(doc__tag=tag['id'],relevant=2).count()
            try:
                tag['relevance'] = round(tag['rel_docs']/(tag['rel_docs']+tag['irrel_docs'])*100)
            except:
                tag['relevance'] = 0

        fields = ['id','title']

        untagged = Doc.objects.filter(query=query).count() - Doc.objects.filter(query=query,tag__query=query).distinct().count() + Doc.objects.filter(query=query2).count() - Doc.objects.filter(query=query2,tag__query=query2).distinct().count()

        users = User.objects.all()

        proj_users = users.query

        user_list = []

        for u in users:
            user_docs = {}
            tdocs = DocOwnership.objects.filter(query=query,user=u) | DocOwnership.objects.filter(query=query2,user=u)
            user_docs['tdocs'] = tdocs.count()
            if user_docs['tdocs']==0:
                user_docs['tdocs'] = False
            else:
                user_docs['reldocs']         = tdocs.filter(relevant=1).count()
                user_docs['irreldocs']       = tdocs.filter(relevant=2).count()
                user_docs['checked_percent'] = round((user_docs['reldocs'] + user_docs['irreldocs']) / user_docs['tdocs'] * 100)
            if query in u.query_set.all():
                user_list.append({
                    'username': u.username,
                    'email': u.email,
                    'onproject': True,
                    'user_docs': user_docs
                })
            else:
                user_list.append({
                    'username': u.username,
                    'email': u.email,
                    'onproject': False,
                    'user_docs': user_docs
                })

        context = {
            'sbs': sbs,
            'query': query,
            'query2': query2,
            'tags': list(tags),
            'fields': fields,
            'untagged': untagged,
            'users': user_list,

            'user': request.user,
            'query_tms': RunStats.objects.filter(query=query).count()
        }


    return HttpResponse(template.render(context, request))



@login_required
def query_tm(request,qid):
    template = loader.get_template('scoping/query_tm.html')
    query = Query.objects.get(pk=qid)

    if request.method == 'POST':
        form = TopicModelForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            obj = form.save()
            obj.query = query
            #obj.method = 'NM'
            obj.save()

            do_nmf.delay(obj.run_id)

            return HttpResponseRedirect(reverse('scoping:query_tm_manager', kwargs={'qid': qid}))

        else:
            print(form.errors)
            print("INVALID")
    # if a GET (or any other method) we'll create a blank form
    else:
        form = TopicModelForm()

    context = {
        'query': query,
        'form': form,
        'project': query.project,
        'fields_1': ['min_freq','max_df','max_features','limit','ngram','fulltext','citations'],
        'fields_2': ['K','alpha','max_iterations','db'],
        'fields_3': ['method']
    }
    return HttpResponse(template.render(context, request))

@login_required
def query_tm_manager(request,qid):
    template = loader.get_template('scoping/query_tm_manager.html')
    query = Query.objects.get(pk=qid)

    tms = RunStats.objects.filter(query=query).order_by('-pk')

    table = TopicTable(tms)

    context = {
        'query': query,
        'table': table,
        'project': query.project
    }
    return HttpResponse(template.render(context, request))

@login_required
def run_model(request,run_id):

    run = RunStats.objects.get(pk=run_id)
    qid = run.query.id

    do_nmf.delay(run_id)

    return HttpResponseRedirect(reverse(
        'scoping:query_tm_manager', kwargs={'qid': qid}
    ))


##################################################
## User home page

@login_required
def userpage(request, pid):
    template = loader.get_template('scoping/user.html')

    project = Project.objects.get(pk=pid)
    # Queries
    queries = Tag.objects.filter(
        query__users=request.user,
        query__project=project
    ).values('query__id','query__type','id')

    query_list = []

    for qt in queries:
        docstats = {}
        q = Query.objects.get(pk=qt['query__id'])
        tag = Tag.objects.get(pk=qt['id'])
        docstats['ndocs'] = Doc.objects.filter(tag=tag).distinct().count()
        dos = DocOwnership.objects.filter(query=q,user=request.user,tag=tag)
        docstats['revdocs']         = dos.count()
        docstats['reviewed_docs']   = dos.filter(relevant__gt=0).count()
        docstats['unreviewed_docs'] = dos.filter(relevant=0).count()
        if request.user.profile.type=="default":
            doctypes = [1,2,3,4]
        else:
            doctypes = [5,6,7,8]
        dts = []
        for i in doctypes:
            dt = dos.filter(relevant=i).count()
            dts.append({
                "r":i,
                "n":dt
            })
        docstats['dts'] = dts
        try:
            if request.user.profile.type=="default":
                docstats['relevance'] = round(dts[0]['n']/(dts[0]['n']+dts[1]['n'])*100)
            else:
                docstats['relevance'] = round( (dts[0]['n']+dts[2]['n']) /
                (dts[0]['n']+dts[1]['n']+dts[2]['n']+dts[3]['n']) * 100 )
        except:
            docstats['relevance'] = 0

        if docstats['revdocs'] > 0:
            query_list.append({
                'id': q.id,
                'tag': tag,
                'type': q.type,
                'title': q.title,
                'docstats': docstats
            })

    query = queries.last()

    context = {
        'user': request.user,
        'queries': query_list,
        'query': query,
        'project': project
    }
    return HttpResponse(template.render(context, request))

##################################################
## Exclude docs from snowballing session
@login_required
def sbsKeepDoc(request,qid,did):

    #Set doc review to 0
    docs = DocOwnership.objects.all(doc=did, query=qid, user=request.user)

    print(docs)


    return HttpResponseRedirect(reverse('scoping:doclist', kwargs={'qid': qid, 'q2id': q2id, 'sbsid': sbsid}))

##################################################
## Exclude docs from snowballing session
@login_required
def sbsExcludeDoc(request,qid,did):

    #Set doc review to 0
    docs = DocOwnership.objects.all(doc=did, query=qid, user=request.user)

    print(docs)


    return HttpResponseRedirect(reverse('scoping:doclist', kwargs={'qid': qid, 'q2id': q2id, 'sbsid': sbsid}))

##################################################
## View all docs
@login_required
def doclist(request, pid, qid, q2id='0',sbsid='0'):

    p = Project.objects.get(pk=pid)
    template = loader.get_template('scoping/docs.html')

    print(str(qid))
    print(str(q2id))

    if qid == 0 or qid=='0':
        qid = Query.objects.all().last().id

    query = Query.objects.get(pk=qid)
    qdocs = Doc.objects.filter(query__id=qid)

    if q2id != '0' and sbsid != '0':
        #TODO: Select categories B2, B4 and F2
        query_b = Query.objects.get(pk=qid)
        query_f = Query.objects.get(pk=q2id)
        qdocs_b = Doc.objects.filter(query__id=qid)
        qdocs_f = Doc.objects.filter(query__id=q2id)
        all_docs = qdocs_b | qdocs_f
    else:
        query_f  = False
        all_docs = qdocs

    ndocs = all_docs.count()

    docs = list(all_docs[:500].values('pk','wosarticle__ti','wosarticle__ab','wosarticle__py'))


    fields = []
    basic_fields = []
    author_fields = []
    relevance_fields = []
    wos_fields = []
    basic_field_names = ['Title', 'Abstract', 'Year'] #, str(request.user)]

    relevance_fields.append({"path": "fulltext", "name": "Full Text"})
    relevance_fields.append({"path": "docfile__id", "name": "PDF"})
    relevance_fields.append({"path": "tech_technology", "name": "Technology"})
    relevance_fields.append({"path": "tech_innovation", "name": "Innovation"})
    relevance_fields.append({"path": "relevance_netrelevant", "name": "NETs relevant"})
    relevance_fields.append({"path": "relevance_techrelevant", "name": "Technology relevant"})
    relevance_fields.append({"path": "note__text", "name": "Notes"})
    relevance_fields.append({"path": "relevance_time", "name": "Time of Rating"})
    relevance_fields.append({"path": "relevance_agreement", "name": "Agreement"})
    relevance_fields.append({"path": "k", "name": "K Core"})
    relevance_fields.append({"path": "degree", "name": "Degree"})
    relevance_fields.append({"path": "eigen_cent", "name": "Eigenvector centrality"})
    relevance_fields.append({"path": "distance", "name": "Distance to Kates"})


    for f in WoSArticle._meta.get_fields():
        path = "wosarticle__"+f.name

        if f.verbose_name in basic_field_names:
            print(f.name)
            basic_fields.append({"path": path, "name": f.verbose_name})
        fields.append({"path": path, "name": f.verbose_name})
        wos_fields.append({"path": path, "name": f.verbose_name})

    for u in User.objects.filter(project=p):
        path = "docownership__"+u.username
        fields.append({"path": path, "name": u.username})
        relevance_fields.append({"path": path, "name": u.username})

    for f in DocAuthInst._meta.get_fields():
        path = "docauthinst__"+f.name
        if f.name !="doc" and f.name !="query" and f.name!="id":
            fields.append({"path": path, "name": f.verbose_name})
            author_fields.append({"path": path, "name": f.verbose_name})

    fields.append({"path": "tag__title", "name": "Tag name"})
    relevance_fields.append({"path": "tag__title", "name": "Tag name"})





    context = {
        'query': query,
        'project': query.project,
        'query2' : query_f,
        'docs': docs,
        'fields': fields,
        'basic_fields': basic_fields,
        'author_fields': author_fields,
        'relevance_fields': relevance_fields,
        'wos_fields': wos_fields,
        'ndocs': ndocs,
        'sbsid': sbsid,
        'basic_field_names': basic_field_names
    }
    return HttpResponse(template.render(context, request))



###########################################################
## List documents related to a Snowballing session
@login_required
def docrellist(request,sbsid,qid=0,q2id=0,q3id=0):

    request.session['appmode'] == "snowballing"

    template = loader.get_template('scoping/docrels.html')

    # Get snowballing session info
    sbs = SnowballingSession.objects.get(pk=sbsid)

    # Get the backward and forward queries associated with the the current SBS
    if qid == 0 or qid == '0':
        query_b1 = Query.objects.filter(type="backward", snowball=sbs.id, substep=1).last()
    else:
        query_b1 = Query.objects.get(pk=qid)
    if q2id == 0 or q2id == '0':
        query_b2 = Query.objects.filter(type="backward", snowball=sbs.id, substep=2).last()
    else:
        query_b2 = Query.objects.get(pk=q2id)
    if q3id == 0 or q3id == '0':
        query_f = Query.objects.filter(type="forward", snowball=sbs.id).last()
    else:
        query_f = Query.objects.get(pk=q3id)

    # Get all document relationships
    docrels = DocRel.objects.filter(seedquery=query_b1).order_by("relation")
    print(docrels.values("relation")[400:406])

    docs = []
    count = {}
    count['TOTAL'] = 0
    count['category1']  = 0
    count['category2']  = 0
    count['optional']  = 0
    count['discarded']  = 0
    count['B1']  = 0
    count['B2']  = 0
    count['B3']  = 0
    count['B4']  = 0
    count['B5']  = 0
    count['F1']  = 0
    count['F2']  = 0
    count['F3']  = 0

    for dr in docrels:
        count['TOTAL'] += 1
        if "a" == "a":
            tmp = {}
            tmp['title']      = dr.title
            tmp['author']     = dr.au
            tmp['py']         = dr.PY
            tmp['doi']        = dr.doi
            tmp['hasdoi']     = dr.hasdoi
            tmp['docmatch_q'] = dr.docmatch_q
            tmp['timatch_q']  = dr.timatch_q
            tmp['indb']       = dr.indb
            tmp['sametech']   = dr.sametech
            if dr.relation == -1:
                tmp['querytype']  = 'B'
            if dr.relation == 1:
                tmp['querytype']  = 'F'
            if dr.relation == 0:
                tmp['querytype']  = 'Undef'

            # Specific document category
            if (dr.relation == -1 and dr.indb == 1 and dr.sametech == 1):
                tmp['category'] = "B1"
                tmp['user_category'] = "optional"
                count['B1']  += 1
                count['optional'] += 1
            if (dr.relation == -1 and dr.indb == 1 and dr.sametech != 1 and dr.docmatch_q):
                tmp['category'] = "B2"
                tmp['user_category'] = "Category 1"
                count['B2']  += 1
                count['category1'] += 1
            if (dr.relation == -1 and dr.indb == 1 and dr.sametech != 1 and not dr.docmatch_q):
                tmp['category'] = "B3"
                tmp['user_category'] = "discarded"
                count['B3']  += 1
                count['discarded'] += 1
            if (dr.relation == -1 and dr.indb == 2 and dr.docmatch_q):
                tmp['category'] = "B4"
                tmp['user_category'] = "Category 2"
                count['B4']  += 1
                count['category2'] += 1
            if (dr.relation == -1 and dr.indb == 2 and not dr.docmatch_q):
                tmp['category'] = "B5"
                tmp['user_category'] = "discarded"
                count['B5']  += 1
                count['discarded'] += 1
            if (dr.relation == 1 and dr.indb == 1 and dr.sametech == 1 ):
                tmp['category'] = "F1"
                tmp['user_category'] = "optional"
                count['F1']  += 1
                count['optional'] += 1
            if (dr.relation == 1 and dr.indb > 0 and dr.docmatch_q):
                tmp['category'] = "F2"
                tmp['user_category'] = "Category 1"
                count['F2']  += 1
                count['category1'] += 1
            if (dr.relation == 1 and dr.indb > 0 and not dr.docmatch_q):
                tmp['category'] = "F3"
                tmp['user_category'] = "discarded"
                count['F3']  += 1
                count['discarded'] += 1

            # Get abstract when possible
            try:
                d = dr.referent
                tmp['abstract']   = d.content[0:10]
            except:
                tmp['abstract']   = "None"
            #tmp['abstract']   = "None"

            # Get document relevance when possible
            try:
                r = DocOwnership.objects.get(doc = dr.referent)
                tmp['relevant']   = r.relevant
            except:
                tmp['relevant']   = "NA"

            docs.append(tmp)
        else:
            print("you should not be there...")

    context = {
        'docs': docs,
        'count': count,
        'sbsid': sbsid,
        'query_b1': query_b1,
        'query_b2': query_b2,
        'query_f': query_f
    }

    return HttpResponse(template.render(context, request))

def create_internal_et(request,pid):

    p = Project.objects.get(pk=pid)

    et, created = EmailTokens.objects.get_or_create(
        user = request.user,
        project = p,
        email= request.user.email,
        AU = request.user.username
    )


    return HttpResponseRedirect(reverse(
        'scoping:add_doc_form', kwargs={
            'authtoken': et.id
        }
    ))

def add_doc_form(request,pid=0,authtoken=0,r=0,did=0):
    author_docs = None
    uf = None
    if int(did) > 0:
        try:
            doc = Doc.objects.get(pk=did)
        except:
            return HttpResponseRedirect(reverse(
                'scoping:add_doc_form', kwargs={
                    'authtoken':authtoken
                }
            ))
    else:
        doc = None
    try:
        project = Project.objects.get(pk=pid)
    except:
        project = None

    techs = None
    doctechs = None

    if authtoken!=0:
        em = EmailTokens.objects.get(pk=authtoken)
        if em.project is None:
            em.project = em.category.project
            em.save()
        p = em.project
        pid = p.id
        try:
            em.sname, em.initial = em.AU.split(',')
        except:
            em.sname = em.AU
            em.initial = ""

        author_docs = Doc.objects.filter(
            query__qtype='MN',
            query__upload_link=em,
            wosarticle__ti__isnull=False
        ).distinct()
        if author_docs.count()==0:
            author_docs = False

        template = loader.get_template('scoping/ext_doc_add_form.html')

        f2 = None

        if request.method == "POST":
            if "dtype" in request.POST:
                ndf = NewDoc(request.POST)
                if ndf.is_valid():
                    if ndf.cleaned_data['url'] == "":
                        url, created = URLs.objects.get_or_create(
                            url=str(uuid.uuid1())
                        )
                    else:
                        url, created = URLs.objects.get_or_create(
                            url=ndf.cleaned_data['url']
                        )
                    surl = short_url.encode_url(url.id)
                    ut, created = UT.objects.get_or_create(UT=surl)
                    if created and did is not 0:
                        doc = Doc.objects.get(pk=did)
                        doc.UT.delete()
                        doc.UT=ut
                        doc.save()
                    doc, created = Doc.objects.get_or_create(UT=ut)
                    doc.dtype=ndf.cleaned_data['dtype']
                    doc.url = ndf.cleaned_data['url']
                    doc.save()
                    wa, created = WoSArticle.objects.get_or_create(doc=doc)

                    q = Query(
                        title="uploaded_by_{}".format(em.AU),
                        type="default",
                        text="uploaded_by_{}".format(authtoken)
                    )

                    if em.user:
                        q.creator=em.user

                    if did==0:
                        q.database = "manual"
                        q.r_count = 1
                        #q.technology = t
                        q.project = p
                        q.qtype='MN'
                        q.upload_link=em
                        q.save()

                        doc.query.add(q)
                        doc.save()

                    return HttpResponseRedirect(reverse(
                        'scoping:add_doc_form', kwargs={
                            'authtoken':authtoken,
                            'did': doc.id
                        }
                    ))



            elif "so" in request.POST:
                f2 = DocForm2(request.POST,instance=doc.wosarticle)
                if f2.is_valid():
                    print("valid")
                    f2.save()
                    doc.title = doc.wosarticle.ti
                    doc.content = doc.wosarticle.ab
                    doc.PY = doc.wosarticle.py
                    doc.save()


            elif "surname" in request.POST:
                af = AuthorForm(request.POST)
                if af.is_valid():
                    dai, created = DocAuthInst.objects.get_or_create(
                        doc=doc,
                        position=af.cleaned_data['position']
                    )
                    dai.surname=af.cleaned_data['surname']
                    dai.initials=af.cleaned_data['initials']
                    dai.save()

            elif "delete" in request.POST:
                doc = Doc.objects.get(pk=did)
                if hasattr(doc,'docfile'):
                    doc.docfile.delete()

            elif "technology[]" in request.POST:
                tids = request.POST.getlist('technology[]',None)
                ts = Technology.objects.filter(pk__in=tids)
                for t in ts:
                    doc.technology.add(t)

            elif request.FILES.get('file', False):

                print("DOCCCFILE")
                doc = Doc.objects.get(pk=did)
                uf = UploadDocFile(request.POST, request.FILES)
                if uf.is_valid():
                    uf.save()
                else:
                    e = uf.errors



        #x = y
        afs = [None] * 10

        if did!=0:
            doc = Doc.objects.get(pk=did)
            d = model_to_dict(doc)
            wa = model_to_dict(doc.wosarticle)
            ndf = NewDoc(d)

            ndf.action = "Update"
            if doc.dtype=="WP":
                if wa['py'] is None:
                    wa['py'] = 0
                f2 = DocForm2(wa)
            else:
                if wa['py'] is None:
                    wa['py'] = 2017
                f2 = DocForm2(wa,so=True)

            # Do something different for book chapters
            #if doc.dtype=="BC"


            if wa['ti'] is None:
                f2.action = "Add"
            else:
                f2.action = "Update"


            if doc.wosarticle.ti is not None:
                new_author = True
                for i, af  in enumerate(afs):
                    try:
                        dai = DocAuthInst.objects.get(doc=doc,position=i+1)
                        afs[i] = AuthorForm(model_to_dict(dai))
                        afs[i].i = i+1
                        afs[i].au = dai.AU
                        afs[i].action = "Update"
                    except:
                        if new_author:
                            afs[i] = AuthorForm({
                                'position': i+1,
                                'surname': ""
                            })
                            afs[i].i = i+1
                            afs[i].action = "Add"
                            break

            dais = doc.docauthinst_set.filter(AU__isnull=False).count()

            if doc.docauthinst_set.filter(AU__isnull=False).count() > 0:
                doctechs = doc.technology.all()
                techs = Technology.objects.filter(project=p)

                if hasattr(doc,'docfile') is False:
                    u = uf is None
                    #x = y
                    if uf is None:
                        uf = UploadDocFile()
                    uf.fields["doc"].initial=did
                    uf.action="Upload"
                else:
                    df = doc.docfile
                    uf = DeleteDocField()
                    uf.fields["delete"].initial=1
                    uf.filename = df.file
                    uf.action="Delete"


            #x = y

            #f2.fields['doc'].queryset = Doc.objects.filter(id=did)

        else:
            em.clicked = em.clicked + 1
            em.save()
            ndf = NewDoc()
            ndf.action = "Add"

    forms = [ndf,f2,afs,uf,techs]

    context = {
        'author_docs': author_docs,
        'em': em,
        'ndf': ndf,
        'f2': f2,
        'afs': afs,
        'uf': uf,
        'techs': techs,
        'doctechs': doctechs,
        'project': p
    }
    #return render_to_response('scoping/ext_doc_add_form.html',context)
    return HttpResponse(template.render(context, request))

from django.contrib.postgres.aggregates import StringAgg


##################################################
## View all docs in a Snowball session
@login_required
def doclistsbs(request,sbsid):

    template = loader.get_template('scoping/docs_sbs.html')

    print(str(sbsid))

    if sbsid == 0 or sbsid=='0':
        sbsid = SnowballingSession.objects.all().last().id

    sbs = SnowballingSession.objects.get(pk=sbsid)

    all_docs = []
    queries = Query.objects.filter(snowball=sbsid)

    # Loop over queries
    for q in queries:
        # Filter out non-reference queries
        tmp = str.split(q.title,"_")
        if tmp[len(tmp)-1] == "2":
            qdocs    = Doc.objects.filter(query__id=400,docownership__relevant=1,docownership__query=400)
            #all_docs.append(qdocs.values('UT','wosarticle__ti','wosarticle__ab','wosarticle__py'))
            qdocs2 = qdocs.values('UT','wosarticle__ti','wosarticle__ab','wosarticle__py')
            for d in qdocs2:
                all_docs.append(d)

    print(type(all_docs))
    print(all_docs)

    ndocs = len(all_docs)

    print(ndocs)

    docs = all_docs
    #docs = list(all_docs[:100].values('UT','wosarticle__ti','wosarticle__ab','wosarticle__py'))

    print(len(docs))
    print(docs)


    fields = []

   # for f in Doc._meta.get_fields():
   #     if f.is_relation:
   #         for rf in f.related_model._meta.get_fields():
   #             if not rf.is_relation:
   #                 path = f.name+"__"+rf.name
   #                 fields.append({"path": path, "name": rf.verbose_name})
    for f in WoSArticle._meta.get_fields():
        path = "wosarticle__"+f.name
        if f.name !="doc":
            fields.append({"path": path, "name": f.verbose_name})

   # for f in DocOwnership._meta.get_fields():
   #     if f.name == "user":
   #         path = "docownership__user__username"
   #     else:
   #         path = "docownership__"+f.name
   #     if f.name !="doc" and f.name !="query":
   #         fields.append({"path": path, "name": f.verbose_name})

    for u in User.objects.all():
        path = "docownership__"+u.username
        fields.append({"path": path, "name": u.username})

    for f in DocAuthInst._meta.get_fields():
        path = "docauthinst__"+f.name
        if f.name !="doc" and f.name !="query":
            fields.append({"path": path, "name": f.verbose_name})

    fields.append({"path": "tag__title", "name": "Tag name"})

    basic_fields = ['Title', 'Abstract', 'Year','fulltext'] #, str(request.user)]

    context = {
        'sbs': sbs,
        'docs': docs,
        'fields': fields,
        'basic_fields': basic_fields,
        'ndocs': ndocs,
    }
    return HttpResponse(template.render(context, request))



##################################################
## Ajax function, to return sorted docs

@login_required
def sortdocs(request):

    qid  = request.GET.get('qid',None)
    q2id = request.GET.get('q2id',None)
    fields = request.GET.getlist('fields[]',None)
    field = request.GET.get('field',None)
    sortdir = request.GET.get('sortdir',None)
    extra_field = request.GET.get('extra_field',None)

    f_fields = request.GET.getlist('f_fields[]',None)
    f_operators = request.GET.getlist('f_operators[]',None)
    f_text = request.GET.getlist('f_text[]',None)
    f_join = request.GET.getlist('f_join[]',None)

    sort_dirs = request.GET.getlist('sort_dirs[]',None)
    sort_fields = request.GET.getlist('sort_fields[]',None)

    tag_title = request.GET.get('tag_title',None)
    download = request.GET.get('download',None)

    # get the query
    query = Query.objects.get(pk=qid)

    p = query.project

    # filter the docs according to the query
    if q2id != '0':
        query_f = Query.objects.get(pk=q2id)
        qdocs_f = Doc.objects.filter(query__id=q2id)
        all_docs = Doc.objects.filter(query__id=qid) | qdocs_f
        filt_docs = Doc.objects.filter(query__id=qid) | qdocs_f
    else:
        query_f  = False
        all_docs = Doc.objects.filter(query__id=qid).values_list('pk',flat=True)
        filt_docs = Doc.objects.filter(pk__in=all_docs)

    #if "tag__title" in fields:
    #    filt_docs = filt_docs.filter(tag__query__id=qid)

    fields = tuple(fields)

    single_fields = ['pk']
    mult_fields = []
    users = []
    rfields = []
    for f in fields:
        if "docauthinst" in f or "tag__" in f or "note__text" in f:
            mult_fields.append(f)
            #single_fields.append(f)
        elif "docownership" in f:
            users.append(f)
        elif "relevance_" in f:
            rfields.append(f)
            single_fields.append(f)
        else:
            single_fields.append(f)
    single_fields = tuple(single_fields)
    mult_fields_tuple = tuple(mult_fields)

    tech = query.technology
    print(len(filt_docs))
    # annotate with relevance
    if "relevance_netrelevant" in rfields:
        filt_docs = filt_docs.annotate(relevance_netrelevant=models.Sum(
            models.Case(
                models.When(docownership__relevant=1,then=1),
                default=0,
                output_field=models.IntegerField()
            )
        ))
    if "relevance_techrelevant" in rfields:
        filt_docs = filt_docs.annotate(relevance_techrelevant=models.Sum(
            models.Case(
                models.When(docownership__relevant=1,docownership__query__technology=tech,then=1),
                default=0,
                output_field=models.IntegerField()
            )
        ))
    if "relevance_agreement" in rfields:
        filt_docs = filt_docs.annotate(
            relevance_max=models.Max(
                models.Case(
                    models.When(docownership__relevant__gt=0,docownership__query__technology=tech,
                        then=F('docownership__relevant')
                    ),
                    default=0,
                    output_field=models.IntegerField()
                )
            ),
            relevance_min = models.Min(
                models.Case(
                    models.When(docownership__relevant__gt=0,docownership__query__technology=tech,
                        then=F('docownership__relevant')
                    ),
                    default=99,
                    output_field=models.IntegerField()
                )
            )
        )
        filt_docs = filt_docs.annotate(
            relevance_agreement = F('relevance_max') - F('relevance_min')
        )


    # Annotate with technology names
    if "tech_technology" in fields:
        filt_docs = filt_docs.annotate(
            qtechnology=StringAgg('query__technology__name','; ',distinct=True),
            dtechnology=StringAgg('technology__name','; ',distinct=True),
            #tech_technology=Concat(F('qtechnology'), F('dtechnology'))
        )
        filt_docs = filt_docs.annotate(
            tech_technology=Concat('qtechnology', 'dtechnology')
        )

    # Annotate with innovation names
    if "tech_innovation" in fields:
        filt_docs = filt_docs.annotate(
            qtechnology=StringAgg('query__innovation__name','; ',distinct=True),
            dtechnology=StringAgg('innovation__name','; ',distinct=True),
            #tech_technology=Concat(F('qtechnology'), F('dtechnology'))
        )
        filt_docs = filt_docs.annotate(
            tech_innovation=Concat('qtechnology', 'dtechnology')
        )

    if "wosarticle__doc" in fields:
        filt_docs = filt_docs.annotate(
            wosarticle__doc=Concat(V('<a href="/scoping/document/'+str(p.id)+'/'),'pk',V('">'),'pk',V('</a>'))
        )
    #if
    #x = y
    for i in range(len(f_fields)):
        if "tag__title" in f_fields[i]:
            tag_filter = f_text[i]


    print(len(filt_docs))
    # filter documents with user ratings
    if len(users) > 0:
        uname = users[0].split("__")[1]
        user = User.objects.get(username=uname)
        if "relevance_time" in rfields:
            filt_docs = filt_docs.annotate(
                relevance_time = models.Max(
                    models.Case(
                        models.When(docownership__user=user,
                            then=F('docownership__date')
                        )#,
                        #default=datetime.date(2000,1,2)
                    )
                )
            )

        null_filter = 'docownership__relevant__isnull'
        if q2id!='0':
            reldocs = filt_docs.filter(docownership__user=user,docownership__query=query) | filt_docs.filter(docownership__user=user,docownership__query=query_f)
            if "tag__title" in f_fields:
                reldocs = filt_docs.filter(docownership__user=user,docownership__query=query, docownership__tag__title__icontains=tag_filter) | filt_docs.filter(docownership__user=user,docownership__query=query_f, docownership__tag__title__icontains=tag_filter)
                print(reldocs)
            reldocs = reldocs.values("pk")
            filt_docs = filt_docs.filter(pk__in=reldocs)
        else:
            reldocs = filt_docs.filter(docownership__user=user,docownership__query=query)
            if "tag__title" in f_fields:
                reldocs = filt_docs.filter(docownership__user=user,docownership__query=query, docownership__tag__title__icontains=tag_filter)
                print(reldocs)
            reldocs = reldocs.values("pk")
            filt_docs = filt_docs.filter(pk__in=reldocs)
        for u in users:
            uname = u.split("__")[1]
            user = User.objects.get(username=uname)
            #uval = reldocs.filter(docownership__user=user).docownership
            if "tag__title" in f_fields:
                filt_docs = filt_docs.filter(
                        docownership__user=user,
                        docownership__query=query,
                        docownership__tag__title__icontains=tag_filter
                    ).annotate(**{
                    u: models.Case(
                            models.When(docownership__user=user,docownership__query=query,then='docownership__relevant'),
                            default=0,
                            output_field=models.IntegerField()
                    )
                })
            else:
                filt_docs = filt_docs.filter(docownership__user=user,docownership__query=query).annotate(**{
                    u: models.Case(
                            models.When(docownership__user=user,docownership__query=query,then='docownership__relevant'),
                            default=0,
                            output_field=models.IntegerField()
                    )
                })


    all_docs = filt_docs

    fids = []
    tag_text = ""
    # filter the docs according to the currently active filter
    for i in range(len(f_fields)):
        if i==0:
            joiner = "AND"
            text_joiner = ""
        else:
            joiner = f_join[i-1]
            text_joiner = f_join[i-1]
        if f_operators[i] == "noticontains":
            op = "icontains"
            exclude = True
        elif f_operators[i] == "notexact":
            op = "exact"
            exclude = True
        else:
            op =  f_operators[i]
            exclude = False
        try:
            if "tag__title" in f_fields[i]:
                if q2id != '0':
                    filt_docs = filt_docs.filter(tag__query__id=qid,tag__title__icontains=f_text[i]) | filt_docs.filter(tag__query__id=q2id,tag__title__icontains=f_text[i])
                else:
                    if joiner=="AND":
                        filt_docs = filt_docs.filter(
                            tag__query__id=qid,
                            tag__title__icontains=f_text[i]
                        )
                    else:
                        fids = []
                        fids = fids + list(filt_docs.values_list('id',flat=True))
                        fids = fids + list(all_docs.filter(
                            tag__query__id=qid,
                            tag__title__icontains=f_text[i]
                        ).values_list('id',flat=True))
                        filt_docs = all_docs.filter(id__in=set(fids))
                tag_filter = f_text[i]

            else:
                if "docownership__" in f_fields[i]:
                    f_text[i] = getattr(DocOwnership,f_text[i].upper())
                    print(f_text[i])
                kwargs = {
                    '{0}__{1}'.format(f_fields[i],op): f_text[i]
                }
                print(kwargs)
                if joiner=="AND":
                    if exclude:
                        filt_docs = filt_docs.exclude(**kwargs)
                    else:
                        filt_docs = filt_docs.filter(**kwargs)
                else:
                    if exclude:
                        filt_docs = filt_docs | all_docs.exclude(**kwargs)
                    else:
                        fids = []
                        fids = fids + list(filt_docs.values_list('id',flat=True))
                        fids = fids + list(all_docs.filter(**kwargs).values_list('id',flat=True))
                        print(len(fids))

                        filt_docs = all_docs.filter(id__in=set(fids))

                tag_text+= '{0} {1} {2} {3}'.format(text_joiner, f_fields[i], f_operators[i], f_text[i])
        except:
            break

    if "k" in fields:
        filt_docs = filt_docs.filter(citation_objects=True)



    if tag_title is not None:
        t = Tag(title=tag_title)
        t.text = tag_text
        t.query = query
        t.save()
        Through = Doc.tag.through
        tms = [Through(doc=d,tag=t) for d in filt_docs]
        Through.objects.bulk_create(tms)
        for doc in filt_docs:
            doc.tag.add(t)
        return(JsonResponse("",safe=False))

    if sortdir=="+":
        sortdir=""


    n_docs = len(filt_docs)

    if sort_dirs is not None:
        order_by = ('-PY','pk')
        if len(sort_dirs) > 0:
            order_by = []
        for s in range(len(sort_dirs)):
            sortdir = sort_dirs[s]
            field = sort_fields[s]
            if sortdir=="+":
                sortdir=""
            null_filter = field+'__isnull'
            order_by.append(sortdir+field)
            filt_docs = filt_docs.filter(**{null_filter:False})

        docs = filt_docs.order_by(*order_by).values(*single_fields)
        n_docs = len(docs)
    if download != "true":
        x = filt_docs.values()
        docs = docs[:100]


    if len(mult_fields) > 0:

        for d in docs:
            for m in range(len(mult_fields)):
                f = (mult_fields_tuple[m],)
                if "tag__" in mult_fields_tuple[m]:
                    if q2id!='0':
                        adoc = Tag.objects.all().filter(doc__pk=d['pk'],query=qid).values_list("title") | Tag.objects.all().filter(doc__pk=d['pk'],query=q2id).values_list("title")
                    else:
                        adoc = Tag.objects.all().filter(doc__pk=d['pk'],query=qid).values_list("title")
                else:
                    adoc = filt_docs.filter(pk=d['pk']).values_list(*f).order_by('docauthinst__position')
                if "note__" in mult_fields_tuple[m]:
                    adoc = [x.text for x in Doc.objects.get(pk=d['pk']).note_set.filter(
                        project=query.project
                    )]
                if "docfile__" in mult_fields_tuple[m]:
                    adoc = "/scoping/download_pdf/"+str(d['pk'])
                d[mult_fields[m]] = "; <br>".join(str(x) for x in (list(itertools.chain(*adoc))))
                if "note__" in mult_fields_tuple[m]:
                    d[mult_fields[m]] = "; <br>".join(x.strip() for x in  adoc)

    if request.user.profile.type == "default":
        max = 4
        min = 0
    else:
        max = 8
        min = 5


    for d in docs:
        # work out total relevance
        if "docfile__id" in fields:
            if d['docfile__id']:
                d['docfile__id'] = '<a href="/scoping/download_pdf/'+str(d['docfile__id'])+'"">PDF'

        if "wosarticle__cr" in fields:
            d['wosarticle__cr'] = ';<br>'.join(d['wosarticle__cr'])

        try:
            d['relevance_time'] = formats.date_format(d['relevance_time'], "SHORT_DATETIME_FORMAT")
        except:
            pass
        if "relevance__netrelevantasdfasdf" in rfields:
            d["relevance__netrelevant"] = DocOwnership.objects.filter(doc_id=d['pk'],relevant__gt=0).count()
        # Get the user relevance rating for each doc (if asked)
        if len(users) > 0:
            for u in users:
                uname = u.split("__")[1]
                doc = Doc.objects.get(pk=d['pk'])
                if q2id!='0':
                    do = DocOwnership.objects.filter(doc_id=d['pk'],query__id=qid,user__username=uname) | DocOwnership.objects.filter(doc_id=d['pk'],query__id=q2id,user__username=uname)
                else:
                    do = DocOwnership.objects.filter(doc_id=d['pk'],query__id=qid,user__username=uname)
                if "tag__title" in f_fields:
                    do = do.filter(tag__title__icontains=tag_filter)
                if do.count() > 0:
                    d[u] = do.first().relevant
                    num = do.first().relevant
                    text = do.first().get_relevant_display()
                    tag = str(do.first().tag.id)
                    user = str(User.objects.filter(username=uname).first().id)
                    if download == "false":
                        d[u] = '<select class="relevant_cycle" data-user=' \
                        +user+' data-tag='+tag+' data-id='+str(d['pk'])+' \
                        onchange="cyclescore(this)"\
                        >'
                        for r in range(min,max+1):
                            dis = DocOwnership(
                                relevant=r
                            ).get_relevant_display()
                            sel = ""
                            if r == num:
                                sel = "selected"
                            d[u]+='<option {} value={}>{}</option>'.format(sel, r, dis)



                        #' data-value='+str(d[u])+'\
                        #onclick="cyclescore(this)">'+text+'</span>'
        try:
            if download=="true":
                d['wosarticle__di'] = 'http://dx.doi.org/'+d['wosarticle__di']
            else:
                d['wosarticle__di'] = '<a target="_blank" href="http://dx.doi.org/'+d['wosarticle__di']+'">'+d['wosarticle__di']+'</a>'
        except:
            pass

    if download == "true":
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="documents.csv"'

        writer = csv.writer(response)

        writer.writerow(fields)

        for d in docs:
            row = [d[x] for x in fields]
            writer.writerow(row)

        return response

    #x = zu
    response = {
        'data': list(docs),
        'n_docs': n_docs
    }

    template = loader.get_template('scoping/base.html')
    context = response
    #return HttpResponse(template.render(context, request))

    #x = y
    return JsonResponse(response,safe=False)


def get_tech_docs(tid,other=False):
    if tid=='0':
        tech = Technology.objects.all().values('id')
        tobj = Technology(pk=0,name="NETS: All Technologies")
    else:
        tech = Technology.objects.filter(pk=tid).values('id')
        tobj = Technology.objects.get(pk=tid)
    docs1 = list(Doc.objects.filter(
        query__technology__in=tech,
        query__type="default"
    ).values_list('pk',flat=True))
    docs2 = list(Doc.objects.filter(
        technology__in=tech
    ).values_list('pk',flat=True))
    dids = list(set(docs2)|set(docs1))
    docs = Doc.objects.filter(pk__in=dids)
    nqdocs = Doc.objects.filter(pk__in=docs2).exclude(pk__in=docs1)

    if other:
        return [tech,docs,tobj,nqdocs]
    else:
        return [tech,docs,tobj]

from collections import defaultdict

def technology(request,tid):
    template = loader.get_template('scoping/technology.html')
    tech, docs, tobj, nqdocs = get_tech_docs(tid,other=True)
    project = tobj.project
    docinfo={}
    docinfo['nqdocs'] = nqdocs.distinct('pk').count()
    docinfo['tdocs'] = docs.distinct('pk').count()
    docinfo['reldocs'] = docs.filter(
        docownership__relevant=1,
        docownership__query__technology__in=tech
    ).distinct('pk').count() + nqdocs.distinct('pk').count()

    docs = docs.order_by('PY').filter(PY__gt=1985)

    rdocids = docs.filter(
        docownership__relevant=1,
        docownership__query__technology__in=tech
    ).values_list('pk',flat=True)

    rdocids = list(rdocids)

    rdocs = docs.filter(pk__in=rdocids).values('PY').annotate(
        n=models.Count("pk"),
        relevant=models.Value("Relevant", models.TextField())
    )
    nrdocs = docs.exclude(pk__in=rdocids).values('PY').annotate(
        n=models.Count("pk"),
        relevant=models.Value("Not Relevant", models.TextField())
    )

    all = list(nrdocs)+list(rdocs)
    docjson = json.dumps(all)

    docjson2 = []

    d = defaultdict(dict)
    for l in (rdocs,nrdocs):
        for elem in l:
            d[elem['PY']].update(elem)


    #bypy = docs.values('PY','techrelevant').annotate(
    #    n=models.Count("UT")
    #)

    context = {
        'tech': tobj,
        'docinfo': docinfo,
        'bypy': docjson,
        'nqdocs': nqdocs,
        'project': project
        #'bypy': list(bypy.values('PY','techrelevant','n'))
    }

    return HttpResponse(template.render(context, request))

def download_tdocs(request,tid):
    tech, docs, tobj, nqdocs = get_tech_docs(tid,other=True)
    rdocs = docs.filter(
        docownership__relevant=1,
        docownership__query__technology__in=tech
    )
    trdocs = docs.filter(technology__in=tech).exclude(query__technology__in=tech)
    rdocs = rdocs | trdocs
    rdocs = rdocs.distinct('pk')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="documents.csv"'

    writer = csv.writer(response)

    writer.writerow(['pk','PY','CITATION','DOI'])

    for d in rdocs.iterator():

        row = [d.pk,d.PY,d.citation(),'http://dx.doi.org/'+str(d.wosarticle.di)]
        writer.writerow(row)

    return response

def prepare_authorlist(request,tid):
    tech, docs, tobj = get_tech_docs(tid)
    docs = docs.filter(
        docownership__relevant=1,
        docownership__query__technology__in=tech
    )
    docids = docs.values_list('pk',flat=True)

    emails = Doc.objects.filter(pk__in=docids,wosarticle__em__isnull=False).annotate(
        em_lower=Func(F('wosarticle__em'), function='lower')
    ).distinct('em_lower')#.values('em_lower').distinct()

    ems = []
    em_values = []
    for d in emails.iterator():
        #d = Doc.objects.filter(wosarticle__em__icontains=em['em_lower']).first()
        if d.wosarticle.em is not None:
            evalue = d.wosarticle.em.split(';')[0]
            if evalue not in em_values:
                if d.docauthinst_set.count() == 0:
                    continue
                au = d.docauthinst_set.order_by('position').first().AU
                audocs = docs.filter(docauthinst__AU=au,query__technology__isnull=False).distinct('pk')
                docset = "; ".join([x.citation() for x in audocs])
                et, created = EmailTokens.objects.get_or_create(
                    email=evalue,
                    AU=au,
                    category=tobj
                )
                pcats = Technology.objects.filter(project=tobj.project)
                et_existing = EmailTokens.objects.filter(
                    email=evalue,
                    AU=au,
                    category__in=pcats,
                    sent = True
                ).exclude(category=tobj)
                if et_existing.count() > 0:
                    et.sent_other_tech = True
                else:
                    et.sent_other_tech = False
                et.docset= docset
                et.save()
                link = 'https://apsis.mcc-berlin.net/scoping/external_add/{}'.format(et.id)
                ems.append({
                    "name": au,
                    "email": evalue,
                    "docset": docset,
                    "link": link,
                    "sot": et.sent_other_tech,
                    "sent": et.sent
                })
                em_values.append(evalue)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="email_list.csv"'

    writer = csv.writer(response, delimiter=';')

    writer.writerow(["name","email","docset","link","sent","sent_other_tech"])

    print(ems)

    for em in ems:
        writer.writerow([em["name"],em["email"],em["docset"],em["link"],em["sent"],em["sot"]])

    return response

from django.core.mail import send_mail, EmailMessage
import random

def send_publication(request):

    ems = EmailTokens.objects.filter(user_id__isnull=True,sent=True)

    message = '''Dear colleague,

Some months ago we contacted you regarding our project - a systematic review of Negative Emissions Technologies (NETs) - to ask if you had additional literature that we had not considered.

We are grateful to those who sent us additional documents. Thanks to your assistance we considered over 6000 papers, regarding nearly 2000 as relevant, and extracted and synthesized costs, potentials and side-effects from 861 studies. Unfortunately, it was not possible to include, or to reference, every paper related to negative emissions, but we aimed to transparently document those that informed our analysis and how we selected them (http://www.co2removal.org/methods/).

We are very happy to announce the publication of our three-part review on NETs today. As requested by many of you, we would like to share it with you and point you as well to the data resources the project generated. The latter we made available on a mini-website alongside with some of the headline results from the study in an interactive format (www.co2removal.org). We hope that you will find the studies a useful contribution to the field. They are published in a special issue of ERL on negative emissions

Minx, Jan C. et al. (2018): Negative emissions - Part 1: research landscape and synthesis. Environmental Research Letters 13, 063001. https://doi.org/10.1088/1748-9326/aabf9b

Fuss, Sabine et al. (2018): Negative emissions - Part 2: Costs, potentials and side effects. Environmental Research Letters 13, 063002. https://doi.org/10.1088/1748-9326/aabf9f

Nemet, Gregory F. et al. (2018): Negative emissions - Part 3: Innovation and upscaling. Environmental Research Letters 13, 063003. https://doi.org/10.1088/1748-9326/aabff4

We would like to thank you once again for contributing to the project, by authoring a study or by contributing further studies.
Kind regards,

Jan Minx
'''

    emessage = EmailMessage(
        subject = 'Systematic review of negative emissions technologies',
        body = message,
        from_email = 'nets@mcc-berlin.net',
        to = ['callaghan@mcc-berlin.net'],
        #cc = ['nets@mcc-berlin.net'],
    )
    s = emessage.send()
    if s == 1:
        et.sent = True
        et.save()
        time.sleep(30 + random.randrange(1,50,1)/10)

    chunk_size = 25

    for i in range(2,ems.count()//chunk_size+1):
        try:
            chunk_emails = ems[i*chunk_size:(i+1)*chunk_size]
        except:
            chunk_emails = ems[i*chunk_size:ems.count()]
        print(i)
        print(chunk_emails.count())

        emails = list(chunk_emails.values_list(
            'email',flat=True
        ))

        print(emails)

        emessage = EmailMessage(
            subject = 'Systematic review of negative emissions technologies',
            body = message,
            from_email = 'nets@mcc-berlin.net',
            to = ['nets@mcc-berlin.net'],
            bcc = emails
        )

        s = emessage.send()
        if s == 1:
            #et.sent = True
            #et.save()
            time.sleep(30 + random.randrange(1,50,1)/10)


    return

def send_authorlist(request,tid):

    message = '''Dear {},

a team of researchers at the Mercator Research Institute on Global Commons and Climate Change, the University of Wisconsin, the University of Hamburg and the University of Aberdeen are currently performing a systematic review of the literature on negative emissions technologies, with a particular focus on costs, potentials, and side-effects. Our assessment of bioenergy in combination with carbon capture and storage also looks at bioenergy and geological storage potentials. This project is intended to inform upcoming climate change assessments such as the Special Report on the 1.5°C limit by the Intergovernmental Panel on Climate Change as well as the Sixth Assessment Report.

It is our ambition to cover the literature as comprehensively as possible. So far, we have systematically searched the Web of Science and Scopus, but we are aware that this will not provide an exhaustive list of relevant documents and therefore we are contacting experts in the field directly.

We have identified the following articles authored by yourself below. If you have additional relevant articles that we should cover in our review, we would very much appreciate it, if you could upload them to our system by following this link:

{}

This will make sure that your work on the topic is fully considered. We are very happy to share the research with you, once the manuscripts are finalized.

Thanks so much for all your consideration and efforts.

Warm regards,

Jan Minx

--
Prof. Jan Christoph Minx, PhD

Mercator Research Institute on Global Commons and Climate Change (MCC)
Head of Research Group on Applied Sustainability Sciences (APSIS)

Professor for Science-Policy and Sustainable Development, Hertie School of Governance

Torgauer Str. 12-15
10829 Berlin
Germany

{}
    '''
    tobj = Technology.objects.get(pk=tid)
    ems = EmailTokens.objects.filter(
        category=tobj,
        sent=False,
        sent_other_tech=False
    )
    for et in ems:
        split = et.AU.split(',')
        if len(split) ==1 :
            sname = et.AU
            initial = "Dr"
        else:
            sname, initial = et.AU.split(', ')
        name = "{} {}".format(initial, sname)

        link = 'https://apsis.mcc-berlin.net/scoping/external_add/{}'.format(et.id)
        emessage = EmailMessage(
            subject = 'Systematic review of negative emissions technologies',
            body = message.format(name,link,et.docset),
            from_email = 'nets@mcc-berlin.net',
            to = [et.email],
            cc = ['nets@mcc-berlin.net'],
        )
        s = emessage.send()
        if s == 1:
            et.sent = True
            et.save()
            time.sleep(30 + random.randrange(1,50,1)/10)

    return HttpResponseRedirect(reverse('scoping:technology', kwargs={'tid': tid}))



def document(request, pid, doc_id):

    if request.method == "POST":
        x = 1
        if request.FILES.get('file', False):

            print("DOCCCFILE")
            doc = Doc.objects.get(pk=doc_id)
            uf = UploadDocFile(request.POST, request.FILES)
            if uf.is_valid():
                uf.save()
            else:
                e = uf.errors

    template = loader.get_template('scoping/document.html')
    doc = Doc.objects.get(pk=doc_id)
    project = Project.objects.get(pk=pid)
    authors = DocAuthInst.objects.filter(doc=doc)
    queries = Query.objects.filter(doc=doc,project=project)
    technologies = doc.technology.filter(project=project)
    innovations = doc.innovation.all()
    ratings = doc.docownership_set.filter(query__project=project)
    if request.user.username in ["galm","roger","nemet"]:
        extended=True
    else:
        extended=False

    if hasattr(doc,'docfile') is False:
        uf = UploadDocFile()
        uf.fields["doc"].initial=doc_id
        uf.action="Upload"
    else:
        df = doc.docfile
        uf = DeleteDocField()
        uf.fields["delete"].initial=1
        uf.filename = df.file
        uf.action="Delete"

    ptechs = Technology.objects.filter(project=project).exclude(pk__in=technologies)


    context = {
        'doc': doc,
        'authors': authors,
        'technologies': technologies,
        'innovations': innovations,
        'ratings': ratings,
        'queries': queries,
        'extended': extended,
        'ptechs': ptechs,
        'project': project,
        'uf': uf
    }
    return HttpResponse(template.render(context, request))

def cities(request,qid):
    template = loader.get_template('scoping/cities.html')
    query = Query.objects.get(pk=qid)
    context = {
        'query':query,
        'project': query.project
    }
    return HttpResponse(template.render(context, request))

def city_data(request,qid):
    q = Query.objects.get(pk=qid)
    badcities = ['Metro','Most','Sim','Young','University','Green','Much','Mobile','Federal','Along','Of','Laplace']
    cities = City.objects.filter(doc__query=qid).exclude(name__in=badcities)
    cities = cities.annotate(
        n = Count('doc')
    ).order_by('-n') #.values('name','country__name','n','location')

    response = {"type": "GeometryCollection"}
    geometries = []

    for c in cities:
        geometries.append({
            "type": "Point","coordinates":list(c.location.coords),
            "properties": {"name": c.name, "n": c.n}
        })

    response['geometries'] = geometries
    return JsonResponse(response, safe=False, content_type="application/json")

def city_docs(request,qid):
    template = loader.get_template('scoping/city_docs.html')
    place = request.GET.get('name',None)
    query = Query.objects.get(pk=qid)
    run_id = RunStats.objects.filter(query=query).last().run_id
    badcities = ['Metro','Most','Sim','Young','University','Green','Much','Mobile','Federal','Along','Of','Laplace']
    city = City.objects.filter(
        alt_names__name__unaccent=place
    ) | City.objects.filter(
        name__unaccent=place
    )
    city = city.order_by('-population').first()
    cdocs = city.doc_set.all()

    topics = DocTopic.objects.filter(
        doc__cities=city,
        scaled_score__gt=0.00002,
        run_id=run_id
    )

    topics = topics.annotate(total=(Sum('scaled_score')))

    topics = topics.values('topic','topic__title').annotate(
        tprop=Sum('scaled_score')
    ).order_by('-tprop')

    pie_array = []
    for t in topics:
        pie_array.append([t['tprop'], '/tmv_app/topic/' + str(t['topic']), 'topic_' + str(t['topic'])])

    #y = x

    context = {
        'docs': cdocs,
        'city': city,
        'ndocs': cdocs.count(),
        'pie_array': pie_array,
        'topics': topics,
        'project': query.project
    }
    return HttpResponse(template.render(context, request))

def cycle_score(request):

    qid = int(request.GET.get('qid',None))
    q2id = int(request.GET.get('q2id',None))
    score = int(request.GET.get('score',None))
    doc_id = request.GET.get('doc_id',None)
    user = int(request.GET.get('user',None))
    tag = int(request.GET.get('tag',None))

    query = Query.objects.get(id=qid)

    if query.type == "default":
        if request.user.profile.type == "default":
            max = 4
            min = 0
        else:
            max = 8
            min = 5
        if score == max:
            new_score = min
        else:
            new_score = score+1
        new_score = score
        docown = DocOwnership.objects.filter(query__id=qid, doc__pk=doc_id, user__id=user, tag__id=tag).first()
        docown.relevant = new_score
        docown.save()
    else:
        query2 = Query.objects.get(id=q2id)
        if score == 2:
            new_score = 1
        else:
            new_score = score+1

        # Check
        docown = DocOwnership.objects.filter(query__id=qid, doc__pk=doc_id, user__id=user, tag__id=tag).first()
        if (docown == None):
            docown = DocOwnership.objects.filter(query__id=q2id, doc__pk=doc_id, user__id=user, tag__id=tag).first()

        docown.relevant = new_score
        docown.save()

    return HttpResponse("")

@login_required
@user_passes_test(lambda u: u.is_superuser)
def activate_user(request):

    qid = request.GET.get('qid',None)
    checked = request.GET.get('checked',None)
    user = request.GET.get('user',None)

    query = Query.objects.get(pk=qid)
    user = User.objects.get(username=user)

    if checked=="true":
        query.users.add(user)
        query.save()
        response=1
    else:
        response=-1
        query.users.remove(user)

    return JsonResponse(response,safe=False)

@login_required
def update_criteria(request):
    qid = request.GET.get('qid',None)
    criteria = request.POST['criteria']

    query = Query.objects.get(pk=qid)
    query.criteria = criteria
    query.save()

    return HttpResponseRedirect(reverse('scoping:query', kwargs={'qid': qid}))

@login_required
def assign_docs(request):
    qid = request.GET.get('qid',None)
    users = request.GET.getlist('users[]',None)
    tags = request.GET.getlist('tags[]',None)
    tagdocs = request.GET.getlist('tagdocs[]',None)
    docsplit = request.GET.get('docsplit',None)

    #print(docsplit)

    query = Query.objects.get(pk=qid)

    print(tags)

    dos = []

    for tag in range(len(tags)):
        t = Tag.objects.get(pk=tags[tag])
        ssize = int(tagdocs[tag])
        if ssize==0:
            continue
        user_list = []

        for user in users:
            if DocOwnership.objects.filter(query=query,user__username=user,tag=t).count() == 0:
                user_list.append(User.objects.get(username=user))

        if t.document_linked:
            docs = Doc.objects.filter(query=query,tag=t)
        else:
            docs = DocPar.objects.filter(doc__query=query,tag=t)
        l= len(docs)
        ssize = int(tagdocs[tag])

        if ssize == l:
            full = True
        else:
            full = False

        if full == False:
            for user in user_list:
                docs = docs.exclude(docownership__user=user,docownership__relevant__gt=0)

        my_ids = list(docs.values_list('pk', flat=True))
        try:
            rand_ids = random.sample(my_ids, ssize)
            sample = docs.filter(pk__in=rand_ids).all()
        except:
            continue


        s = 0
        for doc in sample:
            s+=1
            if docsplit=="true":
                user = user_list[s % len(user_list)]
                try: # see if there is already a relevance object (not for docpars)
                    if t.document_linked:
                        r = Docownership.objects.filter(
                            doc=doc,
                            query=query,
                            user=user
                        ).first().relevant
                    else:
                        r = 0
                except:
                    r = 0
                if t.document_linked:
                    docown = DocOwnership(doc=doc,query=query,user=user,tag=t,relevant=r)
                else:
                    docown = DocOwnership(
                        docpar=doc,
                        query=query,
                        user=user,
                        tag=t,
                        relevant=r
                    )
                dos.append(docown)
            else:
                for user in user_list:
                    try:
                        if t.document_linked:
                            r = Docownership.objects.filter(
                                doc=doc,
                                query=query,
                                user=user
                            ).first().relevant
                        else:
                            r = 0
                    except:
                        r = 0

                    if t.document_linked:
                        docown = DocOwnership(doc=doc,query=query,user=user,tag=t,relevant=r)
                    else:
                        docown = DocOwnership(
                            docpar=doc,
                            query=query,
                            user=user,
                            tag=t,
                            relevant=r
                        )
                    dos.append(docown)
    DocOwnership.objects.bulk_create(dos)
    print("Done")

    return HttpResponse("<body>xyzxyz</body>")

import re

@login_required
def par_manager(request, qid):
    query = Query.objects.get(pk=qid)

    pars = DocPar.objects.filter(
        doc__query=query
    ).order_by('doc','n')#.values(

    filtered_pars = pars
    ors = []
    if request.method=="GET":
        ors = request.GET.getlist('ors', None)
        filter = DocParFilter(request.GET, queryset=pars)
        if len(ors) > 0:
            filters = [filtered_pars]
            i = 0
            for key, value in filter.filters.items():
                v = request.GET[key]
                if v == "":
                    continue
                f = '{}__{}'.format(value.name, value.lookup_expr)
                if key in ors:
                    filtered_pars = filtered_pars | filters[i-1].filter(**{f:v})
                    #x = y
                else:
                    filtered_pars = filtered_pars.filter(**{f:v})
                i += 1
                filters.append(filtered_pars)
        else:
            filtered_pars = filter.qs
        tab = DocParTable(filtered_pars)

    RequestConfig(request).configure(tab)

    if request.method=="POST":
        try:
            d = filter.data.urlencode()
        except:
            d = ""
        tagform = TagForm(request.POST)
        if tagform.is_valid():
            tag = tagform.save()
            tag.query = query
            tag.text = d
            tag.document_linked=False
            tag.save()

        Through = DocPar.tag.through
        tms = [Through(docpar=p,tag=tag) for p in filter.qs]
        Through.objects.bulk_create(tms)

    else:
        tagform = TagForm()



    context = {
        'query': query,
        'project': query.project,
        'pars': tab,
        'filter': filter,
        'tagform': tagform,
        'n_pars': filtered_pars.count(),
        'ors': ors
    }
    return render(request, 'scoping/par_manager.html',context)

@login_required
def add_statement(request):
    idpar = request.GET.get('idpar', None)
    text  = request.GET.get('text', None)
    start = request.GET.get('start', None)
    end   = request.GET.get('end', None)

    par = DocPar.objects.get(pk=idpar)
    
    docStat = docStatement(
        par   = par,
        text  = text,
        start = start,
        end   = end,
        #technology = ,
        text_length = len(text))
    docStat.save()
    
    return HttpResponse()

@login_required
def screen_par(request,tid,ctype,doid,todo,done,last_doid):
	# Get tag, query, authors ...
    tag     = Tag.objects.get(pk=tid)
    query   = tag.query
    do      = DocOwnership.objects.get(pk=doid)
    doc     = do.docpar.doc
    authors = DocAuthInst.objects.filter(doc=doc)
	
    for a in authors:
        a.institution = highlight_words(a.institution, tag)
		
    abstract = highlight_words(doc.content, tag)
    title    = highlight_words(doc.wosarticle.ti, tag)
	
    if doc.wosarticle.de is not None:
        de = highlight_words(doc.wosarticle.de, tag)
    else:
        de = None
		
    if doc.wosarticle.kwp is not None:
        kwp = highlight_words(doc.wosarticle.kwp, tag)
    else:
        kwp = None

    notes = Note.objects.filter(
        par     = do.docpar,
        project = tag.query.project
    )

	# Highlight filter words in paragraphs
    pars = [(highlight_words_new(x.text, tag), x.id) for x in doc.docpar_set.all()]

	# Get technologies/statements
    techs = Technology.objects.filter(project=tag.query.project)
    for t in techs:
        if do.docpar.technology.all().filter(pk=t.pk).exists():
            t.active="btn-success"
        else:
            t.active=""
    levels = [techs.filter(level=l) for l in techs.values_list('level',flat=True).distinct()]
    levels = [[(do.docpar.technology.all().filter(pk=t.pk).exists(),t) for t in techs.filter(level=l)] for l in techs.values_list('level',flat=True).distinct()]

    # Create context for web page
    context = {
        'project':tag.query.project,
        'tag': tag,
        'do': do,
        'todo': todo,
        'done': done,
        'pc': round(done/todo*100),
        'ctype': ctype,
        'abstract': abstract,
        'title': title,
        'de': de,
        'kwp': kwp,
        'authors': authors,
        'pars': pars,
        'levels': levels,
        'notes': notes
    }
    return render(request, 'scoping/screen_par.html',context)

@login_required
def rate_par(request,tid,ctype,doid,todo,done):
    tag=Tag.objects.get(pk=tid)
    data = request.POST
    if 'relevant' in data:
        rel = int(data['relevant'])
        done+=1
    else:
        rel = 0
    do = DocOwnership.objects.get(pk=doid)
    do.relevant=rel
    do.save()

    user = request.user

    dois = DocOwnership.objects.filter(
        docpar__doc__wosarticle__isnull=False,
        tag=tag,
        query=tag.query,
        user_id=user
    )
    if ctype==99:
        dois = dois.filter(relevant__gt=0)
    else:
        dois = dois.filter(relevant=ctype)
    d = dois.order_by('date').first()

    return HttpResponseRedirect(reverse(
        'scoping:screen_par',
        kwargs={
            'tid': tid,
            'ctype': ctype,
            'doid': d.id,
            'todo': todo,
            'done': done,
            'last_doid': 0
        }
    ))


## Universal screening function, ctype = type of documents to show
@login_required
def screen(request,qid,tid,ctype,d=0):
    d = int(d)
    ctype = int(ctype)
    query = Query.objects.get(pk=qid)
    tag = Tag.objects.get(pk=tid)

    user = request.user

    if not tag.document_linked:
        dois = DocOwnership.objects.filter(
            docpar__doc__wosarticle__isnull=False,
            tag=tag,
            query=query,
            user=user
        )
        if ctype==99:
            dois = dois.filter(relevant__gt=0)
        else:
            dois = dois.filter(relevant=ctype)
        d = dois.order_by('date').first()
        return HttpResponseRedirect(reverse(
            'scoping:screen_par',
            kwargs={
                'tid': tid,
                'ctype': ctype,
                'doid': d.id,
                'todo': dois.count(),
                'done': 0,
                'last_doid': 0
            }
        ))

    user = request.user

    back = 0

    docs = DocOwnership.objects.filter(
            doc__wosarticle__isnull=False,
            query=query,
            user=user.id,
            tag=tag
    )
    sdocs = docs.filter(relevant__gte=1).count()
    if ctype==99:
        docs = docs.filter(relevant__gte=1)
    else:
        docs = docs.filter(relevant=ctype)

    docs = docs.order_by('date')

    if d < 0:
        d = docs.count() - 1
        back = -1
        ldocs = DocOwnership.objects.filter(
            doc__wosarticle__isnull=False,
            query=query,
            user=user.id,
            tag=tag
        ).order_by('-date')[:1]
        docs = docs | ldocs
        doc = ldocs.first().doc
    else:
        try:
            doc = docs[d].doc
        except:
            doc = None
            return HttpResponseRedirect(reverse('scoping:userpage', kwargs={'pid': query.project.id }))

    tdocs = docs.count() + sdocs


    ndocs = docs.count()

    authors = DocAuthInst.objects.filter(doc=doc)
    for a in authors:
        a.institution=highlight_words(a.institution,query)
    abstract = highlight_words(doc.content,query)
    title = highlight_words(doc.wosarticle.ti,query)
    if doc.wosarticle.de is not None:
        de = highlight_words(doc.wosarticle.de,query)
    else:
        de = None
    if doc.wosarticle.kwp is not None:
        kwp = highlight_words(doc.wosarticle.kwp,query)
    else:
        kwp = None

    # Create the tags for clicking on
    if request.user.username in ["rogers","nemet","galm"]:
        tags = {'Technology': {},'Innovation': {}}
    else:
        tags = {'Technology': {}}#,'Innovation': {}}
    for t in tags:
        m = apps.get_model(app_label='scoping',model_name=t)
        ctags = m.objects.filter(query__doc=doc) | m.objects.filter(doc=doc)

        tags[t]['thing'] = t
        tags[t]['ctags'] = ctags.distinct()
        tags[t]['ntags'] = m.objects.filter(
            project=query.project
        ).exclude(
            query__doc=doc
        ).exclude(doc=doc)
        print(tags)

    if not request.user.username in ["rogers","nemet"]:
    #if request.user.profile.type == "default":
        innovation=False
    else:
        innovation=True

    notes = doc.note_set.filter(project=query.project)

    template = loader.get_template('scoping/doc.html')
    context = {
        'query': query,
        'project': query.project,
        'doc': doc,
        'notes': notes,
        'ndocs': ndocs,
        'user': user,
        'authors': authors,
        'tdocs': tdocs,
        'sdocs': sdocs,
        'abstract': abstract,
        'title': title,
        'de': de,
        'kwp': kwp,
        'ctype': ctype,
        'tags': tags,
        'innovation': innovation,
        'tag': tag,
        'd': d,
        'back': back
    }

    return HttpResponse(template.render(context, request))

@login_required
def download_pdf(request,id):
    f = DocFile.objects.get(pk=id)
    filename= f.file.name
    with open("/var/www/tmv/BasicBrowser/media/{}".format(filename),'rb') as pdf:
        response = HttpResponse(pdf.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'inline;filename={}.pdf'.format(filename)
        return response


@login_required
def do_review(request):

    import time

    tid = request.GET.get('tid',None)
    qid = request.GET.get('query',None)
    doc_id = request.GET.get('doc',None)
    d = request.GET.get('d',None)

    doc = Doc.objects.get(pk=doc_id)
    query = Query.objects.get(pk=qid)
    user = request.user
    tag = Tag.objects.get(pk=tid)

    docown = DocOwnership.objects.filter(doc=doc,query=query,user=user,tag=tag).order_by("relevant").first()

    print(docown.relevant)

    print(docown.user.username)
    print(docown.doc.pk)

    docown.relevant=int(d)
    docown.date=timezone.now()
    docown.save()
    print(docown.relevant)

    x = dir(time)
    time.sleep(1)
    return HttpResponse("")

@login_required
def remove_assignments(request):
    qid = request.GET.get('qid',None)
    query = Query.objects.get(pk=qid)
    todelete = DocOwnership.objects.filter(query=query)
    DocOwnership.objects.filter(query=int(qid)).delete()
    return HttpResponse("")

@login_required
def editdoc(request):
    doc_id = request.POST.get('doc',None)
    field = request.POST.get('field',None)
    value = request.POST.get('value',None)

    doc = Doc.objects.get(pk=doc_id)
    if field == "content":
        doc.content=value
        doc.wosarticle.ab=value
        doc.save()

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

@login_required
def delete(request,thing,thingid):
    from scoping import models
    getattr(models, thing).objects.get(pk=thingid).delete()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

@login_required
def remove_tech(request,doc_id,tid,thing='Technology'):
    doc = Doc.objects.get(pk=doc_id)
    obj = apps.get_model(app_label='scoping',model_name=thing).objects.get(pk=tid)
    getattr(doc,thing.lower()).remove(obj)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

@login_required
def add_note(request):
    doc_id = request.POST.get('docn',None)
    tid = request.POST.get('tag',None)
    qid = request.POST.get('qid',None)
    ctype = request.POST.get('ctype',None)
    d = request.POST.get('d',None)
    text = request.POST.get('note',None)

    tag = Tag.objects.get(pk=tid)

    if not tag.document_linked:
        par = DocPar.objects.get(pk=doc_id)
        note = Note(
            par=par,
            tag=tag,
            user=request.user,
            date=timezone.now(),
            project=tag.query.project,
            text=text
        )
        note.save()
        next = request.POST.get('next', '/')
        return HttpResponseRedirect(next)
    else:
        doc = Doc.objects.get(pk=doc_id)
        note = Note(
            doc=doc,
            tag=tag,
            user=request.user,
            date=timezone.now(),
            project=tag.query.project,
            text=text
        )
        note.save()
        return HttpResponseRedirect(reverse('scoping:screen', kwargs={
            'qid': qid,
            'tid': tid,
            'ctype': ctype,
            'd': d
        }))




#########################################################
## Download the queryset

@login_required
def download(request, qid):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="documents.csv"'

    writer = csv.writer(response)

    headers = []

    for f in WoSArticle._meta.get_fields():
        path = "wosarticle__"+f.name
        if f.name !="doc":
            headers.append({"path": path, "name": f.verbose_name})

    for f in DocAuthInst._meta.get_fields():
        path = "docauthinst__"+f.name
        if f.name !="doc" and f.name !="query":
            headers.append({"path": path, "name": f.verbose_name})

    hrow = [x['name'] for x in headers]
    fields = [x['path'] for x in headers]

    writer.writerow(hrow)

    q = Query.objects.get(pk=qid)
    docs = Doc.objects.filter(query=q)
    docvals = docs.values(*fields)
    for d in docvals:
        row = [d[x] for x in fields]
        writer.writerow(row)


    return response




from django.contrib.auth import logout
def logout_view(request):
    logout(request)
    # Redirect to a success page.
    #return HttpResponse("logout")
    return HttpResponseRedirect(reverse('scoping:index'))

@login_required
def add_manually():

    qid = 308
    tag = 61
    user = User.objects.get(username="delm")
    query = Query.objects.get(id=qid)
    t = Tag.objects.get(pk=tag)
    docs = Doc.objects.filter(query=query,tag=t).distinct()
    for doc in docs:
        try:
            DocOwnership.objects.get(doc=doc,query=query,user=user,tag=tag)
        except:
            docown = DocOwnership(doc=doc,query=query,user=user,tag=t)
            docown.save()
            print("new docown added")

    return HttpResponse("")

import string
def highlight_words(s,query):
    if query.text is None or s is None:
        return s
    if not hasattr(query,'database'):
        query.database = "tag"
    if query.database == "intern":
        args = query.text.split(" ")
        if args[0]=="*":
            return(s)
        q1 = Query.objects.get(id=args[0])
        q2 = Query.objects.get(id=args[2])
        qwords = [re.findall('\w+',query.text) for query in [q1,q2]]
        qwords = [item for sublist in qwords for item in sublist]
        if "sustainability" in query.title:
            qwords = ["sustainab"]
    else:
        qwords = re.findall('\w+',query.text)
        qwords = [q.lower() for q in qwords]

    nots = ["TS","AND","NOT","NEAR","OR","and","W"]
    transtable = {ord(c): None for c in string.punctuation + string.digits}
    try:
        qwords = set([x.split('*')[0].translate(transtable) for x in qwords if x not in nots and len(x.translate(transtable)) > 0])
    except:
        qwords = set()
    print(qwords)
    abstract = []
    try:
        words = s.split(" ")
    except:
        words = []
    for word in words:
        h = False
        for q in qwords:
            if q in word.lower():
                h = True
        if h:
            abstract.append('<span class="t1">'+word+'</span>')
        else:
            abstract.append(word)
    return(" ".join(abstract))


def highlight_words_new(s,query):
    #print("> Entering highlight_words_new")    
    # Check validity of input parameters before proceeding
    if query.text is None or s is None:
        return s
    
    #print("  Paragraph to be processed: " + s)
    
    # WORK IN PROGRESS: To be saved in the database
    pattern = re.compile("[Ee]mission[s]?\\s(\\w+\\s){1,3}negative|NETs|CDR|[Nn]egative.emission[s]?|[Nn]egative.[cC][0Oo]2.emission[s]?|[Nn]egative.carbon.emission[s]?|[Nn]egative.carbon.dioxide.emission[s]?|[Cc]arbon.dioxide.removal|[Cc]arbon.removal|[Cc][0Oo]2.removal|[Cc]arbon.dioxide.sequestration|[Cc]arbon.sequestration|[Cc][0Oo]2.sequestration|[Bb]iomass.with.[Cc]arbon.[Cc]apture.and.[Ss]torage|[Bb]ioenergy.with.[Cc]arbon.[Cc]apture.and.[Ss]torage|BECS|BECCS|[Dd]irect.[Aa]ir.[Cc]apture|DAC|DACCS|[Aa]fforestation|[^a-zA-Z0-9]AR[^a-zA-Z0-9]|[Ee]nhanced.weathering|EW|Biochar|[Ss]oil.[Cc]arbon.[Ss]equestration|SCS|[Oocean].[Ff]ertili[sz]ation|OF")
    
    # Initialise variables
    text_highlighted = []
    kpos = 0
    iter = 1
    nchar = len(s)
    
    # Search for pattern
    m = pattern.search(s)    
    # If no match could be found, simply save text input...
    if m is None:
        #print("No match could be found")
        text_highlighted = s
    # ... Otherwise
    else:
        #print("  Match #"+str(iter)+": ")
        #print(m)
        match_found = True
        if m.start() == 0:
            text_highlighted.append('<span class="t1">'+s[m.start():m.end()]+'</span>')
        else:
            text_highlighted.append(s[0:(m.start()-1)]+'<span class="t1">'+s[m.start():m.end()]+'</span>')
        kpos = m.end()+1
        # Loop over potential other matches
        while kpos <= nchar and match_found:
            iter = iter +1
            match_found = False 
            m = pattern.search(s, kpos)
            if m is not None:
                #print("  Match #"+str(iter)+": ")
                #print(m)
                match_found = True
                text_highlighted.append(s[kpos:(m.start()-1)]+'<span class="t1">'+s[m.start():m.end()]+'</span>')
                kpos = m.end()+1
    
        # Append remaining text if needed
        if kpos <= nchar:
            text_highlighted.append(s[kpos:nchar])
    #print(text_highlighted)
    #print("  Highlighted paragraph:"+" ".join(text_highlighted))
    
    #print("< Exiting highlight_words_new")
    
    return(" ".join(text_highlighted))
