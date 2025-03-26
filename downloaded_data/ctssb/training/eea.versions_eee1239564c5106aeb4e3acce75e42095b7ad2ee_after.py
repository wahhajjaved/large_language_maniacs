from Acquisition import aq_base
from Acquisition import aq_get
from Acquisition import aq_parent
from ZPublisher.BaseRequest import RequestContainer
from eea.versions.interfaces import IVersionEnhanced
from eea.versions.versions import _random_id
from pkg_resources import DistributionNotFound
from pkg_resources import get_distribution
import logging
import transaction

logger = logging.getLogger('eea.versions.migration')

try:
    get_distribution('five.globalrequest')
except DistributionNotFound:
    _GLOBALREQUEST_INSTALLED = False
else:
    _GLOBALREQUEST_INSTALLED = True


if _GLOBALREQUEST_INSTALLED:
    from zope.globalrequest import getRequest


def get_object(catalog, rid):
    """get an object based on the catalog rid

    Code based on ZCatalog.CatalogBrains.AbstractCatalogBrains.getObject
    """
    path = catalog._catalog.getpath(rid)
    path = path.split('/')
    if not path:
        return None

    parent = aq_parent(catalog)
    if (aq_get(parent, 'REQUEST', None) is None 
        and _GLOBALREQUEST_INSTALLED):
        request = getRequest()
        if request is not None:
            # path should be absolute, starting at the physical root
            parent = catalog.getPhysicalRoot()
            request_container = RequestContainer(REQUEST=request)
            parent = aq_base(parent).__of__(request_container)
    if len(path) > 1:
        parent = parent.unrestrictedTraverse(path[:-1])

    return parent.restrictedTraverse(path[-1])


def migrate_versionId_storage(obj):
    """Migrate storage of versionId
    """
    
    old_storage = obj.__annotations__.get('versionId')
    if not old_storage:
        msg = ("no versionId stored for %s, but preset in catalog" %
                        obj.absolute_url())
        logger.warning(msg)

    if isinstance(old_storage, basestring):
        msg = ("Skipping migration of versionId for %s, "
               "already migrated" % obj)
        return

    versionId = obj.__annotations__['versionId']['versionId'].strip()
    obj.__annotations__['versionId'] = versionId

    #has versionId set but does not provide IVersionEnhanced
    #all versioned objects should provide IVersionEnhanced
    if versionId and not IVersionEnhanced.providedBy(obj):
        logger.info("versionId assigned without IVersionEnhanced "
                    "provided %s" % obj)
        alsoProvides(obj, IVersionEnhanced)

    #doesn't have a good versionId (could be empty string),
    #but provides IVersionEnhanced. Will supply object with new versionId
    if not versionId and IVersionEnhanced.providedBy(obj):
        obj.__annotations__['versionId'] = _random_id(obj)

    msg = "Migrated versionId storage for %s (%s)" % (obj, versionId)
    logger.info(msg)


def evolve(context):
    """ Migrate storage of versionId. Also does some cleanup.
    """

    #for all objects indexed in getVersionId index, migrate the storage
    cat = context.portal_catalog
    index = cat._catalog.getIndex('getVersionId')
#   import pdb; pdb.set_trace()
    i = 0
    for versionId, rids in index.items():
        for rid in rids:
            obj = get_object(cat, rid)
            migrate_versionId_storage(obj)
        i += 1
        if (i % 100) == 0:
            transaction.savepoint()

    transaction.commit()

#   index.values()
#   cat._catalog.getpath(599010767)
