"""Garage controller object."""
from couchdb.mapping import TextField, BooleanField, DictField
from uuid import uuid4

from Hub.api import couch
from sys import modules

from Hub.v1.Common.base import HomityObject
from Hub.v1.Garage.Garage_Driver import GarageDriver
from Hub.v1.Garage.Garage_RestDuino_Driver import GarageRestDuinoDriver

GARAGE_CONTROLLER_DRIVERS = [
    "GarageRestDuinoDriver"
]

def _driver_name_to_class(driver_name):
    """
    Convert garage.driver string to driver's class.

    If not found, return generic GarageDriver()
    """
    if driver_name in GARAGE_CONTROLLER_DRIVERS:
        try:
            return reduce(getattr,
                          driver_name.split("."),
                          modules[__name__])()
        except AttributeError:
            return GarageDriver()
    return GarageDriver()

class GarageController(HomityObject):
    """
    Garage controller object.

        {
            "garage_id" : {
                "id" : <uuid of garage>
                "name" : <name of garage>
                "allocated" : <True if garage is being used>
                "num" : <GarageController identifier for garage>
                "open" : <True if garage is open>
                "on" : <True if garage is turned on>
                "location" : <name of parent garage controller>
                "controller" : <id of parent garage controller>
            }
        }
    """
    name = TextField()
    active = BooleanField()
    driver = TextField()
    driver_info = DictField()
    garages = DictField()

    def __init__(self, id=None, **values):
        HomityObject.__init__(self, id, **values)
        self.driver_class = _driver_name_to_class(self.driver)

    @classmethod
    def list(cls,dict_format=False):
        return cls._list(dict_format)

    @classmethod
    def get_for_garage_id(cls, garage_id):
        """Get the GarageController containing garage_id."""
        found, garage_controller = cls._find_in_list(garages=garage_id)
        if found:
            return garage_controller
        else:
            return None

    @classmethod
    def list_available_garages(cls):
        return cls._find_all_subobjects('garages', allocated=True)

    def delete(self):
        """Delete garage controller."""
        del self.class_db[self.id]

    def _add_garage(self, garage_num, garage):
        """Populate fields for new garage object."""
        garage_id = uuid4().hex
        self.garages[garage_id] = {'allocated' : False,
                                   'num' : garage_num,
                                   'id' : garage_id,
                                   'name' : "",
                                   'open' : garage.get('open'),
                                   'on' : garage.get('on'),
                                   'controller' : self.id,
                                   'location' : self.name}

    def refresh(self):
        """Update status for garages belonging to controller."""
        self.driver_class = _driver_name_to_class(self.driver)
        garage_status = self.driver_class.get_garages(self)
        if not garage_status:
            self.active = False
        else:
            self.active = True
            existing_garage_nums_to_ids = ({item.get('num'):item.get('id') for
                                            item in self.garages.values()})
            for garage_num, garage in garage_status.items():
                if garage_num in list(existing_garage_nums_to_ids):
                    garage_id = existing_garage_nums_to_ids.get(garage_num)
                    self.garages[garage_id]['open'] = garage.get('open')
                    self.garages[garage_id]['on'] = garage.get('on')
                    self.garages[garage_id]['location'] = self.name
                    self.garages[garage_id]['controller'] = self.id
                else:
                    self._add_garage(garage_num,
                                     garage)
        self.save()
