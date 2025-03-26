## Indigo plugin for monitoring network devices

import logging
import socket

import iplug
import arp
import wrapper
import clients
import utils

################################################################################
class Plugin(iplug.ThreadedPlugin):

    wrappers = dict()
    arp_cache = None

    #---------------------------------------------------------------------------
    def validatePrefsConfigUi(self, values):
        errors = indigo.Dict()

        utils.validateConfig_Int('threadLoopDelay', values, errors, min=60, max=3600)
        utils.validateConfig_Int('connectionTimeout', values, errors, min=0, max=300)
        utils.validateConfig_Int('arpCacheTimeout', values, errors, min=60, max=3600)

        return ((len(errors) == 0), values, errors)

    #---------------------------------------------------------------------------
    def validateDeviceConfigUi(self, values, typeId, devId):
        errors = indigo.Dict()

        if typeId == 'service':
            wrapper.Service.validateConfig(values, errors)
        elif typeId == 'ping':
            wrapper.Ping.validateConfig(values, errors)
        elif typeId == 'http':
            wrapper.HTTP.validateConfig(values, errors)
        elif typeId == 'local':
            wrapper.Local.validateConfig(values, errors)
        elif typeId == 'ssh':
            wrapper.SSH.validateConfig(values, errors)
        elif typeId == 'macos':
            wrapper.macOS.validateConfig(values, errors)

        return ((len(errors) == 0), values, errors)

    #---------------------------------------------------------------------------
    def deviceStartComm(self, device):
        iplug.ThreadedPlugin.deviceStartComm(self, device)
        typeId = device.deviceTypeId

        wrap = None

        if typeId == 'service':
            wrap = wrapper.Service(device)
        elif typeId == 'ping':
            wrap = wrapper.Ping(device)
        elif typeId == 'http':
            wrap = wrapper.HTTP(device)
        elif typeId == 'local':
            wrap = wrapper.Local(device, self.arp_cache)
        elif typeId == 'ssh':
            wrap = wrapper.SSH(device)
        elif typeId == 'macos':
            wrap = wrapper.macOS(device)
        else:
            self.logger.error(u'unknown device type: %s', typeId)

        self.wrappers[device.id] = wrap

        # XXX we might want to make sure the device status is updated here...
        # the problem with that is it makes for a long plugin startup if all
        # devices update status - especially things like ping and http.
        # !! when status is updated here, start the thread loop with a sleep !!
        #if device.configured: wrap.updateStatus()

    #---------------------------------------------------------------------------
    def deviceStopComm(self, device):
        iplug.ThreadedPlugin.deviceStopComm(self, device)
        self.wrappers.pop(device.id, None)

    #---------------------------------------------------------------------------
    def loadPluginPrefs(self, prefs):
        iplug.ThreadedPlugin.loadPluginPrefs(self, prefs)

        # global socket connection timeout - XXX does this affect all modules?
        sockTimeout = self.getPrefAsInt(prefs, 'connectionTimeout', 5)
        socket.setdefaulttimeout(sockTimeout)

        # setup the arp cache with configured timeout
        arpTimeout = self.getPrefAsInt(prefs, 'arpCacheTimeout', 300)
        self.arp_cache = arp.ArpCache(arpTimeout)

    #---------------------------------------------------------------------------
    def refreshAllDevices(self):
        # update all enabled and configured devices
        for id in self.wrappers:
            wrap = self.wrappers[id]
            wrap.updateStatus()

    #---------------------------------------------------------------------------
    def rebuildArpCache(self):
        self.arp_cache.rebuildArpCache()

    #---------------------------------------------------------------------------
    def runLoopStep(self):
        iplug.ThreadedPlugin.runLoopStep(self)

        self.rebuildArpCache()
        self.refreshAllDevices()

    #---------------------------------------------------------------------------
    # Relay / Dimmer Action callback
    def actionControlDimmerRelay(self, action, device):
        act = action.deviceAction
        self.logger.debug(u'actionControlDimmerRelay[%s] - %s', act, device.name)

        wrap = self.wrappers[device.id]

        #### TURN ON ####
        if act == indigo.kDimmerRelayAction.TurnOn:
            wrap.turnOn()

        #### TURN OFF ####
        elif act == indigo.kDimmerRelayAction.TurnOff:
            wrap.turnOff()

        #### TOGGLE ####
        elif act == indigo.kDimmerRelayAction.Toggle:
            if device.onState:
                wrap.turnOff()
            else:
                wrap.turnOn()

    #---------------------------------------------------------------------------
    # General Action callback
    def actionControlGeneral(self, action, device):
        act = action.deviceAction
        self.logger.debug(u'actionControlGeneral[%s] - %s', act, device.name)

        wrap = self.wrappers[device.id]

        #### STATUS REQUEST ####
        if act == indigo.kDeviceGeneralAction.RequestStatus:
            wrap.updateStatus()

        #### BEEP ####
        elif act == indigo.kDeviceGeneralAction.Beep:
            pass

