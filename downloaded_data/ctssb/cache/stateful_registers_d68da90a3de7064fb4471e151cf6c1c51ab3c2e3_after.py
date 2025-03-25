"""
Example stateful register representation of a BME280 environment sensor
"""

from stateful_registers import (RegisterValue, MultiRegisterValue,
                                SPIRegisterState, I2CRegisterState)


class BME280BaseRegisterState:
    def __init__(self, **kwargs):
        kwargs.setdefault('registers', self.BME280_REGISTERS)
        super().__init__(**kwargs)

    BME280_REGISTERS = [
        RegisterValue('hum_lsb', 0xFE, nbits=8, writeable=False),
        RegisterValue('hum_msb', 0xFD, nbits=8, writeable=False),
        RegisterValue('temp_xlsb', 0xFC, offset=4, nbits=4, writeable=False),
        RegisterValue('temp_lsb', 0xFB, nbits=8, writeable=False),
        RegisterValue('temp_msb', 0xFA, nbits=8, writeable=False),
        RegisterValue('press_xlsb', 0xF9, offset=4, nbits=4, writeable=False),
        RegisterValue('press_lsb', 0xF8, nbits=8, writeable=False),
        RegisterValue('press_msb', 0xF7, nbits=8, writeable=False),
        RegisterValue('spi3w_en', 0xF5, offset=0, nbits=1, writeable=True),
        RegisterValue('filter', 0xF5, offset=2, nbits=3, writeable=True),
        RegisterValue('t_sb', 0xF5, offset=5, nbits=3, writeable=True),
        RegisterValue('mode', 0xF4, offset=0, nbits=2, writeable=True),
        RegisterValue('osrs_p', 0xF4, offset=2, nbits=3, writeable=True),
        RegisterValue('osrs_t', 0xF4, offset=5, nbits=3, writeable=True),
        RegisterValue('measuring', 0xF3, offset=0, nbits=1, writeable=False),
        RegisterValue('im_update', 0xF3, offset=3, nbits=1, writeable=False),
        RegisterValue('osrs_h', 0xF2, offset=0, nbits=3, writeable=True),
        RegisterValue('reset', 0xE0, offset=0, nbits=8, writeable=True),
        RegisterValue('id', 0xD0, offset=0, nbits=8, writeable=False),
    ]
    BME280_REGISTERS += [
        MultiRegisterValue('hum', BME280_REGISTERS[:2]),
        MultiRegisterValue('temp', BME280_REGISTERS[2:5]),
        MultiRegisterValue('press', BME280_REGISTERS[5:8]),
    ]
    BME280_REGISTERS += [RegisterValue('calib{:02}'.format(i), 0x88 + i,
                                       nbits=8, writeable=False)
                         for i in range(26)]
    BME280_REGISTERS += [RegisterValue('calib{:02}'.format(i), 0xE1 + i - 26,
                                    nbits=8, writeable=False)
                         for i in range(26, 42)]


class BMESPIRegisterState(BME280BaseRegisterState, SPIRegisterState):
    def __init__(self, spi_bus, spi_device):
        kwargs = dict(spi_bus=spi_bus, spi_device=spi_device, write_bit=-7,
                      register_size=8, max_speed_hz=7800000)
        super().__init__(**kwargs)

class BMEI2CRegisterState(BME280BaseRegisterState, I2CRegisterState):
    def __init__(self, **kwargs):
        kwargs.setdefault('device_address', 0x77)
        super().__init__(**kwargs)
