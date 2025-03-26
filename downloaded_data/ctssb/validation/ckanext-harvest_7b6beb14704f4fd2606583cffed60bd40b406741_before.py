import logging
from sqlalchemy import or_, distinct
from ckan.model import User
import datetime

from ckan import logic
from ckan.plugins import PluginImplementations
from ckanext.harvest.interfaces import IHarvester

from ckan.logic import NotFound, check_access

from ckanext.harvest import model as harvest_model

from ckanext.harvest.model import (HarvestSource, HarvestJob, HarvestObject)
from ckanext.harvest.logic.dictization import (harvest_source_dictize,
                                               harvest_job_dictize,
                                               harvest_object_dictize)
from ckanext.harvest.logic.schema import harvest_source_db_to_form_schema
log = logging.getLogger(__name__)

def harvest_source_show(context,data_dict):
    '''
    Returns the metadata of a harvest source

    This method just proxies the request to package_show. All auth checks and
    validation will be done there.

    :param id: the id or name of the harvest source
    :type id: string

    :returns: harvest source metadata
    :rtype: dictionary
    '''

    context['schema'] = harvest_source_db_to_form_schema()
    source_dict = logic.get_action('package_show')(context, data_dict)

    # For compatibility with old code, add the active field
    # based on the package state
    source_dict['active'] = (source_dict['state'] == 'active')

    return source_dict


def harvest_source_show_status(context,data_dict):
    '''
    Returns a status report for a harvest source

    Given a particular source, returns a dictionary containing information
    about the source jobs, datasets created, errors, etc.
    Note that this information is already included on the output of
    harvest_source_show, under the 'status' field.

    :param id: the id or name of the harvest source
    :type id: string

    :rtype: dictionary
    '''
    model = context.get('model')

    detailed = context.get('detailed',True)

    source = harvest_model.HarvestSource.get(data_dict['id'])
    if not source:
        raise logic.NotFound('Harvest source {0} does not exist'.format(data_dict['id']))

    out = {}

    jobs = harvest_model.HarvestJob.filter(source=source).all()

    out = {
           'job_count': 0,
           'next_harvest':'',
           'last_harvest_request':'',
           'last_harvest_statistics':{'added':0,'updated':0,'errors':0},
           'overall_statistics':{'added':0, 'errors':0},
           }

    job_count = len(jobs)
    if job_count == 0:
        out['msg'] = 'No jobs yet'
        return out
    else:
        out['job_count'] = job_count

    # Get next scheduled job
    next_job = harvest_model.HarvestJob.filter(source=source,status=u'New').first()
    if next_job:
        out['next_harvest'] = 'Scheduled'
    else:
        out['next_harvest'] = 'Not yet scheduled'

    # Get the last finished job
    last_job = harvest_model.HarvestJob.filter(source=source,status=u'Finished') \
               .order_by(harvest_model.HarvestJob.created.desc()).first()

    if last_job:
        out['last_job_id'] = last_job.id
        out['last_harvest_request'] = str(last_job.gather_finished)

        #Get HarvestObjects from last job with links to packages
        if detailed:
            last_objects = [obj for obj in last_job.objects if obj.package is not None]

            if len(last_objects) == 0:
                # No packages added or updated
                out['last_harvest_statistics']['added'] = 0
                out['last_harvest_statistics']['updated'] = 0
            else:
                # Check wether packages were added or updated
                for last_object in last_objects:
                    # Check if the same package had been linked before
                    previous_objects = model.Session.query(harvest_model.HarvestObject) \
                                             .filter(harvest_model.HarvestObject.package==last_object.package) \
                                             .count()

                    if previous_objects == 1:
                        # It didn't previously exist, it has been added
                        out['last_harvest_statistics']['added'] += 1
                    else:
                        # Pacakge already existed, but it has been updated
                        out['last_harvest_statistics']['updated'] += 1

        # Last harvest errors
        # We have the gathering errors in last_job.gather_errors, so let's also
        # get also the object errors.
        object_errors = model.Session.query(harvest_model.HarvestObjectError).join(harvest_model.HarvestObject) \
                            .filter(harvest_model.HarvestObject.job==last_job)

        out['last_harvest_statistics']['errors'] = len(last_job.gather_errors) \
                                            + object_errors.count()
        # Overall statistics
        packages = model.Session.query(distinct(harvest_model.HarvestObject.package_id), model.Package.name) \
                .join(model.Package).join(HarvestSource) \
                .filter(HarvestObject.source==source) \
                .filter(HarvestObject.current==True) \
                .filter(model.Package.state==u'active')

        out['overall_statistics']['added'] = packages.count()
    else:
        out['last_harvest_request'] = 'Not yet harvested'

    return out


def harvest_source_list(context, data_dict):

    check_access('harvest_source_list',context,data_dict)

    model = context['model']
    session = context['session']
    user = context.get('user','')

    sources = _get_sources_for_user(context, data_dict)

    context.update({'detailed':False})
    return [harvest_source_dictize(source, context) for source in sources]

def harvest_source_for_a_dataset(context, data_dict):
    '''For a given dataset, return the harvest source that
    created or last updated it, otherwise NotFound.'''

    model = context['model']
    session = context['session']

    dataset_id = data_dict.get('id')

    query = session.query(HarvestSource)\
            .join(HarvestObject)\
            .filter_by(package_id=dataset_id)\
            .order_by(HarvestObject.gathered.desc())
    source = query.first() # newest

    if not source:
        raise NotFound

    return harvest_source_dictize(source,context)

def harvest_job_show(context,data_dict):

    check_access('harvest_job_show',context,data_dict)

    id = data_dict.get('id')
    attr = data_dict.get('attr',None)

    job = HarvestJob.get(id,attr=attr)
    if not job:
        raise NotFound

    return harvest_job_dictize(job,context)

def harvest_job_list(context,data_dict):

    check_access('harvest_job_list',context,data_dict)

    model = context['model']
    session = context['session']

    source_id = data_dict.get('source_id',False)
    status = data_dict.get('status',False)

    query = session.query(HarvestJob)

    if source_id:
        query = query.filter(HarvestJob.source_id==source_id)

    if status:
        query = query.filter(HarvestJob.status==status)

    jobs = query.all()

    return [harvest_job_dictize(job,context) for job in jobs]

def harvest_object_show(context,data_dict):

    check_access('harvest_object_show',context,data_dict)

    id = data_dict.get('id')
    attr = data_dict.get('attr',None)
    obj = HarvestObject.get(id,attr=attr)
    if not obj:
        raise NotFound

    return harvest_object_dictize(obj,context)

def harvest_object_list(context,data_dict):

    check_access('harvest_object_list',context,data_dict)

    model = context['model']
    session = context['session']

    only_current = data_dict.get('only_current',True)
    source_id = data_dict.get('source_id',False)

    query = session.query(HarvestObject)

    if source_id:
        query = query.filter(HarvestObject.source_id==source_id)

    if only_current:
        query = query.filter(HarvestObject.current==True)

    objects = query.all()

    return [getattr(obj,'id') for obj in objects]

def harvesters_info_show(context,data_dict):

    check_access('harvesters_info_show',context,data_dict)

    available_harvesters = []
    for harvester in PluginImplementations(IHarvester):
        info = harvester.info()
        if not info or 'name' not in info:
            log.error('Harvester %r does not provide the harvester name in the info response' % str(harvester))
            continue
        info['show_config'] = (info.get('form_config_interface','') == 'Text')
        available_harvesters.append(info)

    return available_harvesters

def _get_sources_for_user(context,data_dict):

    model = context['model']
    session = context['session']
    user = context.get('user','')

    only_active = data_dict.get('only_active',False)
    only_to_run = data_dict.get('only_to_run',False)

    query = session.query(HarvestSource) \
                .order_by(HarvestSource.created.desc())

    if only_active:
        query = query.filter(HarvestSource.active==True) \

    if only_to_run:
        query = query.filter(HarvestSource.frequency!='MANUAL')
        query = query.filter(or_(HarvestSource.next_run<=datetime.datetime.utcnow(),
                                 HarvestSource.next_run==None)
                            )

    user_obj = User.get(user)
    # Sysadmins will get all sources
    if user_obj and user_obj.sysadmin:
        # This only applies to a non sysadmin user when using the
        # publisher auth profile. When using the default profile,
        # normal users will never arrive at this point, but even if they
        # do, they will get an empty list.

        publisher_filters = []
        publishers_for_the_user = user_obj.get_groups(u'publisher')
        for publisher_id in [g.id for g in publishers_for_the_user]:
            publisher_filters.append(HarvestSource.publisher_id==publisher_id)

        if len(publisher_filters):
            query = query.filter(or_(*publisher_filters))
        else:
            # This user does not belong to a publisher yet, no sources for him/her
            return []

        log.debug('User %s with publishers %r has Harvest Sources: %r',
                  user, publishers_for_the_user, [(hs.id, hs.url) for hs in query])

    sources = query.all()

    return sources

