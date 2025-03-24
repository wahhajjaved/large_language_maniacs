import os
import base64
from datetime import datetime
from xos.config import Config
from util.logger import Logger, logging
from observer.steps import *
from django.db.models import F, Q
from core.models import *
from django.db import reset_queries
import json
import time
import pdb

logger = Logger(level=logging.INFO)

def f7(seq):
    seen = set()
    seen_add = seen.add
    return [ x for x in seq if not (x in seen or seen_add(x))]

def elim_dups(backend_str):
    strs = backend_str.split(' // ')
    strs2 = f7(strs)
    return ' // '.join(strs2)

def deepgetattr(obj, attr):
    return reduce(getattr, attr.split('.'), obj)


class InnocuousException(Exception):
    pass

class DeferredException(Exception):
    pass

class FailedDependency(Exception):
    pass

class SyncStep(object):
    """ An XOS Sync step.

    Attributes:
        psmodel        Model name the step synchronizes
        dependencies    list of names of models that must be synchronized first if the current model depends on them
    """
    slow=False
    def get_prop(self, prop):
        try:
            sync_config_dir = Config().sync_config_dir
        except:
            sync_config_dir = '/etc/xos/sync'
        prop_config_path = '/'.join(sync_config_dir,self.name,prop)
        return open(prop_config_path).read().rstrip()

    def __init__(self, **args):
        """Initialize a sync step
           Keyword arguments:
                   name -- Name of the step
                provides -- XOS models sync'd by this step
        """
        dependencies = []
        self.driver = args.get('driver')
        self.error_map = args.get('error_map')

        try:
            self.soft_deadline = int(self.get_prop('soft_deadline_seconds'))
        except:
            self.soft_deadline = 5 # 5 seconds

        return

    def fetch_pending(self, deletion=False):
        # This is the most common implementation of fetch_pending
        # Steps should override it if they have their own logic
        # for figuring out what objects are outstanding.

        main_objs = self.observes
	if (type(main_objs) is not list):
		main_objs=[main_obj]
	
	objs = []
	for main_obj in main_objs:
		if (not deletion):
		    lobjs = main_obj.objects.filter(Q(enacted__lt=F('updated')) | Q(enacted=None),Q(lazy_blocked=False,Q(no_sync=False)))
		else:
		    lobjs = main_obj.deleted_objects.all()
	        objs.extend(lobjs)

        return objs
        #return Instance.objects.filter(ip=None)

    def check_dependencies(self, obj, failed):
        for dep in self.dependencies:
            peer_name = dep[0].lower() + dep[1:]    # django names are camelCased with the first letter lower

            try:
                peer_object = deepgetattr(obj, peer_name)
                try:
                    peer_objects = peer_object.all()
                except AttributeError:
                    peer_objects = [peer_object]
            except:
                peer_objects = []

            if (hasattr(obj,'controller')):
                try:
                    peer_objects = filter(lambda o:o.controller==obj.controller, peer_objects)
                except AttributeError:
                    pass

            if (failed in peer_objects):
                if (obj.backend_status!=failed.backend_status):
                    obj.backend_status = failed.backend_status
                    obj.save(update_fields=['backend_status'])
                raise FailedDependency("Failed dependency for %s:%s peer %s:%s failed  %s:%s" % (obj.__class__.__name__, str(getattr(obj,"pk","no_pk")), peer_object.__class__.__name__, str(getattr(peer_object,"pk","no_pk")), failed.__class__.__name__, str(getattr(failed,"pk","no_pk"))))

    def call(self, failed=[], deletion=False):
        pending = self.fetch_pending(deletion)
        for o in pending:
            # another spot to clean up debug state
            try:
                reset_queries()
            except:
                # this shouldn't happen, but in case it does, catch it...
                logger.log_exc("exception in reset_queries")

            sync_failed = False
            try:
                backoff_disabled = Config().observer_backoff_disabled
            except:
                backoff_disabled = 0

            try:
                scratchpad = json.loads(o.backend_register)
                if (scratchpad):
                    next_run = scratchpad['next_run']
                    if (not backoff_disabled and next_run>time.time()):
                        sync_failed = True
            except:
                logger.log_exc("Exception while loading scratchpad")
                pass

            if (not sync_failed):
                try:
                    for f in failed:
                        self.check_dependencies(o,f) # Raises exception if failed
                    if (deletion):
                        self.delete_record(o)
                        o.delete(purge=True)
                    else:
                        self.sync_record(o)
                        o.enacted = datetime.now() # Is this the same timezone? XXX
                        scratchpad = {'next_run':0, 'exponent':0}
                        o.backend_register = json.dumps(scratchpad)
                        o.backend_status = "1 - OK"
                        o.save(update_fields=['enacted','backend_status','backend_register'])
                except (InnocuousException,Exception,DeferredException) as e:
                    logger.log_exc("sync step failed!")
                    try:
                        if (o.backend_status.startswith('2 - ')):
                            str_e = '%s // %r'%(o.backend_status[4:],e)
                            str_e = elim_dups(str_e)
                        else:
                            str_e = '%r'%e
                    except:
                        str_e = '%r'%e

                    try:
                        error = self.error_map.map(str_e)
                    except:
                        error = '%s'%str_e

                    if isinstance(e, InnocuousException) and not force_error:
                        o.backend_status = '1 - %s'%error
                    else:
                        o.backend_status = '2 - %s'%error

                    try:
                        scratchpad = json.loads(o.backend_register)
                        scratchpad['exponent']
                    except:
                        logger.log_exc("Exception while updating scratchpad")
                        scratchpad = {'next_run':0, 'exponent':0}

                    # Second failure
                    if (scratchpad['exponent']):
                        if isinstance(e,DeferredException):
                            delay = scratchpad['exponent'] * 60 # 1 minute
                        else:
                            delay = scratchpad['exponent'] * 600 # 10 minutes
                        # cap delays at 8 hours
                        if (delay>8*60*60):
                            delay=8*60*60
                        scratchpad['next_run'] = time.time() + delay

                    scratchpad['exponent']+=1

                    o.backend_register = json.dumps(scratchpad)

                    # TOFIX:
                    # DatabaseError: value too long for type character varying(140)
                    if (o.pk):
                        try:
                            o.backend_status = o.backend_status[:1024]
                            o.save(update_fields=['backend_status','backend_register','updated'])
                        except:
                            print "Could not update backend status field!"
                            pass
                    sync_failed = True


            if (sync_failed):
                failed.append(o)

        return failed

    def sync_record(self, o):
        return

    def delete_record(self, o):
        return

    def __call__(self, **args):
        return self.call(**args)
