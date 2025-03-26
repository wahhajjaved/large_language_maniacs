
import os
import numpy
import scipy.interpolate
import pymeasure

dirname = os.path.dirname(__file__) 

class dewar_temp(object):
    ch = [1, 2, 3, 4, 5, 6]
    curve_file = os.path.join(dirname, 'temp_curve/model218.ch%d.csv')
    curve_name = ['DT-670', 'DT-670', 'DT-670', 'DT-670', 'DT-670', 'DT-670']
    curve_sn = ['D6032982', 'D6033864', 'D6033865', 'D6034038', 'D6034069',
                'D6034276']
    curve_format = [2, 2, 2, 2, 2, 2]
    input_types = [0, 0]
    
    _curve = []
    _s2k = []
    
    def __init__(self, initialize=False):
        com = pymeasure.gpib_prologix('192.168.40.33', 30)
        self.tm = pymeasure.Lakeshore.model218(com)
        
        if initialize:
            self.initialize_diode_type()
            self.initialize_temp_curves()
            pass
        pass
        
    def initialize_diode_type(self):
        self.tm.input_type_set('A', self.input_types[0])
        self.tm.input_type_set('B', self.input_types[1])
        return
            
    def initialize_temp_curves(self):
        for i,_c in enumerate(self.ch):
            print('set temp curve ch=%d'%_c)
            path = self.curve_file%(_c)
            temp, unit = numpy.loadtxt(path, delimiter=',', unpack=True)
            self.tm.curve_point_set_line(20+_c, unit, temp)
            self.tm.curve_header_set(20+_c, self.curve_name[i], self.curve_sn[i],
                                     self.curve_format[i], 300.0, 1)
            self.tm.input_curve_set(i, 20+i)
            
            self._curve.append([temp, unit])
            self._s2k.append(scipy.interpolate.interp1d(unit, temp,
                                                        bounds_error=False,
                                                        fill_value=0.0))
            continue
        return
        
    def temperature_query(self):
        """
        Check the temperature.
        
        NOTE: Lakeshore 218 has a sampling speed limit of 16 samples/sec.
        
        Args
        ====
        Nothing.
        
        Returns
        =======
        < data : list(float) :  >
            Return a list of K-value and Sensor-value.
            data[0] = a list of temperature in K.
            data[1] = a list of sensor value.
        
        Examples
        ========
        >>> tm.temperature_query()
        [[4.1, 4.2, 4.2, 4.1, 300, 300, 300, 300],
         [-1.1, -1.3, -1.2, -1.3, -0.1, -0.1, -0.1, -0.1]]
        """
        sens = self.tm.sensor_units_reading_query(0)
        sens = [sens[i-1] for i in self.ch]
        kel = [_s2k(_s) for _s2k, _s in zip(self._s2k, sens)]
        return kel, sens
        
    
