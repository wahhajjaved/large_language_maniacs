import logging

from twisted.python.compat import nativeString
from twisted.web.error import UnsupportedMethod
from twisted.web.resource import EncodingResourceWrapper, IResource, NoResource, \
    _computeAllowedMethods
from twisted.web.server import GzipEncoderFactory
from zope.interface import implementer

logger = logging.getLogger(__name__)

import mimetypes

mimetypes.init()


def get_extensions_for_type(general_type):
    for ext in mimetypes.types_map:
        if mimetypes.types_map[ext].split('/')[0] == general_type:
            yield ext


IMAGE_EXTENSIONS = list(get_extensions_for_type('image'))
FONT_EXTENSIONS = list(get_extensions_for_type('font'))


@implementer(IResource)
class BasicResource:
    """ Basic Resource

    This class is a node for the resource tree, It's a slightly simpler version of
    C{twisted.web.resource.Resource}

    """
    isGzipped = False
    entityType = IResource
    server = None
    isLeaf = False

    def __init__(self):
        """
        Initialize.
        """
        self._children = {}

    def getChildWithDefault(self, path, request):
        """ Get Child With Default

        This is the method queried by the site/server, if we implement this and then
        only use getChild, we have greater control when something fails
        @see C{FileUnderlayResource}


        def getChildForRequest(resource, request):
            # Traverse resource tree to find who will handle the request.
            while request.postpath and not resource.isLeaf:
                pathElement = request.postpath.pop(0)
                request.prepath.append(pathElement)
                resource = resource.getChildWithDefault(pathElement, request)
            return resource

        """

        resource = self

        from txhttputil.site.FileUnderlayResource import FileUnderlayResource
        fileUnderlayResourceStack = []

        if isinstance(self, FileUnderlayResource):
            fileUnderlayResourceStack.append((resource, [path] + request.postpath))

        while True:
            resource = resource.getChild(path, request)

            if isinstance(resource, FileUnderlayResource):
                fileUnderlayResourceStack.append((resource, list(request.postpath)))

            # If we've run into a dead end, return it.
            if isinstance(resource, NoResource):
                break

            # If the resource is a leaf, this IS the resource we should render
            if resource.isLeaf:
                # Break before popping the path
                break

            # If there are no more paths to pop, this must be it
            if not request.postpath:
                break

            path = request.postpath.pop(0)
            request.prepath.append(path)

        # Look back through the file resources and see if there are any matches
        if isinstance(resource, NoResource) or isinstance(resource, FileUnderlayResource):
            while fileUnderlayResourceStack:
                resource, postPath = fileUnderlayResourceStack.pop()
                fileResource = resource.getFileResource(postPath)
                if not isinstance(fileResource, NoResource):
                    return fileResource

        return resource

    def getChild(self, path, request):
        if path in self._children:
            return self._children[path]
        return NoResource()

    def putChild(self, path: bytes, child):
        if b'/' in path:
            raise Exception("Path %s can not start or end with '/' ", path)

        self._children[path] = child
        child.server = self.server

    def deleteChild(self, path: bytes):
        if b'/' in path:
            raise Exception("Path %s can not start or end with '/' ", path)

        del self._children[path]

    def render(self, request):
        # Optionally, Do some checking with userSession.userDetails.group
        # userSession = IUserSession(request.getSession())

        m = getattr(self, 'render_' + nativeString(request.method), None)
        if not m:
            raise UnsupportedMethod(_computeAllowedMethods(self))
        return m(request)

    def render_HEAD(self, request):
        return self.render_GET(request)

    def _gzipIfRequired(self, resource):
        if (not isinstance(resource, EncodingResourceWrapper)
            and hasattr(resource, 'isGzipped')
            and resource.isGzipped):
            return EncodingResourceWrapper(resource, [GzipEncoderFactory()])
        return resource
