from ftw.publisher.sender.interfaces import IPathBlacklist
from Acquisition import aq_inner
from Products.CMFCore.utils import getToolByName
from datetime import datetime
from ftw.publisher.controlling.interfaces import IStatisticsCacheController
from ftw.publisher.controlling.utils import persistent_aware, unpersist
from plone.memoize import instance
from zope.annotation.interfaces import IAnnotations
from zope.component import adapts
import os
import simplejson

try:
    from ftw.publisher.sender.interfaces import IConfig
except ImportError:
    SENDER_INSTALLED = False
else:
    SENDER_INSTALLED = True

if SENDER_INSTALLED:
    from ftw.publisher.sender.utils import sendRequestToRealm


# annotations key on portal
ANNOTATIONS_CURRENT_REALM = 'publisher-controlling-current-realm'
# annotations key on realm
ANNOTATIONS_PREFIX = 'publisher-controlling-statistic-'
ANNOTATIONS_VERSION_KEY = 'publisher-controlling-version'
ANNOTATIONS_DATE_KEY = 'publisher-controlling-last-update'


class StatisticsCacheController(object):
    adapts(IStatisticsCacheController)

    def __init__(self, context):
        context = aq_inner(context)
        self.context = context
        self.portal = context.portal_url.getPortalObject()
        self.portal_annotations = IAnnotations(self.portal)
        self.realm_annotations = self.get_current_realm() and IAnnotations(self.get_current_realm())

    def rebuild_cache(self):
        """ Rebuilds the cache for each statistics view which
        is registered in portal_actions
        """
        for view in self._list_statistics_views():
            elements = list(view.get_elements_for_cache(self))
            self._store_elements_for(view.__name__, elements)
        self._increment_cache_version()
        self._set_last_update_date()

    def get_cache_version(self):
        """ The cache version is incremented after every successful
        update of the cache.
        """
        if not self.realm_annotations:
            return -1
        return int(self.realm_annotations.get(ANNOTATIONS_VERSION_KEY, 0))

    def last_updated(self):
        """ Returns a datetime when the last successfull cache
        update happened.
        """
        if not self.realm_annotations:
            return -1
        return self.realm_annotations.get(ANNOTATIONS_DATE_KEY, 0)

    def get_elements_for(self, view_name, default=None,
                         unpersist_data=True):
        """ Returns the cached elements for a view (registered
        in portal_actions)
        """
        if not self.realm_annotations:
            return ()
        key = ANNOTATIONS_PREFIX + view_name
        data = self.realm_annotations.get(key, default)
        if unpersist_data:
            data = unpersist(data)
        return data

    def get_current_realm(self):
        """ Returns the currently select realm object
        """
        realm = self.portal_annotations.get(ANNOTATIONS_CURRENT_REALM, None)
        if realm:
            return realm
        else:
            for realm in IConfig(self.portal).getRealms():
                if realm.active:
                    self.set_current_realm(realm)
                    return realm
        return None

    def set_current_realm(self, realm):
        """ Sets the current realm (realm object)
        """
        self.portal_annotations[ANNOTATIONS_CURRENT_REALM] = realm

    @instance.memoize
    def get_remote_objects(self):
        """ Returns a list of remote objects (as dicts) with some basic
        information.
        """
        jdata = sendRequestToRealm({}, self.get_current_realm(),
                                   '@@publisher-controlling-json-remote-object')
        bl = IPathBlacklist(self.context)
        data = filter(lambda item:bl.is_blacklisted(item.get('original_path')),
                      simplejson.loads(jdata))
        return data

    @instance.memoize
    def remote_objects_by_path(self):
        """ Returns a dict of remote objects with the path as key
        """
        return dict([(elm['path'], elm) for elm in self.get_remote_objects()])

    def get_remote_item(self, obj=None, brain=None, path=None):
        """ Returns the remote item as dict (if existing) or None.
        Provide either the local obj, the local brain or the local
        path relative to the plone site.
        """
        if not obj and not brain and not path:
            raise ValueError('Provide either obj, brain or path')
        portal = self.context.portal_url.getPortalObject()
        if obj or brain:
            if not getattr(self, '_portal_path', None):
                self._portal_path = '/'.join(portal.getPhysicalPath()) + '/'
            if obj:
                fullpath = '/'.join(obj.getPhysicalPath())
            elif brain:
                fullpath = brain.getPath()
            if not fullpath.startswith(self._portal_path):
                raise Exception('Cannot get remote item: %s does not start with %s' % (
                        `fullpath`,
                        `self._portal_path`,
                        ))
            path = fullpath[len(self._portal_path):]
        return self.remote_objects_by_path().get(path, None)

    def remote_to_local_path(self, remote_path):
        """ Convert a remote path to the local path
        """
        if not getattr(self, '_portal_path', None):
            portal = self.context.portal_url.getPortalObject()
            self._portal_path = '/'.join(portal.getPhysicalPath()) + '/'
        if remote_path.startswith('/'):
            remote_path = remote_path[1:]
        return os.join(self._portal_path, remote_path)

    def get_local_brain(self, remote_path):
        """ Returns the brain of a remote path or None
        """
        query = {
            'path': {
                'query': remote_path,
                'limit': 0,
                }
            }
        brains = self.context.portal_catalog(query)
        if len(brains)==0:
            return None
        else:
            return brains[0]

    def _list_statistics_views(self):
        """ Returns a generator of views which are statistic views
        """
        actions_tool = getToolByName(aq_inner(self.context), 'portal_actions')
        actions = actions_tool.listActionInfos(
            object=aq_inner(self.context),
            categories=('publisher_controlling_actions',))

        for action in actions:
            if action['allowed']:
                url = action['url']
                url = url.endswith('/') and url[:-1] or url
                view_name = url.split('/')[-1]
                yield self.context.restrictedTraverse(view_name)


    def _store_elements_for(self, view_name, elements):
        """ Stores a list of elements for a view_name
        """
        if not self.realm_annotations:
            return
        key = ANNOTATIONS_PREFIX + view_name
        data = persistent_aware(elements)
        self.realm_annotations[key] = data

    def _increment_cache_version(self):
        """ Increments the cache version
        """
        if not self.realm_annotations:
            return
        version = int(self.get_cache_version())
        version += 1
        self.realm_annotations[ANNOTATIONS_VERSION_KEY] = version

    def _set_last_update_date(self):
        """ Sets the "last_updated" information to now
        """
        if not self.realm_annotations:
            return
        self.realm_annotations[ANNOTATIONS_DATE_KEY] = datetime.now()

