"""
get country code for weather underground
"""

try:
    from pkg_resources import resource_filename
except ImportError:
    def resource_filename(package_or_requirement, resource_name):
        return os.path.join(os.path.dirname(__file__), resource_name)

import json
import os
import pycountry
import weather_underground
from wunderground_exceptions import *


class Country_Code(object):
    def __init__(self,name = None):
        if name:
            self._name = name
        else:
            self._name = resource_filename('weather_underground', "mapping")

        print self._name
        self._mapping =json.load(open(self._name))

    @staticmethod            
    def get_country_iso_code(name):

        try:
            country = pycountry.countries.get(name=name)
        except KeyError:
            raise NoSuchCountryException(name)
        else:
            return country.alpha2


    def get_country_code(self,name):
        iso = self.get_country_iso_code(name.title())
        try:
            code = self._mapping[iso]
        except KeyError:
            raise NoSuchMappingException(name)
        else: 
            return code



