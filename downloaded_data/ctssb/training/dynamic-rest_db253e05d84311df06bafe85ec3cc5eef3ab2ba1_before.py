from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import QueryDict
from django.utils.datastructures import MergeDict

from rest_framework import viewsets, exceptions
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from dynamic_rest.renderers import DynamicBrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer

from dynamic_rest.pagination import DynamicPageNumberPagination
from dynamic_rest.metadata import DynamicMetadata
from dynamic_rest.filters import DynamicFilterBackend, DynamicSortingFilter


dynamic_settings = getattr(settings, 'DYNAMIC_REST', {})
UPDATE_REQUEST_METHODS = ('PUT', 'PATCH', 'POST')


class QueryParams(QueryDict):

    """
    Extension of Django's QueryDict. Instantiated from a DRF Request
    object, and returns a mutable QueryDict subclass.
    Also adds methods that might be useful for our usecase.
    """

    def __init__(self, query_params, *args, **kwargs):
        query_string = getattr(query_params, 'urlencode', lambda: '')()
        kwargs['mutable'] = True
        super(QueryParams, self).__init__(query_string, *args, **kwargs)

    def add(self, key, value):
        """
        Method to accept a list of values and append to flat list.
        QueryDict.appendlist(), if given a list, will append the list,
        which creates nested lists. In most cases, we want to be able
        to pass in a list (for convenience) but have it appended into
        a flattened list.
        TODO: Possibly throw an error if add() is used on a non-list param.
        """
        if isinstance(value, list):
            for val in value:
                self.appendlist(key, val)
        else:
            self.appendlist(key, value)


class WithDynamicViewSetMixin(object):
    """A viewset that can support dynamic API features.

    Attributes:
      features: A list of features supported by the viewset.
      sideload: Whether or not to enable sideloading in the DynamicRenderer.
      meta: Extra data that is added to the response by the DynamicRenderer.
    """

    INCLUDE = 'include[]'
    EXCLUDE = 'exclude[]'
    FILTER = 'filter{}'
    SORT = 'sort[]'
    PAGE = dynamic_settings.get('PAGE_QUERY_PARAM', 'page')
    PER_PAGE = dynamic_settings.get('PAGE_SIZE_QUERY_PARAM', 'per_page')

    # TODO: add support for `sort{}`
    pagination_class = DynamicPageNumberPagination
    metadata_class = DynamicMetadata
    renderer_classes = (JSONRenderer, DynamicBrowsableAPIRenderer)
    features = (INCLUDE, EXCLUDE, FILTER, PAGE, PER_PAGE, SORT)
    sideload = True
    meta = None
    filter_backends = (DynamicFilterBackend, DynamicSortingFilter)

    def initialize_request(self, request, *args, **kargs):
        """
        Override DRF initialize_request() method to swap request.GET
        (which is aliased by request.QUERY_PARAMS) with a mutable instance
        of QueryParams, and to convert request MergeDict to a subclass of dict
        for consistency (MergeDict is not a subclass of dict)
        """
        try:
            request.GET = QueryParams(request.GET)
        except UnicodeEncodeError:
            # WSGIRequest does not support Unicode values in the query string.
            # Deal with this here to avoid 500s, code adapted from:
            # https://github.com/django/django/blob/1.7.9/django/core/handlers/wsgi.py#L130 # noqa
            request.GET = QueryParams(
                request.environ.get('QUERY_STRING', '').encode('utf-8')
            )

        request = super(WithDynamicViewSetMixin, self).initialize_request(
            request, *args, **kargs
        )

        # MergeDict doesn't have the same API as dict.
        # Django has deprecated MergeDict and DRF is moving away from
        # using it - thus, were comfortable replacing it with a QueryDict
        # This will allow the data property to have normal dict methods.
        if isinstance(request._full_data, MergeDict):
            data_as_dict = request.data.dicts[0]
            for d in request.data.dicts[1:]:
                data_as_dict.update(d)
            request._full_data = data_as_dict

        return request

    def get_renderers(self):
        """Optionally block Browsable API rendering. """
        renderers = super(WithDynamicViewSetMixin, self).get_renderers()
        if dynamic_settings.get('ENABLE_BROWSABLE_API') is False:
            return [
                r for r in renderers if not isinstance(r, BrowsableAPIRenderer)
            ]
        else:
            return renderers

    def get_request_feature(self, name):
        """Parses the request for a particular feature.

        Arguments:
          name: A feature name.

        Returns:
          A feature parsed from the URL if the feature is supported, or None.
        """
        if '[]' in name:
            # array-type
            return self.request.QUERY_PARAMS.getlist(
                name) if name in self.features else None
        elif '{}' in name:
            # object-type (keys are not consistent)
            return self._extract_object_params(
                name) if name in self.features else {}
        else:
            # single-type
            return self.request.QUERY_PARAMS.get(
                name) if name in self.features else None

    def _extract_object_params(self, name):
        """
        Extract object params, return as dict
        """

        params = self.request.query_params.lists()
        params_map = {}
        prefix = name[:-1]
        offset = len(prefix)
        for name, value in params:
            if name.startswith(prefix):
                if name.endswith('}'):
                    name = name[offset:-1]
                elif name.endswith('}[]'):
                    # strip off trailing []
                    # this fixes an Ember queryparams issue
                    name = name[offset:-3]
                else:
                    # malformed argument like:
                    # filter{foo=bar
                    raise exceptions.ParseError(
                        "'%s' is not a well-formed filter key" % name
                    )
            else:
                continue
            params_map[name] = value

        return params_map

    def get_queryset(self, queryset=None):
        """
        Returns a queryset for this request.

        Arguments:
          queryset: Optional root-level queryset.
        """
        serializer = self.get_serializer()
        return getattr(self, 'queryset', serializer.Meta.model.objects.all())

    def get_request_fields(self):
        """Parses the `include[]` and `exclude[]` features.

        Extracts the dynamic field features from the request parameters
        into a field map that can be passed to a serializer.

        Returns:
          A nested dict mapping serializer keys to
          True (include) or False (exclude).
        """
        if hasattr(self, '_request_fields'):
            return self._request_fields

        include_fields = self.get_request_feature('include[]')
        exclude_fields = self.get_request_feature('exclude[]')
        request_fields = {}
        for fields, include in(
                (include_fields, True),
                (exclude_fields, False)):
            if fields is None:
                continue
            for field in fields:
                field_segments = field.split('.')
                num_segments = len(field_segments)
                current_fields = request_fields
                for i, segment in enumerate(field_segments):
                    last = i == num_segments - 1
                    if segment:
                        if last:
                            current_fields[segment] = include
                        else:
                            if segment not in current_fields:
                                current_fields[segment] = {}
                            current_fields = current_fields[segment]
                    elif not last:
                        # empty segment must be the last segment
                        raise exceptions.ParseError(
                            "'%s' is not a valid field" %
                            field)

        self._request_fields = request_fields
        return request_fields

    def is_update(self):
        if (
            self.request and
            self.request.method.upper() in UPDATE_REQUEST_METHODS
        ):
            return True
        else:
            return False

    def get_serializer(self, *args, **kwargs):
        if 'request_fields' not in kwargs:
            kwargs['request_fields'] = self.get_request_fields()
        if 'sideload' not in kwargs:
            kwargs['sideload'] = self.sideload
        if self.is_update():
            kwargs['include_fields'] = '*'
        return super(
            WithDynamicViewSetMixin, self).get_serializer(
            *args, **kwargs)

    def paginate_queryset(self, *args, **kwargs):
        if self.PAGE in self.features:
            # make sure pagination is enabled
            if self.PER_PAGE not in self.features and \
                    self.PER_PAGE in self.request.QUERY_PARAMS:
                # remove per_page if it is disabled
                self.request.QUERY_PARAMS[self.PER_PAGE] = None
            return super(
                WithDynamicViewSetMixin, self).paginate_queryset(
                *args, **kwargs)
        return None

    def _prefix_inex_params(self, request, feature, prefix):
        values = self.get_request_feature(feature)
        if not values:
            return
        del request.query_params[feature]
        request.query_params.add(
            feature,
            [prefix + val for val in values]
        )

    def list_related(self, request, pk=None, field_name=None):
        """Fetch related object(s), as if sideloaded (used to support
        link objects).

        This method gets mapped to `/<resource>/<pk>/<field_name>/` by
        DynamicRouter for all DynamicRelationField fields. Generally,
        this method probably shouldn't be overridden.

        An alternative implementation would be to generate reverse queries.
        For an exploration of that approach, see:
            https://gist.github.com/ryochiji/54687d675978c7d96503
        """

        # Explicitly disable support filtering. Applying filters to this
        # endpoint would require us to pass through sideload filters, which
        # can have unintended consequences when applied asynchronously.
        if self.get_request_feature(self.FILTER):
            raise ValidationError(
                "Filtering is not enabled on relation endpoints."
            )

        # Prefix include/exclude filters with field_name so it's scoped to
        # the parent object.
        field_prefix = field_name + '.'
        self._prefix_inex_params(request, self.INCLUDE, field_prefix)
        self._prefix_inex_params(request, self.EXCLUDE, field_prefix)

        # Filter for parent object, include related field.
        self.request.query_params.add('filter{pk}', pk)
        self.request.query_params.add('include[]', field_prefix)

        # Get serializer and field.
        serializer = self.get_serializer()
        field = serializer.fields.get(field_name)
        if field is None:
            raise ValidationError("Unknown field: %s" % field_name)

        # Query for root object, with related field prefetched
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        obj = queryset.first()

        if not obj:
            return Response("Not found", status=404)

        # Serialize the related data. Use the field's serializer to ensure
        # it's configured identically to the sideload case.
        serializer = field.serializer
        try:
            # TODO(ryo): Probably should use field.get_attribute() but that
            #            seems to break a bunch of things. Investigate later.
            serializer.instance = getattr(obj, field.source)
        except ObjectDoesNotExist:
            # See:
            # http://jsonapi.org/format/#fetching-relationships-responses-404
            # This is a case where the "link URL exists but the relationship
            # is empty" and therefore must return a 200.
            return Response({}, status=200)

        return Response(serializer.data)


class DynamicModelViewSet(WithDynamicViewSetMixin, viewsets.ModelViewSet):
    pass
