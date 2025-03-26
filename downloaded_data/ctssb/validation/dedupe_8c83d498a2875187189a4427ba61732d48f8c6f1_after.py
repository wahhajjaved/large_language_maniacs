import simplejson as json
from simplejson.scanner import py_make_scanner
import dedupe.core

def _from_json(json_object):                                   
    if '__class__' in json_object:                            
        if json_object['__class__'] == 'frozenset':
            return frozenset(json_object['__value__'])
        if json_object['__class__'] == 'tuple':
            return tuple(json_object['__value__'])
    return json_object

class dedupe_encoder(json.JSONEncoder):

    def default(self, python_object):
        if isinstance(python_object, frozenset):                                
            python_object = {'__class__': 'frozenset',
                    '__value__': list(python_object)}
        if isinstance(python_object, dedupe.core.frozendict) :
            python_object = dict(python_object)
        
        return python_object

    def encode(self, python_object):
        if isinstance(python_object, tuple) :
            python_object = {'__class__': 'tuple',
                    '__value__': list(python_object)}
        
        return json.JSONEncoder.encode(self, python_object)

class dedupe_decoder(json.JSONDecoder):

    def __init__(self, **kwargs):
        json._toggle_speedups(False) # in simplejson, without this
                                     # some strings can be bytestrings
                                     # instead of unicode
                                     # https://code.google.com/p/simplejson/issues/detail?id=40
        json.JSONDecoder.__init__(self, object_hook=_from_json, **kwargs)
        # Use the custom JSONArray
        self.parse_array = self.JSONArray
        # Use the python implemenation of the scanner
        self.scan_once = py_make_scanner(self) 

    def JSONArray(self, s_and_end, scan_once, **kwargs):
        values, end = json.decoder.JSONArray(s_and_end, scan_once, **kwargs)
        return tuple(values), end

