# Standard Modules
from collections import namedtuple, OrderedDict
import socket
import sys
import os
import os.path
import subprocess
import time
import threading


# XBMC Modules
import xbmcaddon
import xbmcgui
import xbmc

__addon__ = xbmcaddon.Addon('script.module.osmcsetting.networking')
DIALOG = xbmcgui.Dialog()


# Custom modules
sys.path.append(xbmc.translatePath(os.path.join(__addon__.getAddonInfo('path'), 'resources', 'lib')))

import osmc_bluetooth
import osmc_network

WIFI_THREAD_NAME = 'wifi_population_thread'
BLUETOOTH_THREAD_NAME = 'bluetooth_population_thread'


def log(message):
    xbmc.log(str(message), level=xbmc.LOGDEBUG)


def lang(id):
    san = __addon__.getLocalizedString(id).encode('utf-8', 'ignore')
    return san


gui_ids = { \
 \
    1000: 'Header Group list',
    101: 'Wired Network',
    102: 'Wireless Network',
    103: 'Bluetooth',
    10111: 'Wired - Manual/ DHCP toggle',
    10112: 'Wired - IP Address',
    910112: 'Wired - IP Address VALUE',
    10113: 'Wired - Subnet Mask',
    910113: 'Wired - Subnet Mask VALUE',
    10114: 'Wired - Default Gateway',
    910114: 'Wired - Default Gateway VALUE',
    10115: 'Wired - Primary DNS',
    910115: 'Wired - Primary DNS VALUE',
    10116: 'Wired - Secondary DNS',
    910116: 'Wired - Secondary DNS VALUE',
    10118: 'Wired - Apply',
    10119: 'Wired - Reset',
    10120: 'Wired - Enable Adapter',
    10121: 'Wired - Toggle wait for network service',
    10211: 'Wireless - Automatically configure the network toggle',
    10212: 'Wireless - IP Address',
    910212: 'Wireless - IP Address VALUE',
    10213: 'Wireless - Subnet Mask',
    910213: 'Wireless - Subnet Mask VALUE',
    10214: 'Wireless - Default Gateway',
    910214: 'Wireless - Default Gateway VALUE',
    10215: 'Wireless - Primary DNS',
    910215: 'Wireless - Primary DNS VALUE',
    10216: 'Wireless - Secondary DNS',
    910216: 'Wireless - Secondary DNS VALUE',
    10217: 'Wireless - Enable Adapter',
    10218: 'Wireless - Apply',
    10219: 'Wireless - Reset',
    10221: 'Wireless - Toggle wait for network service',
    10301: 'Bluetooth - Toggle Bluetooth Adapter',
    10303: 'Bluetooth - Toggle Discovery',
    10401:  'Tethering (wifi) - Hotspot SSID label',
    910401: 'Tethering (Wifi) - Hotspot SSID VALUE',
    10402:  'Tethering (Wifi) - Hotspot passphrase label',
    910402: 'Tethering (Wifi) - Hotspot passphrase VALUE',
    10403:  'Tethering (Wifi) - Enable Button',
    10404:  'Tethering (Wifi) - Disable Button',
    10405:  'Tethering (Ethernet) - Enable Button',
    10406:  'Tethering (Ethernet) - Disable Button',
    5000: 'WiFi panel',
    6000: 'Bluetooth paired devices panel',
    7000: 'Bluetooth discoverd devices panel'

}

ip_controls = [10112, 10113, 10114, 10115, 10116, 910112, 910113, 910114, 910115, 910116, 10212, 10213, 10214, 10215
    , 10216, 910212, 910213, 910214, 910215, 910216, ]

SELECTOR_WIRED_NETWORK = 101
SELECTOR_WIRELESS_NETWORK = 102
SELECTOR_BLUETOOTH = 103
SELECTOR_TETHERING = 104

MAIN_MENU = [SELECTOR_WIRED_NETWORK, SELECTOR_WIRELESS_NETWORK, SELECTOR_BLUETOOTH, SELECTOR_TETHERING]

BLUETOOTH_CONTROLS = [10303, 6000, 7000]

BLUETOOTH_DISCOVERY = 10303
BLUETOOTH_ENABLE_TOGGLE = 10301

ALL_WIRED_CONTROLS = [10111, 10112, 10113, 10114, 10115, 10116, 10118, 10119, 910112, 910113, 910114,
                      910115, 910116]
WIRED_STATUS_LABEL = 81000
WIRED_IP_VALUES = [910112, 910113, 910114, 910115, 910116]
WIRED_IP_LABELS = [10112, 10113, 10114, 10115, 10116]
WIRED_APPLY_BUTTON = 10118
WIRED_RESET_BUTTON = 10119
WIRED_DHCP_MANUAL_BUTTON = 10111
WIRED_IP_LABELS = [10112, 10113, 10114, 10115, 10116]
WIRED_ADAPTER_TOGGLE = 10120
WIRED_APPLY_BUTTON = 10118
WIRED_RESET_BUTTON = 10119
WIRED_DHCP_MANUAL_BUTTON = 10111
WIRED_WAIT_FOR_NETWORK = 10121

ALL_WIRELESS_CONTROLS = [5000, 910212, 910213, 910214, 910215, 910216, 10211, 10212, 10213, 10214, 10215, 10216,
                         10218, 10219]

WIRELESS_STATUS_LABEL = 82000
WIRELESS_IP_VALUES = [910212, 910213, 910214, 910215, 910216]
WIRELESS_IP_LABELS = [10212, 10213, 10214, 10215, 10216]
WIRELESS_ADAPTER_TOGGLE = 10217
WIRELESS_APPLY_BUTTON = 10218
WIRELESS_RESET_BUTTON = 10219
WIRELESS_DHCP_MANUAL_BUTTON = 10211
WIRELESS_NETWORKS = 5000
WIRELESS_WAIT_FOR_NETWORK = 10221

ALL_TETHERING_CONTROLS = [10401, 910401, 10402, 910402, 10403, 10404, 10405, 10406, 10407]
TETHERING_WIFI_SSID_LABEL = 10401
TETHERING_WIFI_SSID_VALUE = 910401
TETHERING_WIFI_PASSPHRASE_LABEL = 10402
TETHERING_WIFI_PASSPHRASE_VALUE = 910402
TETHERING_WIFI_RADIOBUTTON = 10403
TETHERING_ETHERNET_RADIOBUTTON = 10404
TETHERING_ENABLE = 10405
TETHERING_DISABLE = 10406
TETHERING_WARNING = 10407





class networking_gui(xbmcgui.WindowXMLDialog):
    current_network_config = {}  # holds the current network config

    reboot_required_file = '/tmp/.reboot-needed'

    use_preseed = False

    internet_protocol = 'IPV4'


    def setUsePreseed(self, value):
        self.use_preseed = value

    def __init__(self, strXMLname, strFallbackPath, strDefaultName, **kwargs):
        self.setting_values = kwargs.get('setting_values', {})

        # this stores the wifi password for sending to connman (or equivalent)
        self.wireless_password = None

        # current panel we are on
        self.current_panel = -1

        # Wired Network List (of one a way of showing connected icon )
        self.WDP = None

        # wifi panel (WFP)
        self.WFP = None

        # bluetooth paired device panel (BTP)
        self.BTP = None

        # bluetooth discovered device panel (BTD)
        self.BTD = None

        # list containing list items of all wifi networks
        self.wifis = []

        # connected SSID, the ssid we are currently connected to
        self.conn_ssid = None

        # list containing list items of all paired bluetooth devices
        self.paired_bluetooths = []

        # list containing list items of all discovered bluetooth devices
        self.discovered_bluetooths = []

        # Bluetooth GUI update Thread
        self.bluetooth_population_thread = None

        self.preseed_data = None

        self.wired_status_label = None

        self.wireless_status_label = None

        self.hotspot_ssid = None

        self.hotspot_passphrase = None

    def onInit(self):
        # Wired Network Label
        self.wired_status_label = self.getControl(WIRED_STATUS_LABEL);

        # wifi panel (WFP)
        self.WFP = self.getControl(5000)

        # Wireless Network Label
        self.wireless_status_label = self.getControl(WIRELESS_STATUS_LABEL);

        # bluetooth paired device panel (BTP)
        self.BTP = self.getControl(6000)

        # bluetooth discovered device panel (BTD)
        self.BTD = self.getControl(7000)

        # Hide panel selectors if devices are not present
        if not osmc_network.is_wifi_available():
            self.toggle_controls(False, [SELECTOR_WIRELESS_NETWORK])
            self.toggle_controls(False, [SELECTOR_TETHERING])

        if not osmc_bluetooth.is_bluetooth_available():
            self.toggle_controls(False, [SELECTOR_BLUETOOTH])

        panel_to_show = SELECTOR_WIRED_NETWORK
        if self.use_preseed and not osmc_network.get_nfs_ip_cmdline_value():
             self.preseed_data = osmc_network.parse_preseed()
             if self.preseed_data:
                 if self.preseed_data['Interface'].startswith('wlan') and osmc_network.is_wifi_available():
                     panel_to_show = SELECTOR_WIRELESS_NETWORK
                 else:
                     panel_to_show = SELECTOR_WIRED_NETWORK

        # set all the panels to invisible except the first one
        for ctl in MAIN_MENU:
            self.getControl(ctl * 10).setVisible(True if ctl == panel_to_show else False)
        if panel_to_show == SELECTOR_WIRED_NETWORK:
            self.populate_wired_panel()
        if panel_to_show == SELECTOR_WIRELESS_NETWORK:
            self.populate_wifi_panel(False)

        if self.use_preseed and not osmc_network.get_nfs_ip_cmdline_value():
            self.setup_networking_from_preseed()

    def setup_networking_from_preseed(self):
        wired = False
        connected = False

        if self.preseed_data['Interface'].startswith('wlan') and osmc_network.is_wifi_available():
            if not osmc_network.is_wifi_enabled():
                self.toggle_wifi()
            ssid = self.preseed_data['SSID']
            encrypted = False
            preseed_password = None
            if 'Password' in self.preseed_data:
                encrypted = True
                preseed_password = self.preseed_data['Password']

            connected = self.connect_to_wifi(ssid, encrypted, preseed_password, True)

        if self.preseed_data is None or self.preseed_data['Interface'].startswith('eth') or not connected:
            wired = True
            if not osmc_network.is_ethernet_enabled():
                self.toggle_ethernet()
            self.current_network_config = self.get_wired_config()
            connected = True

        if connected:
            if self.preseed_data is None or 'dhcp' in self.preseed_data['Method']:
                self.current_network_config['IPV4']['Method'] = 'dhcp'
            else:
                self.current_network_config['IPV4']['Method'] = 'manual'
                self.current_network_config['IPV4']['Address'] = self.preseed_data['Address']
                self.current_network_config['IPV4']['Netmask'] = self.preseed_data['Netmask']
                if self.preseed_data['Gateway']:
                    self.current_network_config['IPV4']['Gateway'] = self.preseed_data['Gateway']
                if self.preseed_data['DNS_1']:
                    self.current_network_config['IPV4']['DNS_1'] = self.preseed_data['DNS_1']
                if self.preseed_data['DNS_2']:
                    self.current_network_config['IPV4']['DNS_2'] = self.preseed_data['DNS_2']

            osmc_network.apply_network_changes(self.current_network_config, 'IPV4')

        if wired:
            self.populate_wired_panel()
        else:
            self.populate_wifi_panel(False)

    def onClick(self, controlID):
        if controlID in ip_controls:
            self.edit_ip_address(controlID)
        elif controlID in BLUETOOTH_CONTROLS + [BLUETOOTH_ENABLE_TOGGLE]:
            self.handle_bluetooth_selection(controlID)
            self.populate_bluetooth_panel()

        elif controlID in ALL_WIRED_CONTROLS + [WIRED_ADAPTER_TOGGLE]:
            self.handle_wired_selection(controlID)

        elif controlID in ALL_WIRELESS_CONTROLS + [WIRELESS_ADAPTER_TOGGLE]:
            self.handle_wireless_selection(controlID)

        elif controlID == WIRED_WAIT_FOR_NETWORK:
            osmc_network.toggle_wait_for_network(not osmc_network.is_connman_wait_for_network_enabled())
            waitForNetworkRadioButton = self.getControl(WIRED_WAIT_FOR_NETWORK)
            waitForNetworkRadioButton.setSelected(osmc_network.is_connman_wait_for_network_enabled())

        elif controlID == WIRELESS_WAIT_FOR_NETWORK:
            osmc_network.toggle_wait_for_network(not osmc_network.is_connman_wait_for_network_enabled())
            waitForNetworkRadioButton = self.getControl(WIRELESS_WAIT_FOR_NETWORK)
            waitForNetworkRadioButton.setSelected(osmc_network.is_connman_wait_for_network_enabled())

        elif controlID in ALL_TETHERING_CONTROLS:
            self.handle_tethering_selection(controlID)

    def onAction(self, action):
        actionID = action.getId()
        focused_control = self.getFocusId()

        log('actionID = ' + str(actionID))
        log('focused_control = %s,   %s' % (type(focused_control), focused_control))

        if actionID in (10, 92):
            self.stop_wifi_population_thread()
            self.stop_bluetooth_population_thread()
            xbmc.sleep(200)
            self.close()

        if focused_control in MAIN_MENU:
            if focused_control != self.current_panel:

                self.current_panel = focused_control
                # stop any running threads on change of panel
                self.stop_wifi_population_thread()
                self.stop_bluetooth_population_thread()

                if focused_control == SELECTOR_WIRED_NETWORK:
                    self.populate_wired_panel()

                elif focused_control == SELECTOR_WIRELESS_NETWORK:
                    self.populate_wifi_panel()

                elif focused_control == SELECTOR_BLUETOOTH:
                    self.populate_bluetooth_panel()

                elif focused_control == SELECTOR_TETHERING:
                    self.populate_tethering_panel()

            # change to the required settings panel
            for ctl in MAIN_MENU:
                self.getControl(ctl * 10).setVisible(True if ctl == focused_control else False)

        if focused_control in WIRED_IP_LABELS:
            self.update_current_ip_settings(WIRED_IP_VALUES)
            self.update_apply_reset_button('WIRED')

        if focused_control in WIRELESS_IP_LABELS:
            self.update_current_ip_settings(WIRELESS_IP_VALUES)
            self.update_apply_reset_button('WIRELESS')

    def edit_ip_address(self, controlID):
        relevant_label_control = self.getControl(900000 + controlID)
        current_label = relevant_label_control.getLabel()

        if current_label == '___ : ___ : ___ : ___':
            current_label = ''

        user_input = DIALOG.input(lang(32004), current_label, type=xbmcgui.INPUT_IPADDRESS)

        if not user_input or user_input == '0.0.0.0':

            relevant_label_control.setLabel(current_label)

        else:
            # validate ip_address format
            try:
                socket.inet_aton(user_input)

            except:
                'The address provided is not a valid IP address.', 'OSMC Network Setup'
                ok = DIALOG.ok(lang(32004), lang(32005))

                self.edit_ip_address(controlID)

                return

            # ip_string = ' : '.join(str(user_input).split('.'))
            relevant_label_control.setLabel(user_input)

            return

    def stop_wifi_population_thread(self):
        # call the wifi checking bot to exit, if it exists
        try:
            self.wifi_populate_bot.stop_thread()
        except:
            pass

    def stop_bluetooth_population_thread(self):
        try:
            self.bluetooth_population_thread.stop_thread()
        except:
            pass

    def show_busy_dialogue(self):
        xbmc.executebuiltin("ActivateWindow(busydialog)")

    def clear_busy_dialogue(self):
        xbmc.executebuiltin("Dialog.Close(busydialog)")

    def toggle_controls(self, enabled, control_ids):
        for control_id in control_ids:
            control = self.getControl(control_id)
            control.setEnabled(enabled)
            control.setVisible(True)

    def hide_controls(self, control_ids):
        for control_id in control_ids:
            control = self.getControl(control_id)
            control.setVisible(False)

    def get_wired_config(self):
        return osmc_network.get_ethernet_settings()

    def populate_wired_panel(self):
        if os.path.isfile(self.reboot_required_file):
            # 'NFS Network Settings'
            # 'The displayed network configuration may be out dated - A reboot is recommended before proceeding'
            DIALOG.ok(lang(32036), lang(32038))
        # Clear wired network Panel
        self.hide_controls(ALL_WIRED_CONTROLS)
        if osmc_network.is_ethernet_enabled():
            self.current_network_config = self.get_wired_config()
            if self.current_network_config:
                interface = self.current_network_config['Interface']
                if self.current_network_config['State'] == 'configuration':
                    status = lang(32044) + ': ' + interface + ' ('+ lang(32076) + ')'
                else:
                    if osmc_network.has_network_connection(True):
                        # 'Status'                               'Connected'
                        status = lang(32044) + ': ' + interface + ' (' + lang(32046) + ')'
                    else:
                        # 'Status'                               'No internet'
                        status = lang(32044) + ': ' + interface + ' (' + lang(32047) + ')'
                self.wired_status_label.setLabel(status)
                if self.current_network_config['State'] == 'configuration':
                    self.current_network_config[self.internet_protocol]['Method'] = 'manual'
                if self.current_network_config['State'] in ['online', 'ready', 'configuration']:
                    self.toggle_controls(True, ALL_WIRED_CONTROLS)
                    self.update_manual_DHCP_button(WIRED_DHCP_MANUAL_BUTTON, WIRED_IP_VALUES, WIRED_IP_LABELS)
                    self.populate_ip_controls(self.current_network_config, WIRED_IP_VALUES)

                    # enable reset and apply button
                    self.update_apply_reset_button('WIRED')

            else:  # no wired connection
                self.hide_controls(WIRED_IP_VALUES + WIRELESS_IP_VALUES)
                # 'Status'     'no wired connection'
                status = lang(32044) + ': ' + lang(32049)
                self.wired_status_label.setLabel(status)
                self.clear_ip_controls(WIRED_IP_VALUES)
        else:  # Disabled
            self.clear_ip_controls(WIRED_IP_VALUES)
            self.hide_controls(ALL_WIRED_CONTROLS)
            # 'Status'     'disabled'
            status = lang(32044) + ': ' + lang(32048)
            self.wired_status_label.setLabel(status)
            self.update_apply_reset_button('WIRED')

        adapterRadioButton = self.getControl(WIRED_ADAPTER_TOGGLE)
        adapterRadioButton.setSelected(osmc_network.is_ethernet_enabled())
        adapterRadioButton.setEnabled(True)

        waitForNetworkRadioButton = self.getControl(WIRED_WAIT_FOR_NETWORK)
        waitForNetworkRadioButton.setSelected(osmc_network.is_connman_wait_for_network_enabled())
        waitForNetworkRadioButton.setEnabled(True)

    def update_manual_DHCP_button(self, button_id, ip_values, ip_labels):
        manualDHCPButton = self.getControl(button_id)
        if 'dhcp' in self.current_network_config[self.internet_protocol]['Method']:
            # 'Configure Network Manually'
            manualDHCPButton.setLabel(lang(32006))
            # if configuration is by DHCP disable controls
            self.toggle_controls(False, ip_values)
            self.toggle_controls(False, ip_labels)
        else:
            # 'Configure Network Using DHCP'
            manualDHCPButton.setLabel(lang(32033))
            self.toggle_controls(True, ip_values)
            self.toggle_controls(True, ip_labels)

    def populate_ip_controls(self, settings_dict, controls):
        ip_address = self.getControl(controls[0])
        ip_address.setLabel(settings_dict[self.internet_protocol]['Address'])
        subnet = self.getControl(controls[1])
        subnet.setLabel(settings_dict[self.internet_protocol]['Netmask'])
        defaultGateway = self.getControl(controls[2])
        if settings_dict[self.internet_protocol].has_key('Gateway'):
            defaultGateway.setLabel(settings_dict[self.internet_protocol]['Gateway'])
        else:
            defaultGateway.setLabel('')
            defaultGateway.setEnabled(False)
        primaryDNS = self.getControl(controls[3])
        if settings_dict['Nameservers']['DNS_1']:
            primaryDNS.setLabel(settings_dict['Nameservers']['DNS_1'])
        else:
            primaryDNS.setLabel('')
        secondaryDNS = self.getControl(controls[4])
        if settings_dict['Nameservers']['DNS_2']:
            secondaryDNS.setLabel(settings_dict['Nameservers']['DNS_2'])
        else:
            secondaryDNS.setLabel('')

    def clear_ip_controls(self, controls):
        ip_address = self.getControl(controls[0])
        ip_address.setLabel('')
        subnet = self.getControl(controls[1])
        subnet.setLabel('')
        defaultGateway = self.getControl(controls[2])
        defaultGateway.setLabel('')
        primaryDNS = self.getControl(controls[3])
        primaryDNS.setLabel('')
        secondaryDNS = self.getControl(controls[4])
        secondaryDNS.setLabel('')
        self.toggle_controls(False, controls)

    def update_current_ip_settings(self, controls):
        ip_address = self.getControl(controls[0])
        self.current_network_config[self.internet_protocol]['Address'] = ip_address.getLabel()
        subnet = self.getControl(controls[1])
        self.current_network_config[self.internet_protocol]['Netmask'] = subnet.getLabel()
        defaultGateway = self.getControl(controls[2])
        self.current_network_config[self.internet_protocol]['Gateway'] = defaultGateway.getLabel()
        primaryDNS = self.getControl(controls[3])
        self.current_network_config['Nameservers']['DNS_1'] = primaryDNS.getLabel()
        secondaryDNS = self.getControl(controls[4])
        if secondaryDNS.getLabel():
            self.current_network_config['Nameservers']['DNS_2'] = secondaryDNS.getLabel()

    def handle_wired_selection(self, control_id):
        if control_id == WIRED_DHCP_MANUAL_BUTTON:
            if self.current_network_config[self.internet_protocol]['Method'] == 'dhcp':
                self.current_network_config[self.internet_protocol]['Method'] = 'manual'
            elif self.current_network_config[self.internet_protocol]['Method'] == 'nfs_dhcp':
                self.current_network_config[self.internet_protocol]['Method'] = 'nfs_manual'
            elif self.current_network_config[self.internet_protocol]['Method'] == 'manual':
                self.current_network_config[self.internet_protocol]['Method'] = 'dhcp'
            elif self.current_network_config[self.internet_protocol]['Method'] == 'nfs_manual':
                self.current_network_config[self.internet_protocol]['Method'] = 'nfs_dhcp'
            self.update_manual_DHCP_button(WIRED_DHCP_MANUAL_BUTTON, WIRED_IP_VALUES, WIRED_IP_LABELS)
            if 'dhcp' in self.current_network_config[self.internet_protocol]['Method']:
                self.hide_controls(WIRED_IP_VALUES)

        if control_id == WIRED_RESET_BUTTON:
            self.current_network_config = self.get_wired_config()
            self.populate_ip_controls(self.current_network_config, WIRED_IP_VALUES)
            self.update_manual_DHCP_button(WIRED_DHCP_MANUAL_BUTTON, WIRED_IP_VALUES, WIRED_IP_LABELS)
            self.setFocusId(WIRED_DHCP_MANUAL_BUTTON)

        if control_id == WIRED_APPLY_BUTTON:
            if self.current_network_config:
                osmc_network.apply_network_changes(self.current_network_config, self.internet_protocol)
                if self.current_network_config[self.internet_protocol]['Method'] in ['nfs_dhcp', 'nfs_manual']:
                    with open(self.reboot_required_file, 'w') as f:
                        f.write('d')
                    # 'NFS Network Settings'
                    # 'Your Settings will not take effect until you reboot. Reboot Now?''
                    if DIALOG.yesno(lang(32036), lang(32037)):
                        xbmc.executebuiltin('Reboot')
                else:
                    self.populate_wired_panel()
                self.setFocusId(WIRED_DHCP_MANUAL_BUTTON)

        if control_id == WIRED_ADAPTER_TOGGLE:
            self.toggle_ethernet()
            self.populate_wired_panel()

        self.update_apply_reset_button('WIRED')

    def toggle_ethernet(self):
        self.show_busy_dialogue()
        self.hide_controls(ALL_WIRED_CONTROLS)
        # 'Status'              'Configuring...'
        self.wired_status_label.setLabel(lang(32044) + ' : ' + lang(32016))
        osmc_network.toggle_ethernet_state(not osmc_network.is_ethernet_enabled())
        # 5 second wait to allow connman to make the changes before refreshing
        time.sleep(2)
        self.clear_busy_dialogue()

    def update_apply_reset_button(self, type):
        if type == 'WIRED':
            if cmp(self.get_wired_config(), self.current_network_config) == 0 or not self.get_wired_config():
                self.toggle_controls(False, [WIRED_RESET_BUTTON, WIRED_APPLY_BUTTON])
            else:
                self.toggle_controls(True, [WIRED_RESET_BUTTON, WIRED_APPLY_BUTTON])
        if type == 'WIRELESS':
            wireless_config = self.get_wireless_config(self.conn_ssid)
            if cmp(wireless_config, self.current_network_config) == 0:
                self.toggle_controls(False, [WIRELESS_RESET_BUTTON, WIRELESS_APPLY_BUTTON])
            else:
                self.toggle_controls(True, [WIRELESS_RESET_BUTTON, WIRELESS_APPLY_BUTTON])

    def get_wireless_config(self, ssid):
        if ssid is not None:
            wifi = None
            for adapterAddress, wifis in osmc_network.get_wifi_networks().iteritems():
                if ssid in wifis:
                    wifi = wifis[ssid]
            if wifi:
                config = wifi
                if self.wireless_password:
                    config['Password'] = self.wireless_password
                return config
        return {}

    def populate_wifi_panel(self, scan=False):
        if osmc_network.is_wifi_available():
            if osmc_network.is_wifi_enabled():
                # Start the wifi population thread
                threadRunning = False
                for t in threading.enumerate():
                    if t.getName() == WIFI_THREAD_NAME:
                        threadRunning = True
                if not threadRunning:
                    self.wifi_populate_bot = wifi_populate_bot(scan, self.getControl(5000), self.conn_ssid)
                    self.wifi_populate_bot.setDaemon(True)
                    self.wifi_populate_bot.start()

                self.current_network_config = osmc_network.get_connected_wifi()
                self.conn_ssid = None
                if 'SSID' in self.current_network_config:
                    self.conn_ssid = self.current_network_config['SSID']
                if self.conn_ssid:
                    if 'Address' in self.current_network_config[self.internet_protocol]:
                        self.update_manual_DHCP_button(WIRELESS_DHCP_MANUAL_BUTTON, WIRELESS_IP_VALUES, WIRELESS_IP_LABELS)
                        self.populate_ip_controls(self.current_network_config, WIRELESS_IP_VALUES)
                    self.toggle_controls(True, [WIRELESS_ADAPTER_TOGGLE,  WIRELESS_NETWORKS,
                                                WIRELESS_DHCP_MANUAL_BUTTON])
                    if osmc_network.has_network_connection(True):
                        # 'Status'            'Connected'
                        status = lang(32044) + ': ' + lang(32046)
                    else:
                        # 'Status'            'No internet'
                        status = lang(32044) + ':  ' + lang(32047)
                    self.wireless_status_label.setLabel(status)
                else:  # not connected to a network
                    self.hide_controls(WIRELESS_IP_VALUES + WIRELESS_IP_LABELS + [WIRELESS_DHCP_MANUAL_BUTTON,
                                                                                  WIRELESS_APPLY_BUTTON,
                                                                                  WIRELESS_RESET_BUTTON])
                    self.toggle_controls(True, [WIRELESS_ADAPTER_TOGGLE, WIRELESS_NETWORKS])
                    self.clear_ip_controls(WIRELESS_IP_VALUES)
                    # 'Status'           'No wireless Connection'
                    status = lang(32044) + ': ' + lang(32050)
                    self.wireless_status_label.setLabel(status)

            else:  # Wifi disabled
                self.hide_controls(ALL_WIRELESS_CONTROLS)
                # 'Status'            'disabled'
                status = lang(32044) + ': ' + lang(32048)
                self.wireless_status_label.setLabel(status)

            adapterRadioButton = self.getControl(WIRELESS_ADAPTER_TOGGLE)
            adapterRadioButton.setSelected(osmc_network.is_wifi_enabled())
            adapterRadioButton.setEnabled(True)

        else:  # Wifi not available
            self.toggle_controls(False, ALL_WIRELESS_CONTROLS)

        waitForNetworkRadioButton = self.getControl(WIRELESS_WAIT_FOR_NETWORK)
        waitForNetworkRadioButton.setSelected(osmc_network.is_connman_wait_for_network_enabled())
        waitForNetworkRadioButton.setEnabled(True)

    def handle_wireless_selection(self, control_id):
        if control_id == 5000:  # wireless network
            self.handle_selected_wireless_network()

        elif control_id == WIRELESS_DHCP_MANUAL_BUTTON:
            if self.current_network_config[self.internet_protocol]['Method'] == 'dhcp':
                self.current_network_config[self.internet_protocol]['Method'] = 'manual'
            elif self.current_network_config[self.internet_protocol]['Method'] == 'manual':
                self.current_network_config[self.internet_protocol]['Method'] = 'dhcp'
                self.hide_controls(WIRELESS_IP_VALUES)
            self.update_manual_DHCP_button(WIRELESS_DHCP_MANUAL_BUTTON, WIRELESS_IP_VALUES, WIRELESS_IP_LABELS)
            if 'dhcp' in self.current_network_config[self.internet_protocol]['Method']:
                self.hide_controls(WIRELESS_IP_VALUES)

        elif control_id == WIRELESS_RESET_BUTTON:
            self.current_network_config = self.get_wireless_config(self.conn_ssid)
            self.update_manual_DHCP_button(WIRELESS_DHCP_MANUAL_BUTTON, WIRELESS_IP_VALUES, WIRELESS_IP_LABELS)
            self.setFocusId(WIRELESS_DHCP_MANUAL_BUTTON)

        elif control_id == WIRELESS_APPLY_BUTTON:
            if self.current_network_config:
                osmc_network.apply_network_changes(self.current_network_config)
                self.populate_wifi_panel()
                self.setFocusId(WIRELESS_DHCP_MANUAL_BUTTON)

        elif control_id == WIRELESS_ADAPTER_TOGGLE:
            self.toggle_wifi()
            self.populate_wifi_panel()

        self.update_apply_reset_button('WIRELESS')

    def toggle_wifi(self):
        self.show_busy_dialogue()
        self.WFP.reset()
        self.hide_controls(ALL_WIRELESS_CONTROLS)
        self.toggle_controls(True, [WIRELESS_NETWORKS])
        wifi_state = not osmc_network.is_wifi_enabled()
        osmc_network.toggle_wifi_state(wifi_state)
        # 5 second wait to allow connman to make the changes before refreshing
        time.sleep(5)
        if not wifi_state:
            self.stop_wifi_population_thread()
            self.current_network_config = {}
        self.clear_busy_dialogue()

    def handle_selected_wireless_network(self):
        item = self.WFP.getSelectedItem()
        path = item.getProperty('Path')
        encrypted = item.getProperty('Encrypted') == 'True'
        connected = item.getProperty('Connected')
        ssid = item.getProperty('SSID')
        if connected == 'False':
            if not self.conn_ssid:  # if we are not connected to a network connect
                if self.connect_to_wifi(ssid, encrypted):
                    if '_hidden_' not in path:
                        strength = self.current_network_config['Strength']
                        icon = wifi_populate_bot.get_wifi_icon(encrypted, strength, True)
                        item.setIconImage(icon)
                        item.setProperty('Connected', 'True')

            else:  # Display a toast asking the user to disconnect first
                # 'Please disconnect from the current network before connecting'
                message = lang(32053)
                # 'Wireless'
                xbmc.executebuiltin("XBMC.Notification(%s,%s,%s)" % (lang(32041), message, "2500"))

        else:
            if ssid == self.conn_ssid:
                #                             'Disconnect from'
                selection = DIALOG.select(lang(32042) + ' ' + self.conn_ssid + '?',
                                          [lang(32051),lang(32058), lang(32059)])
                if selection == -1 or selection == 0:
                    return
                self.show_busy_dialogue()
                self.conn_ssid = None
                self.wireless_password = None
                self.current_network_config = {}
                self.hide_controls(WIRELESS_IP_VALUES + WIRELESS_IP_LABELS)
                osmc_network.wifi_disconnect(path)
                if selection == 2: # we also want to remove/forget this network
                    osmc_network.wifi_remove(path)
                self.WFP.removeItem(self.WFP.getSelectedPosition())
                self.toggle_controls(False, [SELECTOR_TETHERING])
                self.populate_wifi_panel()
                self.clear_busy_dialogue()

    def connect_to_wifi(self, ssid, encrypted, password=None, scan=False):
        if scan:
            self.show_busy_dialogue()
            osmc_network.scan_wifi()
            self.clear_busy_dialogue()

        wifi = None
        for adapterAddress, wifis in osmc_network.get_wifi_networks().iteritems():
            if ssid in wifis:
                wifi = wifis[ssid]

        if wifi:
            # 'Configuring'
            self.wireless_status_label.setLabel(lang(32016))
            path = wifi['path']
            connection_status = False
            hiddenssid = None
            connect = False
            if '_hidden_' in path :
                # 'Enter SSID to connect to this hidden network'
                hiddenssid = DIALOG.input(lang(32073))
            else:
                # 'Wireless'   'Connect to'
                if DIALOG.yesno(lang(32041), lang(32052) + ' ' + ssid + '?'):
                    connect = True
            if connect or hiddenssid:
                self.show_busy_dialogue()
                # try without a password see if connman has the password
                script_base_path = os.path.join(__addon__.getAddonInfo('path'), 'resources', 'lib') + '/'
                connection_status = osmc_network.wifi_connect(path, None, hiddenssid, script_base_path)
                self.clear_busy_dialogue()
                if not connection_status and encrypted:
                    if password is None:
                        password = DIALOG.input(lang(32013), type=xbmcgui.INPUT_ALPHANUM,
                                            option=xbmcgui.ALPHANUM_HIDE_INPUT)
                    if password:
                        self.wireless_password = password
                        self.show_busy_dialogue()
                        connection_status = osmc_network.wifi_connect(path, password, hiddenssid, script_base_path)
                        self.clear_busy_dialogue()
                if not connection_status:
                    # 'Connection to '                  'failed'
                    message = lang(32043) + ' ' + ssid + ' ' + lang(32025)
                    #                                                   'Wireless'
                    xbmc.executebuiltin("XBMC.Notification(%s,%s,%s)" % (lang(32041), message, "2500"))
                    self.current_network_config = {}
                    self.clear_ip_controls(WIRELESS_IP_VALUES)
                    self.toggle_controls(False, [WIRELESS_DHCP_MANUAL_BUTTON])
                    #         'Status'           'Not connected'
                    status = lang(32044) + ': ' + lang(32050)
                    self.wireless_status_label.setLabel(status)
                    self.clear_busy_dialogue()
                    return False
                else:
                    self.show_busy_dialogue()
                    self.current_network_config = osmc_network.get_connected_wifi()
                    self.update_manual_DHCP_button(WIRELESS_DHCP_MANUAL_BUTTON, WIRELESS_IP_VALUES, WIRELESS_IP_LABELS)
                    self.populate_ip_controls(self.current_network_config, WIRELESS_IP_VALUES)
                    self.toggle_controls(True, [WIRELESS_ADAPTER_TOGGLE, WIRELESS_NETWORKS,
                                                WIRELESS_DHCP_MANUAL_BUTTON])
                    self.conn_ssid = self.current_network_config['SSID']
                    interface = self.current_network_config['Interface']
                    if osmc_network.has_network_connection(True):
                        # 'Status'                               'Connected'
                        status = lang(32044) + ': ' + interface + ' (' + lang(32046) + ')'
                    else:
                        # 'Status'                               'No internet'
                        status = lang(32044) + ': ' + interface + ' (' + lang(32047) + ')'
                    self.wireless_status_label.setLabel(status)
                    self.toggle_controls(True, [SELECTOR_TETHERING])
                    self.clear_busy_dialogue()
                    return True
        else:
            return False

    def sort_strength(self, itm):
        try:
            metric = int(itm.getProperty('strength'))
            if itm.getProperty('Connected') == 'True':
                # make sure the connected network is always at the top
                metric += 100
        except:
            metric = 0
        return metric

    def populate_bluetooth_panel(self):
        bluetoothRadioButton = self.getControl(BLUETOOTH_ENABLE_TOGGLE)
        bluetooth_enabled = osmc_bluetooth.is_bluetooth_enabled()
        bluetoothRadioButton.setSelected(bluetooth_enabled)

        # disable all if bluetooth is not enabled
        if not bluetooth_enabled:
            # disable all controls
            self.toggle_controls(False, BLUETOOTH_CONTROLS)
            return

        self.toggle_controls(True, BLUETOOTH_CONTROLS)
        discoveryRadioButton = self.getControl(BLUETOOTH_DISCOVERY)
        discoveryRadioButton.setSelected(osmc_bluetooth.is_discovering())
        # Start Bluetooth Population Thread
        threadRunning = False
        for t in threading.enumerate():
            if t.getName() == BLUETOOTH_THREAD_NAME:
                threadRunning = True
        if not threadRunning:
            self.bluetooth_population_thread = bluetooth_population_thread(self.BTD, self.BTP)
            self.bluetooth_population_thread.setDaemon(True)
            self.bluetooth_population_thread.start()

    def handle_bluetooth_selection(self, control_id):
        if control_id == BLUETOOTH_ENABLE_TOGGLE:  # Enable Bluetooth
            self.show_busy_dialogue()
            if osmc_bluetooth.is_bluetooth_enabled():
                osmc_bluetooth.toggle_bluetooth_state(False)
                self.stop_bluetooth_population_thread()
            else:
                osmc_bluetooth.toggle_bluetooth_state(True)
            self.clear_busy_dialogue()

        if control_id == BLUETOOTH_DISCOVERY:  # Discovery
            self.show_busy_dialogue()
            if not osmc_bluetooth.is_discovering():
                osmc_bluetooth.start_discovery()
            else:
                osmc_bluetooth.stop_discovery()
            xbmc.sleep(1500)
            self.clear_busy_dialogue()


        if control_id == 6000:  # paired devices
            item = self.BTP.getSelectedItem()
            if item:
                address = item.getProperty('address')
                alias = item.getProperty('alias')
                connected = item.getProperty('connected') == 'True'
                #                                'Cancel'     'Re-connect'  'Remove Device'
                selection = DIALOG.select(alias, [lang(32051), lang(32075), lang(32021)])
                if selection == -1 or selection == 0:
                    return

                if selection == 1: # Reconnect
                    if not connected:
                        self.show_busy_dialogue()
                        if self.connect_bluetooth(address, alias):
                            self.bluetooth_population_thread.update_bluetooth_lists()
                        self.clear_busy_dialogue()

                if selection == 2:
                    osmc_bluetooth.remove_device(address)
                    self.setFocusId(BLUETOOTH_ENABLE_TOGGLE)
                    self.bluetooth_population_thread.update_bluetooth_lists()

        if control_id == 7000:  # Discovered devices
            item = self.BTD.getSelectedItem()
            if item:
                address = item.getProperty('address')
                alias = item.getProperty('alias')
                #              'Connect With Device'                        'No'        'Pair and Connect' 'pair'
                selection = DIALOG.select(lang(32022) + ' ' + alias + '?', [lang(32055),lang(32056), lang(32057)])
                if selection == -1 or selection == 0:
                    return
                self.show_busy_dialogue()
                self.setFocusId(BLUETOOTH_DISCOVERY)
                if selection == 1:
                    script_base_path = os.path.join(__addon__.getAddonInfo('path'), 'resources', 'lib') + '/'
                    result = osmc_bluetooth.pair_device(address, script_base_path)

                    if not result:
                        #         'Connection to '                       'failed'
                        message = lang(32024) + ' ' + alias + ' ' + lang(32025)
                        #                                                     'Bluetooth'
                        xbmc.executebuiltin("XBMC.Notification(%s,%s,%s)" % (lang(32020), message, "2500"))
                        self.clear_busy_dialogue()
                        return
                if self.connect_bluetooth(address, alias):
                    osmc_bluetooth.set_device_trusted(address, True)
                    self.bluetooth_population_thread.update_bluetooth_lists()
                self.clear_busy_dialogue()

    def connect_bluetooth(self, address, alias):
        connected = osmc_bluetooth.connect_device(address)
        if not connected:
             #         'Connection to'                       'failed'
            message = lang(32024) + ' ' + alias + ' ' + lang(32025)
            #                                                     'Bluetooth'
            xbmc.executebuiltin("XBMC.Notification(%s,%s,%s)" % (lang(32020), message, "2500"))
        return connected

    def populate_tethering_panel(self):
        wifi_tethering = osmc_network.is_tethering_wifi()
        ethernet_tethering = osmc_network.is_tethering_ethernet()
        self.toggle_controls(True, ALL_TETHERING_CONTROLS)
        if wifi_tethering:
            self.handle_tethering_selection(TETHERING_WIFI_RADIOBUTTON)
        if ethernet_tethering:
            self.handle_tethering_selection(TETHERING_ETHERNET_RADIOBUTTON)
        if not wifi_tethering and not ethernet_tethering:
            self.handle_tethering_selection(TETHERING_WIFI_RADIOBUTTON)

        # disable controls if tethering is active
        if wifi_tethering or ethernet_tethering:
            self.toggle_controls(False, [TETHERING_WIFI_SSID_LABEL,TETHERING_WIFI_SSID_VALUE, TETHERING_WIFI_PASSPHRASE_LABEL,
                                         TETHERING_WIFI_PASSPHRASE_VALUE, TETHERING_ENABLE, TETHERING_WIFI_RADIOBUTTON,
                                         TETHERING_ETHERNET_RADIOBUTTON])
        else:
            self.toggle_controls(False, [TETHERING_DISABLE])

        wifiSSIDLabel = self.getControl(TETHERING_WIFI_SSID_VALUE)
        self.hotspot_ssid  = osmc_network.get_tethering_SSID();
        if not self.hotspot_ssid:
            self.hotspot_ssid = 'osmc_wifi';
        wifiSSIDLabel.setLabel(self.hotspot_ssid)
        self.hotspot_passphrase = osmc_network.get_tethering_passphrase();
        if not self.hotspot_passphrase:
            self.hotspot_passphrase = 'h0tsp0t0smc'
        control_label = ' '.join([self.hotspot_passphrase[i: i + 33] for i in
                                  xrange(0, len(self.hotspot_passphrase), 33)])
        wifiPassphaseLabel = self.getControl(TETHERING_WIFI_PASSPHRASE_VALUE)
        wifiPassphaseLabel.setLabel(control_label)

    def handle_tethering_selection(self, control_id):
        if control_id in [TETHERING_WIFI_RADIOBUTTON, TETHERING_ETHERNET_RADIOBUTTON]:
            wifi_radiobutton = self.getControl(TETHERING_WIFI_RADIOBUTTON)
            ethernet_radiobutton = self.getControl(TETHERING_ETHERNET_RADIOBUTTON)
            wifi_radiobutton.setSelected(False)
            ethernet_radiobutton.setSelected(False)
            if control_id == TETHERING_WIFI_RADIOBUTTON:
                self.hide_controls([TETHERING_WARNING])
                wifi_radiobutton.setSelected(True)
                ethernet_radiobutton.setSelected(False)
                self.toggle_controls(True, [TETHERING_WIFI_SSID_LABEL,TETHERING_WIFI_SSID_VALUE,
                                            TETHERING_WIFI_PASSPHRASE_LABEL, TETHERING_WIFI_PASSPHRASE_VALUE])
            else:
                self.toggle_controls(True, [TETHERING_WARNING])
                wifi_radiobutton.setSelected(False)
                ethernet_radiobutton.setSelected(True)
                self.toggle_controls(False, [TETHERING_WIFI_SSID_LABEL,TETHERING_WIFI_SSID_VALUE,
                                            TETHERING_WIFI_PASSPHRASE_LABEL, TETHERING_WIFI_PASSPHRASE_VALUE])

        if control_id == TETHERING_WIFI_SSID_LABEL:
            wifiSSIDLabel = self.getControl(TETHERING_WIFI_SSID_VALUE)
            enteredSSID = DIALOG.input(lang(32068), self.hotspot_ssid)
            if enteredSSID:
                self.hotspot_ssid = enteredSSID
                wifiSSIDLabel.setLabel(enteredSSID)

        if control_id == TETHERING_WIFI_PASSPHRASE_LABEL:
            wifiPassphraseLabel = self.getControl(TETHERING_WIFI_PASSPHRASE_VALUE)
            currentPassphrase =self.hotspot_passphrase
            enteredPassphrase = DIALOG.input(lang(32069), currentPassphrase)
            if enteredPassphrase:
                self.hotspot_passphrase = enteredPassphrase
                control_label = ' '.join([self.hotspot_passphrase[i: i + 33] for i in
                                  xrange(0, len(self.hotspot_passphrase), 33)])
                wifiPassphraseLabel.setLabel(control_label)

        if control_id == TETHERING_ENABLE:
            wifi_radiobutton = self.getControl(TETHERING_WIFI_RADIOBUTTON)
            technology = None
            ssid = None
            passphrase = None
            if wifi_radiobutton.isSelected():
                technology = 'wifi'
                ssid = self.hotspot_ssid
                if len(ssid) == 0:
                    # 'Portable Hotspot'
                    # 'SSID must be set to enable WiFi Tethering'
                    DIALOG.ok(lang(32063), lang(32070))
                    return
                passphrase = self.hotspot_passphrase
                if len(passphrase) > 63:
                    # 'Portable Hotspot'
                    # 'Passphrase must be 63 characters or less"'
                    DIALOG.ok(lang(32063), lang(32074))
                    return
                if len(passphrase) < 8:
                    # 'Portable Hotspot'
                    # 'Passphrase must at least 8 characters long'
                    DIALOG.ok(lang(32063), lang(32071))
                    return
            else:
                technology = 'ethernet'

            log('Enabling '+ technology +' Hotspot')
            if technology is 'wifi':
                log('Hotspot ssid = ' + ssid)

            if osmc_network.tethering_enable(technology, ssid, passphrase):
                self.setFocusId(TETHERING_DISABLE)
                self.toggle_controls(False, [TETHERING_WIFI_SSID_LABEL,TETHERING_WIFI_SSID_VALUE, TETHERING_WIFI_PASSPHRASE_LABEL,
                                         TETHERING_WIFI_PASSPHRASE_VALUE, TETHERING_ENABLE, TETHERING_WIFI_RADIOBUTTON,
                                         TETHERING_ETHERNET_RADIOBUTTON, TETHERING_ENABLE])
                self.toggle_controls(True, [TETHERING_DISABLE])
            else:
                # 'Portable Hotspot'
                # 'Error enabling hotspot - see log for details'
                DIALOG.ok(lang(32063), lang(32072))

        if control_id == TETHERING_DISABLE:
            log('Disabling Hotspot')
            osmc_network.tethering_disable()
            self.setFocusId(SELECTOR_TETHERING)
            self.toggle_controls(True, [TETHERING_WIFI_SSID_LABEL,TETHERING_WIFI_SSID_VALUE, TETHERING_WIFI_PASSPHRASE_LABEL,
                                     TETHERING_WIFI_PASSPHRASE_VALUE, TETHERING_ENABLE, TETHERING_WIFI_RADIOBUTTON,
                                     TETHERING_ETHERNET_RADIOBUTTON, TETHERING_ENABLE])
            self.toggle_controls(False, [TETHERING_DISABLE])


class bluetooth_population_thread(threading.Thread):
    def __init__(self, discovered_list_control, trusted_list_control):
        super(bluetooth_population_thread, self).__init__(name=BLUETOOTH_THREAD_NAME)
        self.exit = False
        self.discovered_list_control = discovered_list_control
        self.trusted_list_control = trusted_list_control
        self.trusted_dict = {}
        self.discovered_dict = {}

    def run(self):
        runs = 0
        while not self.exit:
            # update gui every 2 seconds
            if runs % 200 == 0 and not self.exit:
                self.update_bluetooth_lists()
            # every 4 seconds output debug info
            if runs % 400 == 0 and not self.exit:
                log('-- DISCOVERED ---')
                log(self.discovered_dict)
                log('-- TRUSTED --')
                log(self.trusted_dict)

            xbmc.sleep(10)
            runs += 1

    def update_bluetooth_lists(self):
        self.trusted_dict = self.populate_bluetooth_dict(True)
        self.discovered_dict = self.populate_bluetooth_dict(False)
        self.update_list_control(dict(self.discovered_dict), self.discovered_list_control)
        self.update_list_control(dict(self.trusted_dict), self.trusted_list_control)

    def stop_thread(self):
        self.exit = True

    def update_list_control(self, devices_dict, list_control):
        items_to_be_removed = []
        for itemIndex in range(0, list_control.size()):
            listItem = list_control.getListItem(itemIndex)
            address = listItem.getProperty('address')
            if address in devices_dict.keys():
                connected = listItem.getProperty('connected') == 'True'
                # connected status differs
                if not connected == devices_dict[address]['connected']:
                    log('Connected status differs')
                    items_to_be_removed.append(itemIndex)
                else:
                    devices_dict.pop(address)
            else:
                items_to_be_removed.append(itemIndex)

        for itemIndex in items_to_be_removed:
            try:
                list_control.removeItem(itemIndex)
            except:
                pass

        if len(devices_dict.keys()) > 0:
            for address, info in devices_dict.iteritems():
                list_control.addItem(self.create_bluetooth_item(address, info))

    def create_bluetooth_item(self, address, info):
        label = address
        if info['alias']:
            label = info['alias']
        item = xbmcgui.ListItem(label)
        icon_image = 'disconnected.png'
        if info['connected']:
            icon_image = 'connected.png'
        item.setIconImage(icon_image)
        item.setProperty('address', address)
        item.setProperty('alias', info['alias'])
        item.setProperty('connected', str(info['connected']))
        return item

    def populate_bluetooth_dict(self, paired):
        devices = {}
        if paired:
            devices = osmc_bluetooth.list_trusted_devices()
        else:
            devices = osmc_bluetooth.list_discovered_devices()
        bluetooth_dict = {}
        for address in devices.keys():
            alias = str(osmc_bluetooth.get_device_property(address, 'Alias'))
            paired = osmc_bluetooth.get_device_property(address, 'Paired')
            connected = osmc_bluetooth.get_device_property(address, 'Connected')
            trusted = osmc_bluetooth.get_device_property(address, 'Trusted')
            bluetooth_dict[address] = {'alias': alias, 'paired': paired,
                                       'connected': connected, 'trusted': trusted}
        return bluetooth_dict

    def sort_alias(self, itm):
        try:
            metric = int(itm.getProperty('alias'))
        except:
            metric = 0

        return metric


class wifi_scanner_bot(threading.Thread):
    def __init__(self):
        super(wifi_scanner_bot, self).__init__()

    def run(self):
        osmc_network.scan_wifi()


class wifi_populate_bot(threading.Thread):
    def __init__(self, scan, wifi_list_control, conn_ssid):

        super(wifi_populate_bot, self).__init__(name=WIFI_THREAD_NAME)

        self.WFP = wifi_list_control
        self.scan = scan
        self.exit = False
        self.conn_ssid = conn_ssid
        self.wifis = []
        self.current_network_config = None

        if self.scan:
            self.wifi_scanner_bot = wifi_scanner_bot()
            self.wifi_scanner_bot.setDaemon(True)
            self.wifi_scanner_bot.start()

    def run(self):
        running_dict = {}
        runs = 0
        while not self.exit:
            # only run the network check every 2 seconds, but allow the exit command to be checked every 10ms
            if runs % 200 == 0 and not self.exit:
                log('Updating Wifi networks')
                wifis = osmc_network.get_wifi_networks()

                running_dict.update(wifis)

                self.update_list_control(running_dict, len(wifis.keys()) > 1)

                # find any connected setting and load its values into the controls
                for adapterAddress, wifis in running_dict.iteritems():
                    for ssid, info in wifis.iteritems():
                        try:
                            if info['Connected'] == 'True':
                                self.current_network_config = self.get_wireless_config(ssid)
                                self.populate_ip_controls(info, WIRELESS_IP_VALUES)
                        except:
                            pass
             # every minute re-scan wifi unless the thread has been asked to exit
            if not self.exit and runs % 600 == 0:
                self.wifi_scanner_bot = wifi_scanner_bot()
                self.wifi_scanner_bot.setDaemon(True)
                self.wifi_scanner_bot.start()
            xbmc.sleep(10)
            runs += 1

    def stop_thread(self):
        self.exit = True

    def update_list_control(self, running_dict, multiAdpter):
        items_to_be_removed = []
        for itemIndex in range(0, self.WFP.size()):
            listItem = self.WFP.getListItem(itemIndex)
            listItemAdapterAddress = listItem.getProperty('AdapterAddress')
            listItemSSID = listItem.getProperty('SSID')
            listItemConnected = True if listItem.getProperty('Connected') in 'True' else False
            if listItemAdapterAddress in running_dict.keys():
                    if listItemSSID in running_dict[listItemAdapterAddress].keys():
                        wifi = running_dict[listItemAdapterAddress][listItemSSID]
                        networkConnected = True if wifi['State']in ('ready', 'online') else False
                        expectedLabel = self.getListItemLabel(wifi, multiAdpter);
                        if listItem.getLabel() == expectedLabel and listItemConnected == networkConnected:
                            running_dict[listItemAdapterAddress].pop(listItemSSID)
                        else:
                            items_to_be_removed.append(itemIndex)
                    else:
                        items_to_be_removed.append(itemIndex)
            else:
                items_to_be_removed.append(itemIndex)

        for itemIndex in reversed(items_to_be_removed):
            self.WFP.removeItem(itemIndex)

        if len(running_dict.keys()) > 0:
            for adapterAddress, wifis in running_dict.iteritems():
                for ssid, info in wifis.iteritems():
                    self.WFP.addItem(self.convert_wifi_to_listitem(info, multiAdpter))
                    connected = True if info['State'] in ('ready', 'online') else False
                    if connected and ssid == self.conn_ssid:
                        self.WFP.selectItem(self.WFP.size() - 1)

    def getListItemLabel(self, wifi, multiAdapter):
        ssid = wifi['SSID']
        interface = wifi['Interface']
        if multiAdapter:
            return ssid + ' (' + interface + ')'
        else:
            return ssid

    def convert_wifi_to_listitem(self, wifi, multiAdapter):

        # {'path': str(path),
        # 'SSID': str(dbus_properties['Name']),
        # 'Strength': int(dbus_properties['Strength']),
        # 'State' : str(dbus_properties['State'])}

        ssid = wifi['SSID']
        strength = wifi['Strength']
        state = wifi['State']
        path = wifi['path']
        encrypted = True if wifi['Security'] != 'none' else False
        connected = True if wifi['State'] in ('ready', 'online') else False
        address = wifi['AdapterAddress']

        # icon_tuple = (connected, encrypted, strength)
        icon_image = self.get_wifi_icon(encrypted, strength, connected)

        item = xbmcgui.ListItem(self.getListItemLabel(wifi, multiAdapter))
        item.setIconImage(icon_image)
        item.setProperty('Strength', str(strength))
        item.setProperty('Encrypted', str(encrypted))
        item.setProperty('Path', path)
        item.setProperty('Connected', str(connected))
        item.setProperty('SSID', ssid)
        item.setProperty('AdapterAddress', address)

        if connected:
            self.conn_ssid = ssid

        return item

    @staticmethod
    def get_wifi_icon(encrypted, strength, connected):
        filename = ''
        if connected:
            filename += 'c'
        else:
            filename += 'nc'
        if encrypted:
            filename += 'e'
        else:
            filename += 'ne'
        if strength >= 0 and strength <= 40:
            filename += '020'
        if strength >= 41 and strength <= 60:
            filename += '6080'
        if strength >= 61 and strength <= 100:
            filename += '80100'

        filename += ".png"
        return filename
