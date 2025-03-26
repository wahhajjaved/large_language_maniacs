from datetime import datetime
from copy import copy

from django.db import models
from djangotoolbox.fields import ListField, EmbeddedModelField

from django_statemodel.signals import save_timestamp_cache, set_default_state


OPTIONS_CLASS = "StateModelMeta"
OPTIONS_ATTR_NAME = "_statemodelmeta"
DONE_INITIALIZING = "_statemodel_done_initializing"


class StateModelBase(models.base.ModelBase):
    def __new__(mcs, name, bases, attrs):
        # Look at Options for information about the StateModel states
        options = attrs.pop(OPTIONS_CLASS, None)
        if options is None:
            options = {}
        else:
            options = options.__dict__

        # Get the field name for state from the meta options
        state_field_name = options.get('state_field_name', 'state')
        state_timestamps_field_name = options.get('state_timestamps_field_name',
                                                  'state_timestamps')

        # Get a Django field from the given model's _meta object
        def get_field(model, field):
            if hasattr(model, "_meta"):
                try:
                    return model._meta.get_field(field)
                except models.fields.FieldDoesNotExist:
                    return None
            return None

        # Check if any of the inherited models have the state field
        parent_has_state = False
        for parent in bases:
            if bool(get_field(parent, state_field_name)) or \
                    bool(get_field(parent, state_timestamps_field_name)):
                parent_has_state = True
                break

        # If the options are in the attrs and the state field isn't already
        # inherited, add the statemodel fields. Django doesn't allow overriding.
        if not parent_has_state and options:

            # state_map contains the mapping of states values to their attribute
            # names.
            state_map = options.get('state_map', [])
            default_state = options.get('default_state')
            add_states_to_model = options.get('add_states_to_model', True)

            if state_map:
                # default_state is either the first state in the map, or as
                # overridden
                if default_state is None:
                    default_state = state_map[0][0]

                # Assign the states as attributes to the model
                if add_states_to_model:
                    for key, value in state_map:
                        attrs[value] = key

            # db_index boolean to add an index to the state field.
            db_index = options.get('db_index', True)

            # Check if we should store the timestamp as utc
            use_utc = options.get('use_utc', True)

            # Check if we allow None states
            allow_none_state = options.get('allow_none_state', True)
            if not allow_none_state and default_state is None:
                raise ValueError("'allow_none_state' cannot be False while "
                                 "'default_state' is set to None or 'state_map'"
                                 " is undefined.")

            # Add the state-model fields
            attrs[state_field_name] = models.IntegerField(null=True,
                                                          db_index=db_index,
                                                          choices=state_map)
            attrs[state_timestamps_field_name] = \
                        ListField(EmbeddedModelField(StateTransitionTimestamp),
                                  default=[],
                                  blank=True)

            # Save the options for this model in an object attached to the model
            options_cache = StateModelBase.StateModelOptions(
                dict(state_map), default_state, use_utc, allow_none_state,
                db_index, add_states_to_model, state_field_name,
                state_timestamps_field_name)
            attrs[OPTIONS_ATTR_NAME] = options_cache

        elif parent_has_state and options:
            raise AttributeError("Django does not allow field overriding with "
                                 "inheritance. '%s' should only be a member "
                                 "of one model in the inheritance tree."
                                 % OPTIONS_CLASS)

        cls = super(StateModelBase, mcs).__new__(mcs, name, bases, attrs)

        # Check if this is an abstract model
        is_abstract_model = getattr(attrs.get('Meta', {}), "abstract", False)

        # Add signals to the inheriting models to save the state transitions
        if not is_abstract_model:
            models.signals.pre_save.connect(save_timestamp_cache,
                                            sender=cls)
            models.signals.post_init.connect(set_default_state,
                                             sender=cls)
        return cls

    class StateModelOptions(object):
        def __init__(self, state_map, default_state, use_utc, allow_none_state,
                     db_index, add_states_to_model, state_field_name,
                     state_timestamps_field_name):
            self.state_map = copy(state_map)
            self.default_state = default_state
            self.use_utc = use_utc
            self.allow_none_state = allow_none_state
            self.db_index = db_index
            self.add_states_to_model = add_states_to_model
            self.state_field_name = state_field_name
            self.state_timestamps_field_name = state_timestamps_field_name
            self.state_timestamps_cache_name = \
                                    "_%s_cache" % state_timestamps_field_name


class StateTransitionTimestamp(models.Model):
    state = models.IntegerField(
        blank=False,
        null=False,
        help_text="The state of this transition")

    state_time = models.DateTimeField(
        blank=False,
        null=False,
        default=datetime.utcnow,
        help_text="The time this state was entered")

    def __unicode__(self):
        return "%s: %s" % (self.state, self.state_time)


class StateModel(models.Model):
    __metaclass__ = StateModelBase

    class Meta:
        abstract = True

    def __setattr__(self, key, value):
        meta_options = getattr(self, OPTIONS_ATTR_NAME)
        # Check if we are setting the "state" field and that we are done
        # initializing. Done initializing means the __init__ is finished.
        if key == meta_options.state_field_name and \
                getattr(self, DONE_INITIALIZING, False):
            # Value can be a tuple of (<state>, <datetime object>)
            if isinstance(value, (tuple, list)):
                if len(value) != 2 or not isinstance(value[1], datetime):
                    raise ValueError("'%s' must be in the format: <state> or "
                                     "(<state>, <datetime>)"
                                     % meta_options.state_field_name)

                timestamp = value[1]
                value = value[0]
            else:
                # If no timestamp is given, set it to now
                timestamp = datetime.utcnow() if meta_options.use_utc else \
                            datetime.now()

            if not meta_options.allow_none_state and value is None:
                raise ValueError("The given state value is None, and None "
                                 "states are not allowed.")

            if value not in meta_options.state_map and value is not None:
                raise ValueError("The given state '%s' is not a valid state "
                                 "listed in the statemap: '%s'."
                                 % (value, meta_options.state_map))

            # Don't update the state's timestamp if the state hasn't changed.
            if value != getattr(self, meta_options.state_field_name):
                # We store the timestamp in a cache until the model is saved.
                # This way, we only update the state_timestamps once per save.
                state_transition = StateTransitionTimestamp(
                                        state=value, state_time=timestamp)
                setattr(self,
                        meta_options.state_timestamps_cache_name,
                        state_transition)

        super(StateModel, self).__setattr__(key, value)
