'''
Created on 23-07-2013

@author: kamil
'''
from django.utils.translation import ugettext as _
from django.http.response import Http404
from rest_framework.generics import get_object_or_404

from rest_framework.response import Response
from rest_framework import status

from filthy.exceptions import FilterValueError
import logging

class WrappedResultMixin(object):
    
    def create(self, request, *args, **kwargs):
        response = super(WrappedResultMixin, self).create(request, *args, **kwargs)
        if not 200 <= response.status_code < 300: return response
        wrapped_data = {"result": response.data}
        response.data = wrapped_data
        return response
    
    def retrieve(self, request, *args, **kwargs):
        response = super(WrappedResultMixin, self).retrieve(request, *args, **kwargs)
        if not 200 <= response.status_code < 300: return response
        wrapped_data = {"result": response.data}
        response.data = wrapped_data
        return response
    
    def update(self, request, *args, **kwargs):
        response = super(WrappedResultMixin, self).update(request, *args, **kwargs)
        if not 200 <= response.status_code < 300: return response
        wrapped_data = {"result": response.data}
        response.data = wrapped_data
        return response
    
    def partial_update(self, request, *args, **kwargs):
        response = super(WrappedResultMixin, self).partial_update(request, *args, **kwargs)
        if not 200 <= response.status_code < 300: return response
        wrapped_data = {"result": response.data}
        response.data = wrapped_data
        return response
    
    def destroy(self, request, *args, **kwargs):
        response = super(WrappedResultMixin, self).destroy(request, *args, **kwargs)
        if not 200 <= response.status_code < 300: return response
        wrapped_data = {"result": response.data}
        response.data = wrapped_data
        return response

class FilterMixin(object):
    
    filters = {}
    
    def get_queryset(self):
        qs = super(FilterMixin, self).get_queryset()
        filters = self.__class__.filters
        search_kwargs = self.build_search_kwargs(filters, self.request.QUERY_PARAMS)
        for kwarg in search_kwargs:
            qs = self.filter_with_search_kwarg(qs, kwarg)
        return qs
    
    def filter_with_search_kwarg(self, qs, kwarg):
        target_kwarg, search_condition, negate = kwarg
        if negate:
            return qs.exclude(**{target_kwarg: search_condition})
        else:
            return qs.filter(**{target_kwarg: search_condition})
    
    def build_search_kwargs(self, filters, query_params):
        search_kwargs = set()
        possible_kwargs = self.generate_possible_kwargs(filters)
        for key, value in filters.items():
            possible_kwargs = self.generate_possible_kwargs({key: value})
            target_kwarg = value[0]
            transformation = value[1]
            for pk in possible_kwargs:
                kwarg_tuple = self.build_kwarg(pk)
                if kwarg_tuple is None:
                    continue
                key, negate = kwarg_tuple
                try:
                    raw_condition = query_params[key]
                except KeyError:
                    continue
                try:
                    search_condition = transformation(raw_condition)
                except Exception as e:
                    msg = _(u"Failed to parse filter `{0}` parameter.")
                    raise FilterValueError(detail=msg.format(pk))
                search_kwargs.add((target_kwarg, search_condition, negate))
        return search_kwargs
    
    def generate_possible_kwargs(self, filters):
        non_negated = filters.keys()
        negated = map(lambda k: "!" + k, non_negated)
        return non_negated + negated
    
    def build_kwarg(self, key):
        negate = key.startswith("!")
        return (key, negate)


class TrackDependencyMixin(object):
    
    related = {}
    
    def track(self, key, pk_or_pks):
        if key == type(None):
            return
        if not hasattr(self, 'tracked_dependencies'):
            self.tracked_dependencies = {}
        if key not in self.tracked_dependencies:
            d = {key: set()}
            self.tracked_dependencies.update(d)
        new_list = self.safe_append(self.tracked_dependencies[key], pk_or_pks)
        self.tracked_dependencies[key] = new_list
    
    def safe_append(self, old_set, for_appending):
        if hasattr(for_appending, '__iter__'):
            return old_set.union(for_appending)
        else:
            old_set.add(for_appending)
            return old_set
    
    def get_related(self):
        related = self.__class__.related
        related_dict = {}
        if hasattr(self, 'tracked_dependencies'):
            for key, value in related.items():
                model_class = key
                related_name, serializer_class = value
                try:
                    qs = model_class.objects.filter(pk__in=self.tracked_dependencies[key])
                    context = self.get_serializer_context()
                    serializer = serializer_class(qs, context=context, many=True)
                    related_dict.update({related_name: serializer.data})
                except KeyError as e:
                    msg = "Key error when serializing related field `%s`. Maybe wrong order in `related`?"
                    logging.getLogger(__name__).error(msg, e)
                    related_dict.update({related_name: []})
            return related_dict
    
    def finalize_response(self, request, response, *args, **kwargs):
        response = super(TrackDependencyMixin, self).finalize_response(
            request,
            response,
            *args,
            **kwargs
        )
        if  200 <= response.status_code < 300 and response.status_code != status.HTTP_204_NO_CONTENT:
            response.data.update({"related": self.get_related()})
        return response

class UpdateOr404Mixin(object):
    """
    Update a model instance, only if it exists
    """
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        self.object = self.get_object_or_none()

        if self.object is None:
            errors = {"detail": "Object was not found."}
            return Response(data=errors, status=status.HTTP_404_NOT_FOUND)
        else:
            created = False
            save_kwargs = {'force_update': True}
            success_status_code = status.HTTP_200_OK

        serializer = self.get_serializer(self.object, data=request.DATA,
                                         files=request.FILES, partial=partial)

        if serializer.is_valid():
            self.pre_save(serializer.object)
            self.object = serializer.save(**save_kwargs)
            self.post_save(self.object, created=created)
            return Response(data=serializer.data, status=success_status_code)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PatchListMixin(object):
    """
    Allow patching lists with 'create' and 'delete' lists in payload.
    """
    identify_by = {'id': 'pk'}
    create_field = 'create'
    delete_field = 'delete'
    cid_field = 'cid'
    
    def patch(self, request, *args, **kwargs):
        """
        We don't perform bulk inserts/deletes in order to fire signals
        """
        serializer_class = self.get_serializer_class()
        for_create = request.DATA.get(self.__class__.create_field, None)
        for_delete = request.DATA.get(self.__class__.delete_field, None)
        if for_create:
            success, created, errors = self.g_create(for_create, serializer_class)
            if not success:
                data = {"detail": "Create failed. Delete skipped.", "errors": errors}
                return Response(data=data, status=status.HTTP_400_BAD_REQUEST)
        else:
            created = []
        if for_delete:
            success, deleted, errors = self.g_destroy(for_delete, serializer_class)
            if not success:
                data = {"detail": "Create succeeded. Delete failed.", "errors": errors}
                return Response(data=data, status=status.HTTP_400_BAD_REQUEST)
        else:
            deleted = []
        data = {}
        return Response(data={"create": created, "delete": deleted})
    
    def g_create(self, for_create, serializer_class):
        created = []
        ctx = self.get_serializer_context()
        for raw_object in for_create:
            cid = raw_object.get(self.__class__.cid_field, None)
            save_kwargs = {'force_insert': True}
            serializer = serializer_class(
                data=raw_object,
                context=ctx,
            )
            if serializer.is_valid():
                self.pre_save(serializer.object)
                self.object = serializer.save(**save_kwargs)
                self.post_save(self.object, created=True)
                d = serializer_class(self.object, context=ctx).data
                d.update({"cid": cid})
                created.append(d)
            else:
                return (False, created, serializer.errors)
        return (True, created, None)            
    
    def g_destroy(self, for_delete, serializer_class):
        deleted = []
        for raw_object in for_delete:
            obj = self.get_object_for_delete(raw_object, self.__class__.identify_by)
            if obj:
                data_chunk = serializer_class(
                    obj,
                    context=self.get_serializer_context()
                ).data
                obj.delete()
                deleted.append(data_chunk)
            else:
                continue
        return (True, deleted, None)
    
    def get_object_for_delete(self, raw_obj, identify_by):
        qs = self.get_queryset()
        filter_kwargs = {}
        for k, v in identify_by.items():
            filter_kwargs.update({v: raw_obj[k]})
        try:
            obj = get_object_or_404(qs, **filter_kwargs)
        except Http404:
            obj = None
        return obj
