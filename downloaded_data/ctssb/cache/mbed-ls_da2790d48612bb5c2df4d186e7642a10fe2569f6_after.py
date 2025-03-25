"""
mbed SDK
Copyright (c) 2011-2015 ARM Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import re
import os
import json
from os import listdir
from os.path import isfile, join

class MbedLsToolsBase:
    """ Base class for mbed-lstools, defines mbed-ls tools interface for mbed-enabled devices detection for various hosts
    """
    def __init__(self):
        """ ctor
        """
        #extra flags
        self.DEBUG_FLAG = False     # Used to enable debug code / prints
        self.ERRORLEVEL_FLAG = 0    # Used to return success code to environment
        self.retarget_data = {}          # Used to retarget mbed-enabled platform properties

        # If there is a local mocking data use it and add / override manufacture_ids
        mock_ids = self.mock_read()
        if mock_ids:
            for mid in mock_ids:
                self.manufacture_ids[mid] = mock_ids[mid]

    # Which OSs are supported by this module
    # Note: more than one OS can be supported by mbed-lstools_* module
    os_supported = []

    # Dictionary describing mapping between manufacturers' ids and platform name.
    manufacture_ids = {
        "0001": "LPC2368",
        "0002": "LPC2368",
        "0003": "LPC2368",
        "0004": "LPC2368",
        "0005": "LPC2368",
        "0006": "LPC2368",
        "0007": "LPC2368",
        "0100": "LPC2368",
        "0183": "UBLOX_C027",
        "0200": "KL25Z",
        "0210": "KL05Z",
        "0220": "KL46Z",
        "0230": "K20D50M",
        "0231": "K22F",
        "0240": "K64F",
        "0245": "K64F",
        "0300": "MTS_GAMBIT",
        "0305": "MTS_MDOT_F405RG",
        "0310": "MTS_DRAGONFLY_F411RE",
        "0315": "MTS_MDOT_F411RE",
        "0400": "MAXWSNENV",
        "0405": "MAX32600MBED",
        "0500": "SPANSION_PLACEHOLDER",
        "0505": "SPANSION_PLACEHOLDER",
        "0510": "SPANSION_PLACEHOLDER",
        "0700": "NUCLEO_F103RB",
        "0705": "NUCLEO_F302R8",
        "0710": "NUCLEO_L152RE",
        "0715": "NUCLEO_L053R8",
        "0720": "NUCLEO_F401RE",
        "0725": "NUCLEO_F030R8",
        "0730": "NUCLEO_F072RB",
        "0735": "NUCLEO_F334R8",
        "0740": "NUCLEO_F411RE",
        "0745": "NUCLEO_F303RE",
        "0750": "NUCLEO_F091RC",
        "0755": "NUCLEO_F070RB",
        "0760": "NUCLEO_F073RZ",
        "0765": "ST_PLACEHOLDER",
        "0770": "ST_PLACEHOLDER",
        "0775": "ST_PLACEHOLDER",
        "0780": "ST_PLACEHOLDER",
        "0785": "ST_PLACEHOLDER",
        "0790": "ST_PLACEHOLDER",
        "0795": "DISCOVERY-F429ZI",
        "0799": "ST_PLACEHOLDER",
        "0805": "DISCO_L053C8",
        "0810": "DISCO_F334C8",
        "0815": "DISCO_F746NG",
        "0820": "DISCO_L476VG",
        "0824": "LPC824",
        "0900": "XPRO_SAMR21",
        "0905": "XPRO_SAMW25",
        "0910": "XPRO_SAML21",
        "0915": "XPRO_SAMD21",
        "1000": "LPC2368",
        "1001": "LPC2368",
        "1010": "LPC1768",
        "1017": "HRM1017",
        "1018": "SSCI824",
        "1034": "LPC11U34",
        "1040": "LPC11U24",
        "1045": "LPC11U24",
        "1050": "LPC812",
        "1060": "LPC4088",
        "1061": "LPC11U35_401",
        "1062": "LPC4088_DM",
        "1070": "NRF51822",
        "1075": "NRF51822_OTA",
        "1080": "OC_MBUINO",
        "1090": "RBLAB_NRF51822",
        "1095": "RBLAB_BLENANO",
        "1100": "NRF51_DK",
        "1105": "NRF51_DK_OTA",
        "1114": "LPC1114",
        "1120": "NRF51_DONGLE",
        "1130": "NRF51822_SBK",
        "1140": "WALLBOT_BLE",
        "1168": "LPC11U68",
        "1234": "UBLOX_C027",
        "1235": "UBLOX_C027",
        "1300": "NUC472-NUTINY",
        "1549": "LPC1549",
        "1600": "LPC4330_M4",
        "1605": "LPC4330_M4",
        "2000": "EFM32_G8XX_STK",
        "2005": "EFM32HG_STK3400",
        "2010": "EFM32WG_STK3800",
        "2015": "EFM32GG_STK3700",
        "2020": "EFM32LG_STK3600",
        "2025": "EFM32TG_STK3300",
        "2030": "EFM32ZG_STK3200",
        "2100": "XBED_LPC1768",
        "3001": "LPC11U24",
        "4000": "LPC11U35_Y5_MBUG",
        "4005": "NRF51822_Y5_MBUG",
        "4100": "MOTE_L152RC",
        "4337": "LPC4337",
        "4500": "DELTA_DFCM_NNN40",
        "5000": "ARM_MPS2",
        "5001": "ARM_MPS2_M0",
        "5003": "ARM_MPS2_M0P",
        "5005": "ARM_MPS2_M0DS",
        "5007": "ARM_MPS2_M1",
        "5009": "ARM_MPS2_M3",
        "5011": "ARM_MPS2_M4",
        "5015": "ARM_MPS2_M7",
        "5020": "HOME_GATEWAY_6LOWPAN",
        "5500": "RZ_A1H",
        "7778": "TEENSY3_1",
        "9001": "LPC1347",
        "9002": "LPC11U24",
        "9003": "LPC1347",
        "9004": "ARCH_PRO",
        "9006": "LPC11U24",
        "9007": "LPC11U35_501",
        "9008": "XADOW_M0",
        "9009": "ARCH_BLE",
        "9010": "ARCH_GPRS",
        "9011": "ARCH_MAX",
        "9012": "SEEED_TINY_BLE",
        "9900": "NRF51_MICROBIT",
        "FFFF": "K20 BOOTLOADER",
        "RIOT": "RIOT",
    }

    MOCK_FILE_NAME = '.mbedls-mock'
    RETARGET_FILE_NAME = 'mbedls.json'
    DETAILS_TXT_NAME = 'DETAILS.TXT'
    MBED_HTM_NAME = 'mbed.htm'

    def mock_read(self):
        """! Load mocking data from local file
        @return Curent mocking configuration (dictionary)
        """
        if isfile(self.MOCK_FILE_NAME):
            if self.DEBUG_FLAG:
                self.debug(self.mock_read.__name__, "reading mock file %s"% self.MOCK_FILE_NAME)
            try:
                with open(self.MOCK_FILE_NAME, "r") as f:
                    return json.load(f)
            except IOError as e:
                self.err("reading file '%s' failed: %s"% (os.path.abspath(self.MOCK_FILE_NAME),
                    str(e)))
            except ValueError as e:
                self.err("reading file '%s' content failed: %s"% (os.path.abspath(self.MOCK_FILE_NAME),
                    str(e)))
        return {}

    def mock_write(self, mock_ids):
        """! Write current mocking structure
        @param mock_ids JSON mock data to dump to file
        """
        if self.DEBUG_FLAG:
            self.debug(self.mock_write.__name__, "writing %s"% self.MOCK_FILE_NAME)
        try:
            with open(self.MOCK_FILE_NAME, "w") as f:
                f.write(json.dumps(mock_ids, indent=4))
        except IOError as e:
            self.err("reading file '%s' failed: %s"% (os.path.abspath(self.MOCK_FILE_NAME),
                str(e)))
        except ValueError as e:
            self.err("reading file '%s' content failed: %s"% (os.path.abspath(self.MOCK_FILE_NAME),
                str(e)))

    def retarget_read(self):
        """! Load retarget data from local file
        @return Curent retarget configuration (dictionary)
        """
        if os.path.isfile(self.RETARGET_FILE_NAME):
            if self.DEBUG_FLAG:
                self.debug(self.retarget_read.__name__, "reading retarget file %s"% self.RETARGET_FILE_NAME)
            try:
                with open(self.RETARGET_FILE_NAME, "r") as f:
                    return json.load(f)
            except IOError as e:
                self.err("reading file '%s' failed: %s"% (os.path.abspath(self.RETARGET_FILE_NAME),
                    str(e)))
            except ValueError as e:
                self.err("reading file '%s' content failed: %s"% (os.path.abspath(self.RETARGET_FILE_NAME),
                    str(e)))
        return {}

    def retarget(self):
        """! Enable retargeting
        """
        self.retarget_data = self.retarget_read()
        return self.retarget_data

    def mock_manufacture_ids(self, mid, platform_name, oper='+'):
        """! Replace (or add if manufacture id doesn't exist) entry in self.manufacture_ids
        @param oper '+' add new mock / override existing entry
                    '-' remove mid from mocking entry
        @return Mocked structure (json format)
        """
        mock_ids = self.mock_read()

        # Operations on mocked structure
        if oper == '+':
            mock_ids[mid] = platform_name
            if self.DEBUG_FLAG:
                self.debug(self.mock_manufacture_ids.__name__, "mock_ids['%s'] = '%s'"% (mid, platform_name))
        elif oper in ['-', '!']:
            if mid in mock_ids:
                mock_ids.pop(mid)
                if self.DEBUG_FLAG:
                    self.debug(self.mock_manufacture_ids.__name__, "removing '%s' mock"% mid)
            elif mid == '*':
                mock_ids = {}   # Zero mocking set
                if self.DEBUG_FLAG:
                    self.debug(self.mock_manufacture_ids.__name__, "zero mocking set")

        self.mock_write(mock_ids)
        return mock_ids

    # Note: 'Ven_SEGGER' - This is used to detect devices from EFM family, they use Segger J-LInk to wrap MSD and CDC
    usb_vendor_list = ['Ven_MBED', 'Ven_SEGGER']

    # Interface
    def list_mbeds(self):
        """! Get information about mbeds connected to device

        @return Returns None or if no error MBED_BOARDS = [ <MBED_BOARD>, ]

        @details MBED_BOARD
        {
            'mount_point' : <>,
            'serial_port' : <>,
            'target_id' : <>,
            'platform_name' : <>,
        }
        # If field unknown, place None
        """
        return None

    def list_mbeds_ext(self):
        """! Function adds extra information for each mbed device
        @return Returns list of mbed devices plus extended data like 'platform_name_unique'
        @details Get information about mbeds with extended parameters/info included
        """
        platform_names = {} # Count existing platforms and assign unique number

        mbeds = self.list_mbeds()
        for i, val in enumerate(mbeds):
            platform_name = val['platform_name']
            if platform_name not in platform_names:
                platform_names[platform_name] = 0
            else:
                platform_names[platform_name] += 1
            # Assign normalized, unique string at the end of target name: TARGET_NAME[x] where x is an ordinal integer
            mbeds[i]['platform_name_unique'] = "%s[%d]" % (platform_name, platform_names[platform_name])

            # Retarget values from retarget (mbedls.json) file
            if self.retarget_data and 'target_id' in val:
                target_id = val['target_id']
                if target_id in self.retarget_data:
                    mbeds[i].update(self.retarget_data[target_id])
                    if self.DEBUG_FLAG:
                        self.debug(self.list_mbeds_ext.__name__, ("retargeting", target_id, mbeds[i]))

            # Add meta data to mbed structure
            mbeds[i]['meta'] = {}

            details_txt = self.get_details_txt(val['mount_point'])
            if details_txt:
                mbeds[i]['meta']['DETAILS.TXT'] = details_txt
                mbeds[i]['fw_version'] = details_txt.get('Version', 'unknown')

            mbed_htm = self.get_mbed_htm(val['mount_point'])
            if mbed_htm:
                mbeds[i]['meta']['mbed.htm'] = mbed_htm
                if 'fw_version' not in mbeds[i]:
                    mbeds[i]['fw_version'] = mbed_htm.get('Version', 'unknown')

            if self.DEBUG_FLAG:
                self.debug(self.list_mbeds_ext.__name__, (mbeds[i]['platform_name_unique'], val['target_id']))
        return mbeds

    def list_platforms(self):
        """! Useful if you just want to know which platforms are currently available on the system
        @return List of (unique values) available platforms
        """
        result = []
        mbeds = self.list_mbeds()
        for i, val in enumerate(mbeds):
            platform_name = str(val['platform_name'])
            if platform_name not in result:
                result.append(platform_name)
        return result

    def list_platforms_ext(self):
        """! Useful if you just want to know how many platforms of each type are currently available on the system
        @return Dict of platform: platform_count
        """
        result = {}
        mbeds = self.list_mbeds()
        for i, val in enumerate(mbeds):
            platform_name = str(val['platform_name'])
            if platform_name not in result:
                result[platform_name] = 1
            else:
                result[platform_name] += 1
        return result

    def list_mbeds_by_targetid(self):
        """! Get information about mbeds with extended parameters/info included
        @return Returns dictionary where keys are TargetIDs and values are mbed structures
        @details Ordered by target id (key: target_id).
        """
        result = {}
        mbed_list = self.list_mbeds_ext()
        for mbed in mbed_list:
            target_id = mbed['target_id']
            result[target_id] = mbed
        return result

    # Private part, methods used to drive interface functions
    def load_mbed_description(self, file_name):
        """! Load JSON file with mbeds' description (mapping between target id and platform name)
            Sets self.manufacture_ids with mapping between manufacturers' ids and platform name.
        """
        #self.manufacture_ids = {}   # TODO: load this values from file
        pass

    def err(self, text):
        """! Prints error messages
        @param text Text to be included in error message
        @details Function prints directly on console
        """
        print 'error: %s'% text

    def debug(self, name, text):
        """! Prints error messages
        @param name Called function name
        @param text Text to be included in debug message
        @details Function prints directly on console
        """
        print 'debug @%s.%s: %s'% (self.__class__.__name__, name, text)

    def __str__(self):
        """! Object to string casting

        @return Stringified class object should be prettytable formated string
        """
        return self.get_string()

    def get_string(self, border=False, header=True, padding_width=0, sortby='platform_name'):
        """! Printing with some sql table like decorators
        @param border Table border visibility
        @param header Table header visibility
        @param padding_width Table padding
        @param sortby Column used to sort results
        @return Returns string which can be printed on console
        """
        from prettytable import PrettyTable
        from prettytable import PLAIN_COLUMNS
        result = ''
        mbeds = self.list_mbeds_ext()
        if mbeds:
            """ ['platform_name', 'mount_point', 'serial_port', 'target_id'] - columns generated from USB auto-detection
                ['platform_name_unique', ...] - columns generated outside detection subsystem (OS dependent detection)
            """
            columns = ['platform_name', 'platform_name_unique', 'mount_point', 'serial_port', 'target_id', 'fw_version']
            pt = PrettyTable(columns)
            pt.padding_width = 1
            for col in columns:
                pt.align[col] = 'l'

            for mbed in mbeds:
                row = []
                for col in columns:
                    row.append(mbed[col] if col in mbed and mbed[col] else 'unknown')
                pt.add_row(row)
            pt.set_style(PLAIN_COLUMNS)
            result = pt.get_string(border=border, header=header, padding_width=padding_width, sortby=sortby)
        return result

    # Private functions supporting API

    def get_json_data_from_file(self, json_spec_filename, verbose=False):
        """! Loads from file JSON formatted string to data structure
        @return None if JSON can be loaded
        """
        result = None
        try:
            with open(json_spec_filename) as data_file:
                try:
                    result = json.load(data_file)
                except ValueError as json_error_msg:
                    result = None
                    if verbose:
                        print "Error parsing file(%s): %s" % (json_spec_filename, json_error_msg)
        except IOError as fileopen_error_msg:
            if verbose:
                print "Warning: %s" % (fileopen_error_msg)
        return result

    def get_mbed_htm_target_id(self, mount_point):
        """! Function scans mbed.htm to get information about TargetID.
        @param mount_point mbed mount point (disk / drive letter)
        @return Function returns targetID, in case of failure returns None.
        @details Note: This function should be improved to scan variety of boards' mbed.htm files
        """
        result = None
        for line in self.get_mbed_htm_lines(mount_point):
            target_id = self.scan_html_line_for_target_id(line)
            if target_id:
                return target_id
        return result

    def get_mbed_htm(self, mount_point):
        """!
        <!-- mbed Microcontroller Website and Authentication Shortcut -->
        <!-- Version: 0200 Build: Mar 26 2014 13:22:20 -->
        <html>
        ...
        </html>
        """
        result = {}
        for line in self.get_mbed_htm_lines(mount_point):
            # Check for Version and Build date of interface chip firmware
            m = re.search(r'^<!-- Version: (\d+) Build: ([\d\w: ]+) -->', line)
            if m:
                version_str, build_str = m.groups()
                result['Version'] = version_str.strip()
                result['Build'] = build_str.strip()

            # Check for mbed URL
            m = re.search(r'url=([\w\d\:/\\\?\.=-_]+)', line)
            if m:
                result['url'] = m.group(1).strip()
        return result

    def get_mbed_htm_lines(self, mount_point):
        result = []
        for mount_point_file in [f for f in listdir(mount_point) if isfile(join(mount_point, f))]:
            if mount_point_file.lower() == self.MBED_HTM_NAME:
                mbed_htm_path = os.path.join(mount_point, mount_point_file)
                try:
                    with open(mbed_htm_path, 'r') as f:
                        result = f.readlines()
                except IOError:
                    if self.DEBUG_FLAG:
                        self.debug(self.get_mbed_htm_target_id.__name__, ('Failed to open file', mbed_htm_path))
        return result

    def get_details_txt(self, mount_point):
        """! Load DETAILS.TXT to dictionary:
            DETAILS.TXT example:
            Version: 0226
            Build:   Aug 24 2015 17:06:30
            Git Commit SHA: 27a236b9fe39c674a703c5c89655fbd26b8e27e1
            Git Local mods: Yes
        """
        result = {}
        path_to_details_txt = os.path.join(mount_point, self.DETAILS_TXT_NAME)
        if os.path.exists(path_to_details_txt):
            try:
                with open(path_to_details_txt, 'r') as f:
                    for line in f.readlines():
                        line_split = line.split(':')
                        if line_split:
                            idx = line.find(':')
                            result[line_split[0]] = line[idx+1:].strip()
            except IOError:
                if self.DEBUG_FLAG:
                    self.debug(self.get_mbed_fw_version.get_details_txt.__name__, ('Failed to open file', path_to_details_txt))
        return result if result else None

    def scan_html_line_for_target_id(self, line):
        """! Scan if given line contains target id encoded in URL.
        @return Returns None when no target_id string in line
        """
        # Detecting modern mbed.htm file format
        m = re.search('\?code=([a-fA-F0-9]+)', line)
        if m:
            result = m.groups()[0]
            if self.DEBUG_FLAG:
                self.debug(self.scan_html_line_for_target_id.__name__, line.strip())
            if self.DEBUG_FLAG:
                self.debug(self.scan_html_line_for_target_id.__name__, (m.groups(), result))
            return result
        # Last resort, we can try to see if old mbed.htm format is there
        else:
            m = re.search('\?auth=([a-fA-F0-9]+)', line)
            if m:
                result = m.groups()[0]
                if self.DEBUG_FLAG:
                    self.debug(self.scan_html_line_for_target_id.__name__, line.strip())
                if self.DEBUG_FLAG:
                    self.debug(self.scan_html_line_for_target_id.__name__, (m.groups(), result))
                return result
        return None
