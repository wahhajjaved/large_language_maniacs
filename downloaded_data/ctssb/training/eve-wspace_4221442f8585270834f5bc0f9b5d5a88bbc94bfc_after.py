#    Eve W-Space
#    Copyright (C) 2013  Andrew Austin and other contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version. An additional term under section
#    7 of the GPL is included in the LICENSE file.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
from datetime import datetime, timedelta
import json
import csv
import pytz

from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.template.response import TemplateResponse
from django.core.urlresolvers import reverse
from django.template import RequestContext
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, Permission
from django.shortcuts import render, get_object_or_404

from Map.models import *
from Map import utils
from core.utils import get_config

# Decorator to check map permissions. Takes request and map_id
# Permissions are 0 = None, 1 = View, 2 = Change
# When used without a permission=x specification, requires Change access


def require_map_permission(permission=2):
    def _dec(view_func):
        def _view(request, map_id, *args, **kwargs):
            current_map = get_object_or_404(Map, pk=map_id)
            if current_map.get_permission(request.user) < permission:
                raise PermissionDenied
            else:
                return view_func(request, map_id, *args, **kwargs)

        _view.__name__ = view_func.__name__
        _view.__doc__ = view_func.__doc__
        _view.__dict__ = view_func.__dict__
        return _view

    return _dec


@login_required
@require_map_permission(permission=1)
def get_map(request, map_id):
    """Get the map and determine if we have permissions to see it.
    If we do, then return a TemplateResponse for the map. If map does not
    exist, return 404. If we don't have permission, return PermissionDenied.
    """
    current_map = get_object_or_404(Map, pk=map_id)
    context = {
        'map': current_map,
        'access': current_map.get_permission(request.user),
        'systemsJSON': current_map.as_json(request.user)
    }
    return TemplateResponse(request, 'map.html', context)


@login_required
@require_map_permission(permission=1)
def map_checkin(request, map_id):
    # Initialize json return dict
    json_values = {}
    current_map = get_object_or_404(Map, pk=map_id)

    # AJAX requests should post a JSON datetime called loadtime
    # back that we use to get recent logs.
    if 'loadtime' not in request.POST:
        return HttpResponse(json.dumps({'error': "No loadtime"}),
                            mimetype="application/json")
    time_string = request.POST['loadtime']

    load_time = datetime.strptime(time_string, "%Y-%m-%d %H:%M:%S.%f")
    load_time = load_time.replace(tzinfo=pytz.utc)

    if request.is_igb_trusted:
        dialog_html = _checkin_igb_trusted(request, current_map)
        if dialog_html is not None:
            json_values.update({'dialogHTML': dialog_html})

    new_log_query = MapLog.objects.filter(timestamp__gt=load_time,
                                          visible=True,
                                          map=current_map)
    log_list = []

    for log in new_log_query:
        #TODO (marbin): Move this to a template.
        log_list.append(
            "<strong>User:</strong> %s <strong>Action:</strong> %s"
            % (log.user.username, log.action)
        )

    log_string = render_to_string('log_div.html', {'logs': log_list})
    json_values.update({'logs': log_string})

    return HttpResponse(json.dumps(json_values), mimetype="application/json")


@login_required
@require_map_permission(permission=1)
def map_refresh(request, map_id):
    """
    Returns an HttpResponse with the updated systemJSON for an asynchronous
    map refresh.
    """
    if not request.is_ajax():
        raise PermissionDenied
    current_map = get_object_or_404(Map, pk=map_id)
    result = [
        datetime.strftime(datetime.now(pytz.utc),
                          "%Y-%m-%d %H:%M:%S.%f"),
        utils.MapJSONGenerator(current_map,
                               request.user).get_systems_json()
    ]
    return HttpResponse(json.dumps(result))


def _checkin_igb_trusted(request, current_map):
    """
    Runs the specific code for the case that the request came from an igb that
    trusts us, returns None if no further action is required, returns a string
    containing the html for a system add dialog if we detect that a new system
    needs to be added
    """
    current_system = System.objects.get(name=request.eve_systemname)
    old_system = None
    result = None
    threshold = datetime.now(pytz.utc) - timedelta(minutes=5)
    recently_active = request.user.locations.filter(
        timestamp__gt=threshold,
        charactername=request.eve_charname
    ).all()

    if recently_active.count():
        old_system = request.user.locations.get(
            charactername=request.eve_charname
        ).system

    #Conditions for the system to be automagically added to the map.
    if (
        old_system in current_map
        and current_system not in current_map
        and not _is_moving_from_kspace_to_kspace(old_system, current_system)
        and recently_active.count()
    ):
        context = {
            'old_system': current_map.systems.filter(
                system=old_system).all()[0],
            'newsystem': current_system,
            'wormholes': utils.get_possible_wh_types(old_system,
                                                     current_system),
        }

        result = render_to_string('igb_system_add_dialog.html', context,
                                  context_instance=RequestContext(request))

    current_system.add_active_pilot(request.user, request.eve_charname,
                                    request.eve_shipname,
                                    request.eve_shiptypename)
    return result


def _is_moving_from_kspace_to_kspace(old_system, current_system):
    """
    returns whether we are moving through kspace
    :param old_system:
    :param current_system:
    :return:
    """
    return old_system.is_kspace() and current_system.is_kspace()


def get_system_context(ms_id):
    map_system = get_object_or_404(MapSystem, pk=ms_id)

    #If map_system represents a k-space system get the relevant KSystem object
    if map_system.system.is_kspace():
        system = map_system.system.ksystem
    else:
        system = map_system.system.wsystem

    scan_threshold = datetime.now(pytz.utc) - timedelta(
        hours=int(get_config("MAP_SCAN_WARNING", None).value)
    )
    interest_offset = int(get_config("MAP_INTEREST_TIME", None).value)
    interest_threshold = (datetime.now(pytz.utc)
                          - timedelta(minutes=interest_offset))

    scan_warning = system.lastscanned < scan_threshold
    if interest_offset > 0:
        interest = (map_system.interesttime and
                    map_system.interesttime > interest_threshold)
    else:
        interest = map_system.interesttime
        # Include any SiteTracker fleets that are active
    st_fleets = map_system.system.stfleets.filter(ended=None).all()
    return {'system': system, 'mapsys': map_system,
            'scanwarning': scan_warning, 'isinterest': interest,
            'stfleets': st_fleets}


@login_required
@require_map_permission(permission=2)
def add_system(request, map_id):
    """
    AJAX view to add a system to a current_map. Requires POST containing:
       topMsID: map_system ID of the parent map_system
       bottomSystem: Name of the new system
       topType: WormholeType name of the parent side
       bottomType: WormholeType name of the new side
       timeStatus: Wormhole time status integer value
       massStatus: Wormhole mass status integer value
       topBubbled: 1 if Parent side bubbled
       bottomBubbled: 1 if new side bubbled
       friendlyName: Friendly name for the new map_system
    """
    if not request.is_ajax():
        raise PermissionDenied
    try:
        # Prepare data
        current_map = Map.objects.get(pk=map_id)
        top_ms = MapSystem.objects.get(pk=request.POST.get('topMsID'))
        bottom_sys = System.objects.get(
            name=request.POST.get('bottomSystem')
        )
        top_type = WormholeType.objects.get(
            name=request.POST.get('topType')
        )
        bottom_type = WormholeType.objects.get(
            name=request.POST.get('bottomType')
        )
        time_status = int(request.POST.get('timeStatus'))
        mass_status = int(request.POST.get('massStatus'))
        top_bubbled = "1" == request.POST.get('topBubbled')
        bottom_bubbled = "1" == request.POST.get('bottomBubbled')
        # Add System
        bottom_ms = current_map.add_system(
            request.user, bottom_sys,
            request.POST.get('friendlyName'), top_ms
        )
        # Add Wormhole
        bottom_ms.connect_to(top_ms, top_type, bottom_type, top_bubbled,
                             bottom_bubbled, time_status, mass_status)

        return HttpResponse()
    except ObjectDoesNotExist:
        return HttpResponse(status=400)


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def remove_system(request, map_id, ms_id):
    """
    Removes the supplied map_system from a map.
    """
    system = get_object_or_404(MapSystem, pk=ms_id)
    system.remove_system(request.user)
    return HttpResponse()


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=1)
def system_details(request, map_id, ms_id):
    """
    Returns a html div representing details of the System given by ms_id in
    map map_id
    """
    if not request.is_ajax():
        raise PermissionDenied

    return render(request, 'system_details.html', get_system_context(ms_id))


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=1)
def system_menu(request, map_id, ms_id):
    """
    Returns the html for system menu
    """
    if not request.is_ajax():
        raise PermissionDenied

    return render(request, 'system_menu.html', get_system_context(ms_id))


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=1)
def system_tooltip(request, map_id, ms_id):
    """
    Returns a system tooltip for ms_id in map_id
    """
    if not request.is_ajax():
        raise PermissionDenied

    return render(request, 'system_tooltip.html', get_system_context(ms_id))


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=1)
def wormhole_tooltip(request, map_id, wh_id):
    """Takes a POST request from AJAX with a Wormhole ID and renders the
    wormhole tooltip for that ID to response.

    """
    if request.is_ajax():
        wh = get_object_or_404(Wormhole, pk=wh_id)
        return HttpResponse(render_to_string(
            "wormhole_tooltip.html",
            {'wh': wh},
            context_instance=RequestContext(request)
        ))
    else:
        raise PermissionDenied


# noinspection PyUnusedLocal
@login_required()
@require_map_permission(permission=2)
def mark_scanned(request, map_id, ms_id):
    """Takes a POST request from AJAX with a system ID and marks that system
    as scanned.

    """
    if request.is_ajax():
        map_system = get_object_or_404(MapSystem, pk=ms_id)
        map_system.system.lastscanned = datetime.now(pytz.utc)
        map_system.system.save()
        return HttpResponse()
    else:
        raise PermissionDenied


# noinspection PyUnusedLocal
@login_required()
def manual_location(request, map_id, ms_id):
    """Takes a POST request form AJAX with a System ID and marks the user as
    being active in that system.

    """
    if request.is_ajax():
        map_system = get_object_or_404(MapSystem, pk=ms_id)
        map_system.system.add_active_pilot(request.user, "OOG Browser",
                                           "Unknown", "Uknown")
        return HttpResponse()
    else:
        raise PermissionDenied


# noinspection PyUnusedLocal
@login_required()
@require_map_permission(permission=2)
def set_interest(request, map_id, ms_id):
    """Takes a POST request from AJAX with an action and marks that system
    as having either utcnow or None as interesttime. The action can be either
    "set" or "remove".

    """
    if request.is_ajax():
        action = request.POST.get("action", "none")
        if action == "none":
            raise Http404
        system = get_object_or_404(MapSystem, pk=ms_id)
        if action == "set":
            system.interesttime = datetime.now(pytz.utc)
            system.save()
            return HttpResponse()
        if action == "remove":
            system.interesttime = None
            system.save()
            return HttpResponse()
        return HttpResponse(status=418)
    else:
        raise PermissionDenied


# noinspection PyUnusedLocal
@login_required()
@require_map_permission(permission=2)
def add_signature(request, map_id, ms_id):
    """
    This function processes the Add Signature form. GET gets the form
    and POST submits it and returns either a blank form or one with errors.
    All requests should be AJAX.
    """
    if not request.is_ajax():
        raise PermissionDenied
    map_system = get_object_or_404(MapSystem, pk=ms_id)

    if request.method == 'POST':
        form = SignatureForm(request.POST)
        if form.is_valid():
            new_sig = form.save(commit=False)
            new_sig.system = map_system.system
            new_sig.sigid = new_sig.sigid.upper()
            new_sig.updated = True
            new_sig.save()
            map_system.system.lastscanned = datetime.now(pytz.utc)
            map_system.system.save()
            new_form = SignatureForm()
            map_system.map.add_log(
                request.user, "Added signature %s to %s (%s)."
                % (new_sig.sigid, map_system.system.name,
                   map_system.friendlyname)
            )
            return TemplateResponse(request, "add_sig_form.html",
                                    {'form': new_form, 'system': map_system})
        else:
            return TemplateResponse(request, "add_sig_form.html",
                                    {'form': form, 'system': map_system})
    else:
        form = SignatureForm()
    return TemplateResponse(request, "add_sig_form.html",
                            {'form': form, 'system': map_system})


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def bulk_sig_import(request, map_id, ms_id):
    """
    GET gets a bulk signature import form. POST processes it, creating sigs
    with blank info and type for each sig ID detected.
    """
    if not request.is_ajax():
        raise PermissionDenied
    map_system = get_object_or_404(MapSystem, pk=ms_id)
    k = 0
    if request.method == 'POST':
        reader = csv.reader(
            request.POST.get('paste', '').decode('utf-8').splitlines(),
            delimiter="\t"
        )
        for row in reader:
            if k < 75:
                if not Signature.objects.filter(sigid=row[0],
                                                system=map_system.system
                                                ).count():
                    Signature(sigid=row[0], system=map_system.system,
                              info=" ").save()
                    k += 1
        map_system.map.add_log(request.user,
                               "Imported %s signatures for %s(%s)."
                               % (k, map_system.system.name,
                               map_system.friendlyname), True)
        map_system.system.lastscanned = datetime.now(pytz.utc)
        map_system.system.save()
        return HttpResponse()
    else:
        return TemplateResponse(request, "bulk_sig_form.html",
                                {'mapsys': map_system})


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def edit_signature(request, map_id, ms_id, sig_id):
    """
    GET gets a pre-filled edit signature form.
    POST updates the signature with the new information and returns a
    blank add form.
    """
    if not request.is_ajax():
        raise PermissionDenied
    signature = get_object_or_404(Signature, pk=sig_id)
    map_system = get_object_or_404(MapSystem, pk=ms_id)

    if request.method == 'POST':
        form = SignatureForm(request.POST)
        if form.is_valid():
            signature.sigid = request.POST['sigid'].upper()
            signature.updated = True
            signature.info = request.POST['info']
            if request.POST['sigtype'] != '':
                sigtype = SignatureType.objects.get(pk=request.POST['sigtype'])
            else:
                sigtype = None
            signature.sigtype = sigtype
            signature.save()
            map_system.system.lastscanned = datetime.now(pytz.utc)
            map_system.system.save()
            map_system.map.add_log(request.user,
                                   "Updated signature %s in %s (%s)" %
                                   (signature.sigid, map_system.system.name,
                                    map_system.friendlyname))
            return TemplateResponse(request, "add_sig_form.html",
                                    {'form': SignatureForm(),
                                    'system': map_system})
        else:
            return TemplateResponse(request, "edit_sig_form.html",
                                    {'form': form,
                                    'system': map_system, 'sig': signature})
    else:
        return TemplateResponse(request, "edit_sig_form.html",
                                {'form': SignatureForm(instance=signature),
                                'system': map_system, 'sig': signature})


# noinspection PyUnusedLocal
@login_required()
@require_map_permission(permission=1)
def get_signature_list(request, map_id, ms_id):
    """
    Determines the proper escalationThreshold time and renders
    system_signatures.html
    """
    if not request.is_ajax():
        raise PermissionDenied
    system = get_object_or_404(MapSystem, pk=ms_id)
    escalation_downtimes = int(get_config("MAP_ESCALATION_BURN",
                                          request.user).value)
    return TemplateResponse(request, "system_signatures.html",
                            {'system': system,
                            'downtimes': escalation_downtimes})


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def mark_signature_cleared(request, map_id, ms_id, sig_id):
    """
    Marks a signature as having its NPCs cleared.
    """
    if not request.is_ajax():
        raise PermissionDenied
    sig = get_object_or_404(Signature, pk=sig_id)
    sig.clear_rats()
    return HttpResponse()


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def escalate_site(request, map_id, ms_id, sig_id):
    """
    Marks a site as having been escalated.
    """
    if not request.is_ajax():
        raise PermissionDenied
    sig = get_object_or_404(Signature, pk=sig_id)
    sig.escalate()
    return HttpResponse()


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def activate_signature(request, map_id, ms_id, sig_id):
    """
    Marks a site activated.
    """
    if not request.is_ajax():
        raise PermissionDenied
    sig = get_object_or_404(Signature, pk=sig_id)
    sig.activate()
    return HttpResponse()


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def delete_signature(request, map_id, ms_id, sig_id):
    """
    Deletes a signature.
    """
    if not request.is_ajax():
        raise PermissionDenied
    map_system = get_object_or_404(MapSystem, pk=ms_id)
    sig = get_object_or_404(Signature, pk=sig_id)
    sig.delete()
    map_system.map.add_log(request.user, "Deleted signature %s in %s (%s)."
                           % (sig.sigid, map_system.system.name,
                              map_system.friendlyname))
    return HttpResponse()


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def manual_add_system(request, map_id, ms_id):
    """
    A GET request gets a blank add system form with the provided MapSystem
    as top system. The form is then POSTed to the add_system view.
    """
    top_map_system = get_object_or_404(MapSystem, pk=ms_id)
    systems = System.objects.all()
    wormholes = WormholeType.objects.all()
    return render(request, 'add_system_box.html',
                  {'topMs': top_map_system, 'sysList': systems,
                   'whList': wormholes})


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def edit_system(request, map_id, ms_id):
    """
    A GET request gets the edit system dialog pre-filled with current
    information.
    A POST request saves the posted data as the new information.
        POST values are friendlyName, info, and occupied.
    """
    if not request.is_ajax():
        raise PermissionDenied
    map_system = get_object_or_404(MapSystem, pk=ms_id)
    if request.method == 'GET':
        occupied = map_system.system.occupied.replace("<br />", "\n")
        info = map_system.system.info.replace("<br />", "\n")
        return TemplateResponse(request, 'edit_system.html',
                                {'mapsys': map_system,
                                'occupied': occupied, 'info': info}
                                )
    if request.method == 'POST':
        map_system.friendlyname = request.POST.get('friendlyName', '')
        if (
                (map_system.system.info != request.POST.get('info', '')) or
                (map_system.system.occupied !=
                 request.POST.get('occupied', ''))
        ):
            map_system.system.info = request.POST.get('info', '')
            map_system.system.occupied = request.POST.get('occupied', '')
            map_system.system.save()
        map_system.save()
        map_system.map.add_log(request.user, "Edited System: %s (%s)"
                               % (map_system.system.name,
                                  map_system.friendlyname))
        return HttpResponse()
    raise PermissionDenied


# noinspection PyUnusedLocal
@login_required
@require_map_permission(permission=2)
def edit_wormhole(request, map_id, wh_id):
    """
    A GET request gets the edit wormhole dialog pre-filled with current info.
    A POST request saves the posted data as the new info.
    POST values are topType, bottomType, massStatus, timeStatus, topBubbled,
    and bottomBubbled.
    """
    if not request.is_ajax():
        raise PermissionDenied
    wormhole = get_object_or_404(Wormhole, pk=wh_id)
    if request.method == 'GET':
        return TemplateResponse(request, 'edit_wormhole.html',
                                {'wormhole': wormhole}
                                )
    if request.method == 'POST':
        wormhole.mass_status = int(request.POST.get('massStatus', 0))
        wormhole.time_status = int(request.POST.get('timeStatus', 0))
        wormhole.top_type = get_object_or_404(
            WormholeType,
            name=request.POST.get('topType', 'K162')
        )
        wormhole.bottom_type = get_object_or_404(
            WormholeType,
            name=request.POST.get('bottomType', 'K162')
        )
        wormhole.top_bubbled = request.POST.get('topBubbled', '1') == '1'
        wormhole.bottom_bubbled = request.POST.get('bottomBubbled', '1') == '1'
        wormhole.save()
        wormhole.map.add_log(request.user,
                            ("Updated the wormhole between %s(%s) and %s(%s)."
                             % (wormhole.top.system.name,
                                wormhole.top.friendlyname,
                                wormhole.bottom.system.name,
                                wormhole.bottom.friendlyname)))
        return HttpResponse()

    raise PermissiondDenied


@permission_required('Map.add_map')
def create_map(request):
    """
    This function creates a map and then redirects to the new map.
    """
    if request.method == 'POST':
        form = MapForm(request.POST)
        if form.is_valid():
            new_map = form.save()
            new_map.add_log(request.user, "Created the %s map." % new_map.name)
            new_map.add_system(request.user, new_map.root, "Root", None)
            return HttpResponseRedirect(reverse('Map.views.get_map',
                                                kwargs={'map_id': new_map.pk}))
        else:
            return TemplateResponse(request, 'new_map.html', {'form': form})
    else:
        form = MapForm
        return TemplateResponse(request, 'new_map.html', {'form': form, })


# noinspection PyUnusedLocal
@require_map_permission(permission=1)
def destination_list(request, map_id, ms_id):
    """
    Returns the destinations of interest list for K-space systems and
    a blank response for w-space systems.
    """
    #if not request.is_ajax():
    #    raise PermissionDenied
    destinations = Destination.objects.all()
    map_system = get_object_or_404(MapSystem, pk=ms_id)
    try:
        system = KSystem.objects.get(pk=map_system.system.pk)
    except:
        return HttpResponse()
    return render(request, 'system_destinations.html',
                  {'system': system, 'destinations': destinations})


# noinspection PyUnusedLocal
def site_spawns(request, map_id, ms_id, sig_id):
    """
    Returns the spawns for a given signature and system.
    """
    sig = get_object_or_404(Signature, pk=sig_id)
    spawns = SiteSpawn.objects.filter(sigtype=sig.sigtype).all()
    if spawns[0].sysclass != 0:
        spawns = SiteSpawn.objects.filter(sigtype=sig.sigtype,
                                          sysclass=sig.system.sysclass).all()
    return render(request, 'site_spawns.html', {'spawns': spawns})


#########################
#Settings Views         #
#########################
@permission_required('Map.map_admin')
def general_settings(request):
    """
    Returns and processes the general settings section.
    """
    npc_threshold = get_config("MAP_NPC_THRESHOLD", None)
    pvp_threshold = get_config("MAP_PVP_THRESHOLD", None)
    scan_threshold = get_config("MAP_SCAN_WARNING", None)
    interest_time = get_config("MAP_INTEREST_TIME", None)
    escalation_burn = get_config("MAP_ESCALATION_BURN", None)
    if request.method == "POST":
        scan_threshold.value = int(request.POST['scanwarn'])
        interest_time.value = int(request.POST['interesttimeout'])
        pvp_threshold.value = int(request.POST['pvpthreshold'])
        npc_threshold.value = int(request.POST['npcthreshold'])
        escalation_burn.value = int(request.POST['escdowntimes'])
        scan_threshold.save()
        interest_time.save()
        pvp_threshold.save()
        npc_threshold.save()
        escalation_burn.save()
        return HttpResponse()
    return TemplateResponse(
        request, 'general_settings.html',
        {'npcthreshold': npc_threshold.value,
         'pvpthreshold': pvp_threshold.value,
         'scanwarn': scan_threshold.value,
         'interesttimeout': interest_time.value,
         'escdowntimes': escalation_burn.value}
    )


@permission_required('Map.map_admin')
def sites_settings(request):
    """
    Returns the site spawns section.
    """
    return TemplateResponse(request, 'spawns_settings.html',
                            {'spawns': SiteSpawn.objects.all()})


@permission_required('Map.map_admin')
def add_spawns(request):
    """
    Adds a site spawn.
    """
    return HttpResponse()


# noinspection PyUnusedLocal
@permission_required('Map.map_admin')
def delete_spawns(request, spawn_id):
    """
    Deletes a site spawn.
    """
    return HttpResponse()


# noinspection PyUnusedLocal
@permission_required('Map.map_admin')
def edit_spawns(request, spawn_id):
    """
    Alters a site spawn.
    """
    return HttpResponse()


@permission_required('Map.map_admin')
def destination_settings(request):
    """
    Returns the destinations section.
    """
    return TemplateResponse(request, 'dest_settings.html',
                            {'destinations': Destination.objects.all()})


@permission_required('Map.map_admin')
def add_destination(request):
    """
    Add a destination.
    """
    system = get_object_or_404(KSystem, name=request.POST['systemName'])
    Destination(system=system, capital=False).save()
    return HttpResponse()


@permission_required('Map.map_admin')
def delete_destination(request, dest_id):
    """
    Deletes a destination.
    """
    destination = get_object_or_404(Destination, pk=dest_id)
    destination.delete()
    return HttpResponse()


@permission_required('Map.map_admin')
def sigtype_settings(request):
    """
    Returns the signature types section.
    """
    return TemplateResponse(request, 'sigtype_settings.html',
                            {'sigtypes': SignatureType.objects.all()})


# noinspection PyUnusedLocal
@permission_required('Map.map_admin')
def edit_sigtype(request, sigtype_id):
    """
    Alters a signature type.
    """
    return HttpResponse()


@permission_required('Map.map_admin')
def add_sigtype(request):
    """
    Adds a signature type.
    """
    return HttpResponse()


# noinspection PyUnusedLocal
@permission_required('Map.map_admin')
def delete_sigtype(request, sigtype_id):
    """
    Deletes a signature type.
    """
    return HttpResponse()


@permission_required('Map.map_admin')
def map_settings(request, map_id):
    """
    Returns and processes the settings section for a map.
    """
    subject = get_object_or_404(Map, pk=map_id)
    return TemplateResponse(request, 'map_settings_single.html',
                            {'map': subject})


@permission_required('Map.map_admin')
def delete_map(request, map_id):
    """
    Deletes a map.
    """
    subject = get_object_or_404(Map, pk=map_id)
    subject.delete()
    return HttpResponse()


# noinspection PyUnusedLocal
@permission_required('Map.map_admin')
def edit_map(request, map_id):
    """
    Alters a map.
    """
    return HttpResponse('[]')


@permission_required('Map.map_admin')
def global_permissions(request):
    """
    Returns and processes the global permissions section.
    """
    if not request.is_ajax():
        raise PermissionDenied
    group_list = []
    admin_perm = Permission.objects.get(codename="map_admin")
    unrestricted_perm = Permission.objects.get(codename="map_unrestricted")
    add_map_perm = Permission.objects.get(codename="add_map")

    if request.method == "POST":
        for group in Group.objects.all():
            if request.POST.get('%s_unrestricted' % group.pk, None):
                if unrestricted_perm not in group.permissions.all():
                    group.permissions.add(unrestricted_perm)
            else:
                if unrestricted_perm in group.permissions.all():
                    group.permissions.remove(unrestricted_perm)

            if request.POST.get('%s_add' % group.pk, None):
                if add_map_perm not in group.permissions.all():
                    group.permissions.add(add_map_perm)
            else:
                if add_map_perm in group.permissions.all():
                    group.permissions.remove(add_map_perm)

            if request.POST.get('%s_admin' % group.pk, None):
                if admin_perm not in group.permissions.all():
                    group.permissions.add(admin_perm)
            else:
                if admin_perm in group.permissions.all():
                    group.permissions.remove(admin_perm)

        return HttpResponse()
    for group in Group.objects.all():
        entry = {
            'group': group, 'admin': admin_perm in group.permissions.all(),
            'unrestricted': unrestricted_perm in group.permissions.all(),
            'add_map': add_map_perm in group.permissions.all()
        }
        group_list.append(entry)

    return TemplateResponse(request, 'global_perms.html',
                            {'groups': group_list})
