# ===============================================================================
# Copyright (C) 2010 Diego Duclos
#
# This file is part of eos.
#
# eos is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# eos is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with eos.  If not, see <http://www.gnu.org/licenses/>.
# ===============================================================================

import copy
import time
from copy import deepcopy
from itertools import chain
from math import sqrt, log, asinh

from sqlalchemy.orm import validates, reconstructor

import eos.db
from eos import capSim
from eos.effectHandlerHelpers import *
from eos.effectHandlerHelpers import HandledModuleList, HandledDroneCargoList, HandledImplantBoosterList, HandledProjectedDroneList, HandledProjectedModList
from eos.enum import Enum
from eos.saveddata.module import State, Hardpoint
from eos.types import Ship, Character, Slot, Module, Citadel
from utils.timer import Timer
import logging

logger = logging.getLogger(__name__)

try:
    from collections import OrderedDict
except ImportError:
    from utils.compat import OrderedDict


class ImplantLocation(Enum):
    def __init__(self):
        pass

    FIT = 0
    CHARACTER = 1


class Fit(object):
    """Represents a fitting, with modules, ship, implants, etc."""

    PEAK_RECHARGE = 0.25

    def __init__(self, ship=None, name=""):
        """Initialize a fit from the program"""
        # use @mode.setter's to set __attr and IDs. This will set mode as well
        self.ship = ship
        if self.ship:
            self.ship.parent = self

        self.__modules = HandledModuleList()
        self.__drones = HandledDroneCargoList()
        self.__fighters = HandledDroneCargoList()
        self.__cargo = HandledDroneCargoList()
        self.__implants = HandledImplantBoosterList()
        self.__boosters = HandledImplantBoosterList()
        # self.__projectedFits = {}
        self.__projectedModules = HandledProjectedModList()
        self.__projectedDrones = HandledProjectedDroneList()
        self.__projectedFighters = HandledProjectedDroneList()
        self.__character = None
        self.__owner = None

        self.projected = False
        self.name = name
        self.timestamp = time.time()
        self.modeID = None

        self.build()

    @reconstructor
    def init(self):
        """Initialize a fit from the database and validate"""
        self.__ship = None
        self.__mode = None

        if self.shipID:
            item = eos.db.getItem(self.shipID)
            if item is None:
                logger.error("Item (id: %d) does not exist", self.shipID)
                return

            try:
                try:
                    self.__ship = Ship(item, self)
                except ValueError:
                    self.__ship = Citadel(item, self)
                # @todo extra attributes is now useless, however it set to be
                # the same as ship attributes for ease (so we don't have to
                # change all instances in source). Remove this at some point
                self.extraAttributes = self.__ship.itemModifiedAttributes
            except ValueError:
                logger.error("Item (id: %d) is not a Ship", self.shipID)
                return

        if self.modeID and self.__ship:
            item = eos.db.getItem(self.modeID)
            # Don't need to verify if it's a proper item, as validateModeItem assures this
            self.__mode = self.ship.validateModeItem(item)
        else:
            self.__mode = self.ship.validateModeItem(None)

        self.build()

    def build(self):
        self.__extraDrains = []
        self.__ehp = None
        self.__weaponDPS = None
        self.__minerYield = None
        self.__weaponVolley = None
        self.__droneDPS = None
        self.__droneVolley = None
        self.__droneYield = None
        self.__sustainableTank = None
        self.__effectiveSustainableTank = None
        self.__effectiveTank = None
        self.__calculated = False
        self.__capStable = None
        self.__capState = None
        self.__capUsed = None
        self.__capRecharge = None
        self.__calculatedTargets = []
        self.factorReload = False
        self.fleet = None
        self.boostsFits = set()
        self.gangBoosts = None
        self.ecmProjectedStr = 1
        self.commandBonuses = {}

    @property
    def targetResists(self):
        return self.__targetResists

    @targetResists.setter
    def targetResists(self, targetResists):
        self.__targetResists = targetResists
        self.__weaponDPS = None
        self.__weaponVolley = None
        self.__droneDPS = None
        self.__droneVolley = None

    @property
    def damagePattern(self):
        return self.__damagePattern

    @damagePattern.setter
    def damagePattern(self, damagePattern):
        self.__damagePattern = damagePattern
        self.__ehp = None
        self.__effectiveTank = None

    @property
    def isInvalid(self):
        return self.__ship is None

    @property
    def mode(self):
        return self.__mode

    @mode.setter
    def mode(self, mode):
        self.__mode = mode
        self.modeID = mode.item.ID if mode is not None else None

    @property
    def character(self):
        return self.__character if self.__character is not None else Character.getAll0()

    @character.setter
    def character(self, char):
        self.__character = char

    @property
    def ship(self):
        return self.__ship

    @ship.setter
    def ship(self, ship):
        self.__ship = ship
        self.shipID = ship.item.ID if ship is not None else None
        if ship is not None:
            #  set mode of new ship
            self.mode = self.ship.validateModeItem(None) if ship is not None else None
            # set fit attributes the same as ship
            self.extraAttributes = self.ship.itemModifiedAttributes

    @property
    def isStructure(self):
        return isinstance(self.ship, Citadel)

    @property
    def drones(self):
        return self.__drones

    @property
    def fighters(self):
        return self.__fighters

    @property
    def cargo(self):
        return self.__cargo

    @property
    def modules(self):
        return self.__modules

    @property
    def implants(self):
        return self.__implants

    @property
    def boosters(self):
        return self.__boosters

    @property
    def projectedModules(self):
        return self.__projectedModules

    @property
    def projectedFits(self):
        # only in extreme edge cases will the fit be invalid, but to be sure do
        # not return them.
        return [fit for fit in self.__projectedFits.values() if not fit.isInvalid]

    @property
    def commandFits(self):
        return [fit for fit in self.__commandFits.values() if not fit.isInvalid]

    def getProjectionInfo(self, fitID):
        return self.projectedOnto.get(fitID, None)

    def getCommandInfo(self, fitID):
        return self.boostedOnto.get(fitID, None)

    @property
    def projectedDrones(self):
        return self.__projectedDrones

    @property
    def projectedFighters(self):
        return self.__projectedFighters

    @property
    def weaponDPS(self):
        if self.__weaponDPS is None:
            self.calculateWeaponStats()

        return self.__weaponDPS

    @property
    def weaponVolley(self):
        if self.__weaponVolley is None:
            self.calculateWeaponStats()

        return self.__weaponVolley

    @property
    def droneDPS(self):
        if self.__droneDPS is None:
            self.calculateWeaponStats()

        return self.__droneDPS

    @property
    def droneVolley(self):
        if self.__droneVolley is None:
            self.calculateWeaponStats()

        return self.__droneVolley

    @property
    def totalDPS(self):
        return self.droneDPS + self.weaponDPS

    @property
    def totalVolley(self):
        return self.droneVolley + self.weaponVolley

    @property
    def minerYield(self):
        if self.__minerYield is None:
            self.calculateMiningStats()

        return self.__minerYield

    @property
    def droneYield(self):
        if self.__droneYield is None:
            self.calculateMiningStats()

        return self.__droneYield

    @property
    def totalYield(self):
        return self.droneYield + self.minerYield

    @property
    def maxTargets(self):
        return min(self.extraAttributes["maxTargetsLockedFromSkills"],
                   self.ship.getModifiedItemAttr("maxLockedTargets"))

    @property
    def maxTargetRange(self):
        return self.ship.getModifiedItemAttr("maxTargetRange")

    @property
    def scanStrength(self):
        return max([self.ship.getModifiedItemAttr("scan%sStrength" % scanType)
                    for scanType in ("Magnetometric", "Ladar", "Radar", "Gravimetric")])

    @property
    def scanType(self):
        maxStr = -1
        type = None
        for scanType in ("Magnetometric", "Ladar", "Radar", "Gravimetric"):
            currStr = self.ship.getModifiedItemAttr("scan%sStrength" % scanType)
            if currStr > maxStr:
                maxStr = currStr
                type = scanType
            elif currStr == maxStr:
                type = "Multispectral"

        return type

    @property
    def jamChance(self):
        return (1 - self.ecmProjectedStr) * 100

    @property
    def maxSpeed(self):
        speedLimit = self.ship.getModifiedItemAttr("speedLimit")
        if speedLimit and self.ship.getModifiedItemAttr("maxVelocity") > speedLimit:
            return speedLimit

        return self.ship.getModifiedItemAttr("maxVelocity")

    @property
    def alignTime(self):
        agility = self.ship.getModifiedItemAttr("agility") or 0
        mass = self.ship.getModifiedItemAttr("mass")

        return -log(0.25) * agility * mass / 1000000

    @property
    def implantSource(self):
        return self.implantLocation

    @implantSource.setter
    def implantSource(self, source):
        self.implantLocation = source

    @property
    def appliedImplants(self):
        if self.implantLocation == ImplantLocation.CHARACTER:
            return self.character.implants
        else:
            return self.implants

    @validates("ID", "ownerID", "shipID")
    def validator(self, key, val):
        map = {"ID": lambda val: isinstance(val, int),
               "ownerID": lambda val: isinstance(val, int) or val is None,
               "shipID": lambda val: isinstance(val, int) or val is None}

        if not map[key](val):
            raise ValueError(str(val) + " is not a valid value for " + key)
        else:
            return val

    def clear(self, projected=False):
        self.__effectiveTank = None
        self.__weaponDPS = None
        self.__minerYield = None
        self.__weaponVolley = None
        self.__effectiveSustainableTank = None
        self.__sustainableTank = None
        self.__droneDPS = None
        self.__droneVolley = None
        self.__droneYield = None
        self.__ehp = None
        self.__calculated = False
        self.__capStable = None
        self.__capState = None
        self.__capUsed = None
        self.__capRecharge = None
        self.ecmProjectedStr = 1
        self.commandBonuses = {}

        del self.__calculatedTargets[:]
        del self.__extraDrains[:]

        if self.ship:
            self.ship.clear()

        c = chain(
            self.modules,
            self.drones,
            self.fighters,
            self.boosters,
            self.implants,
            self.projectedDrones,
            self.projectedModules,
            self.projectedFighters,
            (self.character, self.extraAttributes),
        )

        for stuff in c:
            if stuff is not None and stuff != self:
                stuff.clear()

        # If this is the active fit that we are clearing, not a projected fit,
        # then this will run and clear the projected ships and flag the next
        # iteration to skip this part to prevent recursion.
        if not projected:
            for stuff in self.projectedFits:
                if stuff is not None and stuff != self:
                    stuff.clear(projected=True)

    # Methods to register and get the thing currently affecting the fit,
    # so we can correctly map "Affected By"
    def register(self, currModifier, origin=None):
        self.__modifier = currModifier
        self.__origin = origin
        if hasattr(currModifier, "itemModifiedAttributes"):
            currModifier.itemModifiedAttributes.fit = origin or self
        if hasattr(currModifier, "chargeModifiedAttributes"):
            currModifier.chargeModifiedAttributes.fit = origin or self

    def getModifier(self):
        return self.__modifier

    def getOrigin(self):
        return self.__origin

    def addCommandBonus(self, warfareBuffID, value, module, effect, runTime="normal"):
        # oh fuck this is so janky
        # @todo should we pass in min/max to this function, or is abs okay?
        # (abs is old method, ccp now provides the aggregate function in their data)
        print "Add command bonus: ", warfareBuffID, " - value: ", value

        if warfareBuffID not in self.commandBonuses or abs(self.commandBonuses[warfareBuffID][1]) < abs(value):
            self.commandBonuses[warfareBuffID] = (runTime, value, module, effect)

    def __runCommandBoosts(self, runTime="normal"):
        logger.debug("Applying gang boosts for %r", self)
        for warfareBuffID in self.commandBonuses.keys():
            # Unpack all data required to run effect properly
            effect_runTime, value, thing, effect = self.commandBonuses[warfareBuffID]

            if runTime != effect_runTime:
                continue

            context = ("commandRun", thing.__class__.__name__.lower())
            if isinstance(thing, Module):
                # This should always be a gang effect, otherwise it wouldn't be added to commandBonuses
                # @todo: Check this
                if effect.isType("gang"):
                    # todo: ensure that these are run with the module is active only
                    context += ("commandRun",)
                    self.register(thing)
                    effect.handler(self, thing, context, warfareBuffID=warfareBuffID)

                # if effect.isType("offline") or (effect.isType("passive") and thing.state >= State.ONLINE) or \
                # (effect.isType("active") and thing.state >= State.ACTIVE):
                #     # Run effect, and get proper bonuses applied
                #     try:
                #         self.register(thing)
                #         effect.handler(self, thing, context)
                #     except:
                #         pass
            else:
                # Run effect, and get proper bonuses applied
                try:
                    self.register(thing)
                    effect.handler(self, thing, context)
                except:
                    pass

            del self.commandBonuses[warfareBuffID]

    def calculateModifiedAttributes(self, targetFit=None, withBoosters=False, dirtyStorage=None):
        timer = Timer(u'Fit: {}, {}'.format(self.ID, self.name), logger)
        logger.debug("Starting fit calculation on: %r, withBoosters: %s", self, withBoosters)

        shadow = False
        if targetFit and not withBoosters:
            logger.debug("Applying projections to target: %r", targetFit)
            projectionInfo = self.getProjectionInfo(targetFit.ID)
            logger.debug("ProjectionInfo: %s", projectionInfo)
            if self == targetFit:
                copied = self  # original fit
                shadow = True
                # Don't inspect this, we genuinely want to reassign self
                # noinspection PyMethodFirstArgAssignment
                self = copy.deepcopy(self)
                self.fleet = copied.fleet
                logger.debug("Handling self projection - making shadow copy of fit. %r => %r", copied, self)
                # we delete the fit because when we copy a fit, flush() is
                # called to properly handle projection updates. However, we do
                # not want to save this fit to the database, so simply remove it
                eos.db.saveddata_session.delete(self)

        if self.commandFits and not withBoosters:
            print "Calculatate command fits and apply to fit"
            for fit in self.commandFits:
                if self == fit:
                    print "nope"
                    continue
                print "calculating ", fit
                fit.calculateModifiedAttributes(self, True)
                #
                # for thing in chain(fit.modules, fit.implants, fit.character.skills, (fit.ship,)):
                #     if thing.item is None:
                #         continue
                #     for effect in thing.item.effects.itervalues():
                #         # And check if it actually has gang boosting effects
                #         if effect.isType("gang"):
                #             effect.handler(self, thing, ("commandRun"))

        # if self.fleet is not None and withBoosters is True:
        #     logger.debug("Fleet is set, gathering gang boosts")
        #
        #     self.gangBoosts = self.fleet.recalculateLinear(withBoosters=withBoosters)
        #
        #     timer.checkpoint("Done calculating gang boosts for %r"%self)

        # elif self.fleet is None:
        #     self.gangBoosts = None

        # If we're not explicitly asked to project fit onto something,
        # set self as target fit
        if targetFit is None:
            targetFit = self
            projected = False
        else:
            projected = not withBoosters

        # If fit is calculated and we have nothing to do here, get out

        # A note on why projected fits don't get to return here. If we return
        # here, the projection afflictions will not be run as they are
        # intertwined into the regular fit calculations. So, even if the fit has
        # been calculated, we need to recalculate it again just to apply the
        # projections. This is in contract to gang boosts, which are only
        # calculated once, and their items are then looped and accessed with
        #     self.gangBoosts.iteritems()
        # We might be able to exit early in the fit calculations if we separate
        # projections from the normal fit calculations. But we must ensure that
        # projection have modifying stuff applied, such as gang boosts and other
        # local modules that may help
        if self.__calculated and not projected and not withBoosters:
            logger.debug("Fit has already been calculated and is not projected, returning: %r", self)
            return

        for runTime in ("early", "normal", "late"):
            # Items that are unrestricted. These items are run on the local fit
            # first and then projected onto the target fit it one is designated
            u = [
                (self.character, self.ship),
                self.drones,
                self.fighters,
                self.boosters,
                self.appliedImplants,
                self.modules
            ] if not self.isStructure else [
                # Ensure a restricted set for citadels
                (self.character, self.ship),
                self.fighters,
                self.modules
            ]

            # Items that are restricted. These items are only run on the local
            # fit. They are NOT projected onto the target fit. # See issue 354
            r = [(self.mode,), self.projectedDrones, self.projectedFighters, self.projectedModules]

            # chain unrestricted and restricted into one iterable
            c = chain.from_iterable(u + r)

            # We calculate gang bonuses first so that projected fits get them
            # if self.gangBoosts is not None:
            #     self.__calculateGangBoosts(runTime)

            for item in c:
                # Registering the item about to affect the fit allows us to
                # track "Affected By" relations correctly
                if item is not None:
                    if not self.__calculated:
                        # apply effects locally if this is first time running them on fit
                        self.register(item)
                        item.calculateModifiedAttributes(self, runTime, False)

                    if projected is True and item not in chain.from_iterable(r):
                        # apply effects onto target fit
                        for _ in xrange(projectionInfo.amount):
                            targetFit.register(item, origin=self)
                            item.calculateModifiedAttributes(targetFit, runTime, True)

                    if targetFit and withBoosters and item in self.modules:
                        # Apply the gang boosts to target fit
                        # targetFit.register(item, origin=self)
                        item.calculateModifiedAttributes(targetFit, runTime, False, True)

            print "Command: "
            print self.commandBonuses

            if not withBoosters and self.commandBonuses:
                self.__runCommandBoosts(runTime)

            timer.checkpoint('Done with runtime: %s' % runTime)

        # Mark fit as calculated
        self.__calculated = True

        # Only apply projected fits if fit it not projected itself.
        if not projected:
            for fit in self.projectedFits:
                if fit.getProjectionInfo(self.ID).active:
                    fit.calculateModifiedAttributes(self, withBoosters=withBoosters, dirtyStorage=dirtyStorage)

        timer.checkpoint('Done with fit calculation')

        if shadow:
            logger.debug("Delete shadow fit object")
            del self

    def fill(self):
        """
        Fill this fit's module slots with enough dummy slots so that all slots are used.
        This is mostly for making the life of gui's easier.
        GUI's can call fill() and then stop caring about empty slots completely.
        """
        if self.ship is None:
            return

        for slotType in (Slot.LOW, Slot.MED, Slot.HIGH, Slot.RIG, Slot.SUBSYSTEM, Slot.SERVICE):
            amount = self.getSlotsFree(slotType, True)
            if amount > 0:
                for _ in xrange(int(amount)):
                    self.modules.append(Module.buildEmpty(slotType))

            if amount < 0:
                # Look for any dummies of that type to remove
                toRemove = []
                for mod in self.modules:
                    if mod.isEmpty and mod.slot == slotType:
                        toRemove.append(mod)
                        amount += 1
                        if amount == 0:
                            break
                for mod in toRemove:
                    self.modules.remove(mod)

    def unfill(self):
        for i in xrange(len(self.modules) - 1, -1, -1):
            mod = self.modules[i]
            if mod.isEmpty:
                del self.modules[i]

    @property
    def modCount(self):
        x = 0
        for i in xrange(len(self.modules) - 1, -1, -1):
            mod = self.modules[i]
            if not mod.isEmpty:
                x += 1
        return x

    def getItemAttrSum(self, dict, attr):
        amount = 0
        for mod in dict:
            add = mod.getModifiedItemAttr(attr)
            if add is not None:
                amount += add

        return amount

    def getItemAttrOnlineSum(self, dict, attr):
        amount = 0
        for mod in dict:
            add = mod.getModifiedItemAttr(attr) if mod.state >= State.ONLINE else None
            if add is not None:
                amount += add

        return amount

    def getHardpointsUsed(self, type):
        amount = 0
        for mod in self.modules:
            if mod.hardpoint is type and not mod.isEmpty:
                amount += 1

        return amount

    def getSlotsUsed(self, type, countDummies=False):
        amount = 0

        for mod in chain(self.modules, self.fighters):
            if mod.slot is type and (not getattr(mod, "isEmpty", False) or countDummies):
                if type in (Slot.F_HEAVY, Slot.F_SUPPORT, Slot.F_LIGHT) and not mod.active:
                    continue
                amount += 1

        return amount

    slots = {Slot.LOW: "lowSlots",
             Slot.MED: "medSlots",
             Slot.HIGH: "hiSlots",
             Slot.RIG: "rigSlots",
             Slot.SUBSYSTEM: "maxSubSystems",
             Slot.SERVICE: "serviceSlots",
             Slot.F_LIGHT: "fighterLightSlots",
             Slot.F_SUPPORT: "fighterSupportSlots",
             Slot.F_HEAVY: "fighterHeavySlots"}

    def getSlotsFree(self, type, countDummies=False):
        if type in (Slot.MODE, Slot.SYSTEM):
            # These slots don't really exist, return default 0
            return 0

        slotsUsed = self.getSlotsUsed(type, countDummies)
        totalSlots = self.ship.getModifiedItemAttr(self.slots[type]) or 0
        return int(totalSlots - slotsUsed)

    def getNumSlots(self, type):
        return self.ship.getModifiedItemAttr(self.slots[type]) or 0

    @property
    def calibrationUsed(self):
        return self.getItemAttrOnlineSum(self.modules, 'upgradeCost')

    @property
    def pgUsed(self):
        return self.getItemAttrOnlineSum(self.modules, "power")

    @property
    def cpuUsed(self):
        return self.getItemAttrOnlineSum(self.modules, "cpu")

    @property
    def droneBandwidthUsed(self):
        amount = 0
        for d in self.drones:
            amount += d.getModifiedItemAttr("droneBandwidthUsed") * d.amountActive

        return amount

    @property
    def droneBayUsed(self):
        amount = 0
        for d in self.drones:
            amount += d.item.volume * d.amount

        return amount

    @property
    def fighterBayUsed(self):
        amount = 0
        for f in self.fighters:
            amount += f.item.volume * f.amountActive

        return amount

    @property
    def fighterTubesUsed(self):
        amount = 0
        for f in self.fighters:
            if f.active:
                amount += 1

        return amount

    @property
    def cargoBayUsed(self):
        amount = 0
        for c in self.cargo:
            amount += c.getModifiedItemAttr("volume") * c.amount

        return amount

    @property
    def activeDrones(self):
        amount = 0
        for d in self.drones:
            amount += d.amountActive

        return amount

    # Expresses how difficult a target is to probe down with scan probes
    # If this is <1.08, the ship is unproabeable
    @property
    def probeSize(self):
        sigRad = self.ship.getModifiedItemAttr("signatureRadius")
        sensorStr = float(self.scanStrength)
        probeSize = sigRad / sensorStr if sensorStr != 0 else None
        # http://www.eveonline.com/ingameboard.asp?a=topic&threadID=1532170&page=2#42
        if probeSize is not None:
            # http://forum.eve-ru.com/index.php?showtopic=74195&view=findpost&p=1333691
            # http://forum.eve-ru.com/index.php?showtopic=74195&view=findpost&p=1333763
            # Tests by tester128 and several conclusions by me, prove that cap is in range
            # from 1.1 to 1.12, we're picking average value
            probeSize = max(probeSize, 1.11)
        return probeSize

    @property
    def warpSpeed(self):
        base = self.ship.getModifiedItemAttr("baseWarpSpeed") or 1
        multiplier = self.ship.getModifiedItemAttr("warpSpeedMultiplier") or 1
        return base * multiplier

    @property
    def maxWarpDistance(self):
        capacity = self.ship.getModifiedItemAttr("capacitorCapacity")
        mass = self.ship.getModifiedItemAttr("mass")
        warpCapNeed = self.ship.getModifiedItemAttr("warpCapacitorNeed")

        if not warpCapNeed:
            return 0

        return capacity / (mass * warpCapNeed)

    @property
    def capStable(self):
        if self.__capStable is None:
            self.simulateCap()

        return self.__capStable

    @property
    def capState(self):
        """
        If the cap is stable, the capacitor state is the % at which it is stable.
        If the cap is unstable, this is the amount of time before it runs out
        """
        if self.__capState is None:
            self.simulateCap()

        return self.__capState

    @property
    def capUsed(self):
        if self.__capUsed is None:
            self.simulateCap()

        return self.__capUsed

    @property
    def capRecharge(self):
        if self.__capRecharge is None:
            self.simulateCap()

        return self.__capRecharge

    @property
    def sustainableTank(self):
        if self.__sustainableTank is None:
            self.calculateSustainableTank()

        return self.__sustainableTank

    def calculateSustainableTank(self, effective=True):
        if self.__sustainableTank is None:
            if self.capStable:
                sustainable = {"armorRepair": self.extraAttributes["armorRepair"],
                               "shieldRepair": self.extraAttributes["shieldRepair"],
                               "hullRepair": self.extraAttributes["hullRepair"]}
            else:
                sustainable = {}

                repairers = []
                # Map a repairer type to the attribute it uses
                groupAttrMap = {"Armor Repair Unit": "armorDamageAmount",
                                "Ancillary Armor Repairer": "armorDamageAmount",
                                "Hull Repair Unit": "structureDamageAmount",
                                "Shield Booster": "shieldBonus",
                                "Ancillary Shield Booster": "shieldBonus",
                                "Remote Armor Repairer": "armorDamageAmount",
                                "Remote Shield Booster": "shieldBonus"}
                # Map repairer type to attribute
                groupStoreMap = {"Armor Repair Unit": "armorRepair",
                                 "Hull Repair Unit": "hullRepair",
                                 "Shield Booster": "shieldRepair",
                                 "Ancillary Shield Booster": "shieldRepair",
                                 "Remote Armor Repairer": "armorRepair",
                                 "Remote Shield Booster": "shieldRepair",
                                 "Ancillary Armor Repairer": "armorRepair", }

                capUsed = self.capUsed
                for attr in ("shieldRepair", "armorRepair", "hullRepair"):
                    sustainable[attr] = self.extraAttributes[attr]
                    dict = self.extraAttributes.getAfflictions(attr)
                    if self in dict:
                        for mod, _, amount, used in dict[self]:
                            if not used:
                                continue
                            if mod.projected is False:
                                usesCap = True
                                try:
                                    if mod.capUse:
                                        capUsed -= mod.capUse
                                    else:
                                        usesCap = False
                                except AttributeError:
                                    usesCap = False
                                # Modules which do not use cap are not penalized based on cap use
                                if usesCap:
                                    cycleTime = mod.getModifiedItemAttr("duration")
                                    amount = mod.getModifiedItemAttr(groupAttrMap[mod.item.group.name])
                                    sustainable[attr] -= amount / (cycleTime / 1000.0)
                                    repairers.append(mod)

                # Sort repairers by efficiency. We want to use the most efficient repairers first
                repairers.sort(key=lambda mod: mod.getModifiedItemAttr(
                    groupAttrMap[mod.item.group.name]) / mod.getModifiedItemAttr("capacitorNeed"), reverse=True)

                # Loop through every module until we're above peak recharge
                # Most efficient first, as we sorted earlier.
                # calculate how much the repper can rep stability & add to total
                totalPeakRecharge = self.capRecharge
                for mod in repairers:
                    if capUsed > totalPeakRecharge:
                        break
                    cycleTime = mod.cycleTime
                    capPerSec = mod.capUse
                    if capPerSec is not None and cycleTime is not None:
                        # Check how much this repper can work
                        sustainability = min(1, (totalPeakRecharge - capUsed) / capPerSec)

                        # Add the sustainable amount
                        amount = mod.getModifiedItemAttr(groupAttrMap[mod.item.group.name])
                        sustainable[groupStoreMap[mod.item.group.name]] += sustainability * (amount / (cycleTime / 1000.0))
                        capUsed += capPerSec

            sustainable["passiveShield"] = self.calculateShieldRecharge()
            self.__sustainableTank = sustainable

        return self.__sustainableTank

    def calculateCapRecharge(self, percent=PEAK_RECHARGE):
        capacity = self.ship.getModifiedItemAttr("capacitorCapacity")
        rechargeRate = self.ship.getModifiedItemAttr("rechargeRate") / 1000.0
        return 10 / rechargeRate * sqrt(percent) * (1 - sqrt(percent)) * capacity

    def calculateShieldRecharge(self, percent=PEAK_RECHARGE):
        capacity = self.ship.getModifiedItemAttr("shieldCapacity")
        rechargeRate = self.ship.getModifiedItemAttr("shieldRechargeRate") / 1000.0
        return 10 / rechargeRate * sqrt(percent) * (1 - sqrt(percent)) * capacity

    def addDrain(self, src, cycleTime, capNeed, clipSize=0):
        """ Used for both cap drains and cap fills (fills have negative capNeed) """

        energyNeutralizerSignatureResolution = src.getModifiedItemAttr("energyNeutralizerSignatureResolution")
        signatureRadius = self.ship.getModifiedItemAttr("signatureRadius")

        # Signature reduction, uses the bomb formula as per CCP Larrikin
        if energyNeutralizerSignatureResolution:
            capNeed = capNeed * min(1, signatureRadius / energyNeutralizerSignatureResolution)

        resistance = self.ship.getModifiedItemAttr("energyWarfareResistance") or 1 if capNeed > 0 else 1
        self.__extraDrains.append((cycleTime, capNeed * resistance, clipSize))

    def removeDrain(self, i):
        del self.__extraDrains[i]

    def iterDrains(self):
        return self.__extraDrains.__iter__()

    def __generateDrain(self):
        drains = []
        capUsed = 0
        capAdded = 0
        for mod in self.modules:
            if mod.state >= State.ACTIVE:
                if (mod.getModifiedItemAttr("capacitorNeed") or 0) != 0:
                    cycleTime = mod.rawCycleTime or 0
                    reactivationTime = mod.getModifiedItemAttr("moduleReactivationDelay") or 0
                    fullCycleTime = cycleTime + reactivationTime
                    if fullCycleTime > 0:
                        capNeed = mod.capUse
                        if capNeed > 0:
                            capUsed += capNeed
                        else:
                            capAdded -= capNeed

                        # If this is a turret, don't stagger activations
                        disableStagger = mod.hardpoint == Hardpoint.TURRET

                        drains.append((int(fullCycleTime), mod.getModifiedItemAttr("capacitorNeed") or 0,
                                       mod.numShots or 0, disableStagger))

        for fullCycleTime, capNeed, clipSize in self.iterDrains():
            # Stagger incoming effects for cap simulation
            drains.append((int(fullCycleTime), capNeed, clipSize, False))
            if capNeed > 0:
                capUsed += capNeed / (fullCycleTime / 1000.0)
            else:
                capAdded += -capNeed / (fullCycleTime / 1000.0)

        return drains, capUsed, capAdded

    def simulateCap(self):
        drains, self.__capUsed, self.__capRecharge = self.__generateDrain()
        self.__capRecharge += self.calculateCapRecharge()
        if len(drains) > 0:
            sim = capSim.CapSimulator()
            sim.init(drains)
            sim.capacitorCapacity = self.ship.getModifiedItemAttr("capacitorCapacity")
            sim.capacitorRecharge = self.ship.getModifiedItemAttr("rechargeRate")
            sim.stagger = True
            sim.scale = False
            sim.t_max = 6 * 60 * 60 * 1000
            sim.reload = self.factorReload
            sim.run()

            capState = (sim.cap_stable_low + sim.cap_stable_high) / (2 * sim.capacitorCapacity)
            self.__capStable = capState > 0
            self.__capState = min(100, capState * 100) if self.__capStable else sim.t / 1000.0
        else:
            self.__capStable = True
            self.__capState = 100

    @property
    def hp(self):
        hp = {}
        for (type, attr) in (('shield', 'shieldCapacity'), ('armor', 'armorHP'), ('hull', 'hp')):
            hp[type] = self.ship.getModifiedItemAttr(attr)

        return hp

    @property
    def ehp(self):
        if self.__ehp is None:
            if self.damagePattern is None:
                ehp = self.hp
            else:
                ehp = self.damagePattern.calculateEhp(self)
            self.__ehp = ehp

        return self.__ehp

    @property
    def tank(self):
        hps = {"passiveShield": self.calculateShieldRecharge()}
        for type in ("shield", "armor", "hull"):
            hps["%sRepair" % type] = self.extraAttributes["%sRepair" % type]

        return hps

    @property
    def effectiveTank(self):
        if self.__effectiveTank is None:
            if self.damagePattern is None:
                ehps = self.tank
            else:
                ehps = self.damagePattern.calculateEffectiveTank(self, self.extraAttributes)

            self.__effectiveTank = ehps

        return self.__effectiveTank

    @property
    def effectiveSustainableTank(self):
        if self.__effectiveSustainableTank is None:
            if self.damagePattern is None:
                eshps = self.sustainableTank
            else:
                eshps = self.damagePattern.calculateEffectiveTank(self, self.sustainableTank)

            self.__effectiveSustainableTank = eshps

        return self.__effectiveSustainableTank

    def calculateLockTime(self, radius):
        scanRes = self.ship.getModifiedItemAttr("scanResolution")
        if scanRes is not None and scanRes > 0:
            # Yes, this function returns time in seconds, not miliseconds.
            # 40,000 is indeed the correct constant here.
            return min(40000 / scanRes / asinh(radius) ** 2, 30 * 60)
        else:
            return self.ship.getModifiedItemAttr("scanSpeed") / 1000.0

    def calculateMiningStats(self):
        minerYield = 0
        droneYield = 0

        for mod in self.modules:
            minerYield += mod.miningStats

        for drone in self.drones:
            droneYield += drone.miningStats

        self.__minerYield = minerYield
        self.__droneYield = droneYield

    def calculateWeaponStats(self):
        weaponDPS = 0
        droneDPS = 0
        weaponVolley = 0
        droneVolley = 0

        for mod in self.modules:
            dps, volley = mod.damageStats(self.targetResists)
            weaponDPS += dps
            weaponVolley += volley

        for drone in self.drones:
            dps, volley = drone.damageStats(self.targetResists)
            droneDPS += dps
            droneVolley += volley

        for fighter in self.fighters:
            dps, volley = fighter.damageStats(self.targetResists)
            droneDPS += dps
            droneVolley += volley

        self.__weaponDPS = weaponDPS
        self.__weaponVolley = weaponVolley
        self.__droneDPS = droneDPS
        self.__droneVolley = droneVolley

    @property
    def fits(self):
        for mod in self.modules:
            if not mod.fits(self):
                return False

        return True

    def __deepcopy__(self, memo):
        copy = Fit()
        # Character and owner are not copied
        copy.character = self.__character
        copy.owner = self.owner
        copy.ship = deepcopy(self.ship, memo)
        copy.name = "%s copy" % self.name
        copy.damagePattern = self.damagePattern
        copy.targetResists = self.targetResists
        copy.notes = self.notes

        toCopy = (
            "modules",
            "drones",
            "fighters",
            "cargo",
            "implants",
            "boosters",
            "projectedModules",
            "projectedDrones",
            "projectedFighters")
        for name in toCopy:
            orig = getattr(self, name)
            c = getattr(copy, name)
            for i in orig:
                c.append(deepcopy(i, memo))

        for fit in self.projectedFits:
            copy.__projectedFits[fit.ID] = fit
            # this bit is required -- see GH issue # 83
            eos.db.saveddata_session.flush()
            eos.db.saveddata_session.refresh(fit)

        return copy

    def __repr__(self):
        return u"Fit(ID={}, ship={}, name={}) at {}".format(
            self.ID, self.ship.item.name, self.name, hex(id(self))
        ).encode('utf8')

    def __str__(self):
        return u"{} ({})".format(
            self.name, self.ship.item.name
        ).encode('utf8')
