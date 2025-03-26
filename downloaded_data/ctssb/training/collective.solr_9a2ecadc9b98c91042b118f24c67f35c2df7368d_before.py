from zope.interface import implements
from zope.component import adapts, getSiteManager
from zope.publisher.interfaces.http import IHTTPRequest
from OFS.Traversable import path2url
from DateTime import DateTime

from collective.solr.interfaces import ISolrFlare
from collective.solr.interfaces import IFlare
from collective.solr.parser import AttrDict

timezone = DateTime().timezone()


class PloneFlare(AttrDict):
    """ a sol(a)r brain, i.e. a data container for search results """
    implements(IFlare)
    adapts(ISolrFlare, IHTTPRequest)

    __allow_access_to_unprotected_subobjects__ = True

    def __init__(self, context, request=None):
        self.context = context
        self.request = request
        self.update(context)        # copy data

    @property
    def id(self):
        """ convenience alias """
        return self.get('id', self.get('getId'))

    def getPath(self):
        """ convenience alias """
        return self['physicalPath']

    def getObject(self, REQUEST=None):
        """ return the actual object corresponding to this flare """
        site = getSiteManager()
        path = self.getPath()
        if not path:
            return None
        return site.unrestrictedTraverse(path)

    def getURL(self, relative=False):
        """ convert the physical path into a url, if it was stored """
        path = self.getPath()
        try:
            url = self.request.physicalPathToURL(path, relative)
        except AttributeError:
            url = path2url(path.split('/'))
        return url

    def pretty_title_or_id(self):
        for attr in 'Title', 'getId', 'id':
            if attr in self:
                return self[attr]
        return '<untitled item>'

    @property
    def ModificationDate(self):
        modified = self.get('modified', None)
        if modified is None:
            return 'n.a.'
        return modified.toZone(timezone).ISO()

    @property
    def data_record_normalized_score_(self):
        score = self.get('score', None)
        if score is None:
            return 'n.a.'
        return '%.1f' % (float(score) * 100)

    @property
    def review_state(self):
        if 'review_state' in self:
            return self['review_state']
        return ''
