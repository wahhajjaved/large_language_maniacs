from abc import abstractmethod, ABC
from weakref import WeakKeyDictionary

from .._OptionallyPresent import OptionallyPresent
from .._Absent import Absent
from ..._typing import RawJSONElement
from ...validator import JSONValidatorInstance


class Property(JSONValidatorInstance, ABC):
    """
    A property of a configuration is an instance value in the configuration
    object's keys. The value of a property is a raw JSON element, or something
    that can be converted to/from raw JSON. The property name can be set to the
    empty string to inherit the attribute name it is set against in the
    configuration.
    """
    def __init__(self,
                 name: str,
                 *,
                 optional: bool = False):
        self.__name: str = name
        self.__optional: bool = optional

        # The instance values of this property
        self.__values = WeakKeyDictionary()

    def name(self) -> str:
        """
        Gets the name of this property.

        :return:    The property name.
        """
        return self.__name

    def is_optional(self) -> bool:
        """
        Whether this property is an optional property.
        """
        return self.__optional

    def __get__(self, instance, owner):
        # If accessed from the class, return the property itself
        if instance is None:
            return self

        # Make sure a value has been set for this property
        if instance not in self.__values:
            raise AttributeError(f"{instance.__class__.__name__} has no value for property '{self.name()}'")

        # Get the value for this property
        return self.__values[instance]

    def __set__(self, instance, value):
        # Must be accessed via an instance
        self._require_instance(instance)

        # Validate the value
        self.validate_value(value)

        # Set the value in the instance dictionary
        self.__values[instance] = value

    @abstractmethod
    def get_as_raw_json(self, instance) -> OptionallyPresent[RawJSONElement]:
        """
        Gets the value of this property as raw JSON.

        :param instance:    The instance to get the value for.
        :return:            The raw JSON, or Absent.
        """
        pass

    @abstractmethod
    def set_from_raw_json(self, instance, value: OptionallyPresent[RawJSONElement]):
        """
        Sets the value of this property from raw JSON.

        :param instance:    The instance to set the value for.
        :param value:       The raw JSON value.
        """
        pass

    def __delete__(self, instance):
        raise AttributeError("Cannot delete configuration properties")

    def __set_name__(self, owner, name: str):
        # Can't have private properties
        if name.startswith("_"):
            raise AttributeError(f"Property names can't start with underscores ({name})")

        # Default the property name to the attribute name if one wasn't set
        if self.__name == "":
            self.__name = name

    @staticmethod
    def _require_instance(instance):
        """
        Raises an exception if instance is None.

        :param instance:    The instance.
        """
        # Make sure we are accessed via an instance
        if instance is None:
            raise AttributeError("Cannot access property through class (requires instance)")

    def validate_value(self, value):
        """
        Performs property value validation. Raises an AttributeError if validation fails.

        :param value:           The value to validate.
        """
        # Check for an absent value if allowed
        if not self.__optional and value is Absent:
            raise AttributeError(f"Cannot set non-optional property {self.name()} as absent")
