# -*- coding: utf-8 -*-

# Create your views here.
import mimetypes
from os import listdir
from os import stat
from os.path import isdir
from os.path import isfile
from os.path import join
from urllib import unquote
from itertools import chain
from datetime import datetime
from time import localtime, strftime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.http import HttpResponseNotFound
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _


def get_sort_key(item):
    return item[1]["order"]

def check_server(function):
    def _dec(view_func):
        def _view(request, * args, ** kwargs):
            try:
                version = settings.PYLOAD.get_server_version()
            except Exception, e:
                return base(request, messages=[_('Can\'t connect to pyLoad. Please check your configuration and make sure pyLoad is running.'), str(e)])
            return view_func(request, * args, ** kwargs)
        
        _view.__name__ = view_func.__name__
        _view.__dict__ = view_func.__dict__
        _view.__doc__ = view_func.__doc__

        return _view

    if function is None:
        return _dec
    else:
        return _dec(function)
        
        
def permission(perm):
    def _dec(view_func):
        def _view(request, * args, ** kwargs):
            if request.user.has_perm(perm) and request.user.is_authenticated():
                return view_func(request, * args, ** kwargs)
            else:
                return base(request, messages=[_('You don\'t have permission to view this page.')])
        
        _view.__name__ = view_func.__name__
        _view.__dict__ = view_func.__dict__
        _view.__doc__ = view_func.__doc__

        return _view

    return _dec



def status_proc(request):
    return {'status': settings.PYLOAD.status_server(), 'captcha': settings.PYLOAD.is_captcha_waiting()}


def base(request, messages):
    return render_to_response(join(settings.TEMPLATE, 'base.html'), {'messages': messages}, RequestContext(request))

@login_required
@permission('pyload.can_see_dl')
@check_server
def home(request):
    res = settings.PYLOAD.status_downloads()

    for link in res:
        if link["status"] == 12:
            link["information"] = "%s kB @ %s kB/s" %  (link["size"] - link["kbleft"], link["speed"])
    
    return render_to_response(join(settings.TEMPLATE, 'home.html'), RequestContext(request, {'content': res}, [status_proc]))
    

@login_required
@permission('pyload.can_see_dl')
@check_server
def queue(request):
    queue = settings.PYLOAD.get_queue_info()

    data = zip(queue.keys(), queue.values())
    data.sort(key=get_sort_key)
            
    return render_to_response(join(settings.TEMPLATE, 'queue.html'), RequestContext(request, {'content': data}, [status_proc]))


@login_required
@permission('pyload.can_download')
@check_server
def downloads(request):

    root = settings.PYLOAD.get_conf_val("general", "download_folder")
    
    if not isdir(root):
        return base(request, [_('Download directory not found.')])
    data = {
        'folder': [],
        'files': []
    }
    
    for item in listdir(root):
        if isdir(join(root, item)):
            folder = {
                'name': item,
                'path': item,
                'files': []
            }
            for file in listdir(join(root, item)):
                if isfile(join(root, item, file)):
                    folder['files'].append(file)
            
            data['folder'].append(folder)
        elif isfile(join(root, item)):
            data['files'].append(item)
    
    
    return render_to_response(join(settings.TEMPLATE, 'downloads.html'), RequestContext(request, {'files': data}, [status_proc]))
    
@login_required
@permission('pyload.can_download')
@check_server
def download(request, path):
    path = unquote(path)
    path = path.split("/")
    
    root = settings.PYLOAD.get_conf_val("general", "download_folder")
    
    dir = join(root, path[1].replace('..', ''))
    if isdir(dir) or isfile(dir):
        if isdir(dir): filepath = join(dir, path[2])
        elif isfile(dir): filepath = dir
        
        if isfile(filepath):
            try:
                type, encoding = mimetypes.guess_type(filepath)
                if type is None:
                    type = 'application/octet-stream'
            
                response = HttpResponse(mimetype=type)
                response['Content-Length'] = str(stat(filepath).st_size)
            
                if encoding is not None:
                    response['Content-Encoding'] = encoding
                     
                response.write(file(filepath, "rb").read())
                return response
            
            except Exception, e:
                return HttpResponseNotFound("File not Found. %s" % str(e))
    
    return HttpResponseNotFound("File not Found.")

@login_required
@permission('pyload.can_see_logs')
@check_server
def logs(request, item=-1):

    perpage = request.session.get('perpage', 34)
    reversed = request.session.get('reversed', False)

    warning = ""
    conf = settings.PYLOAD.get_config()
    if not conf['log']['file_log']['value']:
        warning = "Warning: File log is disabled, see settings page."

    perpage_p = ((20,20), (34, 34), (40, 40), (100, 100), (0,'all'))
    fro = None

    if request.method == 'POST':
        try:
            fro = datetime.strptime(request.POST['from'], '%d.%m.%Y %H:%M:%S')
        except:
            pass
        try:
            perpage = int(request.POST['perpage'])
            request.session['perpage'] = perpage

            reversed = bool(request.POST.get('reversed', False))
            request.session['reversed'] = reversed
        except:
            pass

    try:
        item = int(item)
    except:
        pass

    log = settings.PYLOAD.get_log()
    if perpage == 0:
        item = 0
    
    if item < 1 or type(item) is not int:
        item =  1 if len(log) - perpage + 1 < 1 else len(log) - perpage + 1

    if type(fro) is datetime: # we will search for datetime
        item = -1
        
    data = []
    counter = 0
    perpagecheck = 0
    for l in log:
        counter = counter+1

        if counter >= item:
            try:
                date,time,level,message = l.split(" ", 3)
                dtime = datetime.strptime(date+' '+time, '%d.%m.%Y %H:%M:%S')
            except:
                dtime = None
                date = '?'
                time = ' '
                level = '?'
                message = l
            if item == -1 and dtime is not None and fro <= dtime:
                item = counter #found our datetime
            if item >= 0:
                data.append({'line': counter, 'date': date+" "+time, 'level':level, 'message': message})
                perpagecheck = perpagecheck +1
                if fro is None and dtime is not None: #if fro not set set it to first showed line
                    fro = dtime
            if perpagecheck >= perpage and perpage > 0:
                break

    if fro is None: #still not set, empty log?
        fro = datetime.now()
    if reversed:
        data.reverse()
    return render_to_response(join(settings.TEMPLATE, 'logs.html'), RequestContext(request, {'warning': warning, 'log': data, 'from': fro.strftime('%d.%m.%Y %H:%M:%S'), 'reversed': reversed, 'perpage':perpage, 'perpage_p':sorted(perpage_p), 'iprev': 1 if item - perpage < 1 else item - perpage, 'inext': (item + perpage) if item+perpage < len(log) else item}, [status_proc]))

@login_required
@permission('pyload.can_add_dl')
@check_server
def collector(request):
    queue = settings.PYLOAD.get_collector_info()

    data = zip(queue.keys(), queue.values())
    data.sort(key=get_sort_key)

    return render_to_response(join(settings.TEMPLATE, 'collector.html'), RequestContext(request, {'content': data}, [status_proc]))


@login_required
@permission('pyload.can_change_status')
@check_server
def config(request):
    conf = settings.PYLOAD.get_config()
    plugin = settings.PYLOAD.get_plugin_config()
    accs = settings.PYLOAD.get_accounts()
    messages = []    
    
    for section in chain(conf.itervalues(), plugin.itervalues()):
        for key, option in section.iteritems():
            if key == "desc": continue
            
            if ";" in option["type"]:
                option["list"] = option["type"].split(";")
                
    if request.META.get('REQUEST_METHOD', "GET") == "POST":
        
        errors = []

        for key, value in request.POST.iteritems():
            if not "|" in key: continue
            sec, skey, okey = key.split("|")[:]
            
            if sec == "General":
            
                if conf.has_key(skey):
                    if conf[skey].has_key(okey):
                        try:
                            if str(conf[skey][okey]['value']) != value:
                                settings.PYLOAD.set_conf_val(skey, okey, value)
                        except Exception, e:
                            errors.append("%s | %s : %s" % (skey, okey, e))
                    else:
                        continue
                else:
                    continue
                
            elif sec == "Plugin":
                if plugin.has_key(skey):
                    if plugin[skey].has_key(okey):
                        try:
                            if str(plugin[skey][okey]['value']) != value:
                                settings.PYLOAD.set_conf_val(skey, okey, value, "plugin")
                        except Exception, e:
                            errors.append("%s | %s : %s" % (skey, okey, e))
                    else:
                        continue
                else:
                    continue
            elif sec == "Accounts":
                if ";" in okey:
                    action, name = okey.split(";")
                    
                    if action == "delete":
                        settings.PYLOAD.remove_account(skey, name)
                    elif action == "password":
                        
                        for acc in accs[skey]:
                            if acc["login"] == name and value.strip():
                                settings.PYLOAD.update_account(skey, name, value)
                    
                elif okey == "newacc" and value:
                    # add account
                    
                    pw = request.POST.get("Accounts|%s|newpw" % skey)
                    
                    settings.PYLOAD.update_account(skey, value, pw)
                
        
        if errors:
            messages.append(_("Error occured when setting the following options:"))
            messages.append("")
            messages += errors
        else:
            messages.append(_("All options were set correctly."))
    
    accs = settings.PYLOAD.get_accounts()
    for plugin,accounts in accs.iteritems():
        for user,data in accounts.iteritems():
            if data["trafficleft"] == -1:
                data["trafficleft"] = _("unlimited")
            elif not data["trafficleft"]:
                data["trafficleft"] = ""

            if data["validuntil"] == -1:
                data["validuntil"] = _("unlimited")
            elif not data["validuntil"]:
                data["validuntil"] = ""
            else:
                t = localtime(data["validuntil"])
                data["validuntil"] = strftime("%d-%m-%Y",t)

            
    return render_to_response(join(settings.TEMPLATE, 'settings.html'), RequestContext(request, {'conf': {'Plugin':plugin, 'General':conf, 'Accounts': accs}, 'errors': messages}, [status_proc]))

@login_required
@permission('pyload.can_change_status')
@check_server
def package_ui(request):
    return render_to_response(join(settings.TEMPLATE, 'package_ui.js'), RequestContext(request, {}, ))