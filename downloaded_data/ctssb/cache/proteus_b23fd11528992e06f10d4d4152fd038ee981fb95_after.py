#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
'''
A library to access Tryton's models like a client.
'''
__version__ = "1.8.0"
__all__ = ['Model', 'Wizard']
from types import NoneType
import threading
import datetime
from decimal import Decimal
import proteus.config
from proteus.pyson import PYSONDecoder

_MODELS = threading.local()

class _EvalEnvironment(dict):
    'Dictionary for evaluation'
    def __init__(self, parent):
        super(_EvalEnvironment, self).__init__()
        self.parent = parent

    def __getitem__(self, item):
        if item == '_parent_' + self.parent._parent_field_name \
                and self.parent.parent:
            return _EvalEnvironment(self.parent.parent)
        return self.parent._get_eval()[item]

    def __getattr__(self, item):
        return self.__getitem__(item)

    def get(self, item, default=None):
        try:
            return self.__getattr__(item)
        except:
            pass
        return super(_EvalEnvironment, self).get(item, default)

    def __nonzero__(self):
        return True

    def __str__(self):
        return str(self.parent)

    __repr__ = __str__

    def __contains__(self, item):
        return item in self.parent._fields


class FieldDescriptor(object):
    default = None

    def __init__(self, name, definition):
        super(FieldDescriptor, self).__init__()
        self.name = name
        self.definition = definition

    def __get__(self, instance, owner):
        if instance.id > 0 and self.name not in instance._values:
            instance._read(self.name)
        return instance._values.get(self.name, self.default)

    def __set__(self, instance, value):
        if instance.id > 0 and self.name not in instance._values:
            instance._read(self.name)
        previous = getattr(instance, self.name)
        instance._values[self.name] = value
        if previous != getattr(instance, self.name):
            instance._changed.add(self.name)
            instance._on_change(self.name)
            if instance._parent:
                instance._parent._changed.add(instance._parent_field_name)
                instance._parent._on_change(instance._parent_field_name)


class BooleanDescriptor(FieldDescriptor):
    default = False

    def __set__(self, instance, value):
        assert isinstance(value, bool)
        super(BooleanDescriptor, self).__set__(instance, value)


class CharDescriptor(FieldDescriptor):
    default = None

    def __set__(self, instance, value):
        assert isinstance(value, basestring)
        super(CharDescriptor, self).__set__(instance, value)


class IntegerDescriptor(FieldDescriptor):
    default = 0

    def __set__(self, instance, value):
        assert isinstance(value, (int, long))
        super(IntegerDescriptor, self).__set__(instance, value)


class FloatDescriptor(FieldDescriptor):
    default = 0.0

    def __set__(self, instance, value):
        assert isinstance(value, float)
        super(FloatDescriptor, self).__set__(instance, value)


class NumericDescriptor(FieldDescriptor):
    default = Decimal('0.0')

    def __set__(self, instance, value):
        assert isinstance(value, Decimal)
        # TODO add digits validation
        super(NumericDescriptor, self).__set__(instance, value)


class ReferenceDescriptor(FieldDescriptor):
    def __get__(self, instance, owner):
        value = super(ReferenceDescriptor, self).__get__(instance, owner)
        if isinstance(value, basestring):
            model_name, id = value.split(',', 1)
            if model_name:
                relation = Model.get(model_name, instance._config)
                value = relation(int(id))
                instance._values[self.name] = value
        return value

    def __set__(self, instance, value):
        assert isinstance(value, (Model, NoneType, basestring))
        if isinstance(value, basestring):
            assert value.startswith(',')
        elif isinstance(value, Model):
            assert value.id > 0 and not value._changed
            assert value._config == instance._config
        super(ReferenceDescriptor, self).__set__(instance, value)


class DateDescriptor(FieldDescriptor):
    def __get__(self, instance, owner):
        value = super(DateDescriptor, self).__get__(instance, owner)
        if isinstance(value, datetime.datetime):
            value = value.date()
            instance._values[self.name] = value
        return value

    def __set__(self, instance, value):
        assert isinstance(value, datetime.date)
        super(DateDescriptor, self).__set__(instance, value)


class DateTimeDescriptor(FieldDescriptor):
    def __set__(self, instance, value):
        assert isinstance(value, datetime.datetime)
        super(DateTimeDescriptor, self).__set__(instance, value)


class Many2OneDescriptor(FieldDescriptor):
    def __get__(self, instance, owner):
        relation = Model.get(self.definition['relation'], instance._config)
        value = super(Many2OneDescriptor, self).__get__(instance, owner)
        if isinstance(value, (int, long)) and value is not False:
            value = relation(value)
        elif not value:
            value = None
        instance._values[self.name] = value
        return value

    def __set__(self, instance, value):
        assert isinstance(value, (Model, NoneType))
        if value:
            assert value.id > 0 and not value._changed
            assert value._config == instance._config
        super(Many2OneDescriptor, self).__set__(instance, value)


class One2ManyDescriptor(FieldDescriptor):
    default = []

    def __get__(self, instance, owner):
        relation = Model.get(self.definition['relation'], instance._config)
        value = super(One2ManyDescriptor, self).__get__(instance, owner)
        if not isinstance(value, ModelList):
            value = ModelList((relation(id)
                for id in value or []), instance, self.name,
                self.definition.get('relation_field'))
            instance._values[self.name] = value
        return value

    def __set__(self, instance, value):
        raise AttributeError


class Many2ManyDescriptor(One2ManyDescriptor):
    pass


class ValueDescriptor(object):
    def __init__(self, name, definition):
        super(ValueDescriptor, self).__init__()
        self.name = name
        self.definition = definition

    def __get__(self, instance, owner):
        return getattr(instance, self.name)


class ReferenceValueDescriptor(ValueDescriptor):
    def __get__(self, instance, owner):
        value = super(ReferenceValueDescriptor, self).__get__(instance, owner)
        if isinstance(value, Model):
            value = '%s,%s' % (value.__class__.__name__, value.id)
        return value or False


class Many2OneValueDescriptor(ValueDescriptor):
    def __get__(self, instance, owner):
        value = super(Many2OneValueDescriptor, self).__get__(instance, owner)
        return value and value.id or False


class One2ManyValueDescriptor(ValueDescriptor):
    def __get__(self, instance, owner):
        value = [('add', [])]
        value_list = getattr(instance, self.name)
        for record in value_list:
            if record.id > 0:
                if record._changed:
                    value.append(('write', record.id, record._get_values(
                        fields=record._changed)))
                value[0][1].append(record.id)
            else:
                value.append(('create', record._get_values(
                    fields=record._changed)))
        if value_list.record_removed:
            value.append(('unlink', [x.id for x in value_list.record_removed]))
        if value_list.record_deleted:
            value.append(('delete', [x.id for x in value_list.record_deleted]))
        return value


class Many2ManyValueDescriptor(One2ManyValueDescriptor):
    pass


class EvalDescriptor(object):
    def __init__(self, name, definition):
        super(EvalDescriptor, self).__init__()
        self.name = name
        self.definition = definition

    def __get__(self, instance, owner):
        return getattr(instance, self.name)


class ReferenceEvalDescriptor(EvalDescriptor):
    def __get__(self, instance, owner):
        value = super(ReferenceEvalDescriptor, self).__get__(instance, owner)
        if isinstance(value, Model):
            value = '%s,%s' % (value.__class__.__name__, value.id)
        return value or False


class Many2OneEvalDescriptor(EvalDescriptor):
    def __get__(self, instance, owner):
        value = super(Many2OneEvalDescriptor, self).__get__(instance, owner)
        if value:
            return value.id
        return False


class One2ManyEvalDescriptor(EvalDescriptor):
    def __get__(self, instance, owner):
        return [x.id for x in getattr(instance, self.name)]


class Many2ManyEvalDescriptor(One2ManyEvalDescriptor):
    pass


class MetaModelFactory(object):
    descriptors = {
        'boolean': BooleanDescriptor,
        'char': CharDescriptor,
        'text': CharDescriptor,
        'sha': CharDescriptor,
        'binary': CharDescriptor,
        'selection': CharDescriptor, # TODO implement its own descriptor
        'integer': IntegerDescriptor,
        'biginteger': IntegerDescriptor,
        'float': FloatDescriptor,
        'float_time': FloatDescriptor,
        'numeric': NumericDescriptor,
        'reference': ReferenceDescriptor,
        'date': DateDescriptor,
        'datetime': DateTimeDescriptor,
        'many2one': Many2OneDescriptor,
        'one2many': One2ManyDescriptor,
        'many2many': Many2ManyDescriptor,
    }
    value_descriptors = {
        'reference': ReferenceValueDescriptor,
        'many2one': Many2OneValueDescriptor,
        'one2many': One2ManyValueDescriptor,
        'many2many': Many2ManyValueDescriptor,
    }
    eval_descriptors = {
        'reference': ReferenceEvalDescriptor,
        'many2one': Many2OneEvalDescriptor,
        'one2many': One2ManyEvalDescriptor,
        'many2many': Many2ManyEvalDescriptor,
    }

    def __init__(self, model_name, config=None):
        super(MetaModelFactory, self).__init__()
        self.model_name = model_name
        self.config = config or proteus.config.get_config()

    def __call__(self):
        models_key = 'c%s' % id(self.config)
        if not hasattr(_MODELS, models_key):
            setattr(_MODELS, models_key, {})
        class MetaModel(type):
            'Meta class for Model'
            def __new__(mcs, name, bases, dict):
                if self.model_name in getattr(_MODELS, models_key):
                    return getattr(_MODELS, models_key)[self.model_name]
                proxy = self.config.get_proxy(self.model_name)
                context = self.config.context
                name = self.model_name
                dict['_proxy'] = proxy
                dict['_config'] = self.config
                dict['_fields'] = proxy.fields_get(None, context)
                for field_name, definition in dict['_fields'].iteritems():
                    if field_name == 'id':
                        continue
                    Descriptor = self.descriptors[definition['type']]
                    dict[field_name] = Descriptor(field_name, definition)
                    VDescriptor = self.value_descriptors.get(
                            definition['type'], ValueDescriptor)
                    dict['__%s_value' % field_name] = VDescriptor(
                            field_name, definition)
                    EDescriptor = self.eval_descriptors.get(
                            definition['type'], EvalDescriptor)
                    dict['__%s_eval' % field_name] = EDescriptor(
                            field_name, definition)
                for method in self.config.get_proxy_methods(self.model_name):
                    setattr(mcs, method, getattr(proxy, method))
                res = type.__new__(mcs, name, bases, dict)
                getattr(_MODELS, models_key)[self.model_name] = res
                return res
            __new__.__doc__ = type.__new__.__doc__
        return MetaModel


class ModelList(list):
    'List for Model'

    def __init__(self, sequence=None, parent=None, parent_field_name='',
            parent_name=''):
        if sequence is None:
            sequence = []
        self.parent = parent
        if parent:
            assert parent_field_name
        self.parent_field_name = parent_field_name
        self.parent_name = parent_name
        self.record_removed = set()
        self.record_deleted = set()
        result = super(ModelList, self).__init__(sequence)
        for record in self:
            record._parent = parent
            record._parent_field_name = parent_field_name
            record._parent_name = parent_name
        return result
    __init__.__doc__ = list.__init__.__doc__

    def _changed(self):
        'Signal change to parent'
        if self.parent:
            self.parent._changed.add(self.parent_field_name)
            self.parent._on_change(self.parent_field_name)

    def append(self, record):
        assert isinstance(record, Model)
        if self.parent:
            assert record._config == self.parent._config
        elif self:
            assert record._config == self[0]._config
        assert record._parent is None
        assert not record._parent_field_name
        assert not record._parent_name
        record._parent = self.parent
        record._parent_field_name = self.parent_field_name
        record._parent_name = self.parent_name
        res = super(ModelList, self).append(record)
        self._changed()
        return res
    append.__doc__ = list.append.__doc__

    def extend(self, iterable):
        iterable = list(iterable)
        config = None
        for record in iterable:
            assert isinstance(record, Model)
            if self.parent:
                assert record._config == self.parent._config
            elif self:
                assert record._config == self[0]._config
            elif config:
                assert record._config == config
            else:
                config = record._config
        for record in iterable:
            assert record._parent is None
            assert not record._parent_field_name
            assert not record._parent_name
            record._parent = self.parent
            record._parent_field_name = self.parent_field_name
            record._parent_name = self.parent_name
        res = super(ModelList, self).extend(iterable)
        self._changed()
        return res
    extend.__doc__ = list.extend.__doc__

    def insert(self, index, record):
        raise NotImplementedError
    insert.__doc__ = list.insert.__doc__

    def pop(self, index=-1):
        self.record_removed.add(self[index])
        self[index]._parent = None
        self[index]._parent_field_name = None
        self[index]._parent_name = None
        res = super(ModelList, self).pop(index)
        self._changed()
        return res
    pop.__doc__ = list.pop.__doc__

    def remove(self, record):
        self.record_deleted.add(record)
        record._parent = None
        record._parent_field_name = None
        record._parent_name = None
        res = super(ModelList, self).remove(record)
        self._changed()
        return res
    remove.__doc__ = list.remove.__doc__

    def reverse(self):
        raise NotImplementedError
    reverse.__doc__ = list.reverse.__doc__

    def sort(self):
        raise NotImplementedError
    sort.__doc__ = list.sort.__doc__


class Model(object):
    'Model class for Tryton records'

    __counter = -1
    _proxy = None
    _config = None
    _fields = None

    def __init__(self, id=None, **kwargs):
        super(Model, self).__init__()
        if id:
            assert not kwargs
        self.__id = id or Model.__counter
        if self.__id < 0:
            Model.__counter -= 1
        self._values = {} # store the values of fields
        self._changed = set() # store the changed fields
        self._parent = None # store the parent record
        self._parent_field_name = '' # store the field name in parent record
        self._parent_name = '' # store the field name to parent record
        if self.id < 0:
            self._default_get()

        for field_name, value in kwargs.iteritems():
            definition = self._fields[field_name]
            if definition['type'] in ('one2many', 'many2many'):
                relation = Model.get(definition['relation'])
                value = [isinstance(x, (int, long)) and relation(x) or x
                        for x in value]
                getattr(self, field_name).extend(value)
            else:
                if (definition['type'] == 'many2one'
                        and isinstance(value, (int, long))):
                    relation = Model.get(definition['relation'])
                    value = relation(value)
                setattr(self, field_name, value)
    __init__.__doc__ = object.__init__.__doc__

    @classmethod
    def get(cls, name, config=None):
        'Get a class for the named Model'
        class Spam(Model):
            __metaclass__ = MetaModelFactory(name, config=config)()
        return Spam

    @classmethod
    def reset(cls, config=None, *names):
        'Reset class definition for Models named'
        config = config or proteus.config.get_config()
        models_key = 'c%s' % id(config)
        if not names:
            setattr(_MODELS, models_key, {})
        else:
            models = getattr(_MODELS, models_key, {})
            for name in names:
                del models[name]

    def __str__(self):
        return '<%s(%d)>' % (self.__class__.__name__, self.id)
    __str__.__doc__ = object.__str__.__doc__

    def __repr__(self):
        if self._config == proteus.config.get_config():
            return "proteus.Model.get('%s')(%d)" % (self.__class__.__name__,
                    self.id)
        return "proteus.Model.get('%s', %s)(%d)" % (self.__class__.__name__,
                repr(self._config), self.id)
    __repr__.__doc__ = object.__repr__.__doc__

    def __cmp__(self, other):
        'Compare with other'
        if isinstance(other, Model):
            return cmp(self.id, other.id)
        if isinstance(other, (bool, NoneType)):
            return 1
        raise NotImplementedError

    @property
    def id(self):
        'The unique ID'
        return self.__id

    @classmethod
    def find(cls, condition=None, offset=0, limit=None, order=None):
        'Return records matching condition'
        if condition is None:
            condition = []
        ids = cls._proxy.search(condition, offset, limit, order,
                cls._config.context)
        return [cls(id) for id in ids]

    def reload(self):
        'Reload record'
        self._values = {}
        self._changed = set()

    def save(self):
        'Save the record'
        context = self._config.context
        if self.id < 0:
            values = self._get_values(fields=self._changed)
            self.__id = self._proxy.create(values, context)
        else:
            if not self._changed:
                return
            values = self._get_values(fields=self._changed)
            context['_timestamp'] = self._get_timestamp()
            self._proxy.write(self.id, values, context)
        self.reload()

    def delete(self):
        'Delete the record'
        if self.id > 0:
            context = self._config.context
            context['_timestamp'] = self._get_timestamp()
            return self._proxy.delete(self.id, context)
        self.reload()
        return True

    def _get_values(self, fields=None):
        'Return dictionary values'
        if fields is None:
            fields = self._values.keys()
        return dict((x, getattr(self, '__%s_value' % x)) for x in fields
                if x not in ('id', '_timestamp'))

    @property
    def _timestamp(self):
        'Get _timestamp'
        return self._values.get('_timestamp')

    def _get_timestamp(self):
        'Return dictionary with timestamps'
        result = {'%s,%s' % (self.__class__.__name__, self.id):
                self._timestamp}
        for field, definition in self._fields.iteritems():
            if field not in self._values:
                continue
            if definition['type'] in ('one2many', 'many2many'):
                for record in getattr(self, field):
                    result.update(record._get_timestamp())
        return result

    def _read(self, name):
        'Read field'
        fields = []
        if not self._values:
            fields = [x for x, y in self._fields.iteritems()
                    if y['type'] not in ('one2many', 'many2many', 'binary')]
            fields.append('_timestamp')
        fields.append(name)
        self._values.update(self._proxy.read(self.id, fields,
            self._config.context))

    def _default_get(self):
        'Set default values'
        fields = self._fields.keys()
        self._default_set(self._proxy.default_get(fields, False,
            self._config.context))

    def _default_set(self, values):
        for field, value in values.iteritems():
            definition = self._fields[field]
            if definition['type'] in ('one2many', 'many2many'):
                if value and len(value) and isinstance(value[0], (int, long)):
                    self._values[field] = value
                    continue
                relation = Model.get(definition['relation'], self._config)
                records = []
                for vals in (value or []):
                    record = relation()
                    record._default_set(vals)
                    records.append(record)
                self._values[field] = ModelList(records, self, field,
                        definition.get('relation_field', ''))
            else:
                self._values[field] = value

    def _get_eval(self):
        values = dict((x, getattr(self, '__%s_eval' % x))
                for x in self._fields if x != 'id')
        values['id'] = self.id
        return values

    def _on_change_args(self, args):
        res = {}
        values = self._get_eval()
        del values['id']
        for field, definition in self._fields.iteritems():
            if definition['type'] in ('one2many', 'many2many'):
                values[field] = [x._get_eval() for x in getattr(self, field)]
        if self._parent:
            values['_parent_%s' % self._parent_name] = \
                    _EvalEnvironment(self._parent)
        for arg in args:
            scope = values
            for i in arg.split('.'):
                if i not in scope:
                    scope = False
                    break
                scope = scope[i]
            res[arg] = scope
        return res

    def _on_change_set(self, field, value):
        if self._fields[field]['type'] in ('one2many', 'many2many'):
            if isinstance(value, (list, tuple)):
                self._values[field] = value
                self._changed.add(field)
                return
            to_remove = []
            if value and value.get('remove'):
                for record_id in value['remove']:
                    for record in getattr(self, field):
                        if record.id == record_id:
                            to_remove.append(record)
            for record in to_remove:
                # remove without signal
                list.remove(getattr(self, field), record)
            if value and value.get('add') or value.get('update'):
                for vals in value.get('add', []):
                    relation = Model.get(self._fields[field]['relation'],
                            self._config)
                    # append without signal
                    list.append(getattr(self, field), relation(**vals))
                for vals in value.get('update', []):
                    if 'id' not in vals:
                        continue
                    for record in getattr(self, field):
                        if record.id == vals['id']:
                            for i, j in vals.iteritems():
                                record._values[i] = j
                                record._changed.add(i)
        else:
            self._values[field] = value
            self._changed.add(field)

    def _on_change(self, name):
        'Call on_change for field'
        definition = self._fields[name]
        if definition.get('on_change'):
            if isinstance(definition['on_change'], basestring):
                definition['on_change'] = PYSONDecoder().decode(
                        definition['on_change'])
            args = self._on_change_args(definition['on_change'])
            context = self._config.context
            res = getattr(self._proxy, 'on_change_%s' % name)(args, context)
            later = {}
            for field, value in res.iteritems():
                if field not in self._fields:
                    continue
                if self._fields[field]['type'] in ('one2many', 'many2many'):
                    later[field] = value
                    continue
                self._on_change_set(field, value)
            for field, value in later.iteritems():
                self._on_change_set(field, value)
            if self._parent:
                self._parent._changed.add(self._parent_field_name)
        if definition.get('change_default'):
            context = self._config.context
            default = Model.get('ir.default', config=self._config)
            self._default_set(default.get_default(self.__class__.__name__,
                '%s=%s' % (name, self._get_values([name])[name]), context))
        for field, definition in self._fields.iteritems():
            if not definition.get('on_change_with'):
                continue
            if name not in definition['on_change_with']:
                continue
            if field == name:
                continue
            args = self._on_change_args(definition['on_change_with'])
            context = self._config.context
            res = getattr(self._proxy, 'on_change_with_%s' % field)(args,
                    context)
            self._on_change_set(field, res)


class Wizard(object):
    'Wizard class for Tryton wizards'

    def __init__(self, name, models=None, config=None, context=None):
        if models:
            assert len(set(type(x) for x in models)) == 1
        super(Wizard, self).__init__()
        self.name = name
        self.state = None
        self.states = ['init']
        self.form = None
        self._config = config or proteus.config.get_config()
        self._context = context or {}
        self._proxy = self._config.get_proxy(name, type='wizard')
        self.id = self._proxy.create(self._config.context)
        if models:
            self.datas = {
                    'model': models[0].__class__.__name__,
                    'id': models[0].id,
                    'ids': [model.id for model in models]
                    }
        else:
            self.datas = {}
        self.execute('init')

    def execute(self, state):
        assert state in self.states

        if 'form' not in self.datas:
            self.datas['form'] = {}

        if self.form:
            self.datas['form'].update(self.form._get_values())

        self.state = state
        while self.state != 'end':
            ctx = self._context.copy()
            ctx.update(self._config.context)
            ctx['active_id'] = self.datas.get('id')
            ctx['active_ids'] = self.datas.get('ids')

            res = self._proxy.execute(self.id, self.datas, self.state, ctx)
            if not res:
                break

            if 'datas' in res:
                self.datas['form'] = res['datas']
            elif res['type'] == 'form':
                self.datas['form'] = {}

            if res['type'] == 'form':
                self.states = [x[0] for x in res['state']]
                # XXX set context
                self.form = Model.get(res['object'])()
                self.form._default_set(self.datas['form'])
                return
            elif res['type'] == 'action':
                # TODO run action
                self.state = res['state']
            elif res['type'] == 'print':
                # TODO run print
                self.state = res['state']
            elif res['type'] == 'state':
                self.state = res['state']

        if self.state == 'end':
            self._proxy.delete(self.id, self._config.context)
