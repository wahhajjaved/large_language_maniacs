import math
import copy
import sys

class Invariant:
    """
    This is the Invariant object. It will store the value, name, type, and trace of an invariant.
    """
    def __init__(self, name, stype, trace, val):
        """

        Initializes the Invariant object

        :param stype: The type of the invariant. Either 'Bool', 'Integer', or 'Real'.
        :param name: The name of the invariant.
        :param val: The value of the invariant. For bool it is 'undt', True, or False. For integer and real invariants,
        it is a dictionary containing 'Min' and 'Max'
        :param trace: This is a trace for the invariant. It is only used when an error has occurred and a new invariant
        object will be made to send back the original inputs to the frontend.
        """
        self.name = name
        self.type = stype
        self.trace = trace
        if self.type == 'Bool':
            if val == 'undt':
                self.value = 'undt'
            else:
                self.value = (str(val).lower() == 'True'.lower())
        elif self.type == 'Integer':
            valmin = 'undt' if val['Min'] == 'undt' else int(val['Min'])
            valmax = 'undt' if val['Max'] == 'undt' else int(val['Max'])
            self.value = {'Min': valmin, 'Max': valmax}
        else:
            valmin = 'undt' if val['Min'] == 'undt' else float(val['Min'])
            valmax = 'undt' if val['Max'] == 'undt' else float(val['Max'])
            self.value = {'Min': valmin, 'Max': valmax}

    def __str__(self):
        """
        This is used for printing the invariant. Mostly for debugging

        :return: a string with the name and the value of the invariant
        """
        return self.name + ': ' + str(self.value)

    def __getitem__(self, item):
        if item == 'Type':
            return self.type
        elif item == 'Name':
            return self.name
        elif item == 'Value':
            return self.value
        elif item == 'Trace':
            return self.trace
        else:
            return None

    def get_min(self):
        """
        Gets the minimum of a real or integer invariant.

        :return: the minimum value of an invariant
        """
        return self.value['Min']

    def get_max(self):
        """
        Gets the maximum of a real or integer invariant.

        :return: the maximum value of an invariant
        """
        return self.value['Max']

    def get_val(self):
        """
        Gets the value of an invariant. Used by boolean variables to get the True, False, or 'undt'.

        :return: the value of the invariant
        """
        return self.value

    def set_min(self, val, thm_id=-1):
        # print self.name, self.value, " ==> ", val, " : Theorem ", thm_id
        """
        Sets the minimum of an integer or real invariant. A minimum is only set if it is larger than the current minimum
        (unless the user input the minimum). This checks for conflicts: if a minimum is larger than the maximum, then
        a conflict has occurred.
        If the invariant is an integer invariant, then the ceiling function is applied.

        :param val: The value that the minimum will be set to.
        :param thm_id: The id of the theorem that has set the minimum. It is -1 if it is a user input. This is used for
        the trace
        :return: returns two boolean values: a, b. a is True if no error has occurred and False if an error has
        occurred. b is True if the minumum was changed and False if there was no change.
        """
        if self.type == 'Bool':
            # print('Error: You set min of a bool invariant')
            exit()
        
        # gets ceiling for integer invariants
        if self.type == 'Integer' and val != 'undt':
            if val < 0:
                return True, False
            if abs(val - round(val)) < 0.0001:
                val = int(round(val))
            else:
                val = int(val)
            
        # a change occurs
        if thm_id == -1 and self.value['Min'] != val:
            trace_msg = 'The minimum of ' + self.name + ' from ' + str(self.value['Min']) + ' to ' + str(val)
            self.value['Min'] = val
        elif self.value['Min'] == 'undt':
            return True, False
        elif val == 'undt' or val > self.value['Min']:
            trace_msg = 'The minimum of ' + self.name + ' from ' + str(self.value['Min']) + ' to ' + str(val)
            self.value['Min'] = val
            if val == 'undt':
                trace_msg = 'The maximum of ' + self.name + ' from ' + str(self.value['Max']) + ' to ' + str(val)
                self.value['Max'] = val
        else:
            return True, False

        if self.value['Max'] == 'undt':
            self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
            return True, True
        # a conflict occurs
        elif self.value['Min'] == 'undt' or self.value['Min'] > self.value['Max']:
            # print('Error: You set the minimum larger than the maximum')
            trace_msg += '. Error: the minimum [' + str(self.value['Min']) + '] is greater than the maximum [' + str(self.value['Max']) + ']'
            self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
            return False, True
        else:
            self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
            return True, True

    def set_max(self, val, thm_id=-1):
        """
        Sets the maximum of an integer or real invariant. A maximum is only set if it is less than the current maximum
        (unless the user input the maximum). This checks for conflicts: if a maximum is less than the minimum, then
        a conflict has occurred.
        If the invariant is an integer invariant, then the floor function is applied.

        :param val: The value that the maximum will be set to.
        :param thm_id: The id of the theorem that has set the maximum. It is -1 if it is a user input. This is used for
        the trace.
        :return: returns two boolean values: a, b. a is True if no error has occurred and False if an error has
        occurred. b is True if the maximum was changed and False if there was no change.
        """
        if self.type == 'Bool':
            # print('Error: You set max to a bool invariant')
            exit()

        # gets floor for integer invariants
        if self.type == 'Integer' and val != 'undt':
            if val < 0:
                return True, False
            if abs(val - round(val)) < 0.0001:
                val = int(round(val))
            else:
                val = int(val)+1
            
        # a change occurs

        if val == 'undt' and self.value['Max'] != 'undt':
            trace_msg = 'The maximum value should be undetermined but it is defined';
            self.trace.append({"Message": trace_msg, 'TheoremId': thm_id})
            return False, False
        elif val == 'undt' and self.value['Max'] == 'undt':
            return True, False
        
        if thm_id == -1 and self.value['Max'] != val:
            trace_msg = 'The maximum of ' + self.name + ' from ' + str(self.value['Max']) + ' to ' + str(val)
            self.value['Max'] = val
        elif thm_id == -1 and self.value['Max'] == val:
            return True, False
        elif self.value['Max'] == 'undt' or val < self.value['Max']:
            trace_msg = 'The maximum of ' + self.name + ' from ' + str(self.value['Max']) + ' to ' + str(val)
            self.value['Max'] = val
        else:
            return True, False

        # a conflict occurs
        if self.value['Min'] == 'undt' or self.value['Min'] > self.value['Max']:
            # print('Error: You set the maximum less than the minimum')
            trace_msg += '. Error: the maximum [' + str(self.value['Max']) + '] is less than the minimum [' + str(self.value['Min']) + ']'
            self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
            return False, True
        else:
            self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
            return True, True

    def set_bool(self, val, thm_id=-1):
        """
        Sets the truth value of a boolean invariant. This checks for conflicts: if the truth value changes from True to
        False or False to True, then a conflict occurs.

        :param val: the boolean value that it will be changed to: True or False
        :param thm_id: The id of the theorem that has set the value. It is -1 if it is a user input. This is used for
        the trace
        :return: returns two boolean values: a, b. a is True if no error has occurred and False if an error has
        occurred. b is True if the minumum was changed and False if there was no change.
        """
        if self.type != 'Bool':
            # print('Error: You setting a bool invariant to a number')
            exit()

        # change occurs
        if val != self.value:
            if thm_id == -1 or self.value == 'undt':
                trace_msg = self.name + ' has been set to ' + str(val)
                self.value = val
                self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
                return True, True
            else:
                # print('Error: You set a boolean invariant from' + str(self.value) + ' to ' + str(val))
                trace_msg = 'Error: ' + self.name + ' was changed from ' + str(self.value) + ' to ' + str(val)
                self.trace.append({'Message': trace_msg, 'TheoremId': thm_id})
                self.value = val
                return False, True
        else:
            return True, False

    def check_conflict(self):
        if self.type == 'Bool':
            trace_msg = self.name + ' has been set to ' + str(self.value)
            self.trace.append({'Message': trace_msg, 'TheoremId': -1})
            return True
        else:
            # conflict occurred
            if self.value['Min'] == 'undt' and self.value['Max'] != 'undt':
                trace_msg = 'The minimum has been set to ' + str(self.value['Min']) + ', and the maximum to ' + str(self.value['Max'])
                trace_msg += '. Error: the minimum is undetermined and is the maximum defined.'
                self.trace.append({'Message': trace_msg, 'TheoremId': -1})
                return False
            elif self.value['Max'] != 'undt' and self.value['Min'] > self.value['Max']:
                trace_msg = 'The minimum has been set to ' + str(self.value['Min']) + ', and the maximum to ' + str(self.value['Max'])
                trace_msg += '. Error: the minimum [' + str(self.value['Min']) + '] is greater than the maximum [' + str(self.value['Max']) + ']'
                self.trace.append({'Message': trace_msg, 'TheoremId': -1})
                return False
            else:
                trace_msg = 'The minimum has been set to ' + str(self.value['Min']) + ', and the maximum to ' + str(self.value['Max'])
                self.trace.append({'Message': trace_msg, 'TheoremId': -1})
                return True
                

# The queue object which holds the string invariants
class Queue:
    """
    This is the Queue object. It will store the invariants that have been changed and will be used by the mainline.
    """
    def __init__(self):
        """
        Initializes the Queue object.
        """
        self.queue = []

    def __str__(self):
        """
        Creates a string representation of the queue

        :return: returns a string representation of the queue
        """
        return str(self.queue)

    def push(self, str_invar):
        """

        Pushes an invariant onto the queue.

        :param str_invar: The invariant name.
        :return: no return value
        """
        if str_invar not in self.queue:
            self.queue.append(str_invar)

    def pop(self):
        """

        Pops the invariant at the front of the queue.

        :return: returns the invariant at the front of the queue.
        """
        return self.queue.pop(0)

    def empty(self):
        """

        Checks if the queue is empty

        :return: returns if the queue is empty
        """
        return len(self.queue) == 0


class IngridObj:
    """
    This is the object which runs the INGRID mainline.
    """
    def __init__(self):
        """
        Initializes the invariants and queue for the mainline.
        """
        self.queue = Queue()
        self.invariants = {}
        self.attributes = {}
        self.error_inv = None
        self.error_msg = None
        self.theorems_used = [{'Id': -1, 'Text': 'User Input', 'Name': 'User Input'}]
        self.original_json = {}
        self.current_theorem = None

    def go(self, inv_dict, theorems=[]):
        """
        Runs the ingrid mainline.

        :param inv_dict: this is the invariant dictionary that is given from the json passed from the frontend.
        :param theorems: this is a list of theorems that will be called by the mainline. They should all be children of
        the Theorem class.
        :return: This returns nothing. It will terminate if an error occurs or if the mainline has finished running.
        """
            
        # saves the original invariants just in case of error
        self.original_json = copy.deepcopy(inv_dict)
        invars = copy.deepcopy(inv_dict['Invariants'])
        for key in sorted(list(invars.keys())):
            self.invariants[key] = Invariant(name=invars[key]['Name'], stype=invars[key]['Type'], trace=[], val=invars[key]['Value'])
            success = True
            if invars[key]['Changed'] == 'True':
                success = self.invariants[key].check_conflict()
                self.queue.push(key)
            
            if not success:
                self.error_inv = key
                self.error_msg = 'User input parameters caused an error'
                return
            
        # gives ingrid obj to the theorem object
        for thm in theorems:
            thm.set_ing_obj(self)
        
        # loops through the queue until it is empty
        while not self.queue.empty():
            str_inv = self.queue.pop()
            # calls all theorems involving the current invariant
            for theorem in theorems:
                if not theorem.involves(str_inv):
                    continue
                self.current_theorem = theorem
                try:
                    theorem.run()
                except:
                    self.error_inv = 'Runtime Error'
                    self.error_msg = 'Something blew up in theorem ' + str(theorem.id)
                    
                if self.error_inv is not None:
                    return
                    
                    
    def set(self, str_invar, val, ind='Bool'):
        """
        Sets a specified invariant to a specified value. Used by Theorem when setting invariants. If an error has
        occurred then this will just return and no operations will occur.

        :param str_invar: the name of the invariant.
        :param val: the value which will be set. For real or integer invariants, this is a number. For boolean
        invariants this is a boolean value.
        """
        if self.error_inv is not None:
            return
        if self.current_theorem is None:
            thm_id, thm_str, thm_name = -1, 'User Input', 'User Input'
        else:
            thm_id, thm_str, thm_name = self.current_theorem.id, self.current_theorem.str, self.current_theorem.name
        
        if ind == 'Bool':
            success, changed = self.invariants[str_invar].set_bool(val, thm_id)
        elif ind == 'Max':
            success, changed = self.invariants[str_invar].set_max(val, thm_id)
        else:
            success, changed = self.invariants[str_invar].set_min(val, thm_id)

        if changed:
            self.queue.push(str_invar)
            if {'Id': thm_id, 'Text': thm_str, 'Name': thm_name} not in self.theorems_used:
                self.theorems_used.append( {'Id': thm_id, 'Text': thm_str, 'Name': thm_name} )
        if not success:
            self.error_inv = str_invar
            self.error_msg = 'Error has occurred when setting an invariant.'
            return
        

    def get(self, str_invar, ind='Bool'):
        if ind == 'Max':
            return self.invariants[str_invar].get_max()
        elif ind == 'Min':
            return self.invariants[str_invar].get_min()
        else:
            return self.invariants[str_invar].get_val()

            
    def set_attr(self, str_attr, val):
        if self.error_inv is not None:
            return
    
        if not isinstance(val, basestring):
            self.error_inv = 'Attribute Error'
            self.error_msg = 'Error has occurred when checking an attribute - ask Kyle for more details.'
            return
    
        self.attributes[str_attr] = val
        
    
    def test_attr(self, str_attr, val):
        if str_attr not in self.attributes.keys():
            return False
    
        return self.attributes[str_attr] == val 
    
            
    def create_dict(self):
        """
        Creates a dictionary which will be converted to json for the frontend. This populates the 'Invariants',
        'Theorems', and 'Error' objects when appropriate.

        :return: returns the dictionary which will be converted to json
        """
        json_dict = {}
        # No error has occured
        if self.error_inv is None:
            json_dict['Invariants'] = {}
            for key in list(self.invariants.keys()):
                inv = self.invariants[key]
                json_dict['Invariants'][key] = {'Type': inv['Type'],
                                                'Value': inv['Value'],
                                                'Trace': inv['Trace'],
                                                'Changed': 'False',
                                                'Name': inv['Name']}
            json_dict['Theorems'] = self.theorems_used
            json_dict["Error"] = {"ErrorType": "", "ErrMsg": ""}
        else:
            json_dict['Invariants'] = {}
            for key in list(self.original_json['Invariants'].keys()):
                if key in list(self.invariants.keys()):
                    inv = self.invariants[key]
                else:
                    inv = self.original_json['Invariants'][key]
                
                json_dict['Invariants'][key] = {'Type': self.original_json['Invariants'][key]['Type'],
                                                'Value': self.original_json['Invariants'][key]['Value'],
                                                'Trace': inv['Trace'],
                                                'Changed': 'False',
                                                'Name': self.original_json['Invariants'][key]['Name']}
            json_dict['Theorems'] = self.theorems_used
            json_dict["Error"] = {"ErrorType": self.error_inv, "ErrMsg": self.error_msg}

        json_dict['Addenda'] = self.original_json['Addenda'] 
        return json_dict

class Theorem(object):
    """
    This is the Theorem class from which all theorems should inherit. It contains unimplemented methods which are used
    in the INGRID mainline.
    """
    def __init__(self, thm_id, string, name, ing_obj=None):
        """
        This will initialize the theorem id (self.id) to thm_id and the string that represents the theorem (self.str) to
        string.
        """
        self.id = thm_id
        self.str = string
        self.name = name
        self.ingrid_obj = ing_obj

    def involves(self, str_invar):
        """

        CHILD MUST IMPLEMENT: This checks if an invariant is used in the theorem.

        :param str_invar: The invariant name
        :return: returns True if this function uses this invariant
        """
        raise NotImplementedError

    def run(self):
        """

        CHILD MUST IMPLEMENT: This runs the given theorem.

        :param ingrid_obj: This is the ingid object (IngridObj)
        :return: returns False if a conflict occurred, True otherwise
        """
        raise NotImplementedError

    def congruent(self, str_invar, b, c):
        return self.maxb(str_invar) == self.minb(str_invar) and self.minb(str_invar) != 'undt' and (self.minb(str_invar) - b) % c == 0

    def oddInvar(self, str_invar):
        return self.maxb(str_invar) == self.minb(str_invar) and self.minb(str_invar) != 'undt' and self.minb(str_invar) % 2 == 1

    def evenInvar(self, str_invar):
        return self.maxb(str_invar) == self.minb(str_invar) and self.minb(str_invar) != 'undt' and self.minb(str_invar) % 2 == 0

    def set_ing_obj(self, ing_obj):
        self.ingrid_obj = ing_obj
        
    def set(self, str_invar, val, ind='Bool'):
        self.ingrid_obj.set(str_invar, val, ind)
        
    def maxb(self, str_invar):
        return self.ingrid_obj.get(str_invar, ind='Max')
        
    def minb(self, str_invar):
        return self.ingrid_obj.get(str_invar, ind='Min')
    
    def get(self, str_invar):
        return self.ingrid_obj.get(str_invar)

    def set_attr(self, str_attr, val):
        self.ingrid_obj.set_attr(str_attr, val)
        
    def test_attr(self, str_attr, val):
        return self.ingrid_obj.test_attr(str_attr, val)
