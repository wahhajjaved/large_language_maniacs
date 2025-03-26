import os
import json
import types
import logging
logger = logging.getLogger('peachy')
import re
from peachyprinter.domain.configuration_manager import ConfigurationManager
import peachyprinter.config as config
from peachyprinter.infrastructure.communicator import UsbPacketCommunicator
from peachyprinter.infrastructure.messages import IAmMessage

class ConfigurationBase(object):
    def get(self, source, key, default=None):
        if (key in source):
            value = source[key]
            if type(value) == types.UnicodeType:
                value = str(value)
            return value
        else:
            return default

    def toDict(self):
        d = {}
        for key, value in self.__dict__.items():
            if issubclass(value.__class__, ConfigurationBase):
                d[unicode(key)[1:]] = value.toDict()
            else:
                d[unicode(key)[1:]] = value
        return d


class CircutConfiguration(ConfigurationBase):
    def __init__(self, source={}):
        self._software_revision = self.get(source, u'software_revision', "N/A")
        self._hardware_revision = self.get(source, u'hardware_revision', "N/A")
        self._serial_number = self.get(source, u'serial_number', "N/A")
        self._data_rate = self.get(source, u'data_rate', 0)
        self._print_queue_length = self.get(source, u'print_queue_length', 500)
        self._calibration_queue_length = self.get(source, u'calibration_queue_length', 50)

    @property
    def software_revision(self):
        return self._software_revision

    @software_revision.setter
    def software_revision(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._software_revision = value
        else:
            raise ValueError("software_revision must be of type %s was %s" % (_type , type(value)))

    @property
    def hardware_revision(self):
        return self._hardware_revision

    @hardware_revision.setter
    def hardware_revision(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._hardware_revision = value
        else:
            raise ValueError("hardware_revision must be of type %s was %s" % (_type , type(value)))

    @property
    def serial_number(self):
        return self._serial_number

    @serial_number.setter
    def serial_number(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._serial_number = value
        else:
            raise ValueError("serial_number must be of type %s was %s" % (_type , type(value)))

    @property
    def data_rate(self):
        return self._data_rate

    @data_rate.setter
    def data_rate(self,value):
        _type = types.IntType
        if type(value) == _type:
            self._data_rate = value
        else:
            raise ValueError("data_rate must be of type %s was %s" % (_type , type(value)))

    @property
    def print_queue_length(self):
        return self._print_queue_length

    @print_queue_length.setter
    def print_queue_length(self,value):
        _type = types.IntType
        if type(value) == _type:
            self._print_queue_length = value
        else:
            raise ValueError("print_queue_length must be of type %s was %s" % (_type , type(value)))

    @property
    def calibration_queue_length(self):
        return self._calibration_queue_length

    @calibration_queue_length.setter
    def calibration_queue_length(self,value):
        _type = types.IntType
        if type(value) == _type:
            self._calibration_queue_length = value
        else:
            raise ValueError("calibration_queue_length must be of type %s was %s" % (_type , type(value)))


class CureRateConfiguration(ConfigurationBase):
    def __init__(self, source={}):
        self._base_height                   = self.get(source, u'base_height',                  3.0      )
        self._total_height                  = self.get(source, u'total_height',                 23.0     )
        self._start_speed                   = self.get(source, u'start_speed',                  50.0     )
        self._finish_speed                  = self.get(source, u'finish_speed',                 200.0    )
        self._draw_speed                    = self.get(source, u'draw_speed',                   100.0    )
        self._move_speed                    = self.get(source, u'move_speed',                   300.0    )
        self._use_draw_speed                = self.get(source, u'use_draw_speed',               True     )
        self._override_laser_power          = self.get(source, u'override_laser_power',         True     )
        self._override_laser_power_amount   = self.get(source, u'override_laser_power_amount',  0.05     )

    @property
    def override_laser_power(self):
        return self._override_laser_power

    @override_laser_power.setter
    def override_laser_power(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._override_laser_power = value
        else:
            raise ValueError("Use Override laser Power must be of %s was %s" % (_type, type(value)))

    @property
    def override_laser_power_amount(self):
        return self._override_laser_power_amount

    @override_laser_power_amount.setter
    def override_laser_power_amount(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._override_laser_power_amount = value
        else:
            raise ValueError("Laser Power must be of %s was %s" % (_type, type(value)))

    @property
    def base_height(self):
        return self._base_height

    @base_height.setter
    def base_height(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._base_height = value
        else:
            raise ValueError("Base Height must be of %s was %s" % (_type, type(value)))

    @property
    def total_height(self):
        return self._total_height

    @total_height.setter
    def total_height(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._total_height = value
        else:
            raise ValueError("Total Height must be of %s was %s" % (_type, type(value)))

    @property
    def start_speed(self):
        return self._start_speed

    @start_speed.setter
    def start_speed(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._start_speed = value
        else:
            raise ValueError("Start speed must be of %s was %s" % (_type, type(value)))

    @property
    def finish_speed(self):
        return self._finish_speed

    @finish_speed.setter
    def finish_speed(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._finish_speed = value
        else:
            raise ValueError("Finish Speed must be of %s was %s" % (_type, type(value)))

    @property
    def draw_speed(self):
        return self._draw_speed

    @draw_speed.setter
    def draw_speed(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._draw_speed = value
        else:
            raise ValueError("Draw Speed must be of %s was %s" % (_type, type(value)))

    @property
    def move_speed(self):
        return self._move_speed

    @move_speed.setter
    def move_speed(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._move_speed = value
        else:
            raise ValueError("Move Speed must be of %s was %s" % (_type, type(value)))

    @property
    def use_draw_speed(self):
        return self._use_draw_speed

    @use_draw_speed.setter
    def use_draw_speed(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._use_draw_speed = value
        else:
            raise ValueError("Use draw Speed must be of %s was %s" % (_type, type(value)))


class EmailConfiguration(ConfigurationBase):
    def __init__(self, source = {}):
        self._on = self.get(source, u'on', False)
        self._port = self.get(source, u'port', 25)
        self._host = self.get(source, u'host', 'some.smtp.server')
        self._sender = self.get(source, u'sender', 'senderemail@email.com')
        self._recipient = self.get(source, u'recipient', 'recipientemail@email.com')
        self._username = self.get(source, u'username', '')
        self._password = self.get(source, u'password', '')
        self._email_regex = r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}\b'

    def valid_email(self,potential_email):
        m = re.match(self._email_regex, potential_email,re.I)
        if m != None:
            return True
        return False

    @property
    def on(self):
        return self._on

    @on.setter
    def on(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._on = value
        else:
            raise ValueError("Bit depth must be of %s" % (str(_type)))

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        _type = types.IntType
        if type(value) == _type:
            self._port = value
        else:
            raise ValueError("Port must be of %s was %s" % (_type, type(value)))

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._username = value
        else:
            raise ValueError("Username must be %s" % (str(_type)))

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._password = value
        else:
            raise ValueError("Password must be %s" % (str(_type)))

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._host = value
        else:
            raise ValueError("Hostname must be %s" % (str(_type)))

    @property
    def sender(self):
        return self._sender

    @sender.setter
    def sender(self, value):
        _type = types.StringType
        if type(value) == _type and self.valid_email(value):
            self._sender = value
        else:
            raise ValueError("Sender must be %s" % (str(_type)))

    @property
    def recipient(self):
        return self._recipient

    @recipient.setter
    def recipient(self, value):
        _type = types.StringType
        if type(value) == _type and self.valid_email(value):
            self._recipient = value
        else:
            raise ValueError("Reciepient must be of %s" % (str(_type)))


class OptionsConfiguration(ConfigurationBase):
    def __init__(self, source={}):
        self._shuffle_layers_amount = self.get(source, u'shuffle_layers_amount', 1.0)
        self._post_fire_delay = self.get(source, u'post_fire_delay', 0)
        self._slew_delay = self.get(source, u'slew_delay', 15)
        self._sublayer_height_mm = self.get(source, u'sublayer_height_mm', 0.01)
        self._laser_thickness_mm = self.get(source, u'laser_thickness_mm', 0.5)
        self._scaling_factor = self.get(source, u'scaling_factor', 1.0)
        self._overlap_amount = self.get(source, u'overlap_amount', 1.0)
        self._use_shufflelayers = self.get(source, u'use_shufflelayers', False)

        self._use_sublayers = self.get(source, u'use_sublayers', False)
        self._use_overlap = self.get(source, u'use_overlap', True)
        self._print_queue_delay = self.get(source, u'print_queue_delay', 0.0)
        self._pre_layer_delay = self.get(source, u'pre_layer_delay',0.0)
        self._wait_after_move_milliseconds = self.get(source, u'wait_after_move_milliseconds', 20)
        self._write_wav_files = self.get(source, u'write_wav_files',False)
        self._write_wav_files_folder= self.get(source, u'write_wav_files_folder', 'tmp')


    @property
    def write_wav_files(self):
        return self._write_wav_files

    @write_wav_files.setter
    def write_wav_files(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._write_wav_files = value
        else:
            raise ValueError("Write Wav Files must be of %s" % (str(_type)))

    @property
    def write_wav_files_folder(self):
        return self._write_wav_files_folder

    @write_wav_files_folder.setter
    def write_wav_files_folder(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._write_wav_files_folder = value
        else:
            raise ValueError("Write Wav Files Folder must be of %s" % (str(_type)))

    @property
    def post_fire_delay(self):
        return self._post_fire_delay

    @post_fire_delay.setter
    def post_fire_delay(self, value):
        _type = types.IntType
        if type(value) == _type:
            self._post_fire_delay = value
        else:
            raise ValueError("Post Fire Delay must be of %s" % (str(_type)))

    @property
    def slew_delay(self):
        return self._slew_delay

    @slew_delay.setter
    def slew_delay(self, value):
        _type = types.IntType
        if type(value) == _type:
            self._slew_delay = value
        else:
            raise ValueError("Slew Delay must be of %s" % (str(_type)))

    @property
    def shuffle_layers_amount(self):
        return self._shuffle_layers_amount

    @shuffle_layers_amount.setter
    def shuffle_layers_amount(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._shuffle_layers_amount = value
        else:
            raise ValueError("Shuffle Layers must be of %s" % (str(_type)))

    @property
    def wait_after_move_milliseconds(self):
        return self._wait_after_move_milliseconds

    @wait_after_move_milliseconds.setter
    def wait_after_move_milliseconds(self, value):
        _type = types.IntType
        if type(value) == _type:
            self._wait_after_move_milliseconds = value
        else:
            raise ValueError("Wait after move milliseconds must be of %s" % (str(_type)))

    @property
    def pre_layer_delay(self):
        return self._pre_layer_delay

    @pre_layer_delay.setter
    def pre_layer_delay(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._pre_layer_delay = value
        else:
            raise ValueError("Pre Layer Delay must be of %s" % (str(_type)))


    @property
    def draw_speed(self):
        return self._draw_speed

    @draw_speed.setter
    def draw_speed(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._draw_speed = value
        else:
            raise ValueError("Draw Speed must be of %s" % (str(_type)))

    @property
    def draw_speed(self):
        return self._draw_speed

    @draw_speed.setter
    def draw_speed(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._draw_speed = value
        else:
            raise ValueError("Draw Speed must be of %s" % (str(_type)))

    @property
    def sublayer_height_mm(self):
        return self._sublayer_height_mm

    @sublayer_height_mm.setter
    def sublayer_height_mm(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._sublayer_height_mm = value
        else:
            raise ValueError("Sublayer Height must be of %s" % (str(_type)))

    @property
    def laser_thickness_mm(self):
        return self._laser_thickness_mm

    @laser_thickness_mm.setter
    def laser_thickness_mm(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._laser_thickness_mm = value
        else:
            raise ValueError("Laser Thickness must be of %s" % (str(_type)))

    @property
    def scaling_factor(self):
        return self._scaling_factor

    @scaling_factor.setter
    def scaling_factor(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._scaling_factor = value
        else:
            raise ValueError("Scaling Factor must be of %s" % (str(_type)))

    @property
    def overlap_amount(self):
        return self._overlap_amount

    @overlap_amount.setter
    def overlap_amount(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._overlap_amount = value
        else:
            raise ValueError("overlap_amount must be of %s" % (str(_type)))


    @property
    def use_shufflelayers(self):
        return self._use_shufflelayers

    @use_shufflelayers.setter
    def use_shufflelayers(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._use_shufflelayers = value
        else:
            raise ValueError("Use use_shufflelayers must be of %s" % (str(_type)))


    @property
    def use_sublayers(self):
        return self._use_sublayers

    @use_sublayers.setter
    def use_sublayers(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._use_sublayers = value
        else:
            raise ValueError("use_sublayers must be of %s" % (str(_type)))


    @property
    def use_overlap(self):
        return self._use_overlap

    @use_overlap.setter
    def use_overlap(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._use_overlap = value
        else:
            raise ValueError("use_overlap must be of %s" % (str(_type)))


    @property
    def print_queue_delay(self):
        return self._print_queue_delay

    @print_queue_delay.setter
    def print_queue_delay(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._print_queue_delay = value
        else:
            raise ValueError("print_queue_delay must be of %s" % (str(_type)))


class DripperConfiguration(ConfigurationBase):
    def __init__(self, source = {}):
        self._max_lead_distance_mm = self.get(source, u'max_lead_distance_mm',1.0)
        self._drips_per_mm = self.get(source, u'drips_per_mm',100.0)
        self._dripper_type = self.get(source, u'dripper_type','audio') #TODO
        self._emulated_drips_per_second = self.get(source,u'emulated_drips_per_second',100.0)
        self._photo_zaxis_delay = self.get(source,u'photo_zaxis_delay',3.0)
    
    @property
    def photo_zaxis_delay(self):
        return self._photo_zaxis_delay
    
    @photo_zaxis_delay.setter
    def photo_zaxis_delay(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._photo_zaxis_delay = value
        else:
            raise ValueError("Photo ZAxis Delay must be of %s" % (str(_type)))

    @property
    def max_lead_distance_mm(self):
        return self._max_lead_distance_mm
    
    @max_lead_distance_mm.setter
    def max_lead_distance_mm(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._max_lead_distance_mm = value
        else:
            raise ValueError("Max Lead distance must be of %s" % (str(_type)))
    
    @property
    def dripper_type(self):
        return self._dripper_type
    
    @dripper_type.setter
    def dripper_type(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._dripper_type = value
        else:
            raise ValueError("Dripper Type must be of %s" % (str(_type)))
    
    @property
    def emulated_drips_per_second(self):
        return self._emulated_drips_per_second
    
    @emulated_drips_per_second.setter
    def emulated_drips_per_second(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._emulated_drips_per_second = value
        else:
            raise ValueError("Emulated Drips Per Second must be of %s" % (str(_type)))
    
    @property
    def drips_per_mm(self):
        return self._drips_per_mm
    
    @drips_per_mm.setter
    def drips_per_mm(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._drips_per_mm = value
        else:
            raise ValueError("Drips per mm must be of %s" % (str(_type)))


class CalibrationConfiguration(ConfigurationBase):
    def __init__(self, source = {}):
        self._max_deflection = self.get(source, u'max_deflection', 0.95)
        self._height = self.get(source, u'height',40.0)
        self._lower_points = [ ((l[0][0],l[0][1]), (l[1][0],l[1][1])) for l in source.get(u'lower_points', [[[0.0, 1.0],[-40.0, 40.0]],[[1.0, 0.0],[40.0, -40.0]],[[0.0, 0.0],[-40.0, -40.0]], [[1.0, 1.0],[40.0, 40.0]]]) ]
        self._upper_points = [ ((u[0][0],u[0][1]), (u[1][0],u[1][1])) for u in source.get(u'upper_points', [[[0.0, 1.0],[-30.0, 30.0]],[[1.0, 0.0],[30.0, -30.0]],[[0.0, 0.0],[-30.0, -30.0]], [[1.0, 1.0],[30.0, 30.0]]]) ]
        self._print_area_x = self.get(source, u'print_area_x', 80.0)
        self._print_area_y = self.get(source, u'print_area_y', 80.0)
        self._print_area_z = self.get(source, u'print_area_z', 80.0)
        self._flip_x_axis = self.get(source, u'flip_x_axis', False)
        self._flip_y_axis = self.get(source, u'flip_y_axis', False)
        self._swap_axis = self.get(source, u'swap_axis', False)


    @property
    def print_area_x(self):
        return self._print_area_x

    @print_area_x.setter
    def print_area_x(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._print_area_x = value
        else:
            raise ValueError("print_area_x must be of type %s" % str(_type))

    @property
    def print_area_y(self):
        return self._print_area_y

    @print_area_y.setter
    def print_area_y(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._print_area_y = value
        else:
            raise ValueError("print_area_y must be of type %s" % str(_type))

    @property
    def print_area_z(self):
        return self._print_area_z

    @print_area_z.setter
    def print_area_z(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._print_area_z = value
        else:
            raise ValueError("print_area_z must be of type %s" % str(_type))

    @property
    def flip_x_axis(self):
        return self._flip_x_axis

    @flip_x_axis.setter
    def flip_x_axis(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._flip_x_axis = value
        else:
            raise ValueError("flip_x_axis must be of type %s" % str(_type))

    @property
    def flip_y_axis(self):
        return self._flip_y_axis

    @flip_y_axis.setter
    def flip_y_axis(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._flip_y_axis = value
        else:
            raise ValueError("flip_y_axis must be of type %s" % str(_type))

    @property
    def swap_axis(self):
        return self._swap_axis

    @swap_axis.setter
    def swap_axis(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._swap_axis = value
        else:
            raise ValueError("swap_axis must be of type %s" % str(_type))

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._height = value
        else:
            raise ValueError("Height must be of %s" % (str(_type)))
    
    @property
    def lower_points(self):
        return dict(self._lower_points)

    @lower_points.setter
    def lower_points(self, value):
        _type = types.DictType
        if type(value) == _type:
            self._lower_points = [ (k,v) for k,v in value.items() ]
        else:
            raise ValueError("Data must be of %s" % (str(_type)))
    
    @property
    def upper_points(self):
        return dict(self._upper_points)

    @upper_points.setter
    def upper_points(self, value):
        _type = types.DictType
        if type(value) == _type:
            self._upper_points = [ (k,v) for k,v in value.items() ]
        else:
            raise ValueError("Data must be of %s" % (str(_type)))

    @property
    def max_deflection(self):
        return self._max_deflection

    @max_deflection.setter
    def max_deflection(self, value):
        _type = types.FloatType
        if type(value) == _type:
            self._max_deflection = value
        else:
            raise ValueError("Max Deflection must be of %s" % (str(_type)))


class SerialConfiguration(ConfigurationBase):
    def __init__(self, source = {}):
        self._on = self.get(source, u'on', False)
        self._port = self.get(source, u'port','COM2')
        self._on_command = self.get(source, u'on_command','7')
        self._off_command = self.get(source, u'off_command','8')
        self._layer_started = self.get(source, u'layer_started','S')
        self._layer_ended = self.get(source, u'layer_ended','E')
        self._print_ended = self.get(source, u'print_ended','Z')


    @property
    def on(self):
        return self._on

    @on.setter
    def on(self, value):
        _type = types.BooleanType
        if type(value) == _type:
            self._on = value
        else:
            raise ValueError("Bit depth must be of %s" % (str(_type)))

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._port = value
        else:
            raise ValueError("Port must be of %s was %s" % (_type, type(value)))

    @property
    def on_command(self):
        return self._on_command

    @on_command.setter
    def on_command(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._on_command = value
        else:
            raise ValueError("On command must be %s" % (str(_type)))

    @property
    def off_command(self):
        return self._off_command

    @off_command.setter
    def off_command(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._off_command = value
        else:
            raise ValueError("Off command must be %s" % (str(_type)))

    @property
    def layer_started(self):
        return self._layer_started

    @layer_started.setter
    def layer_started(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._layer_started = value
        else:
            raise ValueError("Layer started command must be of %s" % (str(_type)))

    @property
    def layer_ended(self):
        return self._layer_ended

    @layer_ended.setter
    def layer_ended(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._layer_ended = value
        else:
            raise ValueError("Layer ended command must be of %s" % (str(_type)))

    @property
    def print_ended(self):
        return self._print_ended

    @print_ended.setter
    def print_ended(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._print_ended = value
        else:
            raise ValueError("Print ended command must be of %s" % (str(_type)))


class Configuration(ConfigurationBase):
    def __init__(self, source = {}):
        self._name = self.get(source, u'name', 'Peachy Printer')
        self._serial = SerialConfiguration(source=source.get(u'serial', {}))
        self._calibration = CalibrationConfiguration(source=source.get(u'calibration', {}))
        self._dripper = DripperConfiguration(source=source.get(u'dripper', {}))
        self._options = OptionsConfiguration(source=source.get(u'options', {}))
        self._email = EmailConfiguration(source=source.get(u'email', {}))
        self._cure_rate = CureRateConfiguration(source=source.get(u'cure_rate', {}))
        self._circut = CircutConfiguration(source=source.get(u'circut', {}))

    def toJson(self):
        di = self.toDict()
        return json.dumps(di, sort_keys=True, indent=2)

    @property
    def serial(self):
        return self._serial

    @property
    def calibration(self):
        return self._calibration

    @property
    def dripper(self):
        return self._dripper

    @property
    def options(self):
        return self._options

    @property
    def email(self):
        return self._email

    @property
    def cure_rate(self):
        return self._cure_rate

    @property
    def circut(self):
        return self._circut

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        _type = types.StringType
        if type(value) == _type:
            self._name = value
        else:
            raise ValueError("Name must be of %s was %s" % (str(_type), type(value)))


#TODO: JT 2014-05-28 Find out where this really lives
class ConfigurationGenerator(object):
    def default_configuration(self):
        configuration = Configuration()

        configuration.name                                 = "Peachy Printer"

        configuration.options.sublayer_height_mm           = 0.01
        configuration.options.laser_thickness_mm           = 0.5
        configuration.options.scaling_factor               = 1.0
        configuration.options.overlap_amount               = 1.0
        configuration.options.use_shufflelayers            = False
        configuration.options.use_sublayers                = False
        configuration.options.use_overlap                  = True
        configuration.options.print_queue_delay            = 0.0
        configuration.options.pre_layer_delay              = 0.0

        configuration.dripper.drips_per_mm                 = 100.0
        configuration.dripper.max_lead_distance_mm         = 1.0
        configuration.dripper.dripper_type                 = 'microcontroller'
        configuration.dripper.emulated_drips_per_second    = 1.0
        configuration.dripper.photo_zaxis_delay            = 3.0

        configuration.calibration.max_deflection           = 0.95
        configuration.calibration.height                   = 40.0
        configuration.calibration.lower_points             = {(1.0, 1.0):( 40.0,  40.0), ( 1.0, 0.0):( 40.0, -40.0), (0.0, 0.0):( -40.0, -40.0), (0.0, 1.0):(-40.0, 40.0)}
        configuration.calibration.upper_points             = {(1.0, 1.0):( 30.0,  30.0), ( 1.0, 0.0):( 30.0, -30.0), (0.0, 0.0):( -30.0, -30.0), (0.0, 1.0):(-30.0, 30.0)}

        configuration.serial.on                            = False
        configuration.serial.port                          = "COM2"
        configuration.serial.on_command                    = "7"
        configuration.serial.off_command                   = "8"
        configuration.serial.layer_started                 = "S"
        configuration.serial.layer_ended                   = "E"
        configuration.serial.print_ended                   = "Z"

        configuration.email.on                             = False
        configuration.email.port                           = 25
        configuration.email.host                           = "some.smtp.server"
        configuration.email.sender                         = "senderemail@email.com"
        configuration.email.recipient                      = "recipientemail@email.com"

        configuration.cure_rate.base_height                = 3.0
        configuration.cure_rate.total_height               = 23.0
        configuration.cure_rate.start_speed                = 50.0
        configuration.cure_rate.finish_speed               = 200.0
        configuration.cure_rate.draw_speed                 = 100.0
        configuration.cure_rate.move_speed                 = 300.0
        configuration.cure_rate.use_draw_speed             = True

        configuration.circut.software_revision             = 'sw1'
        configuration.circut.hardware_revision             = 'hw1'
        configuration.circut.serial_number                 = 'sn1'
        configuration.circut.data_rate                     = 0
        configuration.circut.print_queue_length            = 500
        configuration.circut.calibration_queue_length      = 50

        return configuration