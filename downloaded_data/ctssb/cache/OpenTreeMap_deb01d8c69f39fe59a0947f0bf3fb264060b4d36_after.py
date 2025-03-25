import datetime
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.base import ContentFile

from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError
from django.shortcuts import get_object_or_404
from django.db import transaction

from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django_reputation.models import Reputation, UserReputationAction
from profiles.utils import change_reputation_for_user

from treemap.models import Plot, Species, TreePhoto, ImportEvent, Tree, TreeResource, PlotPending, TreePending
from treemap.forms import TreeAddForm
from treemap.views import get_tree_pend_or_plot_pend_by_id_or_404_not_found, permission_required_or_403_forbidden
from api.models import APIKey, APILog
from django.contrib.gis.geos import Point, fromstr

from profiles.models import UserProfile

from api.auth import login_required, create_401unauthorized, login_optional

from functools import wraps

from omgeo import Geocoder
from omgeo.places import PlaceQuery, Viewbox

import json
import struct
import ctypes
import math

import simplejson 

class HttpBadRequestException(Exception):
    pass

class InvalidAPIKeyException(Exception):
    pass

def route(**kwargs):
    @csrf_exempt
    def routed(request, **kwargs2):
        method = request.method
        print " ====> %s" % method
        req_method = kwargs[method]
        return req_method(request, **kwargs2)
    return routed

def json_from_request(request):
    """
    Accessing raw_post_data throws an exception when using the Django test
    client in to make requests in unit tests.
    """
    try:
        data = json.loads(request.raw_post_data)
    except Exception, e:
        data = request.POST
    return data

def validate_and_log_api_req(request):
    # Prefer "apikey" in REQUEST, but take either that or the
    # header value
    key = request.META.get("HTTP_X_API_KEY", None)
    key = request.REQUEST.get("apikey", key)

    if key is None:
        raise InvalidAPIKeyException("key not found as 'apikey' param or 'X-API-Key' header")
    
    apikeys = APIKey.objects.filter(key=key)

    if len(apikeys) > 0:
        apikey = apikeys[0]
    else:
        raise InvalidAPIKeyException("key not found")

    if not apikey.enabled:
        raise InvalidAPIKeyException("key is not enabled")

    # Log the request
    reqstr = ",".join(["%s=%s" % (k,request.REQUEST[k]) for k in request.REQUEST])
    APILog(url=request.get_full_path(),
           remoteip=request.META["REMOTE_ADDR"],
           requestvars=reqstr,
           method=request.method,
           apikey=apikey,
           useragent=request.META.get("HTTP_USER_AGENT",''),
           appver=request.META.get("HTTP_APPLICATIONVERSION",'')
    ).save()

    return apikey
    

def api_call_raw(content_type="image/jpeg"):
    """ Wrap an API call that writes raw binary data """
    def decorate(req_function):
        @wraps(req_function)
        def newreq(request, *args, **kwargs):
            try:
                validate_and_log_api_req(request)
                outp = req_function(request, *args, **kwargs)
                response = HttpResponse(outp)
                response['Content-length'] = str(len(response.content))
                response['Content-Type'] = content_type
            except HttpBadRequestException, bad_request:
                response = HttpResponseBadRequest(bad_request.message)
            
            return response
        return newreq
    return decorate
      
def api_call(content_type="application/json"):
    """ Wrap an API call that returns an object that
        is convertable from json
    """
    def decorate(req_function):
        @wraps(req_function)
        @csrf_exempt
        def newreq(request, *args, **kwargs):
            try:
                validate_and_log_api_req(request)
                outp = req_function(request, *args, **kwargs)
                if issubclass(outp.__class__, HttpResponse):
                    response = outp
                else:
                    response = HttpResponse()
                    response.write('%s' % simplejson.dumps(outp))
                    response['Content-length'] = str(len(response.content))
                    response['Content-Type'] = content_type

            except HttpBadRequestException, bad_request:
                response = HttpResponseBadRequest(bad_request.message)

            return response
            
        return newreq
    return decorate

def datetime_to_iso_string(d):
    if d:
        return d.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return None

def plot_permissions(plot, user):
    perms = { "plot": plot_or_tree_permissions(plot, user) }

    tree = plot.current_tree()
    if tree:
        perms["tree"] = plot_or_tree_permissions(tree, user)

    return perms

def plot_or_tree_permissions(obj, user):
    """ Determine what the given user can do with a tree or plot
        Returns { 
           can_delete: <boolean>, 
           can_edit: <boolean>,
        } """

    can_delete = False
    can_edit = False

    # If user is none or anonymous, they can't do anything
    if not user or user.is_anonymous():
        can_delete = False
        can_edit = False
    # If an object is readonly, it can never be deleted or edited
    elif obj.readonly:
        can_delete = False
        can_edit = False
    # If the user is an admin they can do whatever they want
    # (but not to readonly trees)
    elif user.has_perm('auth.change_user'):
        can_delete = True
        can_edit = True
    else:
        # If the user is the owner of the object
        # they can do whatever
        creator = obj.created_by
        if creator and creator.pk == user.pk:
            can_delete = True
            can_edit = True
        # If the tree is not readonly, and the user isn't an admin
        # and the user doesn't own the objet, editing is allowed
        # but delete is not
        else:
            can_delete = False
            can_edit = True
            
    return { "can_delete": can_delete, "can_edit": can_edit }

def can_delete_tree_or_plot(obj, user):
    permissions = plot_or_tree_permissions(obj, user)
    if "can_delete" in permissions:
        return permissions["can_delete"]
    else:
        # This should never happen, but raising an exception ensures that it will fail loudly if a
        # future refactoring introduces a bug.
        raise Exception("Expected the dict returned from plot_or_tree_permissions to contain 'can_delete'")


@require_http_methods(["GET"])
@api_call()
def status(request):
    return [{ 'api_version': 'v0.1',
              'status': 'online',
              'message': '' }]

@require_http_methods(["GET"])
@api_call()
@login_required
def verify_auth(request):
    user_dict = user_to_dict(request.user)
    user_dict["status"] = "success"
    return user_dict

@require_http_methods(["POST"])
@api_call()
def register(request):
    data = json.loads(request.raw_post_data)

    user = User(username=data["username"],
                first_name=data["firstname"],
                last_name=data["lastname"],
                email=data["email"])

    user.set_password(data["password"])
    user.save()

    user.reputation = Reputation(user=user)
    user.reputation.save()

    profile = UserProfile(user=user,zip_code=data["zipcode"],active=True)
    profile.save()

    return { "status": "success", "id": user.pk }

@require_http_methods(["POST"])
@api_call()
@login_required
def add_tree_photo(request, plot_id):
    uploaded_image = ContentFile(request.raw_post_data)
    uploaded_image.name = "plot_%s.png" % plot_id

    plot = Plot.objects.get(pk=plot_id)
    tree = plot.current_tree()

    if tree is None:
        import_event, created = ImportEvent.objects.get_or_create(file_name='site_add',)
        tree = Tree(plot=plot, last_updated_by=request.user, import_event=import_event)
        tree.plot = plot
        tree.last_updated_by = request.user
        tree.save()

    treephoto = TreePhoto(tree=tree,title=uploaded_image.name,reported_by=request.user)
    treephoto.photo.save("plot_%s.png" % plot_id, uploaded_image)

    treephoto.save()

    return { "status": "succes", "title": treephoto.title, "id": treephoto.pk }


@require_http_methods(["POST"])
@api_call()
@login_required
def add_profile_photo(request, user_id, title):
    uploaded_image = ContentFile(request.raw_post_data)
    uploaded_image.name = "%s.png" % title

    profile = UserProfile.objects.get(user__id=user_id)
    profile.photo.save("%s.png" % title, uploaded_image)

    profile.save()

    return { "status": "succes" }

def extract_plot_id_from_rep(repact):
    content_type = repact.content_type
    if content_type.model == "plot":
        return repact.object_id
    elif content_type.model == 'tree':
        return Tree.objects.get(pk=repact.object_id).plot.pk
    else:
        return None

@require_http_methods(["GET"])
@api_call()
@login_required
def recent_edits(request, user_id):
    if (int(user_id) != request.user.pk):
        return create_401unauthorized()

    result_offset = int(request.REQUEST.get("offset",0))
    num_results = min(int(request.REQUEST.get("length",15)),15)

    acts = UserReputationAction.objects.filter(user=request.user).order_by('-date_created')[result_offset:(result_offset+num_results)]

    keys = []
    for act in acts:
        d = {}
        plot_id = extract_plot_id_from_rep(act)
        d["plot_id"] = plot_id

        if plot_id:
            d["plot"] = plot_to_dict(Plot.objects.get(pk=plot_id),longform=True,user=request.user)

        d["id"] = act.pk
        d["name"] = act.action.name
        d["created"] = datetime_to_iso_string(act.date_created)
        d["value"] = act.value

        keys.append(d)

    return keys
    

@require_http_methods(["PUT"])
@api_call()
@login_required
def update_password(request, user_id):
    data = json.loads(request.raw_post_data)

    pw = data["password"]

    user = User.objects.get(pk=user_id)

    user.set_password(pw)
    user.save()

    return { "status": "success" }

@require_http_methods(["GET"])
@api_call_raw("otm/trees")
def get_trees_in_tile(request):
    """ API Request

    Get pixel coordinates for trees in a 256x256 tile

    Verb: GET
    Params:
       bbox - xmin,ymin,xmax,ymax projected into web mercator
       filter_diameter_min - minimum diameter (note, setting this filters trees with no diameter set)
       filter_diameter_max - maximum diameter (note, setting this filters trees with no diameter set)

    Output:
       Raw Binary format as follows:

       0xA3A5EA         - 3 byte magic number
       0x00             - 1 byte pad
       Number of points - 4 byte uint
       Section Header   - 4 bytes
       Point pair - 2 bytes
       Point pair
       ...
       Point pair
       Section Header
       ...

       Section Header:
       Position  Field          Value  Type
       Byte N    Style Type     0-255  Enum
       Byte N+1  Number of pts         Unsigned Short
       Byte N+3  -----          0      Padding

       Point Pair:
       Position Field     Type
       Byte N   X offset  Byte (Unsigned)
       Byte N+1 Y offset  Byte (Unsigned)

    """
    
    # This method should execute as fast as possible to avoid the django/ORM overhead we are going
    # to execute raw SQL queries
    from django.db import connection, transaction

    cursor = connection.cursor()

    # Construct the bbox
    bbox = request.GET['bbox']
    (xmin,ymin,xmax,ymax) = map(float,bbox.split(","))
    bboxFilterStr = "ST_GeomFromText('POLYGON(({xmin} {ymin},{xmin} {ymax},{xmax} {ymax},{xmax} {ymin},{xmin} {ymin}))', 4326)"
    bboxFilter = bboxFilterStr.format(xmin=xmin,ymin=ymin,xmax=xmax,ymax=ymax)

    (xminM,yminM) = latlng2webm(xmin,ymin) 
    (xmaxM,ymaxM) = latlng2webm(xmax,ymax)
    pixelsPerMeterX = 255.0/(xmaxM - xminM)
    pixelsPerMeterY = 255.0/(ymaxM - yminM)

    # Use postgis to do the SRS math, save ourselves some time
    tidcase = "CASE WHEN treemap_tree.id IS null THEN 0 ELSE 1 END"
    dbhcase = "CASE WHEN treemap_tree.dbh IS null THEN 0 ELSE 2 END"
    spccase = "CASE WHEN treemap_tree.species_id IS null THEN 0 ELSE 4 END"

    selectg = "%s + %s + %s as gid" % (tidcase,dbhcase,spccase)
    selectx = "ROUND((ST_X(t.geometry) - {xoffset})*{xfactor}) as x".format(xoffset=xminM,xfactor=pixelsPerMeterX)
    selecty = "ROUND((ST_Y(t.geometry) - {yoffset})*{yfactor}) as y".format(yoffset=yminM,yfactor=pixelsPerMeterY)
    query = "SELECT {xfield}, {yfield}, {gfield}".format(xfield=selectx,yfield=selecty,gfield=selectg)

    force_species_join = False

    filters = []
    filter_values = {}
    if "filter_dbh_min" in request.GET:
        filters.append("treemap_tree.dbh >= %(filter_diameter_min)s")
        filter_values["filter_diameter_min"] = float(request.GET['filter_dbh_min'])

    if "filter_dbh_max" in request.GET:
        filters.append("treemap_tree.dbh <= %(filter_diameter_max)s")
        filter_values["filter_diameter_max"] = float(request.GET['filter_dbh_max'])

    if "filter_edible" in request.GET:
        filters.append("treemap_species.palatable_human = %(edible)s")
        filter_values["edible"] = request.GET['filter_edible'] == "true"
        force_species_join = True

    if "filter_flowering" in request.GET:
        filters.append("treemap_species.flower_conspicuous = %(flower_conspicuous)s")
        filter_values["flower_conspicuous"] = request.GET['filter_flowering']
        force_species_join = True

    if "filter_native" in request.GET:
        filters.append("treemap_species.native_status = %(native_status)s")
        if request.GET['filter_native'].lower() == "true":
            b = "True"
        else:
            b = "False"

        filter_values["native_status"] = b
        force_species_join = True

    if "filter_fall_colors" in request.GET:
        filters.append("treemap_species.fall_conspicuous = %(fall_conspicuous)s")
        filter_values["fall_conspicuous"] = request.GET['filter_fall_colors']
        force_species_join = True

    if "filter_species" in request.GET:
        filters.append("treemap_tree.species_id = %(species_id)s")
        filter_values["species_id"] = int(request.GET['filter_species'])

    where = "where ST_Contains({bfilter},geometry) AND treemap_plot.present".format(bfilter=bboxFilter)
    subselect = "select ST_Transform(geometry, 900913) as geometry, id from treemap_plot {where}".format(where=where)
    fromq = "FROM ({subselect}) as t LEFT OUTER JOIN treemap_tree ON treemap_tree.plot_id=t.id".format(subselect=subselect)
    
    if force_species_join:
        fromq += " LEFT OUTER JOIN treemap_species ON treemap_species.id=treemap_tree.species_id"

    order = "order by x,y"

    where = ""
    if len(filters) > 0:
        where = "WHERE %s" % (" AND ".join(filters))

    selectQuery = "{0} {1} {2} {3}".format(query, fromq, where, order)

    cursor.execute(selectQuery, filter_values)
    transaction.commit_unless_managed()

    # We have the sorted list, now we want to remove duplicates
    results = []
    rows = cursor.fetchall()
    n = len(rows)

    if n > 0:
        last = rows[0]
        lasti = i = 1
        while i < n:
            if rows[i] != last:
                rows[lasti] = last = rows[i]
                lasti += 1
            i += 1

        rows = rows[:lasti]
    
    # Partition into groups
    groups = {}
    for (x,y,g) in rows:
        if g not in groups:
            groups[g] = []
        
        groups[g].append((x,y))

    # After removing duplicates, we can have at most 1 tree per square
    # (since we are using integer values that fall on pixels)
    assert len(rows) <= 65536 # 256*256

    # right now we only show "type 1" trees so the header is
    # 1 | n trees | 0 | size
    sizeoffileheader = 4+4
    numsections = len(groups)
    sizeofsectionheaders = (1+2+1)*numsections
    sizeofrecord = 2
    buffersize = sizeoffileheader + sizeofsectionheaders + sizeofrecord*len(rows)

    buf = ctypes.create_string_buffer(buffersize)
    bufoffset = 0

    # File Header: magic (3), pad(1), length (4)
    # Little endian, no align
    struct.pack_into("<II", buf, bufoffset, 0xA3A5EA00, len(rows))
    bufoffset += 8 #sizeoffileheader

    for group in groups.keys():
        pts = groups[group]

        # Section header: type (1), num(4)
        # Little endian, no align
        # Default to type 1
        struct.pack_into("<BHx", buf, bufoffset, group, len(pts))
        bufoffset += 4 #sizeofheader

        # Write pairs: x(1), y(1)
        # Litle endian, no align
        for (x,y) in pts:
            struct.pack_into("<BB", buf, bufoffset, x, y)
            bufoffset += 2 #sizeofrecord

    return buf.raw

def latlng2webm(lat,lng):
    num = lat * 0.017453292519943295
    x = 6378137.0 * num
    a = lng * 0.017453292519943295

    y = 3189068.5*math.log((1.0 + math.sin(a))/(1.0 - math.sin(a)))

    return (x,y)

@require_http_methods(["POST"])
@api_call()
def reset_password(request):
    resetform = PasswordResetForm({ "email" : request.REQUEST["email"]})

    if (resetform.is_valid()):
        opts = {
            'use_https': request.is_secure(),
            'token_generator': default_token_generator,
            'from_email': None,
            'email_template_name': 'reset_email_password.html',
            'request': request,
            }

        resetform.save(**opts)
        return { "status": "success" }
    else:
        raise HttpBadRequestException()

@require_http_methods(["GET"])
@api_call()
def version(request):
    """ API Request
    
    Get version information for OTM and the API. Generally, the API is unstable for
    any API version < 1 and minor changes (i.e. 1.4,1.5,1.6) represent no break in
    existing functionality

    Verb: GET
    Params: None
    Output:
      { 
        otm_version, string -> Open Tree Map Version (i.e. 1.0.2)
        api_version, string -> API version (i.e. 1.6) 
      }

    """
    return { "otm_version": settings.OTM_VERSION,
             "api_version": settings.API_VERSION }

@require_http_methods(["GET"])
@api_call_raw("image/jpeg")
def get_tree_image(request, plot_id, photo_id):
    """ API Request

    Verb: GET
    Params:
       
    Output:
      image/jpeg raw data
    """
    treephoto = TreePhoto.objects.get(pk=photo_id)

    if treephoto.tree.plot.pk == int(plot_id):
        return open(treephoto.photo.path, 'rb').read()
    else:
        raise HttpBadRequestException('invalid url (missing objects)')

@require_http_methods(["GET"])
@api_call()
def get_plot_list(request):
    """ API Request

    Get a list of all plots in the database. This is meant to be a lightweight
    listing service. To get more details about a plot use the ^plot/{id}$ service
    
    Verb: GET
    Params: 
      offset, integer, default = 0  -> offset to start results from
      size, integer, default = 100 -> Maximum 10000, number of results to get

    Output:
      [{
          width, integer, opt -> Width of tree bed
          length, integer, opt -> Length of bed
          type, string, opt -> Plot type
          geometry, Point -> Lat/lng pt
          readonly, boolean -> True if this is a readonly tree
          tree, {
             id, integer -> tree id
             species, integer, opt -> Species id
             dbh, real, opt -> Diameter of the tree
          }             
       }]

      """
    start = int(request.REQUEST.get("offset","0"))
    size = min(int(request.REQUEST.get("size", "100")), 10000)
    end = size + start

    # order_by prevents testing weirdness
    plots = Plot.objects.filter(present=True).order_by('id')[start:end]

    return plots_to_list_of_dict(plots,user=request.user)

@require_http_methods(["GET"])
@api_call()
def species_list(request, lat=None, lon=None):
    allspecies = Species.objects.all()

    return [species_to_dict(z) for z in allspecies]

@require_http_methods(["GET"])
@api_call()
@login_optional
def plots_closest_to_point(request, lat=None, lon=None):
    point = Point(float(lon), float(lat), srid=4326)

    distance_string = request.GET.get('distance', settings.MAP_CLICK_RADIUS)
    try:
        distance = float(distance_string)
    except ValueError:
        raise HttpBadRequestException('The distance parameter must be a number')

    max_plots_string = request.GET.get('max_plots', '1')
    try:
        max_plots = int(max_plots_string)
    except ValueError:
        raise HttpBadRequestException('The max_plots parameter must be a number between 1 and 500')

    if max_plots > 500 or max_plots < 1:
        raise HttpBadRequestException('The max_plots parameter must be a number between 1 and 500')

    species = request.GET.get('species', None)

    sort_recent = request.GET.get('filter_recent', None)
    if sort_recent and sort_recent == "true":
        sort_recent = True
    else:
        sort_recent = False

    sort_pending = request.GET.get('filter_pending', None)
    if sort_pending and sort_pending == "true":
        sort_pending = True
    else:
        sort_pending = False

    has_tree = request.GET.get("has_tree",None)
    if has_tree:
        if has_tree == "true":
            has_tree = True
        else:
            has_tree = False

    has_species = request.GET.get("has_species",None)
    if has_species:
        if has_species == "true":
            has_species = True
        else:
            has_species = False

    has_dbh = request.GET.get("has_dbh",None)
    if has_dbh:
        if has_dbh == "true":
            has_dbh = True
        else:
            has_dbh = False

    plots, extent = Plot.locate.with_geometry(
        point, distance, max_plots, species,
        native=str2bool(request.GET,"filter_native"),
        flowering=str2bool(request.GET,'filter_flowering'),
        fall=str2bool(request.GET,'filter_fall_colors'),
        edible=str2bool(request.GET,'filter_edible'),
        dbhmin=request.GET.get("filter_dbh_min",None),
        dbhmax=request.GET.get("filter_dbh_max",None),
        species=request.GET.get("filter_species",None),
        sort_recent=sort_recent, sort_pending=sort_pending,
        has_tree=has_tree, has_species=has_species, has_dbh=has_dbh)

    return plots_to_list_of_dict(plots, longform=True, user=request.user)

def str2bool(ahash, akey):
    if akey in ahash:
        return ahash[akey] == "true"
    else:
        return None

def plots_to_list_of_dict(plots,longform=False,user=None):
    return [plot_to_dict(plot,longform=longform,user=user) for plot in plots]

def point_wkt_to_dict(wkt):
    point = fromstr(wkt)
    return {
        'lat': point.y,
        'lng': point.x,
        'srid': '4326'
    }

def pending_edit_to_dict(pending_edit):
    if pending_edit.field == 'geometry':
        pending_value = point_wkt_to_dict(pending_edit.value) # Pending geometry edits are stored as WKT
    else:
        pending_value = pending_edit.value
    print 'pending_value=%s' % pending_value

    return {
        'id': pending_edit.pk,
        'submitted': datetime_to_iso_string(pending_edit.submitted),
        'value': pending_value,
        'username': pending_edit.submitted_by.username
    }

def plot_to_dict(plot,longform=False,user=None):
    pending_edit_dict = {} #If settings.PENDING_ON then this will be populated and included in the response
    current_tree = plot.current_tree()
    if current_tree:
        tree_dict = { "id" : current_tree.pk }

        if current_tree.species:
            tree_dict["species"] = current_tree.species.pk
            tree_dict["species_name"] = current_tree.species.common_name
            tree_dict["sci_name"] = current_tree.get_scientific_name()

        if current_tree.dbh:
            tree_dict["dbh"] = current_tree.dbh

        if current_tree.height:
            tree_dict["height"] = current_tree.height

        if current_tree.canopy_height:
            tree_dict["canopy_height"] = current_tree.canopy_height

        images = current_tree.treephoto_set.all()

        if len(images) > 0:
            tree_dict["images"] = [{ "id": image.pk, "title": image.title } for image in images]

        if longform:
            tree_dict['tree_owner'] = current_tree.tree_owner
            tree_dict['steward_name'] = current_tree.steward_name
            tree_dict['sponsor'] = current_tree.sponsor

            if len(TreeResource.objects.filter(tree=current_tree)) > 0:
                tree_dict['eco'] = tree_resource_to_dict(current_tree.treeresource)

            if current_tree.steward_user:
                tree_dict['steward_user'] = current_tree.steward_user

            tree_dict['species_other1'] = current_tree.species_other1
            tree_dict['species_other2'] = current_tree.species_other2
            tree_dict['date_planted'] = datetime_to_iso_string(current_tree.date_planted)
            tree_dict['date_removed'] = datetime_to_iso_string(current_tree.date_removed)
            tree_dict['present'] = current_tree.present
            tree_dict['last_updated'] = datetime_to_iso_string(current_tree.last_updated)
            tree_dict['last_updated_by'] = current_tree.last_updated_by.username
            tree_dict['condition'] = current_tree.condition
            tree_dict['canopy_condition'] = current_tree.canopy_condition
            tree_dict['readonly'] = current_tree.readonly

            if settings.PENDING_ON:
                tree_field_reverse_property_name_dict = {'species_id': 'species'}
                for raw_field_name, detail in current_tree.get_active_pend_dictionary().items():
                    if raw_field_name in tree_field_reverse_property_name_dict:
                        field_name = tree_field_reverse_property_name_dict[raw_field_name]
                    else:
                        field_name = raw_field_name
                    pending_edit_dict['tree.' + field_name] = {'latest_value': detail['latest_value'], 'pending_edits': []}
                    for pend in detail['pending_edits']:
                        pend_dict = pending_edit_to_dict(pend)
                        if field_name == 'species':
                            species_set = Species.objects.filter(pk=pend_dict['value'])
                            if species_set:
                                pend_dict['related_fields'] = {
                                    'tree.sci_name': species_set[0].scientific_name,
                                    'tree.species_name': species_set[0].common_name
                                }
                        pending_edit_dict['tree.' + field_name]['pending_edits'].append(pend_dict)

    else:
        tree_dict = None

    base = {
        "id": plot.pk,
        "plot_width": plot.width,
        "plot_length": plot.length,
        "plot_type": plot.type,
        "readonly": plot.readonly,
        "tree": tree_dict,
        "address": plot.geocoded_address,
        "geometry": {
            "srid": plot.geometry.srid,
            "lat": plot.geometry.y,
            "lng": plot.geometry.x
        }
    }

    if user:
        base["perm"] = plot_permissions(plot,user)

    if longform:
        base['power_lines'] = plot.powerline_conflict_potential
        base['sidewalk_damage'] = plot.sidewalk_damage
        base['address_street'] = plot.address_street
        base['address_city'] = plot.address_city
        base['address_zip'] = plot.address_zip

        if plot.data_owner:
            base['data_owner'] = plot.data_owner.pk

        base['last_updated'] = datetime_to_iso_string(plot.last_updated)

        if plot.last_updated_by:
            base['last_updated_by'] = plot.last_updated_by.username

        if settings.PENDING_ON:
            plot_field_reverse_property_name_dict = {'width': 'plot_width', 'length': 'plot_length', 'powerline_conflict_potential': 'power_lines'}

            for raw_field_name, detail in plot.get_active_pend_dictionary().items():
                if raw_field_name in plot_field_reverse_property_name_dict:
                    field_name = plot_field_reverse_property_name_dict[raw_field_name]
                else:
                    field_name = raw_field_name

                if field_name == 'geometry':
                    latest_value = point_wkt_to_dict(detail['latest_value'])
                else:
                    latest_value = detail['latest_value']

                pending_edit_dict[field_name] = {'latest_value': latest_value, 'pending_edits': []}
                for pend in detail['pending_edits']:
                    pending_edit_dict[field_name]['pending_edits'].append(pending_edit_to_dict(pend))
            base['pending_edits'] = pending_edit_dict

    return base

def tree_resource_to_dict(tr):
    return {
    "annual_stormwater_management": with_unit(tr.annual_stormwater_management, "gallons"),
    "annual_electricity_conserved": with_unit(tr.annual_electricity_conserved, "kWh"),
    "annual_energy_conserved": with_unit(tr.annual_energy_conserved, "kWh"),
    "annual_natural_gas_conserved": with_unit(tr.annual_natural_gas_conserved, "kWh"),
    "annual_air_quality_improvement": with_unit(tr.annual_air_quality_improvement, "lbs"),
    "annual_co2_sequestered": with_unit(tr.annual_co2_sequestered, "lbs"),
    "annual_co2_avoided": with_unit(tr.annual_co2_avoided, "lbs"),
    "annual_co2_reduced": with_unit(tr.annual_co2_reduced, "lbs"),
    "total_co2_stored": with_unit(tr.total_co2_stored, "lbs"),
    "annual_ozone": with_unit(tr.annual_ozone, "lbs"),
    "annual_nox": with_unit(tr.annual_nox, "lbs"),
    "annual_pm10": with_unit(tr.annual_pm10, "lbs"),
    "annual_sox": with_unit(tr.annual_sox, "lbs"),
    "annual_voc": with_unit(tr.annual_voc, "lbs"),
    "annual_bvoc": with_unit(tr.annual_bvoc, "lbs") }
    
def with_unit(val,unit):
    return { "value": val, "unit": unit }
        

def species_to_dict(s):
    return {
        "id": s.pk,
        "scientific_name": s.scientific_name,
        "genus": s.genus,
        "species": s.species,
        "cultivar": s.cultivar_name,
        "gender": s.gender,
        "common_name": s.common_name }


def user_to_dict(user):
    return {
        "id": user.pk,
        "firstname": user.first_name,
        "lastname": user.last_name,
        "email": user.email,
        "username": user.username,
        "zipcode": UserProfile.objects.get(user__pk=user.pk).zip_code,
        "reputation": Reputation.objects.reputation_for_user(user).reputation,
        "permissions": list(user.get_all_permissions()),
        "user_type": user_access_type(user)
        }

def user_access_type(user):
    """ Given a user, determine the name and "level" of a user """
    if user.is_superuser:
        return { 'name': 'administrator', 'level': 1000 }
    elif Reputation.objects.reputation_for_user(user).reputation > 1000:
        return { 'name': 'editor', 'level': 500 }
    else:
        return { 'name': 'public', 'level': 0 }


@require_http_methods(["GET"])
@api_call()
def geocode_address(request, address):
    def result_in_bounding_box(result):
        x = float(result.x)
        y = float(result.y)
        left = float(settings.BOUNDING_BOX['left'])
        top = float(settings.BOUNDING_BOX['top'])
        right = float(settings.BOUNDING_BOX['right'])
        bottom = float(settings.BOUNDING_BOX['bottom'])
        return x > left and x < right and y > bottom and y < top

    if address is None or len(address) == 0:
        raise HttpBadRequestException("No address specfified")

    query = PlaceQuery(address, viewbox=Viewbox(
        settings.BOUNDING_BOX['left'],
        settings.BOUNDING_BOX['top'],
        settings.BOUNDING_BOX['right'],
        settings.BOUNDING_BOX['bottom'])
    )

    if 'OMGEO_GEOCODER_SOURCES' in dir(settings) and settings.OMGEO_GEOCODER_SOURCES is not None:
        geocoder = Geocoder(settings.OMGEO_GEOCODER_SOURCES)
    else:
        geocoder = Geocoder()

    results = geocoder.geocode(query)
    if results != False:
        response = []
        for result in results:
            if result_in_bounding_box(result): # some geocoders do not support passing a bounding box filter
                response.append({
                     "match_addr": result.match_addr,
                     "x": result.x,
                     "y": result.y,
                     "score": result.score,
                     "locator": result.locator,
                     "geoservice": result.geoservice,
                     "wkid": result.wkid,
                })
        return response
    else:
        # This is not a very helpful error message, but omgeo as of v1.2 does not
        # report failure details.
        return {"error": "The geocoder failed to generate a list of results."}

def flatten_plot_dict_with_tree_and_geometry(plot_dict):
    if 'tree' in plot_dict and plot_dict['tree'] is not None:
        tree_dict = plot_dict['tree']
        for field_name in tree_dict.keys():
            plot_dict[field_name] = tree_dict[field_name]
        del plot_dict['tree']
    if 'geometry' in plot_dict:
        geometry_dict = plot_dict['geometry']
        for field_name in geometry_dict.keys():
            plot_dict[field_name] = geometry_dict[field_name]
        del plot_dict['geometry']

def rename_plot_request_dict_fields(request_dict):
    '''
    The new plot/tree form requires specific field names that do not directly match
    up with the model objects (e.g. the form expects a 'species_id' field) so this
    helper function renames keys in the dictionary to match what the form expects
    '''
    field_map = {'species': 'species_id', 'width': 'plot_width', 'length': 'plot_length'}
    for map_key in field_map.keys():
        if map_key in request_dict:
            request_dict[field_map[map_key]] = request_dict[map_key]
            del request_dict[map_key]
    return request_dict

@require_http_methods(["POST"])
@api_call()
@login_required
def create_plot_optional_tree(request):
    response = HttpResponse()

    # Unit tests fail to access request.raw_post_data
    request_dict = json_from_request(request)

    # The Django form used to validate and save plot and tree information expects
    # a flat dictionary. Allowing the tree and geometry details to be in nested
    # dictionaries in API calls clarifies, to API clients, the distinction between
    # Plot and Tree and groups the coordinates along with their spatial reference
    flatten_plot_dict_with_tree_and_geometry(request_dict)

    # The new plot/tree form requires specific field names that do not directly match
    # up with the model objects (e.g. the form expects a 'species_id' field) so this
    # helper function renames keys in the dictionary to match what the form expects
    rename_plot_request_dict_fields(request_dict)

    form = TreeAddForm(request_dict, request.FILES)

    if not form.is_valid():
        response.status_code = 400
        if '__all__' in form.errors:
            response.content = simplejson.dumps({"error": form.errors['__all__']})
        else:
            response.content = simplejson.dumps({"error": form.errors})
        return response

    try:
        new_plot = form.save(request)
    except ValidationError, ve:
        response.status_code = 400
        response.content = simplejson.dumps({"error": form.error_class(ve.messages)})
        return response

    new_tree = new_plot.current_tree()
    if new_tree:
        change_reputation_for_user(request.user, 'add tree', new_tree)
    else:
        change_reputation_for_user(request.user, 'add plot', new_plot)

    response.status_code = 201
    response.content = "{\"ok\": %d}" % new_plot.id
    return response

@require_http_methods(["GET"])
@api_call()
@login_optional
def get_plot(request, plot_id):
    return plot_to_dict(Plot.objects.get(pk=plot_id),longform=True,user=request.user)

def compare_fields(v1,v2):
    if v1 is None:
        return v1 == v2
    try:
        v1f = float(v1)
        v2f = float(v2)
        return v1f == v2f
    except ValueError:
        return v1 == v2

@require_http_methods(["PUT"])
@api_call()
@login_required
def update_plot_and_tree(request, plot_id):
    response = HttpResponse()
    try:
        plot = Plot.objects.get(pk=plot_id)
    except Plot.DoesNotExist:
        response.status_code = 400
        response.content = simplejson.dumps({"error": "No plot with id %s" % plot_id})
        return response

    request_dict = json_from_request(request)
    flatten_plot_dict_with_tree_and_geometry(request_dict)

    plot_field_whitelist = ['plot_width','plot_length','type','geocoded_address','edit_address_street', 'address_city', 'address_street', 'address_zip', 'power_lines', 'sidewalk_damage']

    # The Django form that creates new plots expects a 'plot_width' parameter but the
    # Plot model has a 'width' parameter so this dict acts as a translator between request
    # keys and model field names
    plot_field_property_name_dict = {'plot_width': 'width', 'plot_length': 'length', 'power_lines': 'powerline_conflict_potential'}

    # The 'auth.change_user' permission is a proxy for 'is the user a manager'
    user_is_not_a_manager = not request.user.has_perm('auth.change_user')
    should_create_plot_pends = settings.PENDING_ON and plot.was_created_by_a_manager and user_is_not_a_manager

    plot_was_edited = False
    for plot_field_name in request_dict.keys():
        if plot_field_name in plot_field_whitelist:
            if plot_field_name in plot_field_property_name_dict:
                new_name = plot_field_property_name_dict[plot_field_name]
            else:
                new_name = plot_field_name
            new_value = request_dict[plot_field_name]
            if not compare_fields(getattr(plot, new_name), new_value):
                if should_create_plot_pends:
                    plot_pend = PlotPending(plot=plot)
                    plot_pend.set_create_attributes(request.user, new_name, new_value)
                    plot_pend.save()
                else:
                    setattr(plot, new_name, new_value)
                    plot_was_edited = True

    # TODO: Standardize on lon or lng
    if 'lat' in request_dict or 'lon' in request_dict or 'lng' in request_dict:
        new_geometry = Point(x=plot.geometry.x, y=plot.geometry.y)
        if 'lat' in request_dict:
            new_geometry.y = request_dict['lat']
        if 'lng' in request_dict:
            new_geometry.x = request_dict['lng']
        if 'lon' in request_dict:
            new_geometry.x = request_dict['lon']

        if plot.geometry.x != new_geometry.x or plot.geometry.y != new_geometry.y:
            if should_create_plot_pends:
                plot_pend = PlotPending(plot=plot)
                plot_pend.set_create_attributes(request.user, 'geometry', new_geometry)
                plot_pend.save()
            else:
                plot.geometry = new_geometry
                plot_was_edited = True

    if plot_was_edited:
        plot.last_updated = datetime.datetime.now()
        plot.last_updated_by = request.user
        plot.save()
        change_reputation_for_user(request.user, 'edit plot', plot)

    tree_was_edited = False
    tree_was_added = False
    tree = plot.current_tree()
    tree_field_whitelist = ['species','dbh','height','canopy_height', 'canopy_condition']

    if tree is None:
        should_create_tree_pends = False
    else:
        should_create_tree_pends = settings.PENDING_ON and tree.was_created_by_a_manager and user_is_not_a_manager

    for tree_field in Tree._meta.fields:
        if tree_field.name in request_dict and tree_field.name in tree_field_whitelist:
            if tree is None:
                import_event, created = ImportEvent.objects.get_or_create(file_name='site_add',)
                tree = Tree(plot=plot, last_updated_by=request.user, import_event=import_event)
                tree.plot = plot
                tree.last_updated_by = request.user
                tree.save()
                tree_was_added = True
            if tree_field.name == 'species':
                try:
                    if (tree.species and tree.species.pk != request_dict[tree_field.name]) \
                    or (not tree.species and request_dict[tree_field.name]):
                        if should_create_tree_pends:
                            tree_pend = TreePending(tree=tree)
                            tree_pend.set_create_attributes(request.user, 'species_id', request_dict[tree_field.name])
                            tree_pend.save()
                        else:
                            tree.species = Species.objects.get(pk=request_dict[tree_field.name])
                            tree_was_edited = True
                except Exception:
                    response.status_code = 400
                    response.content = simplejson.dumps({"error": "No species with id %s" % request_dict[tree_field.name]})
                    return response
            else: # tree_field.name != 'species'
                if not compare_fields(getattr(tree, tree_field.name), request_dict[tree_field.name]):
                    if should_create_tree_pends:
                        tree_pend = TreePending(tree=tree)
                        tree_pend.set_create_attributes(request.user, tree_field.name, request_dict[tree_field.name])
                        tree_pend.save()
                    else:
                        setattr(tree, tree_field.name, request_dict[tree_field.name])
                        tree_was_edited = True

    if tree_was_edited:
        tree.last_updated = datetime.datetime.now()
        tree.last_updated_by = request.user

    if tree_was_added or tree_was_edited:
        tree.save()

    # You cannot get reputation for both adding and editing a tree in one action
    # so I use an elif here
    if tree_was_added:
        change_reputation_for_user(request.user, 'add tree', tree)
    elif tree_was_edited:
        change_reputation_for_user(request.user, 'edit tree', tree)

    full_plot = Plot.objects.get(pk=plot.id)
    return_dict = plot_to_dict(full_plot, longform=True,user=request.user)
    response.status_code = 200
    response.content = simplejson.dumps(return_dict)
    return response

@require_http_methods(["POST"])
@api_call()
@login_required
@permission_required_or_403_forbidden('treemap.change_pending')
def approve_pending_edit(request, pending_edit_id):
    pend, model = get_tree_pend_or_plot_pend_by_id_or_404_not_found(pending_edit_id)

    pend.approve_and_reject_other_active_pends_for_the_same_field(request.user)

    if model == 'Tree':
        change_reputation_for_user(pend.submitted_by, 'edit tree', pend.tree, change_initiated_by_user=pend.updated_by)
        updated_plot = Plot.objects.get(pk=pend.tree.plot.id)
    else: # model == 'Plot'
        change_reputation_for_user(pend.submitted_by, 'edit plot', pend.plot, change_initiated_by_user=pend.updated_by)
        updated_plot = Plot.objects.get(pk=pend.plot.id)

    return plot_to_dict(updated_plot, longform=True)

@require_http_methods(["POST"])
@api_call()
@login_required
@permission_required_or_403_forbidden('treemap.change_pending')
def reject_pending_edit(request, pending_edit_id):
    pend, model = get_tree_pend_or_plot_pend_by_id_or_404_not_found(pending_edit_id)
    pend.reject(request.user)
    if model == 'Tree':
        updated_plot = Plot.objects.get(pk=pend.tree.plot.id)
    else: # model == 'Plot'
        updated_plot = Plot.objects.get(pk=pend.plot.id)
    return plot_to_dict(updated_plot, longform=True)


@require_http_methods(["DELETE"])
@api_call()
@login_required
@transaction.commit_on_success
def delete_plot(request, plot_id):
    plot = get_object_or_404(Plot, pk=plot_id)
    if can_delete_tree_or_plot(plot, request.user):
        plot.delete()
        return {"ok": True}
    else:
        raise PermissionDenied('%s does not have permission to delete plot %s' % (request.user.username, plot_id))

@require_http_methods(["DELETE"])
@api_call()
@login_required
@transaction.commit_on_success
def delete_current_tree_from_plot(request, plot_id):
    plot = get_object_or_404(Plot, pk=plot_id)
    tree = plot.current_tree()
    if tree:
        if can_delete_tree_or_plot(tree, request.user):
            tree.delete()
            updated_plot = Plot.objects.get(pk=plot_id)
            return plot_to_dict(updated_plot, longform=True, user=request.user)
        else:
            raise PermissionDenied('%s does not have permission to the current tree from plot %s' % (request.user.username, plot_id))
    else:
        raise HttpResponseBadRequest("Plot %s does not have a current tree" % plot_id)

@require_http_methods(["GET"])
@api_call()
def get_current_tree_from_plot(request, plot_id):
    plot = get_object_or_404(Plot, pk=plot_id)
    if  plot.current_tree():
        plot_dict = plot_to_dict(plot, longform=True)
        return plot_dict['tree']
    else:
        raise HttpResponseBadRequest("Plot %s does not have a current tree" % plot_id)
