"""Spoke controller object."""
from couchdb.mapping import TextField, BooleanField, DictField
from uuid import uuid4

from Hub.v1.Common.helpers import update_crontab
from Hub.v1.Common.base import HomityObject

from Hub.api import couch
from sys import modules
from Hub.v1.Spoke.Spoke_Driver import SpokeDriver
from Hub.v1.Spoke.Spoke_RestDuino_Driver import SpokeRestDuinoDriver

SPOKE_DRIVERS = [
    "SpokeRestDuinoDriver"
]

def _driver_name_to_class(driver_name):
    """
    Convert spoke.driver string to driver's class

    If not found, return generic SpokeDriver()
    """
    if driver_name in SPOKE_DRIVERS:
        try:
            return reduce(getattr, driver_name.split("."), modules[__name__])()
        except AttributeError:
            return SpokeDriver()
    return SpokeDriver()

class Spoke(HomityObject):
    """
    Spoke controller object.
        {
        "pin_id" : {
            "id" : <uuid of pin>
            "name" : <name of pin>
            "allocated" : <True if pin is being used>
            "digital" : <True if pin status bool, False if int>
            "output" : <True if pin status is settable, False if readable>
            "num" : <Spoke's identifier for pin>
            "value" : <True|False if digital, integer if analog>
            "schedule" : [
                "action" : <True turning on>
                "minute" : <minute to perform action>
                "hour" : <hour to perform action>
                "days" : <[0,1,2], or [0-6], Sunday=0>
            ]
        }
        }"""
    name = TextField()
    active = BooleanField()
    driver = TextField()
    driver_info = DictField()
    pins = DictField()

    def __init__(self, id=None, **values):
        HomityObject.__init__(self, id, **values)
        self.driver_class = _driver_name_to_class(self.driver)

    @classmethod
    def list(cls,dict_format=False):
        return cls._list(dict_format)

    @classmethod
    def list_available_pins(cls):
        return cls._find_all_subobjects('pins', available=True)

    @classmethod
    def get_for_pin_id(cls, pin_id):
        """Get the spoke containing pin_id."""
        found, spoke = cls._find_in_list(pins=pin_id)
        if found:
            return spoke
        else:
            return None

    def delete(self):
        """Delete spoke."""
        self.clear_spoke_schedule()
        del self.class_db[self.id]

    def _add_pin(self, pin_num, pin):
        """Add new pin to object."""
        pin_id = uuid4().hex
        self.pins[pin_id] = {
            'allocated' : False,
            'num' : pin_num,
            'id' : pin_id,
            'name' : "",
            'schedule' : [],
            'digital' : pin.get('digital'),
            'output' : pin.get('output'),
            'spoke' : self.id,
            'location' : self.name
            }
        if pin.get('digital'):
            self.pins[pin_id]['status'] = pin.get('on')
        else:
            self.pins[pin_id]['status'] = pin.get('value')

    def refresh(self):
        """Update object according to what we get from driver."""
        self.driver_class = _driver_name_to_class(self.driver)
        pin_status = self.driver_class.get_pins(self)
        if not pin_status:
            self.active = False
        else:
            self.active = True
            existing_pin_nums_to_ids = ({item.get('num'):item.get('id') for
                                         item in self.pins.values()})
            for pin_num, pin in pin_status.items():
                if pin_num in list(existing_pin_nums_to_ids):
                    pin_id = existing_pin_nums_to_ids.get(pin_num)
                    self.pins[pin_id]['digital'] = pin.get('digital')
                    self.pins[pin_id]['output'] = pin.get('output')
                    self.pins[pin_id]['location'] = self.name
                    self.pins[pin_id]['spoke'] = self.id
                    if pin.get('digital'):
                        self.pins[pin_id]['status'] = pin.get('on')
                    else:
                        self.pins[pin_id]['status'] = pin.get('value')
                else:
                    self._add_pin(pin_num,
                                  pin)
        self.save()

    def update_pin_schedule(self, pin):
        """
        Update cron for pin schedule.

        Used only for digital output pins to turn on/off
        Driver_actions is a dict containing -
        {"True": <linux cmd to turn on>, "False": <linux cmd to turn off>}
        """
        driver_shell_commands = self.driver_class.get_shell_commands(
            self,
            pin['num'])

        def action_to_command(x):
            """Convert true/false action to shell cmd."""
            x['command'] = driver_shell_commands[str(x['action'])]
            return x
        map(action_to_command,
            pin['schedule'])
        if pin['digital'] and pin['output']:
            update_crontab("%s %s" % (pin['id'], self.id), pin['schedule'])

    def clear_spoke_schedule(self):
        """Clear all pin schedule entries."""
        update_crontab(self.id)
