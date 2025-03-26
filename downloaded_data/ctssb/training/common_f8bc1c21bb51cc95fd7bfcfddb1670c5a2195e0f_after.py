from ..fields import BaseField, DynamicField
from ..patterns import JsonSerializable
from ..plugins.basePlugin import BasePlugin


class BaseFact(BasePlugin, JsonSerializable):
    def __init__(self, **kwargs):
        self.setup()
        for key, value in kwargs.items():
            if key in self.__dict__:
                if isinstance(value, BaseField):
                    self.__dict__[key] = value
                else:
                    self.__dict__[key].value = value
            else:
                setattr(self, key, DynamicField(value=value))
        super().__init__()

    def __hash__(self):
        val = 0
        for key, value in self.get_fields().items():
            val += hash(key) + hash(value)
        if val == 0:
            return -1
        return val

    def __eq__(self, other):
        return hash(self) == hash(other) if isinstance(other, BaseFact) else False

    def setup(self):
        pass

    @property
    def plugin_category(self):
        return BaseFact.__name__

    def is_valid(self):
        for _, f in self.get_fields().items():
            if f.mandatory is True and (f.value is None or f.value is f.default):
                return False
        return True

    def get_fields(self, json=False):
        if not json:
            return {
                key: value
                for key, value in self.__dict__.items()
                if isinstance(value, BaseField)
            }
        return {
            key: value.to_json()
            for key, value in self.__dict__.items()
            if isinstance(value, BaseField)
        }

    def get_info(self):
        data = {"fields": self.get_fields(json=True)}
        return {**super().get_info(), **data}

    def to_json(self):
        obj_dict = {
            "__class__": self.__class__.__name__,
            "__module__": self.__module__,
            "fields": self.get_fields(json=True),
        }
        return obj_dict

    @staticmethod
    def from_json(json_dict):
        fields = {
            key: BaseField.from_json(value)
            for key, value in json_dict["fields"].items()
        }
        del json_dict["fields"]
        json_dict.update(fields)
        return super(BaseFact, BaseFact).from_json(json_dict)
