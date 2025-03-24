from util.json_request import expect_json
import exceptions
import json
import logging
import mimetypes
import os
import StringIO
import sys
import time
from collections import defaultdict
from uuid import uuid4

# to install PIL on MacOSX: 'easy_install http://dist.repoze.org/PIL-1.1.6.tar.gz'
from PIL import Image

from django.http import HttpResponse, Http404, HttpResponseBadRequest, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.context_processors import csrf
from django_future.csrf import ensure_csrf_cookie
from django.core.urlresolvers import reverse
from django.conf import settings
from django import forms

from xmodule.modulestore import Location
from xmodule.x_module import ModuleSystem
from xmodule.error_module import ErrorDescriptor
from xmodule.errortracker import exc_info_to_str
from github_sync import export_to_github
from static_replace import replace_urls

from mitxmako.shortcuts import render_to_response, render_to_string
from xmodule.modulestore.django import modulestore
from xmodule_modifiers import replace_static_urls, wrap_xmodule
from xmodule.exceptions import NotFoundError
from functools import partial
from itertools import groupby
from operator import attrgetter

from xmodule.contentstore.django import contentstore
from xmodule.contentstore.content import StaticContent

from cache_toolbox.core import set_cached_content, get_cached_content, del_cached_content
from auth.authz import is_user_in_course_group_role, get_users_in_course_group_by_role
from auth.authz import get_user_by_email, add_user_to_course_group, remove_user_from_course_group
from auth.authz import INSTRUCTOR_ROLE_NAME, STAFF_ROLE_NAME
from .utils import get_course_location_for_item, get_lms_link_for_item, compute_unit_state

from xmodule.templates import all_templates

log = logging.getLogger(__name__)


COMPONENT_TYPES = ['customtag', 'discussion', 'html', 'problem', 'video']


# ==== Public views ==================================================

@ensure_csrf_cookie
def signup(request):
    """
    Display the signup form.
    """
    csrf_token = csrf(request)['csrf_token']
    return render_to_response('signup.html', {'csrf': csrf_token})


@ensure_csrf_cookie
def login_page(request):
    """
    Display the login form.
    """
    csrf_token = csrf(request)['csrf_token']
    return render_to_response('login.html', {'csrf': csrf_token})


# ==== Views for any logged-in user ==================================

@login_required
@ensure_csrf_cookie
def index(request):
    """
    List all courses available to the logged in user
    """
    courses = modulestore().get_items(['i4x', None, None, 'course', None])

    # filter out courses that we don't have access to
    courses = filter(lambda course: has_access(request.user, course.location), courses)

    return render_to_response('index.html', {
        'courses': [(course.metadata.get('display_name'),
                    reverse('course_index', args=[
                        course.location.org,
                        course.location.course,
                        course.location.name]))
                    for course in courses]
    })


# ==== Views with per-item permissions================================

def has_access(user, location, role=STAFF_ROLE_NAME):
    '''
    Return True if user allowed to access this piece of data
    Note that the CMS permissions model is with respect to courses
    There is a super-admin permissions if user.is_staff is set
    Also, since we're unifying the user database between LMS and CAS, 
    I'm presuming that the course instructor (formally known as admin)
    will not be in both INSTRUCTOR and STAFF groups, so we have to cascade our queries here as INSTRUCTOR
    has all the rights that STAFF do
    '''
    course_location = get_course_location_for_item(location)
    _has_access = is_user_in_course_group_role(user, course_location, role)
    # if we're not in STAFF, perhaps we're in INSTRUCTOR groups
    if not _has_access and role == STAFF_ROLE_NAME:
        _has_access = is_user_in_course_group_role(user, course_location, INSTRUCTOR_ROLE_NAME)
    return _has_access


@login_required
@ensure_csrf_cookie
def course_index(request, org, course, name):
    """
    Display an editable course overview.

    org, course, name: Attributes of the Location for the item to edit
    """
    location = ['i4x', org, course, 'course', name]
    
    # check that logged in user has permissions to this item
    if not has_access(request.user, location):
        raise PermissionDenied()

    upload_asset_callback_url = reverse('upload_asset', kwargs = {
            'org' : org,
            'course' : course,
            'coursename' : name
            })

    course = modulestore().get_item(location)
    sections = course.get_children()

    return render_to_response('overview.html', {
        'sections': sections,
        'parent_location': course.location,
        'new_section_template': Location('i4x', 'edx', 'templates', 'chapter', 'Empty'),
        'new_subsection_template': Location('i4x', 'edx', 'templates', 'sequential', 'Empty'),  # for now they are the same, but the could be different at some point...
        'upload_asset_callback_url': upload_asset_callback_url,
        'create_new_unit_template': Location('i4x', 'edx', 'templates', 'vertical', 'Empty')
    })


@login_required
def edit_subsection(request, location):
    # check that we have permissions to edit this item
    if not has_access(request.user, location):
        raise PermissionDenied()

    item = modulestore().get_item(location)

    lms_link = get_lms_link_for_item(location)

    # make sure that location references a 'sequential', otherwise return BadRequest
    if item.location.category != 'sequential':
        return HttpResponseBadRequest

    parent_locs = modulestore().get_parent_locations(location)

    # we're for now assuming a single parent
    if len(parent_locs) != 1:
        logging.error('Multiple (or none) parents have been found for {0}'.format(location))

    # this should blow up if we don't find any parents, which would be erroneous
    parent = modulestore().get_item(parent_locs[0])

    # remove all metadata from the generic dictionary that is presented in a more normalized UI

    policy_metadata = dict((key,value) for key, value in item.metadata.iteritems() 
        if key not in ['display_name', 'start', 'due', 'format'] and key not in item.system_metadata_fields)

    logging.debug(policy_metadata)

    return render_to_response('edit_subsection.html',
                              {'subsection': item,
                               'create_new_unit_template': Location('i4x', 'edx', 'templates', 'vertical', 'Empty'),
                               'lms_link': lms_link,
                               'parent_item' : parent,
                               'policy_metadata' : policy_metadata
                               })


@login_required
def edit_unit(request, location):
    """
    Display an editing page for the specified module.

    Expects a GET request with the parameter 'id'.

    id: A Location URL
    """
    # check that we have permissions to edit this item
    if not has_access(request.user, location):
        raise PermissionDenied()

    item = modulestore().get_item(location)

    # The non-draft location
    lms_link = get_lms_link_for_item(item.location._replace(revision=None))

    component_templates = defaultdict(list)

    templates = modulestore().get_items(Location('i4x', 'edx', 'templates'))
    for template in templates:
        if template.location.category in COMPONENT_TYPES:
            component_templates[template.location.category].append((
                template.display_name,
                template.location.url(),
            ))

    components = [
        component.location.url()
        for component
        in item.get_children()
    ]

    # TODO (cpennington): If we share units between courses,
    # this will need to change to check permissions correctly so as
    # to pick the correct parent subsection
    containing_subsection_locs = modulestore().get_parent_locations(location)
    containing_subsection = modulestore().get_item(containing_subsection_locs[0])

    containing_section_locs = modulestore().get_parent_locations(containing_subsection.location)
    containing_section = modulestore().get_item(containing_section_locs[0])

    unit_state = compute_unit_state(item)

    try:
        published_date = time.strftime('%B %d, %Y', item.metadata.get('published_date'))
    except TypeError:
        published_date = None

    return render_to_response('unit.html', {
        'unit': item,
        'unit_location': location,
        'components': components,
        'component_templates': component_templates,
        'draft_preview_link': lms_link,
        'published_preview_link': lms_link,
        'subsection': containing_subsection,
        'section': containing_section,
        'create_new_unit_template': Location('i4x', 'edx', 'templates', 'vertical', 'Empty'),
        'unit_state': unit_state,
        'published_date': published_date,
    })


@login_required
def preview_component(request, location):
    # TODO (vshnayder): change name from id to location in coffee+html as well.
    if not has_access(request.user, location):
        raise Http404  # TODO (vshnayder): better error

    component = modulestore().get_item(location)

    return render_to_response('component.html', {
        'preview': get_module_previews(request, component)[0],
        'editor': wrap_xmodule(component.get_html, component, 'xmodule_edit.html')(),
    })


def user_author_string(user):
    '''Get an author string for commits by this user.  Format:
    first last <email@email.com>.

    If the first and last names are blank, uses the username instead.
    Assumes that the email is not blank.
    '''
    f = user.first_name
    l = user.last_name
    if f == '' and l == '':
        f = user.username
    return '{first} {last} <{email}>'.format(first=f,
                                             last=l,
                                             email=user.email)


@login_required
def preview_dispatch(request, preview_id, location, dispatch=None):
    """
    Dispatch an AJAX action to a preview XModule

    Expects a POST request, and passes the arguments to the module

    preview_id (str): An identifier specifying which preview this module is used for
    location: The Location of the module to dispatch to
    dispatch: The action to execute
    """

    instance_state, shared_state = load_preview_state(request, preview_id, location)
    descriptor = modulestore().get_item(location)
    instance = load_preview_module(request, preview_id, descriptor, instance_state, shared_state)
    # Let the module handle the AJAX
    try:
        ajax_return = instance.handle_ajax(dispatch, request.POST)
    except NotFoundError:
        log.exception("Module indicating to user that request doesn't exist")
        raise Http404
    except:
        log.exception("error processing ajax call")
        raise

    save_preview_state(request, preview_id, location, instance.get_instance_state(), instance.get_shared_state())
    return HttpResponse(ajax_return)


def load_preview_state(request, preview_id, location):
    """
    Load the state of a preview module from the request

    preview_id (str): An identifier specifying which preview this module is used for
    location: The Location of the module to dispatch to
    """
    if 'preview_states' not in request.session:
        request.session['preview_states'] = defaultdict(dict)

    instance_state = request.session['preview_states'][preview_id, location].get('instance')
    shared_state = request.session['preview_states'][preview_id, location].get('shared')

    return instance_state, shared_state


def save_preview_state(request, preview_id, location, instance_state, shared_state):
    """
    Save the state of a preview module to the request

    preview_id (str): An identifier specifying which preview this module is used for
    location: The Location of the module to dispatch to
    instance_state: The instance state to save
    shared_state: The shared state to save
    """
    if 'preview_states' not in request.session:
        request.session['preview_states'] = defaultdict(dict)

    request.session['preview_states'][preview_id, location]['instance'] = instance_state
    request.session['preview_states'][preview_id, location]['shared'] = shared_state


def render_from_lms(template_name, dictionary, context=None, namespace='main'):
    """
    Render a template using the LMS MAKO_TEMPLATES
    """
    return render_to_string(template_name, dictionary, context, namespace="lms." + namespace)


def preview_module_system(request, preview_id, descriptor):
    """
    Returns a ModuleSystem for the specified descriptor that is specialized for
    rendering module previews.

    request: The active django request
    preview_id (str): An identifier specifying which preview this module is used for
    descriptor: An XModuleDescriptor
    """

    return ModuleSystem(
        ajax_url=reverse('preview_dispatch', args=[preview_id, descriptor.location.url(), '']).rstrip('/'),
        # TODO (cpennington): Do we want to track how instructors are using the preview problems?
        track_function=lambda type, event: None,
        filestore=descriptor.system.resources_fs,
        get_module=partial(get_preview_module, request, preview_id),
        render_template=render_from_lms,
        debug=True,
        replace_urls=replace_urls,
        user=request.user,
    )


def get_preview_module(request, preview_id, location):
    """
    Returns a preview XModule at the specified location. The preview_data is chosen arbitrarily
    from the set of preview data for the descriptor specified by Location

    request: The active django request
    preview_id (str): An identifier specifying which preview this module is used for
    location: A Location
    """
    descriptor = modulestore().get_item(location)
    instance_state, shared_state = descriptor.get_sample_state()[0]
    return load_preview_module(request, preview_id, descriptor, instance_state, shared_state)


def load_preview_module(request, preview_id, descriptor, instance_state, shared_state):
    """
    Return a preview XModule instantiated from the supplied descriptor, instance_state, and shared_state

    request: The active django request
    preview_id (str): An identifier specifying which preview this module is used for
    descriptor: An XModuleDescriptor
    instance_state: An instance state string
    shared_state: A shared state string
    """
    system = preview_module_system(request, preview_id, descriptor)
    try:
        module = descriptor.xmodule_constructor(system)(instance_state, shared_state)
    except:
        module = ErrorDescriptor.from_descriptor(
            descriptor,
            error_msg=exc_info_to_str(sys.exc_info())
        ).xmodule_constructor(system)(None, None)

    module.get_html = wrap_xmodule(
        module.get_html,
        module,
        "xmodule_display.html",
    )
    module.get_html = replace_static_urls(
        module.get_html,
        module.metadata.get('data_dir', module.location.course)
    )
    save_preview_state(request, preview_id, descriptor.location.url(),
        module.get_instance_state(), module.get_shared_state())

    return module


def get_module_previews(request, descriptor):
    """
    Returns a list of preview XModule html contents. One preview is returned for each
    pair of states returned by get_sample_state() for the supplied descriptor.

    descriptor: An XModuleDescriptor
    """
    preview_html = []
    for idx, (instance_state, shared_state) in enumerate(descriptor.get_sample_state()):
        module = load_preview_module(request, str(idx), descriptor, instance_state, shared_state)
        preview_html.append(module.get_html())
    return preview_html


def _xmodule_recurse(item, action):
    for child in item.get_children():
        _xmodule_recurse(child, action)

    action(item)

def _delete_item(item, recurse=False):
    if recurse:
        children = item.get_children()
        for child in children:
            _delete_item(child, recurse)
        
    modulestore().delete_item(item.location);
    

@login_required
@expect_json
def delete_item(request):
    item_location = request.POST['id']

    # check permissions for this user within this course
    if not has_access(request.user, item_location):
        raise PermissionDenied()

    # optional parameter to delete all children (default False)
    delete_children = request.POST.get('delete_children', False)

    item = modulestore().get_item(item_location)

    if delete_children:
        _xmodule_recurse(item, lambda i: modulestore().delete_item(i.location))
    else:
        modulestore().delete_item(item.location)

    return HttpResponse()


@login_required
@expect_json
def save_item(request):
    item_location = request.POST['id']

    # check permissions for this user within this course
    if not has_access(request.user, item_location):
        raise PermissionDenied()

    if request.POST['data']:
        data = request.POST['data']
        modulestore().update_item(item_location, data)
        
    if request.POST['children']:
        children = request.POST['children']
        modulestore().update_children(item_location, children)

    # cdodge: also commit any metadata which might have been passed along in the
    # POST from the client, if it is there
    # NOTE, that the postback is not the complete metadata, as there's system metadata which is
    # not presented to the end-user for editing. So let's fetch the original and
    # 'apply' the submitted metadata, so we don't end up deleting system metadata
    if request.POST['metadata']:
        posted_metadata = request.POST['metadata']
        # fetch original
        existing_item = modulestore().get_item(item_location)

        # update existing metadata with submitted metadata (which can be partial)
        # IMPORTANT NOTE: if the client passed pack 'null' (None) for a piece of metadata that means 'remove it'
        for metadata_key in posted_metadata.keys():

            # let's strip out any metadata fields from the postback which have been identified as system metadata
            # and therefore should not be user-editable, so we should accept them back from the client
            if metadata_key in existing_item.system_metadata_fields:
                del posted_metadata[metadata_key]
            elif posted_metadata[metadata_key] is None:
                # remove both from passed in collection as well as the collection read in from the modulestore
                if metadata_key in existing_item.metadata:
                    del existing_item.metadata[metadata_key]
                del posted_metadata[metadata_key]

        # overlay the new metadata over the modulestore sourced collection to support partial updates
        existing_item.metadata.update(posted_metadata)

        # commit to datastore
        modulestore().update_metadata(item_location, existing_item.metadata)

    return HttpResponse()


@login_required
@expect_json
def create_draft(request):
    location = request.POST['id']

    # check permissions for this user within this course
    if not has_access(request.user, location):
        raise PermissionDenied()

    # This clones the existing item location to a draft location (the draft is implicit,
    # because modulestore is a Draft modulestore)
    modulestore().clone_item(location, location)

    return HttpResponse()

@login_required
@expect_json
def publish_draft(request):
    location = request.POST['id']

    # check permissions for this user within this course
    if not has_access(request.user, location):
        raise PermissionDenied()

    item = modulestore().get_item(location)
    _xmodule_recurse(item, lambda i: modulestore().publish(i.location, request.user.id))

    return HttpResponse()


@login_required
@expect_json
def unpublish_unit(request):
    location = request.POST['id']

    # check permissions for this user within this course
    if not has_access(request.user, location):
        raise PermissionDenied()

    item = modulestore().get_item(location)
    _xmodule_recurse(item, lambda i: modulestore().unpublish(i.location))

    return HttpResponse()


@login_required
@expect_json
def clone_item(request):
    parent_location = Location(request.POST['parent_location'])
    template = Location(request.POST['template'])
    
    display_name = request.POST.get('display_name')

    if not has_access(request.user, parent_location):
        raise PermissionDenied()

    parent = modulestore().get_item(parent_location)
    dest_location = parent_location._replace(category=template.category, name=uuid4().hex)

    new_item = modulestore().clone_item(template, dest_location)

    # TODO: This needs to be deleted when we have proper storage for static content
    new_item.metadata['data_dir'] = parent.metadata['data_dir']
    
    # replace the display name with an optional parameter passed in from the caller
    if display_name is not None:
        new_item.metadata['display_name'] = display_name

    modulestore().update_metadata(new_item.location.url(), new_item.own_metadata)

    if parent_location.category not in ('vertical',):
        parent_update_modulestore = modulestore('direct')
    else:
        parent_update_modulestore = modulestore()
    parent_update_modulestore.update_children(parent_location, parent.definition.get('children', []) + [new_item.location.url()])

    return HttpResponse(json.dumps({'id': dest_location.url()}))

#@login_required
#@ensure_csrf_cookie
def upload_asset(request, org, course, coursename):
    '''
    cdodge: this method allows for POST uploading of files into the course asset library, which will
    be supported by GridFS in MongoDB.
    '''
    if request.method != 'POST':
        # (cdodge) @todo: Is there a way to do a - say - 'raise Http400'?
        return HttpResponseBadRequest()

    # construct a location from the passed in path
    location = ['i4x', org, course, 'course', coursename]
    if not has_access(request.user, location):
        return HttpResponseForbidden()
    
    # Does the course actually exist?!? Get anything from it to prove its existance
    
    try:
        item = modulestore().get_item(location)
    except:
        # no return it as a Bad Request response
        logging.error('Could not find course' + location)
        return HttpResponseBadRequest()

    # compute a 'filename' which is similar to the location formatting, we're using the 'filename'
    # nomenclature since we're using a FileSystem paradigm here. We're just imposing
    # the Location string formatting expectations to keep things a bit more consistent

    name = request.FILES['file'].name
    mime_type = request.FILES['file'].content_type
    filedata = request.FILES['file'].read()

    file_location = StaticContent.compute_location(org, course, name)

    content = StaticContent(file_location, name, mime_type, filedata)

    # first commit to the DB
    contentstore().save(content)

    # then remove the cache so we're not serving up stale content
    # NOTE: we're not re-populating the cache here as the DB owns the last-modified timestamp
    # which is used when serving up static content. This integrity is needed for
    # browser-side caching support. We *could* re-fetch the saved content so that we have the
    # timestamp populated, but we might as well wait for the first real request to come in
    # to re-populate the cache.
    del_cached_content(content.location)

    # if we're uploading an image, then let's generate a thumbnail so that we can
    # serve it up when needed without having to rescale on the fly
    if mime_type.split('/')[0] == 'image':
        try:
            # not sure if this is necessary, but let's rewind the stream just in case
            request.FILES['file'].seek(0)

            # use PIL to do the thumbnail generation (http://www.pythonware.com/products/pil/)
            # My understanding is that PIL will maintain aspect ratios while restricting
            # the max-height/width to be whatever you pass in as 'size'
            # @todo: move the thumbnail size to a configuration setting?!?
            im = Image.open(request.FILES['file'])

            # I've seen some exceptions from the PIL library when trying to save palletted 
            # PNG files to JPEG. Per the google-universe, they suggest converting to RGB first.
            im = im.convert('RGB')
            size = 128, 128
            im.thumbnail(size, Image.ANTIALIAS)
            thumbnail_file = StringIO.StringIO()
            im.save(thumbnail_file, 'JPEG')
            thumbnail_file.seek(0)
        
            # use a naming convention to associate originals with the thumbnail
            thumbnail_name = content.generate_thumbnail_name()

            # then just store this thumbnail as any other piece of content
            thumbnail_file_location = StaticContent.compute_location(org, course, 
                                                                              thumbnail_name)
            thumbnail_content = StaticContent(thumbnail_file_location, thumbnail_name, 
                                              'image/jpeg', thumbnail_file)
            contentstore().save(thumbnail_content)

            # remove any cached content at this location, as thumbnails are treated just like any
            # other bit of static content
            del_cached_content(thumbnail_content.location)
        except:
            # catch, log, and continue as thumbnails are not a hard requirement
            logging.error('Failed to generate thumbnail for {0}. Continuing...'.format(name))


    return HttpResponse('Upload completed')

'''
This view will return all CMS users who are editors for the specified course
'''
@login_required
@ensure_csrf_cookie
def manage_users(request, location):
    
    # check that logged in user has permissions to this item
    if not has_access(request.user, location, role=INSTRUCTOR_ROLE_NAME):
        raise PermissionDenied()

    return render_to_response('manage_users.html', {
        'staff': get_users_in_course_group_by_role(location, STAFF_ROLE_NAME),
        'add_user_postback_url' : reverse('add_user', args=[location]).rstrip('/'),
        'remove_user_postback_url' : reverse('remove_user', args=[location]).rstrip('/')
    })
    

def create_json_response(errmsg = None):
    if errmsg is not None:
        resp = HttpResponse(json.dumps({'Status': 'Failed', 'ErrMsg' : errmsg}))
    else:
        resp = HttpResponse(json.dumps({'Status': 'OK'}))

    return resp

'''
This POST-back view will add a user - specified by email - to the list of editors for
the specified course
'''
@expect_json
@login_required
@ensure_csrf_cookie
def add_user(request, location):
    email = request.POST["email"]

    if email=='':
        return create_json_response('Please specify an email address.')
    
    # check that logged in user has admin permissions to this course
    if not has_access(request.user, location, role=INSTRUCTOR_ROLE_NAME):
        raise PermissionDenied()
    
    user = get_user_by_email(email)
    
    # user doesn't exist?!? Return error.
    if user is None:
        return create_json_response('Could not find user by email address \'{0}\'.'.format(email))

    # user exists, but hasn't activated account?!?
    if not user.is_active:
        return create_json_response('User {0} has registered but has not yet activated his/her account.'.format(email))

    # ok, we're cool to add to the course group
    add_user_to_course_group(request.user, user, location, STAFF_ROLE_NAME)

    return create_json_response()

'''
This POST-back view will remove a user - specified by email - from the list of editors for
the specified course
'''
@expect_json
@login_required
@ensure_csrf_cookie
def remove_user(request, location):
    email = request.POST["email"]
    
    # check that logged in user has admin permissions on this course
    if not has_access(request.user, location, role=INSTRUCTOR_ROLE_NAME):
        raise PermissionDenied()

    user = get_user_by_email(email)
    if user is None:
        return create_json_response('Could not find user by email address \'{0}\'.'.format(email))

    remove_user_from_course_group(request.user, user, location, STAFF_ROLE_NAME)

    return create_json_response()


# points to the temporary course landing page with log in and sign up
def landing(request, org, course, coursename):
    return render_to_response('temp-course-landing.html', {})


def static_pages(request, org, course, coursename):
    return render_to_response('static-pages.html', {})


def edit_static(request, org, course, coursename):
    return render_to_response('edit-static-page.html', {})


def not_found(request):
    return render_to_response('error.html', {'error': '404'})


def server_error(request):
    return render_to_response('error.html', {'error': '500'})


@login_required
@ensure_csrf_cookie
def asset_index(request, org, course, name):
    """
    Display an editable asset library

    org, course, name: Attributes of the Location for the item to edit
    """
    location = ['i4x', org, course, 'course', name]
    
    # check that logged in user has permissions to this item
    if not has_access(request.user, location):
        raise PermissionDenied()

    upload_asset_callback_url = reverse('upload_asset', kwargs = {
            'org' : org,
            'course' : course,
            'coursename' : name
            })
    
    course_reference = StaticContent.compute_location(org, course, name)
    assets = contentstore().get_all_content_for_course(course_reference)
    asset_display = []
    for asset in assets:
        id = asset['_id']
        display_info = {}
        display_info['displayname'] = asset['displayname']
        display_info['uploadDate'] = asset['uploadDate']
        contentstore_reference = StaticContent.compute_location(id['org'], id['course'], id['name'])
        display_info['url'] = StaticContent.get_url_path_from_location(contentstore_reference)
        
        asset_display.append(display_info)

    print assets[0]
    return render_to_response('asset_index.html', {
        'assets': asset_display,
        'upload_asset_callback_url': upload_asset_callback_url
    })
