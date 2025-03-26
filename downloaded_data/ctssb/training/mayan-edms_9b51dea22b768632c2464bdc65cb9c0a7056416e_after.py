from __future__ import unicode_literals

import inspect
import logging
import urllib
import urlparse

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import resolve, reverse
from django.template import VariableDoesNotExist, Variable
from django.template.defaulttags import URLNode
from django.utils.encoding import smart_str, smart_unicode
from django.utils.http import urlencode, urlquote
from django.utils.translation import ugettext_lazy as _

from acls.models import AccessControlList
from common.utils import return_attrib
from permissions import Permission

logger = logging.getLogger(__name__)


class ResolvedLink(object):
    active = False
    description = None
    icon = None
    tags = None
    text = _('Unnamed link')
    url = '#'


class Menu(object):
    # TODO: Add support for position #{'link': links, 'position': position})

    _registry = {}

    @classmethod
    def get(cls, name):
        return cls._registry[name]

    def __init__(self, name):
        if name in self.__class__._registry:
            raise Exception('A menu with this name already exists')

        self.name = name
        self.bound_links = {}
        self.__class__._registry[name] = self

    def _add_links_to_source(self, links, source, position=None):
        source_links = self.bound_links.setdefault(source, [])

        for link in links:
            source_links.append(link)

    def bind_links(self, links, sources=None, position=None):
        """
        Associate a link to a model, a view inside this menu
        """

        if sources:
            for source in sources:
                self._add_links_to_source(links, source)
        else:
            # Unsourced links display always
            self._add_links_to_source(links, None)

    def resolve(self, context, source=None):
        request = Variable('request').resolve(context)
        current_path = request.META['PATH_INFO']

        # Get sources: view name, view objects
        current_view = resolve(current_path).view_name
        resolved_navigation_object_list = []

        result = []

        if source:
            resolved_navigation_object_list = [source]
        else:
            navigation_object_list = context.get(
                'navigation_object_list', ['object']
            )

            # Multiple objects
            for navigation_object in navigation_object_list:
                try:
                    resolved_navigation_object_list.append(
                        Variable(navigation_object).resolve(context)
                    )
                except VariableDoesNotExist:
                    pass

        for resolved_navigation_object in resolved_navigation_object_list:
            resolved_links = []

            for bound_source, links in self.bound_links.iteritems():
                try:
                    if inspect.isclass(bound_source) and type(resolved_navigation_object) == bound_source or source == CombinedSource(obj=resolved_navigation_object.__class__, view=current_view):
                        for link in links:
                            resolved_link = link.resolve(
                                context=context,
                                resolved_object=resolved_navigation_object
                            )
                            if resolved_link:
                                resolved_links.append(resolved_link)
                        # No need for further content object match testing
                        break
                except TypeError:
                    # When source is a dictionary
                    pass

            if resolved_links:
                result.append(resolved_links)

        resolved_links = []
        # View links
        for link in self.bound_links.get(current_view, []):
            resolved_link = link.resolve(context)
            if resolved_link:
                resolved_links.append(resolved_link)

        if resolved_links:
            result.append(resolved_links)

        resolved_links = []

        # Main menu links
        for link in self.bound_links.get(None, []):
            resolved_link = link.resolve(context)
            if resolved_link:
                resolved_links.append(resolved_link)

        if resolved_links:
            result.append(resolved_links)

        return result


class Link(object):
    def __init__(self, text, view, args=None, condition=None,
                 conditional_disable=None, description=None, icon=None,
                 keep_query=False, klass=None, kwargs=None, permissions=None,
                 remove_from_query=None, tags=None):

        self.args = args or []
        self.condition = condition
        self.conditional_disable = conditional_disable
        self.description = description
        self.icon = icon
        self.keep_query = keep_query
        self.klass = klass
        self.kwargs = kwargs or {}
        self.permissions = permissions or []
        self.remove_from_query = remove_from_query or []
        self.tags = tags
        self.text = text
        self.view = view

    def resolve(self, context, resolved_object=None):
        request = Variable('request').resolve(context)
        current_path = request.META['PATH_INFO']
        current_view = resolve(current_path).view_name

        # If this link has a required permission check that the user have it
        # too
        if self.permissions:
            try:
                Permission.check_permissions(request.user, self.permissions)
            except PermissionDenied:
                # If the user doesn't have the permission, and we are passed
                # an instance, check to see if the user has at least ACL
                # access to the instance.
                if resolved_object:
                    try:
                        AccessControlList.objects.check_access(
                            self.permissions, request.user, resolved_object
                        )
                    except PermissionDenied:
                        return None
                else:
                    return None

        # Check to see if link has conditional display function and only
        # display it if the result of the conditional display function is
        # True
        if self.condition:
            if not self.condition(context):
                return None

        resolved_link = ResolvedLink()
        resolved_link.description = self.description
        resolved_link.icon = self.icon
        resolved_link.klass = self.klass
        resolved_link.tags = self.tags
        resolved_link.text = self.text

        view_name = Variable('"{}"'.format(self.view))
        if isinstance(self.args, list) or isinstance(self.args, tuple):
            # TODO: Don't check for instance check for iterable in try/except
            # block. This update required changing all 'args' argument in
            # links.py files to be iterables and not just strings.
            args = [Variable(arg) for arg in self.args]
        else:
            args = [Variable(self.args)]

        # If we were passed an instance of the view context object we are
        # resolving, inject it into the context. This help resolve links for
        # object lists.
        if resolved_object:
            context['resolved_object'] = resolved_object

        try:
            kwargs = self.kwargs(context)
        except TypeError:
            # Is not a callable
            kwargs = self.kwargs

        kwargs = {key: Variable(value) for key, value in kwargs.iteritems()}

        # Use Django's exact {% url %} code to resolve the link
        node = URLNode(
            view_name=view_name, args=args, kwargs=kwargs, asvar=None
        )

        resolved_link.url = node.render(context)

        # This is for links that should be displayed but that are not clickable
        if self.conditional_disable:
            resolved_link.disabled = self.conditional_disable(context)
        else:
            resolved_link.disabled = False

        # Lets a new link keep the same URL query string of the current URL
        if self.keep_query:
            # Sometimes we are required to remove a key from the URL QS
            previous_path = smart_unicode(
                urllib.unquote_plus(
                    smart_str(
                        request.get_full_path()
                    ) or smart_str(
                        request.META.get(
                            'HTTP_REFERER',
                            reverse(settings.LOGIN_REDIRECT_URL)
                        )
                    )
                )
            )
            query_string = urlparse.urlparse(previous_path).query
            parsed_query_string = urlparse.parse_qs(query_string)

            for key in self.remove_from_query:
                try:
                    del parsed_query_string[key]
                except KeyError:
                    pass

            resolved_link.url = '%s?%s' % (
                urlquote(resolved_link.url),
                urlencode(parsed_query_string, doseq=True)
            )

        # Helps highligh in the UI the current link in effect
        resolved_link.active = self.view == current_view

        return resolved_link


class SourceColumn(object):
    _registry = {}

    @classmethod
    def get_for_source(cls, source):
        try:
            return cls._registry[source]
        except KeyError:
            try:
                return cls._registry[source.model]
            except AttributeError:
                try:
                    return cls._registry[source.__class__]
                except KeyError:
                    return ()
        except TypeError:
            # unhashable type: list
            return ()

    def __init__(self, source, label, attribute=None, func=None):
        self.source = source
        self.label = label
        self.attribute = attribute
        self.func = func
        self.__class__._registry.setdefault(source, [])
        self.__class__._registry[source].append(self)

    def resolve(self, context):
        if self.attribute:
            result = return_attrib(context['object'], self.attribute)
        elif self.func:
            result = self.func(context=context)

        return result


class CombinedSource(object):
    """
    Class that binds a link to a combination of an object and a view.
    This is used to show links relating to a specific object type but only
    in certain views.
    Used by the PageDocument class to show rotatio and zoom link only on
    certain views
    """
    def __init__(self, obj, view):
        self.obj = obj
        self.view = view

    def __hash__(self):
        return hash((self.obj, self.view))

    def __eq__(self, other):
        return hash(self) == hash(other)
