from datetime import datetime
try:
    from calculator.operations import *
    from calculator.exceptions import *
except:
    from .calculator.operations import *
    from .calculator.exceptions import *


def create_new_calculator(operations=None):
    """
    Creates a configuration dict for a new calculator. Optionally pre loads an
    initial set of operations. By default a calculator with no operations
    is created.

    :param operations: Dict with initial operations.
                       ie: {'sum': sum_function, ...}
    """
    return {
        "operations":{} if not operations else operations,
        "history":[]
    }


def perform_operation(calc, operation, params):
    """
    Executes given operation with given params. It returns the result of the
    operation execution.

    :param calc: A calculator.
    :param operation: String with the operation name. ie: 'add'
    :param params: Tuple containing the list of nums to operate with.
                   ie: (1, 2, 3, 4.5, -2)
    """
    if operation not in calc["operations"]: #If the operation isn't supported, raise error
        raise InvalidOperation("{} operation not supported".format(operation))
        
    if not all( type(n) == int or type(n) == float for n in params ): #If any parameter isn't int or float, raise error
        raise InvalidParams("Given params are invalid.")
        
    if len(params) == 0: #If no parameters were passed, raise error
        raise InvalidParams("Given params are invalid.")
        
    calc['history'].append((datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        operation, params, calc["operations"][operation](*params)))

    return calc["operations"][operation](*params) #Otherwise execute the operation, with the passed parameters


def add_new_operation(calc, operation):
    """
    Adds given operation to the list of supported operations for given calculator.

    :param calc: A calculator.
    :param operation: Dict with the single operation to be added.
                      ie: {'add': add_function}
    """
    if type(operation) != dict:
        raise InvalidOperation('Given operation is invalid.')
    if list(operation.keys())[0] not in calc["operations"]:
        calc["operations"][operation.keys()[0]] = operation[operation.keys()[0]]


def get_operations(calc):
    """
    Returns the list of operation names supported by given calculator.
    """
    return calc["operations"].keys() #Return a list of keys, of the operations dictionary


def get_history(calc):
    """
    Returns the history of the executed operations since the last reset or
    since the calculator creation.

    History items must have the following format:
        (:execution_time, :operation_name, :params, :result)

        ie:
        ('2016-05-20 12:00:00', 'add', (1, 2), 3),
    """
    return calc['history']
    


def reset_history(calc):
    """
    Resets the calculator history back to an empty list.
    """
    calc['history'] = []


def repeat_last_operation(calc):
    """
    Returns the result of the last operation executed in the history.
    """
    return None if calc['history'] == [] else calc['history'][-1][-1]
