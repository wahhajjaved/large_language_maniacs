from .exceptions import OperationDeclarationException
from .memory import MEMORY, MemoryValue

TOKENS = {}


class Operation(type):

    def __init__(cls, name, bases, dct):
        if "TOKEN" in dct:
            if dct["TOKEN"] not in TOKENS:
                TOKENS[dct["TOKEN"]] = cls()
            else:
                raise OperationDeclarationException(f"Operation token {dct['TOKEN']} already in use")
        else:
            raise OperationDeclarationException("Operation must have TOKEN attribute")

        if "execute" not in dct:
            raise OperationDeclarationException("Operation must declare execute method")

        super().__init__(name, bases, dct)


class LoadOperation(metaclass=Operation):
    TOKEN = "LOAD"

    def execute(self, arguments):
        MEMORY.r.value = MEMORY.get_value_at_address(arguments[0]).value


class OutOperation(metaclass=Operation):
    TOKEN = "OUT"

    def execute(self, arguments):
        print(f"{arguments[0]} -> {MEMORY.get_value_at_address(arguments[0]).value}")


class CompareOperation(metaclass=Operation):
    TOKEN = "COMPARE"

    def execute(self, arguments):
        value1 = MEMORY.get_value_at_address(arguments[0]).value
        value2 = MEMORY.r.value
        MEMORY.gt.value = int(value1 > value2)
        MEMORY.lt.value = int(value1 < value2)
        MEMORY.eq.value = int(value1 == value2)


class StoreOperation(metaclass=Operation):
    TOKEN = "STORE"

    def execute(self, arguments):
        MEMORY.set_value(MEMORY.r.value, arguments[0])


class InitOperation(metaclass=Operation):
    TOKEN = "INIT"

    def execute(self, arguments):
        MEMORY.set_value(arguments[1], arguments[0])


class JumpOperation(metaclass=Operation):
    TOKEN = "JUMP"

    def execute(self, arguments):
        MEMORY.pc.value = arguments[0]


class AddOperation(metaclass=Operation):
    TOKEN = "ADD"

    def execute(self, arguments):
        if len(arguments) == 1:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.r.value += value
        elif len(arguments) == 2:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.get_value_at_address(arguments[1]).value += value
        elif len(arguments) == 3:
            value1 = MEMORY.get_value_at_address(arguments[0]).value
            value2 = MEMORY.get_value_at_address(arguments[1]).value
            MEMORY.set_value(value1 + value2, arguments[2])


class SubtractOperation(metaclass=Operation):
    TOKEN = "SUBTRACT"

    def execute(self, arguments):
        if len(arguments) == 1:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.r.value -= value
        elif len(arguments) == 2:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.get_value_at_address(arguments[1]).value -= value
        elif len(arguments) == 3:
            value1 = MEMORY.get_value_at_address(arguments[0]).value
            value2 = MEMORY.get_value_at_address(arguments[1]).value
            MEMORY.set_value(value1 - value2, arguments[2])


class MultiplyOperation(metaclass=Operation):
    TOKEN = "MULTIPLY"

    def execute(self, arguments):
        if len(arguments) == 1:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.r.value *= value
        elif len(arguments) == 2:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.get_value_at_address(arguments[1]).value *= value
        elif len(arguments) == 3:
            value1 = MEMORY.get_value_at_address(arguments[0]).value
            value2 = MEMORY.get_value_at_address(arguments[1]).value
            MEMORY.set_value(value1 * value2, arguments[2])


class DivideOperation(metaclass=Operation):
    TOKEN = "DIVIDE"

    def execute(self, arguments):
        if len(arguments) == 1:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.r.value /= value
        elif len(arguments) == 2:
            value = MEMORY.get_value_at_address(arguments[0]).value
            MEMORY.get_value_at_address(arguments[1]).value /= value
        elif len(arguments) == 3:
            value1 = MEMORY.get_value_at_address(arguments[0]).value
            value2 = MEMORY.get_value_at_address(arguments[1]).value
            MEMORY.set_value(value1 / value2, arguments[2])


class JumpGTOperation(metaclass=Operation):
    TOKEN = "JUMPGT"

    def execute(self, arguments):
        if MEMORY.gt.value == 1:
            MEMORY.pc.value = arguments[0]


class HaltOperation(metaclass=Operation):
    TOKEN = "HALT"

    def execute(self, arguments):
        MEMORY.pc.value = MEMORY.get_max_address() + 1


class ClearOperation(metaclass=Operation):
    TOKEN = "CLEAR"

    def execute(self, arguments):
        MEMORY.set_value(0, arguments[0])


class IncrementOperation(metaclass=Operation):
    TOKEN = "INCREMENT"

    def execute(self, arguments):
        MEMORY.set_value(MEMORY.get_value(arguments[0]) + 1, arguments[0])


class DecrementOperation(metaclass=Operation):
    TOKEN = "DECREMENT"

    def execute(self, arguments):
        MEMORY.set_value(MEMORY.get_value(arguments[0]) - 1, arguments[0])


class JumpLTOperation(metaclass=Operation):
    TOKEN = "JUMPLT"

    def execute(self, arguments):
        if MEMORY.lt.value == 1:
            MEMORY.pc.value = arguments[0]


class JumpEQOperation(metaclass=Operation):
    TOKEN = "JUMPEQ"

    def execute(self, arguments):
        if MEMORY.eq.value == 1:
            MEMORY.pc.value = arguments[0]


class JumpNEQOperation(metaclass=Operation):
    TOKEN = "JUMPNEQ"

    def execute(self, arguments):
        if MEMORY.eq.value == 0:
            MEMORY.pc.value = arguments[0]


class InOperation(metaclass=Operation):
    TOKEN = "IN"

    def execute(self, arguments):
        MEMORY.set_value(int(input("Value: ")), arguments[0])


class AnchorOperation(metaclass=Operation):
    TOKEN = "ANCHOR"

    def execute(self, arguments):
        # Handling of this operation occurs in the interpreter during the loading stage
        pass
