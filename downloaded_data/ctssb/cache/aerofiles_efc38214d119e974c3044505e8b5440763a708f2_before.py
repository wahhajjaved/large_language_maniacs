from aerofiles.igc import patterns


class Writer:
    """
    A writer for the IGC flight log file format.

    see http://www.fai.org/gnss-recording-devices/igc-approved-flight-recorders
    or http://carrier.csi.cam.ac.uk/forsterlewis/soaring/igc_file_format/igc_format_2008.html
    """

    REQUIRED_HEADERS = [
        'manufacturer_code',
        'logger_id',
        'date',
        'logger_type',
        'gps_receiver',
    ]

    def __init__(self, fp=None):
        self.fp = fp

    def write_line(self, line):
        self.fp.write(line + '\r\n')

    def write_record(self, type, record):
        self.write_line(type + record)

    def write_logger_id(self, manufacturer, logger_id, extension=None,
                        validate=True):
        """
        Write the manufacturer and logger id header line::

            writer.write_logger_id('XXX', 'ABC', extension='FLIGHT:1')
            # -> AXXXABCFLIGHT:1

        Some older loggers have decimal logger ids which can be written like
        this::

            writer.write_logger_id('FIL', '13961', validate=False)
            # -> AFIL13961

        :param manufacturer: the three-letter-code of the manufacturer
        :param logger_id: the logger id as three-letter-code
        :param extension: anything else that should be appended to this header
            (e.g. ``FLIGHT:1``)
        :param validate: whether to validate the manufacturer and logger_id
            three-letter-codes
        """

        if validate:
            if not patterns.MANUFACTURER_CODE.match(manufacturer):
                raise ValueError('Invalid manufacturer code')
            if not patterns.LOGGER_ID.match(logger_id):
                raise ValueError('Invalid logger id')

        record = '%s%s' % (manufacturer, logger_id)
        if extension:
            record = record + extension

        self.write_record('A', record)

    def write_header(self, source, subtype, value,
                     subtype_long=None, value_long=None):
        if source not in ('F', 'O'):
            raise ValueError('Invalid source')

        if not subtype_long:
            record = '%s%s%s' % (source, subtype, value)
        elif not value_long:
            record = '%s%s%s:%s' % (source, subtype, subtype_long, value)
        else:
            record = '%s%s%s%s:%s' % \
                (source, subtype, value, subtype_long, value_long)

        self.write_record('H', record)

    def write_fr_header(self, subtype, value,
                        subtype_long=None, value_long=None):
        self.write_header(
            'F', subtype, value,
            subtype_long=subtype_long, value_long=value_long
        )

    def write_date(self, date):
        """
        Write the date header::

            writer.write_date(datetime.date(2014, 5, 2))
            # -> HFDTE140502

        :param date: a :class:`datetime.date` instance
        """

        self.write_fr_header('DTE', date.strftime('%y%m%d'))

    def write_fix_accuracy(self, accuracy=None):
        """
        Write the GPS fix accuracy header::

            writer.write_fix_accuracy()
            # -> HFFXA500

            writer.write_fix_accuracy(25)
            # -> HFFXA025

        :param accuracy: the estimated GPS fix accuracy in meters (optional)
        """

        if accuracy is None:
            accuracy = 500

        accuracy = int(accuracy)
        if not 0 < accuracy < 1000:
            raise ValueError('Invalid fix accuracy')

        self.write_fr_header('FXA', '%03d' % accuracy)

    def write_pilot(self, pilot):
        """
        Write the pilot declaration header::

            writer.write_pilot('Tobias Bieniek')
            # -> HFPLTPILOTINCHARGE:Tobias Bieniek

        :param pilot: name of the pilot
        """
        self.write_fr_header('PLT', pilot, subtype_long='PILOTINCHARGE')

    def write_copilot(self, copilot):
        """
        Write the copilot declaration header::

            writer.write_copilot('John Doe')
            # -> HFCM2CREW2:John Doe

        :param copilot: name of the copilot
        """
        self.write_fr_header('CM2', copilot, subtype_long='CREW2')

    def write_glider_type(self, glider_type):
        """
        Write the glider type declaration header::

            writer.write_glider_type('Hornet')
            # -> HFGTYGLIDERTYPE:Hornet

        :param glider_type: the glider type (e.g. ``Hornet``)
        """
        self.write_fr_header('GTY', glider_type, subtype_long='GLIDERTYPE')

    def write_glider_id(self, glider_id):
        """
        Write the glider id declaration header::

            writer.write_glider_id('D-4449')
            # -> HFGIDGLIDERID:D-4449

        The glider id is usually the official registration number of the
        airplane. For example:``D-4449`` or ``N116EL``.

        :param glider_id: the glider registration number
        """
        self.write_fr_header('GID', glider_id, subtype_long='GLIDERID')

    def write_gps_datum(self, code=None, gps_datum=None):
        """
        Write the mandatory GPS datum header::

            writer.write_gps_datum()
            # -> HFDTM100GPSDATUM:WGS-1984

            writer.write_gps_datum(33, 'Guam-1963')
            # -> HFDTM033GPSDATUM:Guam-1963

        Note that the default GPS datum is WGS-1984 and you should use that
        unless you have very good reasons against it.

        :param code: the GPS datum code as defined in the IGC file
            specification, section A8
        :param gps_datum: the GPS datum in written form
        """

        if code is None:
            code = 100

        if gps_datum is None:
            gps_datum = 'WGS-1984'

        self.write_fr_header(
            'DTM',
            '%03d' % code,
            subtype_long='GPSDATUM',
            value_long=gps_datum,
        )

    def write_firmware_version(self, firmware_version):
        """
        Write the firmware version header::

            writer.write_firmware_version('6.4')
            # -> HFRFWFIRMWAREVERSION:6.4

        :param firmware_version: the firmware version of the flight recorder
        """
        self.write_fr_header(
            'RFW', firmware_version, subtype_long='FIRMWAREVERSION')

    def write_hardware_version(self, hardware_version):
        """
        Write the hardware version header::

            writer.write_hardware_version('1.2')
            # -> HFRHWHARDWAREVERSION:1.2

        :param hardware_version: the hardware version of the flight recorder
        """
        self.write_fr_header(
            'RHW', hardware_version, subtype_long='HARDWAREVERSION')

    def write_logger_type(self, logger_type):
        """
        Write the extended logger type header::

            writer.write_logger_type('Flarm-IGC')
            # -> HFFTYFRTYPE:Flarm-IGC

        :param logger_type: the extended type information of the flight
            recorder
        """
        self.write_fr_header('FTY', logger_type, subtype_long='FRTYPE')

    def write_gps_receiver(self, gps_receiver):
        """
        Write the GPS receiver header::

            writer.write_gps_receiver('uBLOX LEA-4S-2,16,max9000m')
            # -> HFGPSuBLOX LEA-4S-2,16,max9000m

        :param gps_receiver: the GPS receiver information
        """
        self.write_fr_header('GPS', gps_receiver)

    def write_pressure_sensor(self, pressure_sensor):
        """
        Write the pressure sensor header::

            writer.write_pressure_sensor('Intersema MS5534B,8191')
            # -> HFPRSPRESSALTSENSOR:Intersema MS5534B,8191

        :param pressure_sensor: the pressure sensor information
        """
        self.write_fr_header(
            'PRS', pressure_sensor, subtype_long='PRESSALTSENSOR')

    def write_competition_id(self, competition_id):
        """
        Write the optional competition id declaration header::

            writer.write_competition_id('TH')
            # -> HFCIDCOMPETITIONID:TH

        :param competition_id: competition id of the glider
        """
        self.write_fr_header(
            'CID', competition_id, subtype_long='COMPETITIONID')

    def write_competition_class(self, competition_class):
        """
        Write the optional competition class declaration header::

            writer.write_competition_class('Club')
            # -> HFCCLCOMPETITIONCLASS:Club

        :param competition_class: competition class of the glider
        """
        self.write_fr_header(
            'CCL', competition_class, subtype_long='COMPETITIONCLASS')

    def write_club(self, club):
        """
        Write the optional club declaration header::

            writer.write_club('LV Aachen')
            # -> HFCLBCLUB:LV Aachen

        :param club: club or organisation for which this flight should be
            scored
        """
        self.write_fr_header('CLB', club, subtype_long='CLUB')

    def write_headers(self, headers):
        """
        Write all the necessary headers in the correct order::

            writer.write_headers({
                'manufacturer_code': 'XCS',
                'logger_id': 'TBX',
                'date': datetime.date(1987, 2, 24),
                'fix_accuracy': 50,
                'pilot': 'Tobias Bieniek',
                'copilot': 'John Doe',
                'glider_type': 'Duo Discus',
                'glider_id': 'D-KKHH',
                'firmware_version': '2.2',
                'hardware_version': '2',
                'logger_type': 'LXNAVIGATION,LX8000F',
                'gps_receiver': 'uBLOX LEA-4S-2,16,max9000m',
                'pressure_sensor': 'INTERSEMA,MS5534A,max10000m',
                'competition_id': '2H',
                'competition_class': 'Doubleseater',
            })

            # -> AXCSTBX
            # -> HFDTE870224
            # -> HFFXA050
            # -> HFPLTPILOTINCHARGE:Tobias Bieniek
            # -> HFCM2CREW2:John Doe
            # -> HFGTYGLIDERTYPE:Duo Discus
            # -> HFGIDGLIDERID:D-KKHH
            # -> HFDTM100GPSDATUM:WGS-1984
            # -> HFRFWFIRMWAREVERSION:2.2
            # -> HFRHWHARDWAREVERSION:2
            # -> HFFTYFRTYPE:LXNAVIGATION,LX8000F
            # -> HFGPSuBLOX LEA-4S-2,16,max9000m
            # -> HFPRSPRESSALTSENSOR:INTERSEMA,MS5534A,max10000m
            # -> HFCIDCOMPETITIONID:2H
            # -> HFCCLCOMPETITIONCLASS:Doubleseater

        This method will throw a :class:`ValueError` if a mandatory header is
        missing and will fill others up with empty strings if no value was
        given. The optional headers are only written if they are part of the
        specified :class:`dict`.

        .. admonition:: Note

            The use of this method is encouraged compared to calling all the
            other header-writing methods manually!

        :param headers: a :class:`dict` of all the headers that should be
        written.
        """

        for header in self.REQUIRED_HEADERS:
            if not header in headers:
                raise ValueError('%s header missing' % header)

        self.write_logger_id(
            headers['manufacturer_code'],
            headers['logger_id'],
            extension=headers.get('logger_id_extension')
        )

        self.write_date(headers['date'])
        self.write_fix_accuracy(headers.get('fix_accuracy'))

        self.write_pilot(headers.get('pilot', ''))
        if 'copilot' in headers:
            self.write_copilot(headers['copilot'])

        self.write_glider_type(headers.get('glider_type', ''))
        self.write_glider_id(headers.get('glider_id', ''))

        self.write_gps_datum(
            code=headers.get('gps_datum_code'),
            gps_datum=headers.get('gps_datum'),
        )

        self.write_firmware_version(headers.get('firmware_version', ''))
        self.write_hardware_version(headers.get('hardware_version', ''))
        self.write_logger_type(headers['logger_type'])
        self.write_gps_receiver(headers['gps_receiver'])
        self.write_pressure_sensor(headers.get('pressure_sensor', ''))

        if 'competition_id' in headers:
            self.write_competition_id(headers['competition_id'])

        if 'competition_class' in headers:
            self.write_competition_class(headers['competition_class'])

        if 'club' in headers:
            self.write_club(headers['club'])

    def write_extensions(self, type, start_byte, extensions):
        num_extensions = len(extensions)
        if num_extensions >= 100:
            raise ValueError('Invalid number of extensions')

        record = '%02d' % num_extensions
        for extension, length in extensions:
            if not patterns.EXTENSION_CODE.match(extension):
                raise ValueError('Invalid extension: %s' % extension)

            end_byte = start_byte + length - 1
            record += '%02d%02d%s' % (start_byte, end_byte, extension)

            start_byte = start_byte + length

        self.write_record(type, record)

    def write_fix_extensions(self, extensions):
        """
        Write the fix extensions description header::

            writer.write_fix_extensions([('FXA', 3), ('SIU', 2), ('ENL', 3)])
            # -> I033638FXA3940SIU4143ENL

        :param extensions: a list of ``(extension, length)`` tuples
        """
        self.write_extensions('I', 36, extensions)

    def write_k_record_extensions(self, extensions):
        """
        Write the K record extensions description header::

            writer.write_fix_extensions([('HDT', 5)])
            # -> J010812HDT

        :param extensions: a list of ``(extension, length)`` tuples
        """
        self.write_extensions('J', 8, extensions)
