try:
    import json
except ImportError:
    import simplejson as json

import sys
import optparse
from copy import deepcopy

class InvalidFormat(ValueError): pass

# http://www.xormedia.com/recursively-merge-dictionaries-in-python/
def dict_recursive_merge(a, b):
    '''recursively merges dict's. not just simple a['key'] = b['key'], if
    both a and bhave a key who's value is a dict then dict_merge is called
    on both values and the result stored in the returned dictionary.'''
    if not isinstance(b, dict):
        return b
    result = deepcopy(a)
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = dict_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result

def get_cli():
    cli = optparse.OptionParser()
    return cli

class Parser(object):
    def parse(self, parts):
        document = {}
        for part in parts:
            document = dict_recursive_merge(document, self.parse_part(part))
        return document

    def split(self, part):
        return part.split('=', 1)

    def create_nested_hash(self, key, value):
        parts = key.split('.')
        document = {}
        current_level = document
        levels = len(parts)
        for index, part in enumerate(parts):
            if part not in current_level:
                if index != ( levels - 1 ):
                    current_level[part] = {}
                else:
                    current_level[part] = value
            current_level = current_level[part]
        return document

    def coerce(self, value):
        return str(value)

    def convert_value_part(self, part, coerce_types=True):
        # TODO allow escaped commas
        # TODO coerce data types
        if "," in part:
            result = part.split(",")
            if coerce_types:
                result = map(self.coerce, result)
        else:
            result = part
            if coerce_types:
                result = self.coerce(result)
        return result

    def parse_part(self, part):
        key, val = self.split(part)
        converted_val = self.convert_value_part(val) 
        return self.create_nested_hash(key, converted_val)

def serialize(obj):
    return json.dumps(obj)

def main(argv=None):
    cli = get_cli()
    opts, args = cli.parse_args(argv)

    parser = Parser()
    result = parser.parse(args) 
    sys.stdout.write(serialize(result) + "\n")

if __name__ == '__main__':
    main()
