# -*- coding: utf-8 -*-
# pylint: disable=W0212, R0904
"""
State tracking functionality for django models
"""
from collections import defaultdict
from functools import wraps
from django.db import models

class FSMMeta(object):
    """
    Models methods transitions meta information
    """
    def __init__(self):
        self.transitions = defaultdict()
    
    @staticmethod
    def _get_state_field(instance):
        """
        Lookup for FSMField in django model instance
        """
        fields = [field for field in instance._meta.fields 
                  if isinstance(field, FSMField) or isinstance(field, FSMKeyField)]
        found = len(fields)
        if found == 0:
            raise TypeError("No FSMField found in model")
        elif found > 1:
            raise TypeError("More than one FSMField found in model")
        return fields[0]

    @staticmethod
    def current_state(instance):
        """
        Return current state of Django model
        """
        field_name = FSMMeta._get_state_field(instance).name
        return getattr(instance, field_name)
        
    def has_transition(self, instance):
        """
        Lookup is any transition exists from current model state
        """
        return self.transitions.has_key(FSMMeta.current_state(instance))

    def to_next_state(self, instance):
        """
        Switch to next state
        """
        field_name = FSMMeta._get_state_field(instance).name
        curr_state = getattr(instance, field_name)
        setattr(instance, field_name, self.transitions[curr_state])


def transition(source='*', target=None, save=False):
    """
    Method decorator for mark allowed transition
    """
    # pylint: disable=C0111
    def inner_transition(func):
        if not hasattr(func, '_django_fsm'):
            setattr(func, '_django_fsm', FSMMeta())

        if isinstance(source, (list, tuple)):
            for state in source:
                func._django_fsm.transitions[state] = target
        else:
            func._django_fsm.transitions[source] = target

        @wraps(func)
        def _change_state(instance, *args, **kwargs):            
            meta = func._django_fsm
            if not meta.has_transition(instance):
                raise NotImplementedError("Can't switch from state '%s' using method '%s'" % (FSMMeta.current_state(instance), func.func_name))
            
            func(instance, *args, **kwargs)

            meta.to_next_state(instance)
            if save:
                instance.save()
        
        return _change_state
    
    if not target:
        raise ValueError("Result state not specified")
    
    return inner_transition



class FSMField(models.Field):
    """
    State Machine support for Django model

    """
    __metaclass__ = models.SubfieldBase
    
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 50
        super(FSMField, self).__init__(*args, **kwargs)

    def get_internal_type(self):
        return 'CharField'


class FSMKeyField(models.ForeignKey):
    """
    State Machine support for Django model

    """
