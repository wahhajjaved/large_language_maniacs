# -*- python -*-
#
#       OpenAlea.OALab: Multi-Paradigm GUI
#
#       Copyright 2014 INRIA - CIRAD - INRA
#
#       File author(s): Julien Coste <julien.coste@inria.fr>
#
#       File contributor(s):
#
#       Distributed under the Cecill-C License.
#       See accompanying file LICENSE.txt or copy at
#           http://www.cecill.info/licences/Licence_CeCILL-C_V1-en.html
#
#       OpenAlea WebSite : http://openalea.gforge.inria.fr
#
###############################################################################
import ast
import re
from openalea.core import logger


#########################################
## Function to define to parse r model
#########################################
def parse_docstring_r(code):
    """
    parse a string (not a docstring), get the docstring and return information on the model.

    :use: model, inputs, outputs = parse_docstring_r(multiline_string_to_parse)

    :param string: docstring to parse (string)
    :return: model, inputs, outputs
    """

    def parse_cmdline(comment):
        line =''
        if 'cmdline' in comment:
            line = comment.split('cmdline')[1]
            line = line.split('=')[1]
            line = line.split('\n')[0].strip()
        return line

    comment = get_docstring_r(code)
    inputs, outputs = parse_input_and_output(comment)
    if inputs:
        inputs = map(InputObj, inputs)
    if outputs:
        outputs = map(OutputObj, ouputs)

    cmdline = parse_cmdline(comment) 
    return 'Rfunction', inputs, outputs, cmdline


def get_docstring_r(code):
    """
    Get a docstring from a code text
    """
    comments = []
    for l in code.splitlines():
        l = l.strip()
        if l and l.startswith('#'):
            comments.append(l)
        elif l != '':
            break

    return '\n'.join(comments)


def parse_functions_r(docstring):
    """
    Parse a docstring with format:
        my_model(a:int=4, b)->r:int

    Unused.

    :return: model, inputs, outputs
    """

    # TODO
    #print '-> parse_functions_r', docstring
    return False, True, True, True

#########################################
## Safe ast parsing
#########################################

def ast_parse(string):
    try:
        M = ast.parse(string)
    except SyntaxError, e:
        logger.warning(str(e))
        logger.warning("Syntax error when parsing: " + string[:30] + "...")
        M = ast.parse("")
    return M


#########################################
## Detect inputs and outputs in docstring
#########################################
def parse_docstring(string):
    """
    parse a string (not a docstring), get the docstring and return information on the model.

    :use: model, inputs, outputs = parse_docstring(multiline_string_to_parse)

    :param string: docstring to parse (string)
    :return: model, inputs, outputs
    """
    d = get_docstring(string)
    model, inputs, outputs = parse_doc(d)
    return model, inputs, outputs


def get_docstring(string):
    """
    Get a docstring from a string
    """
    M = ast_parse(string)
    return ast.get_docstring(M)


def parse_doc(docstring):
    """
    Parse a docstring.

    :return: model, inputs, outputs
    """
    model, inputs, outputs = parse_function(docstring)

    inputs2, outputs2 = parse_input_and_output(docstring)

    # TODO: make a real beautifull merge
    if inputs2:
        inputs = inputs2
    if outputs2:
        outputs = outputs2

    ret_inputs = None
    ret_outputs = None
    if inputs:
        ret_inputs = [InputObj(inp) for inp in inputs]
    if outputs:
        ret_outputs = [OutputObj(outp) for outp in outputs]

    return model, ret_inputs, ret_outputs


def parse_function(docstring):
    """
    Parse a docstring with format:
        my_model(a:int=4, b)->r:int

    Unused.

    :return: model, inputs, outputs
    """
    inputs = None
    outputs = None
    model = None
    if hasattr(docstring, "splitlines"):
        for docline in docstring.splitlines():
            if ("->" in docline):
                outputs = docline.split("->")[-1].split(",")
                model = docline.split("->")[0].split("(")[0]
                inputs = docline.split("(")[-1].split(")")[0].split(",")
    return model, inputs, outputs


def parse_input_and_output(docstring):
    """
    Parse a docstring with format:
        inputs = input_name:input_type=input_default_value, ...
        outputs = output_name:output_type, ...

    :use:
        >>> '''
        >>> inputs = a:int=4, b
        >>> outputs = r:float
        >>> '''

    :return: inputs, outputs
    """
    inputs = []
    outputs = []
    if hasattr(docstring, "splitlines"):
        docsplit = docstring.splitlines()
        for line in docsplit:
            line = line.strip()
            if re.search('input\s*=', line):
                line = line.split('input')[1]
                line = line.split('=',1)[1].strip()
                inputs = line.split(',')
                inputs = [x.strip() for x in inputs]
            if re.search('output\s*=', line):
                line = line.split('output')[1]
                line = line.split('=',1)[1].strip()
                outputs = line.split(',')
                outputs = [x.strip() for x in outputs]


    return inputs, outputs


def parse_lpy(string):
    """
    Take a lpy string_file, parse it and return only the docstring of the file.

    :param string: string representation of lpy file
    :return: docstring of the file if exists (must be a multiline docstring!). If not found, return None.

    :use:
        >>> f = open(lpyfilename, "r")
        >>> lpystring = f.read()
        >>> f.close()
        >>>
        >>> docstring = parse_lpy(lpystring)
        >>>
        >>> from openalea.oalab.model.parse import parse_doc
        >>> if docstring is not None:
        >>>     model, inputs, outputs = parse_doc(docstring)
        >>>     print "model : ", model
        >>>     print "inputs : ", inputs
        >>>     print "outputs : ", outputs
    """
    # TODO: need a code review
    begin = None
    begintype = None
    doclines = string.splitlines()
    i = 0
    for docline in doclines:
        i += 1
        if docline == '"""':
            begin = i
            begintype = '"""'
            break
        elif docline == "'''":
            begin = 1
            begintype = "'''"
            break
        elif docline == '"""':
            begin = 2
            begintype = '"""'
            break
        elif docline == "'''":
            begin = 2
            begintype = "'''"
            break

    if begin is not None:
        end = begin - 1
        for docline in doclines[begin:]:
            end += 1
            if docline == begintype:
                docstrings = doclines[begin:end]
                return "\n".join(docstrings)
    return None


###########################
## Input and Output Objects
###########################
class InputObj(object):
    """
    Inputs object with:
        - an attribute *name*: name of the input obj (str) (mandatory)
        - an attribute *interface*: interface/type of the input obj (str) (optional)
        - an attribute *default*: default value of the input obj (str) (optional)

    :param string: string object with format "input_name:input_type=input_default_value" or "input_name=input_default_value" or "input_name:input_type" or "input_name"
    """
    def __init__(self, string=''):
        self.name = None
        self.interface = None
        self.default = None
        if "=" in string:
            if ":" in string:
                self.name = string.split(":")[0].strip()
                self.interface = string.split(":")[1].split("=")[0].strip()
                self.default = string.split("=")[-1].strip()
            else:
                self.name = string.split("=")[0].strip()
                self.default = string.split("=")[1].strip()
        elif ":" in string:
            self.name = string.split(":")[0].strip()
            self.interface = string.split(":")[1].strip()
        else:
            self.name = string.strip()

    def __repr__(self):
        return "InputObject. Name: " + str(self.name) + ". Interface: " + str(self.interface) + ". Default Value: " + str(self.default) + "."


class OutputObj(InputObj):
    """
    Outputs object is the same as InputObj with a custom __repr__
    """
    def __repr__(self):
        return "OutputObject. Name: " + str(self.name) + ". Interface: " + str(self.interface) + ". Default Value: " + str(self.default) + "."


################################
## Detect functions in docstring
################################
def parse_functions(codestring):
    """
    parse the code *codestring* and detect what are the functions defined inside (search *init*, *step*, *animate* and *run*)
    :return: has_init(), has_step(), has_animate(), has_run() (list of bool)
    """
    return has_init(codestring), has_step(codestring), has_animate(codestring), has_run(codestring)


def has_step(codestring):
    """
    :return: True if *docstring* define a function *"step"*
    """
    r = ast_parse(codestring)
    functions_list = [x.name for x in ast.walk(r) if isinstance(x, ast.FunctionDef)]
    if "step" in functions_list:
        return True
    else:
        return False


def has_animate(codestring):
    """
    :return: True if *docstring* define a function *"animate"*
    """
    r = ast_parse(codestring)
    functions_list = [x.name for x in ast.walk(r) if isinstance(x, ast.FunctionDef)]
    if "animate" in functions_list:
        return True
    else:
        return False


def has_init(codestring):
    """
    :return: True if *docstring* define a function *"init"*
    """
    r = ast_parse(codestring)
    functions_list = [x.name for x in ast.walk(r) if isinstance(x, ast.FunctionDef)]
    if "init" in functions_list:
        return True
    else:
        return False


def has_run(codestring):
    """
    :return: True if *docstring* define a function *"run"*
    """
    r = ast_parse(codestring)
    functions_list = [x.name for x in ast.walk(r) if isinstance(x, ast.FunctionDef)]
    if "run" in functions_list:
        return True
    else:
        return False
