#===============================================================================
# Copyright (C) 2010 Diego Duclos
#
# This file is part of pyfa.
#
# pyfa is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyfa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyfa.  If not, see <http://www.gnu.org/licenses/>.
#===============================================================================

import locale
import copy
import threading
import logging
import wx
from codecs import open

import eos.db
import eos.types

from eos.types import State, Slot

from service.market import Market
from service.damagePattern import DamagePattern
from service.character import Character
from service.fleet import Fleet
from service.settings import SettingsProvider
from service.port import Port

logger = logging.getLogger(__name__)

class FitBackupThread(threading.Thread):
    def __init__(self, path, callback):
        threading.Thread.__init__(self)
        self.path = path
        self.callback = callback

    def run(self):
        path = self.path
        sFit = Fit.getInstance()
        allFits = map(lambda x: x[0], sFit.getAllFits())
        backedUpFits = sFit.exportXml(self.callback, *allFits)
        backupFile = open(path, "w", encoding="utf-8")
        backupFile.write(backedUpFits)
        backupFile.close()

        # Send done signal to GUI
        wx.CallAfter(self.callback, -1)


class FitImportThread(threading.Thread):
    def __init__(self, paths, callback):
        threading.Thread.__init__(self)
        self.paths = paths
        self.callback = callback

    def run(self):
        sFit = Fit.getInstance()
        fits = sFit.importFitFromFiles(self.paths, self.callback)

        # Send done signal to GUI
        wx.CallAfter(self.callback, -1, fits)


class Fit(object):
    instance = None

    @classmethod
    def getInstance(cls):
        if cls.instance is None:
            cls.instance = Fit()

        return cls.instance

    def __init__(self):
        self.pattern = DamagePattern.getInstance().getDamagePattern("Uniform")
        self.targetResists = None
        self.character = Character.getInstance().all5()
        self.booster = False
        self.dirtyFitIDs = set()

        serviceFittingDefaultOptions = {
            "useGlobalCharacter": False,
            "useGlobalDamagePattern": False,
            "defaultCharacter": self.character.ID,
            "useGlobalForceReload": False,
            "colorFitBySlot": False,
            "rackSlots": True,
            "rackLabels": True,
            "compactSkills": True,
            "showTooltip": True,
            "showMarketShortcuts": False}

        self.serviceFittingOptions = SettingsProvider.getInstance().getSettings(
            "pyfaServiceFittingOptions", serviceFittingDefaultOptions)

    def getAllFits(self):
        fits = eos.db.getFitList()
        names = []
        for fit in fits:
            names.append((fit.ID, fit.name))

        return names

    def getFitsWithShip(self, shipID):
        """ Lists fits of shipID, used with shipBrowser """
        fits = eos.db.getFitsWithShip(shipID)
        names = []
        for fit in fits:
            names.append((fit.ID, fit.name, fit.booster, fit.timestamp))

        return names

    def getBoosterFits(self):
        """ Lists fits flagged as booster """
        fits = eos.db.getBoosterFits()
        names = []
        for fit in fits:
            names.append((fit.ID, fit.name, fit.shipID))

        return names

    def countAllFits(self):
        return eos.db.countAllFits()

    def countFitsWithShip(self, shipID):
        count = eos.db.countFitsWithShip(shipID)
        return count

    def groupHasFits(self, groupID):
        sMkt = Market.getInstance()
        grp = sMkt.getGroup(groupID)
        items = sMkt.getItemsByGroup(grp)
        for item in items:
            if self.countFitsWithShip(item.ID) > 0:
                return True
        return False

    def getModule(self, fitID, pos):
        fit = eos.db.getFit(fitID)
        return fit.modules[pos]

    def newFit(self, shipID, name=None):
        ship = eos.types.Ship(eos.db.getItem(shipID))
        fit = eos.types.Fit(ship)
        fit.name = name if name is not None else "New %s" % fit.ship.item.name
        fit.damagePattern = self.pattern
        fit.targetResists = self.targetResists
        fit.character = self.character
        fit.booster = self.booster
        eos.db.save(fit)
        self.recalc(fit)
        return fit.ID

    def toggleBoostFit(self, fitID):
        fit = eos.db.getFit(fitID)
        fit.booster = not fit.booster
        eos.db.commit()

    def renameFit(self, fitID, newName):
        fit = eos.db.getFit(fitID)
        fit.name = newName
        eos.db.commit()

    def deleteFit(self, fitID):
        fit = eos.db.getFit(fitID)
        sFleet = Fleet.getInstance()
        sFleet.removeAssociatedFleetData(fit)

        eos.db.remove(fit)

        # refresh any fits this fit is projected onto. Otherwise, if we have
        # already loaded those fits, they will not reflect the changes
        for projection in fit.projectedOnto.values():
            eos.db.saveddata_session.refresh(projection.victim_fit)

    def copyFit(self, fitID):
        fit = eos.db.getFit(fitID)
        newFit = copy.deepcopy(fit)
        eos.db.save(newFit)
        return newFit.ID

    def clearFit(self, fitID):
        if fitID is None:
            return None

        fit = eos.db.getFit(fitID)
        fit.clear()
        return fit

    def toggleFactorReload(self, fitID):
        if fitID is None:
            return None

        fit = eos.db.getFit(fitID)
        fit.factorReload = not fit.factorReload
        eos.db.commit()
        self.recalc(fit)

    def switchFit(self, fitID):
        if fitID is None:
            return None

        fit = eos.db.getFit(fitID)

        if self.serviceFittingOptions["useGlobalCharacter"]:
            if fit.character != self.character:
                fit.character = self.character

        if self.serviceFittingOptions["useGlobalDamagePattern"]:
            if fit.damagePattern != self.pattern:
                fit.damagePattern = self.pattern

        eos.db.commit()
        self.recalc(fit, withBoosters=True)

    def getFit(self, fitID, projected = False):
        ''' Gets fit from database, and populates fleet data.

        Projected is a recursion flag that is set to reduce recursions into projected fits
        '''
        if fitID is None:
            return None
        fit = eos.db.getFit(fitID)
        inited = getattr(fit, "inited", None)

        if inited is None or inited is False:
            sFleet = Fleet.getInstance()
            f = sFleet.getLinearFleet(fit)
            if f is None:
                sFleet.removeAssociatedFleetData(fit)
                fit.fleet = None
            else:
                fit.fleet = f

            if not projected:
                print "Not projected, getting projected fits"
                for fitP in fit.projectedFits:
                    self.getFit(fitP.ID, projected = True)
                self.recalc(fit, withBoosters=True)
                fit.fill()

            eos.db.commit()
            fit.inited = True
        return fit

    def searchFits(self, name):
        results = eos.db.searchFits(name)
        fits = []
        for fit in results:
            fits.append((
                fit.ID, fit.name, fit.ship.item.ID, fit.ship.item.name, fit.booster,
                fit.timestamp))
        return fits

    def addImplant(self, fitID, itemID):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        item = eos.db.getItem(itemID, eager="attributes")
        try:
            implant = eos.types.Implant(item)
        except ValueError:
            return False

        fit.implants.append(implant)
        self.recalc(fit)
        return True

    def removeImplant(self, fitID, position):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        implant = fit.implants[position]
        fit.implants.remove(implant)
        self.recalc(fit)
        return True

    def addBooster(self, fitID, itemID):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        item = eos.db.getItem(itemID, eager="attributes")
        try:
            booster = eos.types.Booster(item)
        except ValueError:
            return False

        fit.boosters.append(booster)
        self.recalc(fit)
        return True

    def removeBooster(self, fitID, position):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        booster = fit.boosters[position]
        fit.boosters.remove(booster)
        self.recalc(fit)
        return True

    def project(self, fitID, thing):
        fit = eos.db.getFit(fitID)

        if isinstance(thing, int):
            thing = eos.db.getItem(thing,
                                   eager=("attributes", "group.category"))

        if isinstance(thing, eos.types.Fit):
            if thing in fit.projectedFits:
                return

            fit.__projectedFits[thing.ID] = thing

            # this bit is required -- see GH issue # 83
            eos.db.saveddata_session.flush()
            eos.db.saveddata_session.refresh(thing)
        elif thing.category.name == "Drone":
            drone = None
            for d in fit.projectedDrones.find(thing):
                if d is None or d.amountActive == d.amount or d.amount >= 5:
                    drone = d
                    break

            if drone is None:
                drone = eos.types.Drone(thing)
                fit.projectedDrones.append(drone)

            drone.amount += 1
        elif thing.group.name == "Effect Beacon":
            module = eos.types.Module(thing)
            module.state = State.ONLINE
            fit.projectedModules.append(module)
        else:
            module = eos.types.Module(thing)
            module.state = State.ACTIVE
            if not module.canHaveState(module.state, fit):
                module.state = State.OFFLINE
            fit.projectedModules.append(module)

        eos.db.commit()
        self.recalc(fit)
        return True

    def toggleProjected(self, fitID, thing, click):
        fit = eos.db.getFit(fitID)
        if isinstance(thing, eos.types.Drone):
            if thing.amountActive == 0 and thing.canBeApplied(fit):
                thing.amountActive = thing.amount
            else:
                thing.amountActive = 0
        elif isinstance(thing, eos.types.Module):
            thing.state = self.__getProposedState(thing, click)
            if not thing.canHaveState(thing.state, fit):
                thing.state = State.OFFLINE
        elif isinstance(thing, eos.types.Fit):
            print "toggle fit"
            projectionInfo = thing.getProjectionInfo(fitID)
            if projectionInfo:
                projectionInfo.active = not projectionInfo.active

        eos.db.commit()
        self.recalc(fit)

    def changeAmount(self, fitID, projected_fit, amount):
        """Change amount of projected fits"""
        fit = eos.db.getFit(fitID)
        amount = min(20, max(1, amount))  # 1 <= a <= 20
        projectionInfo = projected_fit.getProjectionInfo(fitID)
        if projectionInfo:
            projectionInfo.amount = amount

        eos.db.commit()
        self.recalc(fit)

    def removeProjected(self, fitID, thing):
        fit = eos.db.getFit(fitID)
        if isinstance(thing, eos.types.Drone):
            fit.projectedDrones.remove(thing)
        elif isinstance(thing, eos.types.Module):
            fit.projectedModules.remove(thing)
        else:
            del fit.__projectedFits[thing.ID]
            #fit.projectedFits.remove(thing)

        eos.db.commit()
        self.recalc(fit)

    def appendModule(self, fitID, itemID):
        fit = eos.db.getFit(fitID)
        item = eos.db.getItem(itemID, eager=("attributes", "group.category"))
        try:
            m = eos.types.Module(item)
        except ValueError:
            return False

        if m.item.category.name == "Subsystem":
            fit.modules.freeSlot(m.getModifiedItemAttr("subSystemSlot"))

        if m.fits(fit):
            m.owner = fit
            numSlots = len(fit.modules)
            fit.modules.append(m)
            if m.isValidState(State.ACTIVE):
                m.state = State.ACTIVE

            # As some items may affect state-limiting attributes of the ship, calculate new attributes first
            self.recalc(fit)
            # Then, check states of all modules and change where needed. This will recalc if needed
            self.checkStates(fit, m)

            fit.fill()
            eos.db.commit()

            return numSlots != len(fit.modules)
        else:
            return None

    def removeModule(self, fitID, position):
        fit = eos.db.getFit(fitID)
        if fit.modules[position].isEmpty:
            return None

        numSlots = len(fit.modules)
        fit.modules.toDummy(position)
        self.recalc(fit)
        self.checkStates(fit, None)
        fit.fill()
        eos.db.commit()
        return numSlots != len(fit.modules)

    def moveCargoToModule(self, fitID, moduleIdx, cargoIdx, copyMod=False):
        """
        Moves cargo to fitting window. Can either do a copy, move, or swap with current module
        If we try to copy/move into a spot with a non-empty module, we swap instead.

        To avoid redundancy in converting Cargo item, this function does the
        sanity checks as opposed to the GUI View. This is different than how the
        normal .swapModules() does things, which is mostly a blind swap.
        """
        fit = eos.db.getFit(fitID)

        module = fit.modules[moduleIdx]

        # Gather modules and convert Cargo item to Module, silently return if not a module
        try:
            cargoP = eos.types.Module(fit.cargo[cargoIdx].item)
            cargoP.owner = fit
            if cargoP.isValidState(State.ACTIVE):
                cargoP.state = State.ACTIVE
        except:
            return

        if cargoP.slot != module.slot:  # can't swap modules to different racks
            return

        # remove module that we are trying to move cargo to
        fit.modules.remove(module)

        if not cargoP.fits(fit):  # if cargo doesn't fit, rollback and return
            fit.modules.insert(moduleIdx, module)
            return

        fit.modules.insert(moduleIdx, cargoP)

        if not copyMod:  # remove existing cargo if not cloning
            fit.cargo.remove(fit.cargo[cargoIdx])

        if not module.isEmpty:  # if module is placeholder, we don't want to convert/add it
            moduleP = eos.types.Cargo(module.item)
            moduleP.amount = 1
            fit.cargo.insert(cargoIdx, moduleP)

        eos.db.commit()
        self.recalc(fit)

    def swapModules(self, fitID, src, dst):
        fit = eos.db.getFit(fitID)
        # Gather modules
        srcMod = fit.modules[src]
        dstMod = fit.modules[dst]

        # To swap, we simply remove mod and insert at destination.
        fit.modules.remove(srcMod)
        fit.modules.insert(dst, srcMod)
        fit.modules.remove(dstMod)
        fit.modules.insert(src, dstMod)

        eos.db.commit()

    def cloneModule(self, fitID, src, dst):
        """
        Clone a module from src to dst

        This will overwrite dst! Checking for empty module must be
        done at a higher level
        """
        fit = eos.db.getFit(fitID)
        # Gather modules
        srcMod = fit.modules[src]
        dstMod = fit.modules[dst]  # should be a placeholder module

        new = copy.deepcopy(srcMod)
        new.owner = fit
        if new.fits(fit):
            # insert copy if module meets hardpoint restrictions
            fit.modules.remove(dstMod)
            fit.modules.insert(dst, new)

            eos.db.commit()
            self.recalc(fit)

    def addCargo(self, fitID, itemID, amount=1, replace=False):
        """
        Adds cargo via typeID of item. If replace = True, we replace amount with
        given parameter, otherwise we increment
        """

        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        item = eos.db.getItem(itemID)
        cargo = None

        # adding from market
        for x in fit.cargo.find(item):
            if x is not None:
                # found item already in cargo, use previous value and remove old
                cargo = x
                fit.cargo.remove(x)
                break

        if cargo is None:
            # if we don't have the item already in cargo, use default values
            cargo = eos.types.Cargo(item)

        fit.cargo.append(cargo)
        if replace:
            cargo.amount = amount
        else:
            cargo.amount += amount

        self.recalc(fit)
        eos.db.commit()

        return True

    def removeCargo(self, fitID, position):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        charge = fit.cargo[position]
        fit.cargo.remove(charge)
        self.recalc(fit)
        return True

    def addDrone(self, fitID, itemID):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        item = eos.db.getItem(itemID, eager=("attributes", "group.category"))
        if item.category.name == "Drone":
            drone = None
            for d in fit.drones.find(item):
                if d is not None and d.amountActive == 0 and d.amount < max(5, fit.extraAttributes["maxActiveDrones"]):
                    drone = d
                    break

            if drone is None:
                drone = eos.types.Drone(item)
                if drone.fits(fit) is True:
                    fit.drones.append(drone)
                else:
                    return False
            drone.amount += 1
            eos.db.commit()
            self.recalc(fit)
            return True
        else:
            return False

    def mergeDrones(self, fitID, d1, d2, projected=False):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        if d1.item != d2.item:
            return False

        if projected:
            fit.projectedDrones.remove(d1)
        else:
            fit.drones.remove(d1)

        d2.amount += d1.amount
        d2.amountActive += d1.amountActive if d1.amountActive > 0 else -d2.amountActive
        eos.db.commit()
        self.recalc(fit)
        return True

    def splitDrones(self, fit, d, amount, l):
        total = d.amount
        active = d.amountActive > 0
        d.amount = amount
        d.amountActive = amount if active else 0

        newD = eos.types.Drone(d.item)
        newD.amount = total - amount
        newD.amountActive = newD.amount if active else 0
        l.append(newD)
        eos.db.commit()

    def splitProjectedDroneStack(self, fitID, d, amount):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        self.splitDrones(fit, d, amount, fit.projectedDrones)

    def splitDroneStack(self, fitID, d, amount):
        if fitID is None:
            return False

        fit = eos.db.getFit(fitID)
        self.splitDrones(fit, d, amount, fit.drones)

    def removeDrone(self, fitID, i, numDronesToRemove=1):
        fit = eos.db.getFit(fitID)
        d = fit.drones[i]
        d.amount -= numDronesToRemove
        if d.amountActive > 0:
            d.amountActive -= numDronesToRemove

        if d.amount == 0:
            del fit.drones[i]

        eos.db.commit()
        self.recalc(fit)
        return True

    def toggleDrone(self, fitID, i):
        fit = eos.db.getFit(fitID)
        d = fit.drones[i]
        if d.amount == d.amountActive:
            d.amountActive = 0
        else:
            d.amountActive = d.amount

        eos.db.commit()
        self.recalc(fit)
        return True

    def toggleImplant(self, fitID, i):
        fit = eos.db.getFit(fitID)
        implant = fit.implants[i]
        implant.active = not implant.active

        eos.db.commit()
        self.recalc(fit)
        return True

    def toggleBooster(self, fitID, i):
        fit = eos.db.getFit(fitID)
        booster = fit.boosters[i]
        booster.active = not booster.active

        eos.db.commit()
        self.recalc(fit)
        return True

    def changeChar(self, fitID, charID):
        if fitID is None or charID is None:
            if charID is not None:
                self.character = Character.getInstance().all5()

            return

        fit = eos.db.getFit(fitID)
        fit.character = self.character = eos.db.getCharacter(charID)
        self.recalc(fit)

    def isAmmo(self, itemID):
        return eos.db.getItem(itemID).category.name == "Charge"

    def setAmmo(self, fitID, ammoID, modules):
        if fitID is None:
            return

        fit = eos.db.getFit(fitID)
        ammo = eos.db.getItem(ammoID) if ammoID else None

        for mod in modules:
            if mod.isValidCharge(ammo):
                mod.charge = ammo

        self.recalc(fit)

    def getTargetResists(self, fitID):
        if fitID is None:
            return

        fit = eos.db.getFit(fitID)
        return fit.targetResists

    def setTargetResists(self, fitID, pattern):
        if fitID is None:
            return

        fit = eos.db.getFit(fitID)
        fit.targetResists = pattern
        eos.db.commit()

        self.recalc(fit)

    def getDamagePattern(self, fitID):
        if fitID is None:
            return

        fit = eos.db.getFit(fitID)
        return fit.damagePattern

    def setDamagePattern(self, fitID, pattern):
        if fitID is None:
            return

        fit = eos.db.getFit(fitID)
        fit.damagePattern = self.pattern = pattern
        eos.db.commit()

        self.recalc(fit)

    def setMode(self, fitID, mode):
        if fitID is None:
            return

        fit = eos.db.getFit(fitID)
        fit.mode = mode
        eos.db.commit()

        self.recalc(fit)

    def setAsPattern(self, fitID, ammo):
        if fitID is None:
            return

        sDP = DamagePattern.getInstance()
        dp = sDP.getDamagePattern("Selected Ammo")
        if dp is None:
            dp = eos.types.DamagePattern()
            dp.name = "Selected Ammo"

        fit = eos.db.getFit(fitID)
        for attr in ("em", "thermal", "kinetic", "explosive"):
            setattr(dp, "%sAmount" % attr, ammo.getAttribute("%sDamage" % attr) or 0)

        fit.damagePattern = dp
        self.recalc(fit)

    def exportFit(self, fitID):
        fit = eos.db.getFit(fitID)
        return Port.exportEft(fit)

    def exportEftImps(self, fitID):
        fit = eos.db.getFit(fitID)
        return Port.exportEftImps(fit)

    def exportDna(self, fitID):
        fit = eos.db.getFit(fitID)
        return Port.exportDna(fit)

    def exportXml(self, callback=None, *fitIDs):
        fits = map(lambda fitID: eos.db.getFit(fitID), fitIDs)
        return Port.exportXml(callback, *fits)

    def backupFits(self, path, callback):
        thread = FitBackupThread(path, callback)
        thread.start()

    def importFitsThreaded(self, paths, callback):
        thread = FitImportThread(paths, callback)
        thread.start()

    def importFitFromFiles(self, paths, callback=None):
        """
        Imports fits from file(s). First processes all provided paths and stores
        assembled fits into a list. This allows us to call back to the GUI as
        fits are processed as well as when fits are being saved.

        returns
        """
        defcodepage = locale.getpreferredencoding()

        fits = []
        for path in paths:
            if callback:  # Pulse
                wx.CallAfter(callback, "Processing file:\n%s"%path)

            file = open(path, "r")
            srcString = file.read()
            codec_found = None
            # If file had ANSI encoding, convert it to unicode using system
            # default codepage, or use fallbacks UTF-16, then cp1252 on any
            # encoding errors
            if isinstance(srcString, str):
                attempt_codecs = (defcodepage, "utf-16", "cp1252")
                for page in attempt_codecs:
                    try:
                        srcString = unicode(srcString, page)
                        codec_found = page
                    except UnicodeDecodeError:
                        logger.warn("Error unicode decoding %s from page %s, trying next codec", path, page)
                    else:
                        break
            else:
                # nasty hack to detect other transparent utf-16 loading
                if srcString[0] == '<' and 'utf-16' in srcString[:128].lower():
                    codec_found = "utf-16"
                else:
                    codec_found = "utf-8"

            _, fitsImport = Port.importAuto(srcString, path, callback=callback, encoding=codec_found)
            fits += fitsImport

        IDs = []
        numFits = len(fits)
        for i, fit in enumerate(fits):
            # Set some more fit attributes and save
            fit.character = self.character
            fit.damagePattern = self.pattern
            fit.targetResists = self.targetResists
            eos.db.save(fit)
            IDs.append(fit.ID)
            if callback:  # Pulse
                wx.CallAfter(
                    callback,
                    "Processing complete, saving fits to database\n(%d/%d)" %
                    (i+1, numFits)
                )

        return fits

    def importFitFromBuffer(self, bufferStr, activeFit=None):
        _, fits = Port.importAuto(bufferStr, activeFit=activeFit)
        for fit in fits:
            fit.character = self.character
            fit.damagePattern = self.pattern
            fit.targetResists = self.targetResists
            eos.db.save(fit)
        return fits

    def checkStates(self, fit, base):
        changed = False
        for mod in fit.modules:
            if mod != base:
                if not mod.canHaveState(mod.state):
                    mod.state = State.ONLINE
                    changed = True
        for mod in fit.projectedModules:
            if not mod.canHaveState(mod.state, fit):
                mod.state = State.OFFLINE
                changed = True
        for drone in fit.projectedDrones:
            if drone.amountActive > 0 and not drone.canBeApplied(fit):
                drone.amountActive = 0
                changed = True

        # If any state was changed, recalculate attributes again
        if changed:
            self.recalc(fit)

    def toggleModulesState(self, fitID, base, modules, click):
        proposedState = self.__getProposedState(base, click)
        if proposedState != base.state:
            base.state = proposedState
            for mod in modules:
                if mod != base:
                    mod.state = self.__getProposedState(mod, click,
                                                        proposedState)

        eos.db.commit()
        fit = eos.db.getFit(fitID)

        # As some items may affect state-limiting attributes of the ship, calculate new attributes first
        self.recalc(fit)
        # Then, check states of all modules and change where needed. This will recalc if needed
        self.checkStates(fit, base)

    # Old state : New State
    localMap = {State.OVERHEATED: State.ACTIVE,
                State.ACTIVE: State.ONLINE,
                State.OFFLINE: State.ONLINE,
                State.ONLINE: State.ACTIVE}
    projectedMap = {State.OVERHEATED: State.ACTIVE,
                    State.ACTIVE: State.OFFLINE,
                    State.OFFLINE: State.ACTIVE,
                    State.ONLINE: State.ACTIVE}  # Just in case

    def __getProposedState(self, mod, click, proposedState=None):
        if mod.slot is Slot.SUBSYSTEM or mod.isEmpty:
            return State.ONLINE

        currState = mod.state
        transitionMap = self.projectedMap if mod.projected else self.localMap
        if proposedState is not None:
            state = proposedState
        elif click == "right":
            state = State.OVERHEATED
        elif click == "ctrl":
            state = State.OFFLINE
        else:
            state = transitionMap[currState]
            if not mod.isValidState(state):
                state = -1

        if mod.isValidState(state):
            return state
        else:
            return currState

    def refreshFit(self, fitID):
        if fitID is None:
            return None

        fit = eos.db.getFit(fitID)
        eos.db.commit()
        self.recalc(fit)

    def recalc(self, fit, withBoosters=False):
        logger.debug("="*10+"recalc"+"="*10)
        if fit.factorReload is not self.serviceFittingOptions["useGlobalForceReload"]:
            fit.factorReload = self.serviceFittingOptions["useGlobalForceReload"]
        fit.clear()
        fit.calculateModifiedAttributes(withBoosters=withBoosters, dirtyStorage=self.dirtyFitIDs)
