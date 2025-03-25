from abc import ABC, abstractmethod
from argparse import Action, ArgumentParser
from typing import Type, Union, Any, Iterable, Tuple, Dict, Set

from ...meta import non_default_kwargs
from ..util import is_flag_reason, is_short_flag, is_long_flag, flag_from_name
from .._ArgumentParserConfigurer import ArgumentParserConfigurer
from .._CLIRepresentable import CLIRepresentable
from .._typing import OptionsList


class Option(ArgumentParserConfigurer, ABC):
    """
    Descriptor class which sets an option on an option-handler.
    """
    def __init__(self,
                 *flags: str,
                 action: Union[str, Type[Action]] = ...,
                 nargs: Union[int, str] = ...,
                 const: Any = ...,
                 default: Any = ...,
                 choices: Iterable[Any] = ...,
                 required: bool = ...,
                 metavar: Union[str, Tuple[str, ...]] = ...,
                 help: str = ...):
        # Check the flags are supplied correctly
        self._check_flags(flags)

        self._name: str = ""
        self._flags: Tuple[str] = flags

        # Save any non-default arguments as kwargs
        self._kwargs: Dict[str, Any] = non_default_kwargs(Option.__init__, locals())

        # The representation of the keyword arguments to the option's __init__ method
        self._kwargs_repr: Dict[str, Any] = {}

    # =========== #
    # NAMES/FLAGS #
    # =========== #

    @property
    def name(self) -> str:
        """
        Gets the name of this option.

        :return: The option's name.
        """
        return self._name

    def _require_name(self, message: str):
        """
        Raises an exception with the provided message if the name
        for this option has not yet been set.

        :param message:     The message to raise.
        :raises NameError:  If the name has not been set yet.
        """
        if self._name == "":
            raise NameError(message)

    @property
    def flags(self) -> Tuple[str]:
        """
        Gets the flags that correspond to this option.

        :return:    The option string.
        """
        return self._flags

    def _require_flags(self, message: str):
        """
        Raises an exception with the provided message if the flags
        for this option has not yet been set.

        :param message:     The message to raise.
        :raises NameError:  If the flags have not been set yet.
        """
        if len(self._flags) == 0:
            raise NameError(message)

    @staticmethod
    def _check_flags(flags: Tuple[str]):
        """
        Makes sure the flags given to __init__ are correct.

        :param flags:   The flags as given to __init__.
        """
        # Get the number of flags given
        num_flags = len(flags)

        # If no flags are given, a long flag will be inferred from the attribute name
        if num_flags == 0:
            return

        # Can only have 2 flags at most (1 short and 1 long)
        if num_flags > 2:
            raise ValueError("Provided too many flags (can only have 2)")

        # Make sure the flags are strings
        for flag in flags:
            if not isinstance(flag, str):
                raise TypeError(f"Flags must be strings but got a {type(flag).__qualname__}")

        # Make sure the flags are in fact flags
        for flag in flags:
            flag_reason = is_flag_reason(flag)
            if flag_reason is not None:
                raise ValueError(f"'{flag}' is not a flag: {flag_reason}")

        # If two flags given, make sure one is short and one is long
        if num_flags == 2:
            if (
                    (is_short_flag(flags[0]) and is_short_flag(flags[1])) or
                    (is_long_flag(flags[0]) and is_long_flag(flags[1]))
            ):
                raise ValueError(f"If providing 2 flags, one must be a short flag and the other a long flag")

    def __set_name__(self, owner, name: str):
        # Only optional handlers can use options
        from .._OptionHandler import OptionHandler
        if not issubclass(owner, OptionHandler):
            raise TypeError(f"Class {owner.__name__} is not an OptionHandler")

        # Can't have private options
        if name.startswith("_"):
            raise ValueError(f"Option names can't start with underscores")

        # Can't reuse options (use a copy instead)
        if self._name != "":
            # If assigning the same name (e.g. in generic base class), just ignore
            if self._name == name:
                return

            raise NameError(f"Can't reuse options; use a copy instead")

        # If no flags were specified, create one from the name
        if len(self._flags) == 0:
            self._flags = (flag_from_name(name),)

        # Save our name
        self._name = name

        # Get our help text from the owner if we don't have it already
        if "help" not in self._kwargs:
            help = owner.get_help_text_for_option(self)
            if help is not None:
                self._kwargs["help"] = help

    # ============== #
    # REPRESENTATION #
    # ============== #

    def __repr__(self) -> str:
        # Get the representation of the kwargs to the __init__ method
        kwargs_repr = ', '.join(f"{key}={self._type_repr(value)}" for key, value in self._kwargs_repr.items())
        if kwargs_repr != "":
            kwargs_repr = ", " + kwargs_repr

        return f"{type(self).__qualname__}({self._flags_repr()}{kwargs_repr})"

    def get_repr_imports(self) -> Set[Type]:
        """
        Gets the types that require importing to fulfil the representation.
        """
        return {value
                for value in self._kwargs_repr.values()
                if isinstance(value, type) and issubclass(value, CLIRepresentable)}

    def _flags_repr(self) -> str:
        """
        Gets the representation of the flags to this option.

        :return:    The representation of the flags.
        """
        return ', '.join(repr(flag) for flag in self._flags)

    def _update_kwargs_repr(self, name: str, value: Any, condition: bool):
        """
        Updates the kwarg representation of this option if the condition is True.

        :param name:        The name of the keyword argument.
        :param value:       Its value.
        :param condition:   The condition under which to do the update.
        """
        if condition:
            self._kwargs_repr[name] = value

    def copy(self) -> 'Option':
        """
        Creates a copy of this option.

        :return:    The option copy.
        """
        return type(self)(*self._flags, **self._kwargs_repr)

    @staticmethod
    def _type_repr(value: Any) -> str:
        """
        Same a repr() but with a different implementation for types.

        :param value:   The value to represent.
        :return:        The representation.
        """
        if isinstance(value, type):
            return value.__name__

        return repr(value)

    # ====== #
    # VALUES #
    # ====== #

    def __get__(self, instance, owner):
        # If called on the class, return the option itself
        if instance is None:
            return self

        # Can't get the value until the option has been bound
        self._require_name("Can't get option value until it is bound")

        # If called on an instance, the instance must be an option-value handler
        from .._OptionValueHandler import OptionValueHandler
        if not isinstance(instance, OptionValueHandler):
            raise TypeError(f"Instance '{instance}' is not an option-value handler")

        # Get the option's value from the namespace
        namespace_value = getattr(instance.namespace, self.name)

        # Validate the namespace value
        self._validate_namespace_value(namespace_value)

        return self._namespace_value_to_internal_value(namespace_value)

    @abstractmethod
    def _namespace_value_to_internal_value(self, namespace_value: Any) -> Any:
        """
        Converts the namespace value for this option into its internal type.

        :param namespace_value:     The option's value from the namespace.
        :return:                    The option's internal value.
        :raises Exception:          If the namespace value is invalid.
        """
        pass

    def __set__(self, instance, value):
        # Must have a name set to access the namespace
        self._require_name("Can't set the value until the option is bound")

        # The instance must be an option-value handler
        from .._OptionValueHandler import OptionValueHandler
        if not isinstance(instance, OptionValueHandler):
            raise TypeError(f"Instance '{instance}' is not an option-value handler")

        # Make sure the value is valid
        self._validate_internal_value(value)

        # Convert to a namespace value
        namespace_value = self._internal_value_to_namespace_value(value)

        # Set the option's value
        setattr(instance.namespace, self.name, namespace_value)

    @abstractmethod
    def _validate_internal_value(self, internal_value: Any):
        """
        Checks that the internal value is valid.

        :param internal_value:  The value to check.
        """
        pass

    @abstractmethod
    def _internal_value_to_namespace_value(self, internal_value: Any) -> Any:
        """
        Converts an internal value for this option into a namespace
        value.

        :param internal_value:  The value attempting to be set.
        :return:                The actual value that should be set.
        :raises Exception:      If the value cannot be validated.
        """
        pass

    def get_as_options_list(self, instance) -> OptionsList:
        """
        Gets the value of this option as an options list.

        :param instance:    The option value handler to get the value from.
        :return:            The options-list representation.
        """
        # Make sure we have flags to use
        self._require_name("Can't get option value as option list before the option has been bound")

        # The instance must be an option-value handler
        from .._OptionValueHandler import OptionValueHandler
        if not isinstance(instance, OptionValueHandler):
            raise TypeError(f"Instance '{instance}' is not an option-value handler")

        # Get the namespace value of the option
        namespace_value = getattr(instance.namespace, self.name)

        # Validate the namespace value
        self._validate_namespace_value(namespace_value)

        # Let the sub-type format the options-list from the value
        return self._namespace_value_to_options_list(namespace_value)

    @abstractmethod
    def _validate_namespace_value(self, namespace_value: Any):
        """
        Checks the namespace value is valid.

        :param namespace_value: The namespace value to check.
        """
        pass

    @abstractmethod
    def _namespace_value_to_options_list(self, namespace_value: Any) -> OptionsList:
        """
        Converts the namespace value of this option into an options list.

        :param namespace_value:     The namespace value of the option.
        :return:                    The options-list representation of the value.
        """
        pass

    def set_from_options_list(self, instance, options_list: OptionsList):
        """
        Sets the value of this option from an options-list.

        :param instance:        The option value handler to set the value against.
        :param options_list:    The options-list value to set.
        """
        # Must have a name set to access the namespace
        self._require_name("Can't set the value via options-list until the option is bound")

        # The instance must be an option-value handler
        from .._OptionValueHandler import OptionValueHandler
        if not isinstance(instance, OptionValueHandler):
            raise TypeError(f"Instance '{instance}' is not an option-value handler")

        # Get a parser to parse the options list
        parser = self.get_configured_parser()

        # Parse the options list
        namespace = parser.parse_args(options_list)

        # Get the namespace value
        namespace_value = getattr(namespace, self.name)

        # Set it on the instance's namespace
        setattr(instance.namespace, self.name, namespace_value)

    # ===== #
    # OTHER #
    # ===== #

    def __eq__(self, other) -> bool:
        # Must be an option
        if not isinstance(other, Option):
            return False

        return self is other or self._kwargs == other._kwargs

    def configure_parser(self, parser: ArgumentParser):
        # Need a name to configure the parser's 'dest' argument
        self._require_name("Cannot configure a parser before the option is bound")

        parser.add_argument(*self._flags, dest=self._name, **self._kwargs)
