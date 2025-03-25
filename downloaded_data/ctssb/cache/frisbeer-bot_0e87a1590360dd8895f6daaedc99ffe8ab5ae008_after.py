import datetime

import logging
from fuzzywuzzy import fuzz


class Cache:
    def __init__(self, key, data, case_insensitive=True):
        self.data_store = {}
        self.case_insensitive = case_insensitive
        for entity in data:
            key_val = entity[key]
            if case_insensitive:
                key_val = key_val.lower()
            self.data_store[key_val] = entity
        self.timestamp = datetime.datetime.now()

    def get(self, key):
        if self.case_insensitive:
            return self.data_store[key.lower()]
        return self.data_store[key]

    def fuzzy_get(self, key):
        try:
            return self.get(key)
        except KeyError:
            pass
        if self.case_insensitive:
            key_val = key.lower()
        else:
            key_val = key
        fuzzes = [(data_key, fuzz.partial_ratio(data_key, key_val)) for data_key in self.data_store.keys()]
        fuzzes = sorted(fuzzes, key=lambda key_ratio_pair: key_ratio_pair[1])
        logging.debug("Best match for {} was {} at level {}".format(key, fuzzes[-1][0], fuzzes[-1][1]))
        return self.data_store[fuzzes[-1][0]]

    def is_valid(self):
        if (datetime.datetime.now() - self.timestamp).total_seconds() > 30:
            logging.debug("Cache is too old")
            return False
        logging.debug("Cache ok")
        return True
